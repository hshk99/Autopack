"""Deterministic auditor/quality parsing (BUILD-187 Phase 8).

Parses auditor results deterministically without guessing.
Only populates structured fields when parsing is high-confidence.
Uses explicit "not_parsed" / "unknown" indicators for uncertain data.

Properties:
- No guessing or LLM inference
- Explicit unknown indicators
- Deterministic output for same input
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Deterministic timestamp for reproducible artifacts
DETERMINISTIC_TIMESTAMP = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@dataclass
class ParsedIssue:
    """A parsed issue from auditor output."""

    issue_key: str
    severity: str  # "low", "medium", "high", "critical", or "unknown"
    description: str
    source: str = "auditor"
    category: str = "general"
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    confidence: str = "high"  # "high", "medium", "low"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "issue_key": self.issue_key,
            "severity": self.severity,
            "description": self.description,
            "source": self.source,
            "category": self.category,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "confidence": self.confidence,
        }


@dataclass
class ParsedSuggestedPatch:
    """A parsed suggested patch from auditor output."""

    patch_id: str
    description: str
    patch_content: Optional[str] = None  # None if not deterministically extractable
    affected_files: List[str] = field(default_factory=list)
    confidence: str = "high"  # "high", "medium", "low"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "patch_id": self.patch_id,
            "description": self.description,
            "patch_content": self.patch_content,
            "affected_files": self.affected_files,
            "confidence": self.confidence,
        }


@dataclass
class AuditorParseResult:
    """Result of parsing auditor output.

    Uses explicit "not_parsed" / "unknown" for uncertain fields.
    """

    parse_status: str = "not_parsed"  # "parsed", "partial", "not_parsed"
    confidence_overall: str = "unknown"  # "high", "medium", "low", "unknown"
    recommendation: str = "unknown"  # "approve", "revise", "reject", "unknown"
    issues: List[ParsedIssue] = field(default_factory=list)
    suggested_patches: List[ParsedSuggestedPatch] = field(default_factory=list)
    files_mentioned: List[str] = field(default_factory=list)
    raw_messages: List[str] = field(default_factory=list)
    parse_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "parse_status": self.parse_status,
            "confidence_overall": self.confidence_overall,
            "recommendation": self.recommendation,
            "issues": [i.to_dict() for i in self.issues],
            "suggested_patches": [p.to_dict() for p in self.suggested_patches],
            "files_mentioned": self.files_mentioned,
            "raw_messages": self.raw_messages,
            "parse_notes": self.parse_notes,
        }

    @property
    def has_issues(self) -> bool:
        """Check if any issues were parsed."""
        return len(self.issues) > 0

    @property
    def has_patches(self) -> bool:
        """Check if any patches were parsed."""
        return len(self.suggested_patches) > 0


def parse_auditor_result(
    auditor_messages: List[str],
    approved: bool,
    issues_found: Optional[List[Dict]] = None,
) -> AuditorParseResult:
    """Parse auditor result deterministically.

    Only populates structured fields when parsing is deterministic
    and high-confidence. Uses "unknown" for uncertain data.

    Args:
        auditor_messages: List of auditor message strings
        approved: Whether auditor approved the patch
        issues_found: Optional pre-parsed issues from auditor

    Returns:
        AuditorParseResult with deterministic fields
    """
    result = AuditorParseResult(
        raw_messages=auditor_messages or [],
        recommendation="approve" if approved else "revise",
    )

    # Parse pre-structured issues if available (do this first, even if no messages)
    if issues_found:
        for issue_dict in issues_found:
            parsed = _parse_issue_dict(issue_dict)
            if parsed:
                result.issues.append(parsed)
        if result.issues:
            result.parse_notes.append(f"Parsed {len(result.issues)} pre-structured issues")

    # Extract file mentions deterministically
    files = _extract_file_mentions(auditor_messages)
    result.files_mentioned = sorted(set(files))
    if result.files_mentioned:
        result.parse_notes.append(f"Found {len(result.files_mentioned)} file mentions")

    # Determine parse status and confidence
    if result.issues or result.files_mentioned:
        result.parse_status = "partial" if not result.issues else "parsed"
        result.confidence_overall = "medium" if result.issues else "low"
    else:
        result.parse_status = "not_parsed"
        result.confidence_overall = "unknown"

    # Add note if no messages were provided
    if not auditor_messages and not result.issues:
        result.parse_notes.append("No auditor messages to parse")

    return result


def _parse_issue_dict(issue_dict: Dict) -> Optional[ParsedIssue]:
    """Parse a single issue dictionary.

    Only returns ParsedIssue if we can deterministically extract key fields.
    """
    if not isinstance(issue_dict, dict):
        return None

    # Required: issue_key or some identifier
    issue_key = issue_dict.get("issue_key") or issue_dict.get("id") or issue_dict.get("key")
    if not issue_key:
        # Generate deterministic key from description if available
        description = issue_dict.get("description", "")
        if description:
            # Use first 50 chars of description as key
            issue_key = f"issue-{hash(description[:50]) % 100000:05d}"
        else:
            return None

    # Extract severity with fallback to "unknown"
    severity = issue_dict.get("severity", "unknown")
    if severity not in ("low", "medium", "high", "critical", "unknown"):
        severity = "unknown"

    # Extract description
    description = issue_dict.get("description", "")
    if not description:
        description = issue_dict.get("message", "No description")

    return ParsedIssue(
        issue_key=str(issue_key),
        severity=severity,
        description=description[:500],  # Truncate for safety
        source=issue_dict.get("source", "auditor"),
        category=issue_dict.get("category", "general"),
        file_path=issue_dict.get("file") or issue_dict.get("file_path"),
        line_number=_safe_int(issue_dict.get("line") or issue_dict.get("line_number")),
        confidence="high",  # Pre-structured data is high confidence
    )


def _extract_file_mentions(messages: List[str]) -> List[str]:
    """Extract file path mentions from messages deterministically.

    Uses regex patterns for common file path formats.
    Only returns high-confidence matches.
    """
    files = []

    # Patterns for file paths
    patterns = [
        # Standard paths: src/foo/bar.py, ./path/file.ts
        r"(?:^|[\s\(\[\{\"'])([a-zA-Z0-9_\-./]+\.[a-zA-Z]{1,10})(?:$|[\s\)\]\}\"':,])",
        # Explicit path references: in file.py, at path/to/file.js
        r"(?:in|at|file|path)\s+['\"]?([a-zA-Z0-9_\-./]+\.[a-zA-Z]{1,10})['\"]?",
    ]

    for message in messages:
        for pattern in patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            for match in matches:
                # Filter out likely non-file-path matches
                if _is_likely_file_path(match):
                    files.append(match)

    return files


def _is_likely_file_path(s: str) -> bool:
    """Check if string is likely a file path."""
    if not s or len(s) < 3:
        return False

    # Must have extension
    if "." not in s:
        return False

    # Common file extensions
    extensions = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
        ".md", ".txt", ".html", ".css", ".scss", ".sql", ".sh", ".bash",
        ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cpp", ".h",
        ".rb", ".php", ".xml", ".toml", ".ini", ".cfg", ".env",
    }

    ext = "." + s.rsplit(".", 1)[-1].lower()
    if ext not in extensions:
        return False

    # Should not be a URL
    if "://" in s or s.startswith("http"):
        return False

    # Should not be an email
    if "@" in s:
        return False

    return True


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert value to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_quality_gate_result(
    quality_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Parse quality gate report deterministically.

    Args:
        quality_report: Quality gate report dictionary

    Returns:
        Parsed result with explicit unknown indicators
    """
    result = {
        "quality_level": quality_report.get("quality_level", "unknown"),
        "risk_level": "unknown",
        "risk_score": None,
        "blocked": quality_report.get("blocked", False),
        "block_reason": quality_report.get("block_reason"),
        "parse_confidence": "unknown",
    }

    # Parse risk assessment if available
    risk_assessment = quality_report.get("risk_assessment")
    if isinstance(risk_assessment, dict):
        result["risk_level"] = risk_assessment.get("risk_level", "unknown")
        result["risk_score"] = risk_assessment.get("risk_score")
        result["parse_confidence"] = "high"
    elif quality_report.get("risk_level"):
        result["risk_level"] = quality_report.get("risk_level")
        result["risk_score"] = quality_report.get("risk_score")
        result["parse_confidence"] = "medium"

    return result
