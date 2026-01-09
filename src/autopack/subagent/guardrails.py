"""
Guardrails enforcement for sub-agent outputs.

Ensures sub-agent outputs comply with safety requirements:
- No secrets in artifacts
- No side effects
- Deterministic traceability

BUILD-197: Claude Code sub-agent guardrails
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class GuardrailType(Enum):
    """Types of guardrail checks."""

    NO_SECRETS = "no_secrets"
    NO_SIDE_EFFECTS = "no_side_effects"
    DETERMINISTIC_PATHS = "deterministic_paths"
    BOUNDED_SCOPE = "bounded_scope"
    FILE_REFERENCE_VALIDITY = "file_reference_validity"


class ViolationSeverity(Enum):
    """Severity of guardrail violations."""

    CRITICAL = "critical"  # Must block - secrets, side effects
    WARNING = "warning"  # Should investigate
    INFO = "info"  # Informational only


@dataclass
class GuardrailViolation:
    """A single guardrail violation."""

    guardrail: GuardrailType
    severity: ViolationSeverity
    message: str
    location: Optional[str] = None  # File path or section where violation found
    snippet: Optional[str] = None  # Redacted snippet showing violation
    remediation: Optional[str] = None


@dataclass
class GuardrailResult:
    """Result of guardrail checks."""

    passed: bool
    violations: list[GuardrailViolation] = field(default_factory=list)
    warnings: list[GuardrailViolation] = field(default_factory=list)
    checked_guardrails: list[GuardrailType] = field(default_factory=list)

    @property
    def critical_violations(self) -> list[GuardrailViolation]:
        """Get only critical violations."""
        return [v for v in self.violations if v.severity == ViolationSeverity.CRITICAL]

    def to_markdown(self) -> str:
        """Generate markdown report of guardrail results."""
        lines = [
            "# Guardrail Check Results",
            "",
            f"**Status**: {'PASSED' if self.passed else 'FAILED'}",
            f"**Violations**: {len(self.violations)}",
            f"**Warnings**: {len(self.warnings)}",
            "",
        ]

        if not self.passed:
            lines.extend(["## Critical Violations", ""])
            for v in self.critical_violations:
                lines.append(f"### {v.guardrail.value}")
                lines.append("")
                lines.append(f"**Message**: {v.message}")
                if v.location:
                    lines.append(f"**Location**: {v.location}")
                if v.snippet:
                    lines.append(f"**Snippet**: `{v.snippet}`")
                if v.remediation:
                    lines.append(f"**Remediation**: {v.remediation}")
                lines.append("")

        if self.warnings:
            lines.extend(["## Warnings", ""])
            for w in self.warnings:
                lines.append(f"- **{w.guardrail.value}**: {w.message}")
            lines.append("")

        lines.extend(["## Checked Guardrails", ""])
        for g in self.checked_guardrails:
            lines.append(f"- {g.value}")

        return "\n".join(lines)


class SubagentGuardrails:
    """
    Enforces guardrails on sub-agent outputs.

    Checks for:
    1. Secrets leakage (API keys, tokens, passwords, credentials)
    2. Side effect indicators (API calls, file writes outside handoff)
    3. Path validity (files exist, paths are within allowed scope)
    4. Deterministic naming (output files follow conventions)
    """

    # Patterns that indicate potential secrets (conservative - may have false positives)
    SECRET_PATTERNS = [
        # API keys
        (r"['\"]?(?:api[_-]?key|apikey)['\"]?\s*[:=]\s*['\"][^'\"]{20,}['\"]", "API key"),
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API key"),
        (r"sk-ant-[a-zA-Z0-9-]{20,}", "Anthropic API key"),
        (r"glm-[a-zA-Z0-9]{20,}", "GLM API key"),
        # Bearer tokens
        (r"[Bb]earer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer token"),
        # AWS
        (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
        (r"['\"]?(?:aws[_-]?secret)['\"]?\s*[:=]\s*['\"][^'\"]{30,}['\"]", "AWS secret"),
        # Generic secrets
        (r"['\"]?(?:password|passwd|pwd)['\"]?\s*[:=]\s*['\"][^'\"]{8,}['\"]", "Password"),
        (r"['\"]?(?:secret|token|credential)['\"]?\s*[:=]\s*['\"][^'\"]{16,}['\"]", "Secret/token"),
        # OAuth
        (
            r"['\"]?(?:client[_-]?secret)['\"]?\s*[:=]\s*['\"][^'\"]{20,}['\"]",
            "OAuth client secret",
        ),
        (r"['\"]?(?:refresh[_-]?token)['\"]?\s*[:=]\s*['\"][^'\"]{20,}['\"]", "Refresh token"),
        # Database
        (
            r"(?:postgres|mysql|mongodb)://[^:]+:[^@]{8,}@",
            "Database connection string with password",
        ),
        # Private keys
        (r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", "Private key"),
        # Session/cookie
        (r"['\"]?(?:session[_-]?id|sessionid)['\"]?\s*[:=]\s*['\"][^'\"]{20,}['\"]", "Session ID"),
    ]

    # Patterns that indicate potential side effects
    SIDE_EFFECT_PATTERNS = [
        # HTTP methods
        (r"requests\.(post|put|patch|delete)\s*\(", "HTTP write operation"),
        (r"httpx\.(post|put|patch|delete)\s*\(", "HTTP write operation"),
        (
            r"fetch\s*\([^)]*method\s*:\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]",
            "HTTP write operation",
        ),
        # File operations outside handoff
        (r"open\s*\([^)]*['\"][^'\"]*(?<!handoff)[/\\][^'\"]+['\"][^)]*['\"]w", "File write"),
        # Subprocess/shell
        (r"subprocess\.(run|call|Popen)\s*\(", "Subprocess execution"),
        (r"os\.system\s*\(", "Shell command execution"),
        # Database writes
        (r"\.(?:insert|update|delete|execute)\s*\(", "Database write operation"),
        # API calls
        (r"\.create_listing\s*\(", "Marketplace listing creation"),
        (r"\.upload\s*\(", "File upload operation"),
        (r"\.publish\s*\(", "Publishing operation"),
        (r"\.trade\s*\(|\.place_order\s*\(", "Trading operation"),
    ]

    # Allowed output paths (relative to run directory)
    ALLOWED_OUTPUT_PATHS = [
        "handoff/",
    ]

    def __init__(self, run_dir: Optional[Path] = None):
        """
        Initialize guardrails checker.

        Args:
            run_dir: Run directory for path validation
        """
        self.run_dir = Path(run_dir) if run_dir else None

    def check_no_secrets(self, content: str, location: str = "content") -> list[GuardrailViolation]:
        """
        Check content for potential secrets.

        Args:
            content: Text content to check
            location: Location identifier for error messages

        Returns:
            List of violations found
        """
        violations = []

        for pattern, secret_type in self.SECRET_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                # Redact the actual secret in the snippet
                snippet = match.group(0)
                redacted = re.sub(r"[a-zA-Z0-9]{4,}", "[REDACTED]", snippet)

                violations.append(
                    GuardrailViolation(
                        guardrail=GuardrailType.NO_SECRETS,
                        severity=ViolationSeverity.CRITICAL,
                        message=f"Potential {secret_type} detected",
                        location=location,
                        snippet=redacted,
                        remediation=f"Remove or redact the {secret_type} before saving output",
                    )
                )

        return violations

    def check_no_side_effects(
        self, content: str, location: str = "content"
    ) -> list[GuardrailViolation]:
        """
        Check content for side effect indicators.

        Args:
            content: Text content to check
            location: Location identifier for error messages

        Returns:
            List of violations found
        """
        violations = []

        for pattern, effect_type in self.SIDE_EFFECT_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                violations.append(
                    GuardrailViolation(
                        guardrail=GuardrailType.NO_SIDE_EFFECTS,
                        severity=ViolationSeverity.WARNING,
                        message=f"Potential side effect: {effect_type}",
                        location=location,
                        snippet=match.group(0),
                        remediation="Sub-agents should not execute side effects; this should be research/planning only",
                    )
                )

        return violations

    def check_deterministic_paths(
        self,
        file_references: list[str],
        location: str = "file_references",
    ) -> list[GuardrailViolation]:
        """
        Check that file references are deterministic and valid.

        Args:
            file_references: List of file paths referenced
            location: Location identifier for error messages

        Returns:
            List of violations found
        """
        violations = []

        for ref in file_references:
            # Check for non-deterministic patterns
            if re.search(r"\d{10,}", ref):  # Timestamps in filenames
                violations.append(
                    GuardrailViolation(
                        guardrail=GuardrailType.DETERMINISTIC_PATHS,
                        severity=ViolationSeverity.WARNING,
                        message="Path contains timestamp - may not be deterministic",
                        location=location,
                        snippet=ref,
                        remediation="Use stable, predictable file names",
                    )
                )

            # Check for absolute paths (should be relative to run dir)
            if ref.startswith("/") or (len(ref) > 2 and ref[1] == ":"):
                violations.append(
                    GuardrailViolation(
                        guardrail=GuardrailType.DETERMINISTIC_PATHS,
                        severity=ViolationSeverity.WARNING,
                        message="Absolute path detected - should use relative paths",
                        location=location,
                        snippet=ref,
                        remediation="Use paths relative to the run directory",
                    )
                )

            # Validate path exists if run_dir is set
            if self.run_dir:
                full_path = self.run_dir / ref
                if not full_path.exists():
                    violations.append(
                        GuardrailViolation(
                            guardrail=GuardrailType.FILE_REFERENCE_VALIDITY,
                            severity=ViolationSeverity.WARNING,
                            message="Referenced file does not exist",
                            location=location,
                            snippet=ref,
                            remediation="Verify file path is correct",
                        )
                    )

        return violations

    def check_output_path(self, output_path: str) -> list[GuardrailViolation]:
        """
        Check that output path is within allowed directories.

        Args:
            output_path: Proposed output path

        Returns:
            List of violations found
        """
        violations = []

        # Normalize path
        normalized = output_path.replace("\\", "/")

        # Check if path is within allowed directories
        is_allowed = any(normalized.startswith(allowed) for allowed in self.ALLOWED_OUTPUT_PATHS)

        if not is_allowed:
            violations.append(
                GuardrailViolation(
                    guardrail=GuardrailType.BOUNDED_SCOPE,
                    severity=ViolationSeverity.CRITICAL,
                    message="Output path is outside allowed directories",
                    location="output_path",
                    snippet=output_path,
                    remediation=f"Output must be within: {', '.join(self.ALLOWED_OUTPUT_PATHS)}",
                )
            )

        # Check for path traversal attempts
        if ".." in output_path:
            violations.append(
                GuardrailViolation(
                    guardrail=GuardrailType.BOUNDED_SCOPE,
                    severity=ViolationSeverity.CRITICAL,
                    message="Path traversal detected",
                    location="output_path",
                    snippet=output_path,
                    remediation="Do not use '..' in output paths",
                )
            )

        return violations

    def validate_output(
        self,
        content: str,
        output_path: str,
        file_references: Optional[list[str]] = None,
    ) -> GuardrailResult:
        """
        Validate sub-agent output against all guardrails.

        Args:
            content: Output content to validate
            output_path: Where the output will be saved
            file_references: List of files referenced in output

        Returns:
            GuardrailResult with all violations and warnings
        """
        all_violations: list[GuardrailViolation] = []
        all_warnings: list[GuardrailViolation] = []
        checked = []

        # Check for secrets
        checked.append(GuardrailType.NO_SECRETS)
        secret_violations = self.check_no_secrets(content)
        all_violations.extend(secret_violations)

        # Check for side effects
        checked.append(GuardrailType.NO_SIDE_EFFECTS)
        effect_violations = self.check_no_side_effects(content)
        # Side effect indicators are warnings, not blocking
        all_warnings.extend(effect_violations)

        # Check output path
        checked.append(GuardrailType.BOUNDED_SCOPE)
        path_violations = self.check_output_path(output_path)
        all_violations.extend(path_violations)

        # Check file references
        if file_references:
            checked.append(GuardrailType.DETERMINISTIC_PATHS)
            checked.append(GuardrailType.FILE_REFERENCE_VALIDITY)
            ref_violations = self.check_deterministic_paths(file_references)
            all_warnings.extend(ref_violations)

        # Determine pass/fail based on critical violations
        critical = [v for v in all_violations if v.severity == ViolationSeverity.CRITICAL]
        passed = len(critical) == 0

        return GuardrailResult(
            passed=passed,
            violations=all_violations,
            warnings=all_warnings,
            checked_guardrails=checked,
        )

    def redact_secrets(self, content: str) -> str:
        """
        Redact potential secrets from content.

        Args:
            content: Content that may contain secrets

        Returns:
            Content with secrets redacted
        """
        result = content

        for pattern, _ in self.SECRET_PATTERNS:

            def redact_match(match: re.Match) -> str:
                original = match.group(0)
                # Keep first 4 chars, redact rest
                if len(original) > 8:
                    return original[:4] + "[REDACTED]"
                return "[REDACTED]"

            result = re.sub(pattern, redact_match, result, flags=re.IGNORECASE)

        return result

    def validate_subagent_output(
        self,
        output: Any,  # SubagentOutput from output_contract.py
        strict: bool = True,
    ) -> GuardrailResult:
        """
        Validate a SubagentOutput object.

        Args:
            output: SubagentOutput object to validate
            strict: If True, treat warnings as violations

        Returns:
            GuardrailResult
        """
        result = self.validate_output(
            content=output.content,
            output_path=f"handoff/{output.get_filename()}",
            file_references=output.file_references,
        )

        # In strict mode, elevate warnings to violations
        if strict:
            for warning in result.warnings:
                if warning.severity == ViolationSeverity.WARNING:
                    result.violations.append(
                        GuardrailViolation(
                            guardrail=warning.guardrail,
                            severity=ViolationSeverity.CRITICAL,
                            message=f"[STRICT] {warning.message}",
                            location=warning.location,
                            snippet=warning.snippet,
                            remediation=warning.remediation,
                        )
                    )
            result.passed = len(result.violations) == 0

        return result
