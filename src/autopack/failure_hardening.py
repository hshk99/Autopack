"""Failure-Mode Hardening Loop (Phase 4 of True Autonomy).

Per IMPLEMENTATION_PLAN_TRUE_AUTONOMY.md Phase 4:
- Deterministic mitigation registry for common failure patterns
- Self-improving failure prevention
- Token-efficient (no LLM calls for known patterns)

Key principles:
- Deterministic-first: Pattern matching, not LLM inference
- Fast fail-fast: Quick detection and mitigation
- Telemetry-driven: Learn from actual failures
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class FailurePattern:
    """A known failure pattern with deterministic mitigation."""

    pattern_id: str
    name: str
    description: str
    detector: Callable[[str, Dict], bool]  # (error_text, context) -> is_match
    mitigation: Callable[[Dict], Dict]  # (context) -> mitigation_result
    priority: int = 5  # 1=highest, 10=lowest
    enabled: bool = True


@dataclass
class MitigationResult:
    """Result of applying a mitigation."""

    success: bool
    pattern_id: str
    actions_taken: List[str]
    suggestions: List[str]
    fixed: bool = False  # True if error is likely resolved


class FailureHardeningRegistry:
    """Registry of known failure patterns and their mitigations.

    This is the core of the failure-mode hardening loop. Patterns are
    registered deterministically (no LLM calls) and applied in priority order.
    """

    def __init__(self):
        """Initialize the registry with built-in patterns."""
        self.patterns: Dict[str, FailurePattern] = {}
        self._register_builtin_patterns()

    def _register_builtin_patterns(self):
        """Register built-in failure patterns."""

        # Pattern 1: Missing Python dependencies
        self.register_pattern(
            FailurePattern(
                pattern_id="python_missing_dep",
                name="Python Missing Dependency",
                description="ImportError or ModuleNotFoundError",
                detector=self._detect_missing_python_dep,
                mitigation=self._mitigate_missing_python_dep,
                priority=1,
            )
        )

        # Pattern 2: Wrong working directory
        self.register_pattern(
            FailurePattern(
                pattern_id="wrong_working_dir",
                name="Wrong Working Directory",
                description="FileNotFoundError for expected project files",
                detector=self._detect_wrong_working_dir,
                mitigation=self._mitigate_wrong_working_dir,
                priority=2,
            )
        )

        # Pattern 3: Missing test discovery
        self.register_pattern(
            FailurePattern(
                pattern_id="missing_test_discovery",
                name="Missing Test Discovery",
                description="Pytest/test runner found no tests",
                detector=self._detect_missing_test_discovery,
                mitigation=self._mitigate_missing_test_discovery,
                priority=3,
            )
        )

        # Pattern 4: Scope mismatch (trying to modify out-of-scope files)
        self.register_pattern(
            FailurePattern(
                pattern_id="scope_mismatch",
                name="Scope Mismatch",
                description="Attempting to modify files outside governed scope",
                detector=self._detect_scope_mismatch,
                mitigation=self._mitigate_scope_mismatch,
                priority=2,
            )
        )

        # Pattern 5: Missing Node.js dependencies
        self.register_pattern(
            FailurePattern(
                pattern_id="node_missing_dep",
                name="Node.js Missing Dependency",
                description="Cannot find module (Node.js)",
                detector=self._detect_missing_node_dep,
                mitigation=self._mitigate_missing_node_dep,
                priority=1,
            )
        )

        # Pattern 6: Permission errors
        self.register_pattern(
            FailurePattern(
                pattern_id="permission_error",
                name="Permission Error",
                description="PermissionError or EACCES",
                detector=self._detect_permission_error,
                mitigation=self._mitigate_permission_error,
                priority=4,
            )
        )

    def register_pattern(self, pattern: FailurePattern):
        """Register a failure pattern.

        Args:
            pattern: FailurePattern to register
        """
        self.patterns[pattern.pattern_id] = pattern
        logger.debug(f"[FailureHardening] Registered pattern: {pattern.pattern_id}")

    def list_patterns(self) -> List[str]:
        """List all registered pattern IDs.

        Returns:
            List of pattern IDs sorted by priority (lowest first)
        """
        return sorted(self.patterns.keys(), key=lambda pid: self.patterns[pid].priority)

    def detect_and_mitigate(
        self, error_text: str, context: Dict
    ) -> Optional[MitigationResult]:
        """Detect failure pattern and apply mitigation.

        Args:
            error_text: Error message/stack trace
            context: Execution context (workspace, phase_id, scope, etc.)

        Returns:
            MitigationResult if pattern detected and mitigated, None otherwise
        """
        # Sort patterns by priority (lowest number = highest priority)
        sorted_patterns = sorted(
            [p for p in self.patterns.values() if p.enabled],
            key=lambda p: p.priority,
        )

        for pattern in sorted_patterns:
            try:
                if pattern.detector(error_text, context):
                    logger.info(
                        f"[FailureHardening] Detected pattern: {pattern.pattern_id} ({pattern.name})"
                    )

                    # Extract module name for dependency errors (to enable specific suggestions)
                    if pattern.pattern_id == "python_missing_dep":
                        match = re.search(r"ModuleNotFoundError: No module named ['\"]?(\w+)", error_text)
                        if match:
                            context["detected_module"] = match.group(1)
                    elif pattern.pattern_id == "node_missing_dep":
                        match = re.search(r"Cannot find module ['\"](\w+)", error_text)
                        if match:
                            context["detected_module"] = match.group(1)

                    # Apply mitigation
                    mitigation_data = pattern.mitigation(context)

                    result = MitigationResult(
                        success=mitigation_data.get("success", False),
                        pattern_id=pattern.pattern_id,
                        actions_taken=mitigation_data.get("actions_taken", []),
                        suggestions=mitigation_data.get("suggestions", []),
                        fixed=mitigation_data.get("fixed", False),
                    )

                    logger.info(
                        f"[FailureHardening] Mitigation applied: "
                        f"success={result.success}, fixed={result.fixed}"
                    )

                    return result

            except Exception as e:
                logger.warning(
                    f"[FailureHardening] Failed to process pattern {pattern.pattern_id}: {e}"
                )

        return None

    # ========================
    # Detectors
    # ========================

    def _detect_missing_python_dep(self, error_text: str, context: Dict) -> bool:
        """Detect missing Python dependency."""
        patterns = [
            r"ModuleNotFoundError: No module named ['\"]?(\w+)",
            r"ImportError: cannot import name",
            r"ImportError: No module named",
        ]
        return any(re.search(p, error_text, re.IGNORECASE) for p in patterns)

    def _detect_wrong_working_dir(self, error_text: str, context: Dict) -> bool:
        """Detect wrong working directory."""
        if "FileNotFoundError" not in error_text and "ENOENT" not in error_text:
            return False

        # Check if expected project files are mentioned
        project_markers = [
            "package.json",
            "requirements.txt",
            "Cargo.toml",
            "go.mod",
            "pom.xml",
        ]
        return any(marker in error_text for marker in project_markers)

    def _detect_missing_test_discovery(self, error_text: str, context: Dict) -> bool:
        """Detect missing test discovery."""
        patterns = [
            r"collected 0 items",
            r"no tests ran",
            r"ERROR: not found.*test",
            r"cannot find.*test",
        ]
        return any(re.search(p, error_text, re.IGNORECASE) for p in patterns)

    def _detect_scope_mismatch(self, error_text: str, context: Dict) -> bool:
        """Detect scope mismatch (out-of-scope file modification)."""
        patterns = [
            r"outside.*scope",
            r"not in governed scope",
            r"blocked.*scope",
        ]
        return any(re.search(p, error_text, re.IGNORECASE) for p in patterns)

    def _detect_missing_node_dep(self, error_text: str, context: Dict) -> bool:
        """Detect missing Node.js dependency."""
        patterns = [
            r"Cannot find module ['\"](\w+)",
            r"Error: Cannot find module",
            r"MODULE_NOT_FOUND",
        ]
        return any(re.search(p, error_text, re.IGNORECASE) for p in patterns)

    def _detect_permission_error(self, error_text: str, context: Dict) -> bool:
        """Detect permission errors."""
        patterns = [
            r"PermissionError",
            r"EACCES",
            r"permission denied",
        ]
        return any(re.search(p, error_text, re.IGNORECASE) for p in patterns)

    # ========================
    # Mitigations
    # ========================

    def _mitigate_missing_python_dep(self, context: Dict) -> Dict:
        """Mitigate missing Python dependency."""
        workspace = context.get("workspace", Path.cwd())
        detected_module = context.get("detected_module")

        suggestions = []
        actions_taken = []

        # If we detected a specific module name, suggest installing it directly
        if detected_module:
            suggestions.append(f"pip install {detected_module}")

        # Detect package manager and add generic suggestions
        if (workspace / "requirements.txt").exists():
            suggestions.append("pip install -r requirements.txt")
        elif (workspace / "pyproject.toml").exists():
            content = (workspace / "pyproject.toml").read_text()
            if "poetry" in content.lower():
                suggestions.append("poetry install")
            elif "uv" in content.lower():
                suggestions.append("uv pip install -r requirements.txt")
            else:
                suggestions.append("pip install -e .")
        elif (workspace / "setup.py").exists():
            suggestions.append("pip install -e .")

        actions_taken.append("Detected missing Python dependency")

        return {
            "success": len(suggestions) > 0,
            "actions_taken": actions_taken,
            "suggestions": suggestions,
            "fixed": False,  # Requires user action
        }

    def _mitigate_wrong_working_dir(self, context: Dict) -> Dict:
        """Mitigate wrong working directory."""
        workspace = context.get("workspace", Path.cwd())

        suggestions = [
            f"Ensure working directory is: {workspace}",
            "Check that commands are run with correct cwd parameter",
        ]

        return {
            "success": True,
            "actions_taken": ["Detected wrong working directory"],
            "suggestions": suggestions,
            "fixed": False,
        }

    def _mitigate_missing_test_discovery(self, context: Dict) -> Dict:
        """Mitigate missing test discovery."""
        workspace = context.get("workspace", Path.cwd())

        suggestions = []
        actions_taken = ["Detected missing test discovery"]

        # Check for test directories
        test_dirs = ["tests", "test", "__tests__", "spec"]
        found_test_dir = None
        for test_dir in test_dirs:
            if (workspace / test_dir).exists():
                found_test_dir = test_dir
                break

        if found_test_dir:
            suggestions.append(f"pytest {found_test_dir}/ -v")
            suggestions.append(f"Check test file naming: test_*.py or *_test.py")
        else:
            suggestions.append("Create tests/ directory")
            suggestions.append("Add test files: test_*.py")

        return {
            "success": True,
            "actions_taken": actions_taken,
            "suggestions": suggestions,
            "fixed": False,
        }

    def _mitigate_scope_mismatch(self, context: Dict) -> Dict:
        """Mitigate scope mismatch."""
        scope_paths = context.get("scope_paths", [])

        suggestions = [
            "Only modify files within the defined scope",
            f"Allowed scope: {', '.join(scope_paths[:5])}..." if scope_paths else "No scope defined",
            "Request scope expansion if needed",
        ]

        return {
            "success": True,
            "actions_taken": ["Detected scope mismatch"],
            "suggestions": suggestions,
            "fixed": False,
        }

    def _mitigate_missing_node_dep(self, context: Dict) -> Dict:
        """Mitigate missing Node.js dependency."""
        workspace = context.get("workspace", Path.cwd())
        detected_module = context.get("detected_module")

        suggestions = []
        actions_taken = ["Detected missing Node.js dependency"]

        # If we detected a specific module name, suggest installing it directly
        if detected_module:
            # Detect package manager for specific install command
            if (workspace / "yarn.lock").exists():
                suggestions.append(f"yarn add {detected_module}")
            elif (workspace / "pnpm-lock.yaml").exists():
                suggestions.append(f"pnpm add {detected_module}")
            else:
                suggestions.append(f"npm install {detected_module}")

        # Add generic package manager suggestions
        if (workspace / "yarn.lock").exists():
            suggestions.append("yarn install")
        elif (workspace / "pnpm-lock.yaml").exists():
            suggestions.append("pnpm install")
        else:
            suggestions.append("npm install")

        return {
            "success": len(suggestions) > 0,
            "actions_taken": actions_taken,
            "suggestions": suggestions,
            "fixed": False,
        }

    def _mitigate_permission_error(self, context: Dict) -> Dict:
        """Mitigate permission errors."""
        suggestions = [
            "Check file/directory permissions",
            "Ensure user has write access to target files",
            "Consider using sudo (if safe and appropriate)",
        ]

        return {
            "success": True,
            "actions_taken": ["Detected permission error"],
            "suggestions": suggestions,
            "fixed": False,
        }


# Global registry instance
_registry = None


def get_registry() -> FailureHardeningRegistry:
    """Get the global failure hardening registry.

    Returns:
        Global FailureHardeningRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = FailureHardeningRegistry()
    return _registry


def detect_and_mitigate_failure(
    error_text: str, context: Dict
) -> Optional[MitigationResult]:
    """Convenience function: detect and mitigate failure.

    Args:
        error_text: Error message/stack trace
        context: Execution context

    Returns:
        MitigationResult if pattern detected, None otherwise
    """
    registry = get_registry()
    return registry.detect_and_mitigate(error_text, context)
