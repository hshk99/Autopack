"""
Patch policy enforcement for governed patch application.

This module provides policy validation for patch operations, enforcing:
- Protected path restrictions (core Autopack files)
- Allowed path overrides (maintenance operations)
- Scope constraints (build plan restrictions)
- Internal mode exceptions (self-repair operations)
"""

import re
from typing import List, Optional


class ValidationResult:
    """Result of patch policy validation."""

    def __init__(
        self,
        valid: bool,
        violations: Optional[List[str]] = None,
        blocked_files: Optional[List[str]] = None,
    ):
        """
        Initialize validation result.

        Args:
            valid: Whether validation passed
            violations: List of violation messages
            blocked_files: List of files that triggered violations
        """
        self.valid = valid
        self.violations = violations or []
        self.blocked_files = blocked_files or []

    def __bool__(self) -> bool:
        """Allow using ValidationResult in boolean context."""
        return self.valid

    def __repr__(self) -> str:
        if self.valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, violations={len(self.violations)}, blocked_files={self.blocked_files})"


class PatchPolicy:
    """
    Enforces patch policy constraints for workspace isolation.

    This class encapsulates the logic for validating patch operations against:
    - Protected paths (Autopack core files that should not be modified)
    - Allowed paths (exceptions that override protection)
    - Scope paths (build plan file restrictions)
    - Internal mode (maintenance operations that unlock core files)
    """

    def __init__(
        self,
        protected_paths: List[str],
        allowed_paths: List[str],
        scope_paths: Optional[List[str]] = None,
        internal_mode: bool = False,
    ):
        """
        Initialize patch policy.

        Args:
            protected_paths: List of path prefixes that are protected from modification
            allowed_paths: List of path prefixes that override protection
            scope_paths: Optional list of allowed file paths (scope enforcement)
            internal_mode: If True, allows broader access for maintenance operations
        """
        self.protected_paths = protected_paths
        self.allowed_paths = allowed_paths
        self.scope_paths = scope_paths or []
        self.internal_mode = internal_mode

    def validate_paths(self, files_touched: List[str]) -> ValidationResult:
        """
        Validate that touched files comply with policy constraints.

        Args:
            files_touched: List of file paths from the patch

        Returns:
            ValidationResult with validation status and any violations
        """
        violations = []
        blocked_files = []

        # Check 1: Protected paths
        for file_path in files_touched:
            if self.is_path_protected(file_path):
                violations.append(f"Protected path: {file_path}")
                blocked_files.append(file_path)

        # Check 2: Scope enforcement (if configured)
        if self.scope_paths:
            # Normalize scope paths for comparison
            normalized_scope = set()
            scope_prefixes: List[str] = []

            for path in self.scope_paths:
                norm = self._normalize_path(path)
                if not norm:
                    continue

                # Check if it's a directory prefix (ends with separator)
                raw = str(path or "")
                is_prefix = raw.strip().endswith(("/", "\\"))
                if is_prefix:
                    # Keep prefixes in canonical "dir/" form
                    scope_prefixes.append(norm.rstrip("/") + "/")
                else:
                    normalized_scope.add(norm.rstrip("/"))

            # Validate each file against scope
            for file_path in files_touched:
                normalized_file = self._normalize_path(file_path).rstrip("/")
                in_exact = normalized_file in normalized_scope
                in_prefix = any(normalized_file.startswith(prefix) for prefix in scope_prefixes)

                if not in_exact and not in_prefix:
                    violations.append(f"Outside scope: {file_path}")
                    if file_path not in blocked_files:
                        blocked_files.append(file_path)

        is_valid = len(violations) == 0
        return ValidationResult(valid=is_valid, violations=violations, blocked_files=blocked_files)

    def is_path_protected(self, file_path: str) -> bool:
        """
        Check if a file path is protected from modification.

        Args:
            file_path: Relative file path to check

        Returns:
            True if path is protected, False otherwise
        """
        # Normalize path separators
        normalized_path = file_path.replace("\\", "/")

        # Check if path is explicitly allowed (overrides protection)
        if self.is_path_allowed(normalized_path):
            return False

        # Check if path matches any protected prefix
        for protected in self.protected_paths:
            if normalized_path.startswith(protected.replace("\\", "/")):
                return True

        return False

    def is_path_allowed(self, file_path: str) -> bool:
        """
        Check if a file path is explicitly allowed (overrides protection).

        Args:
            file_path: Relative file path to check

        Returns:
            True if path is allowed, False otherwise
        """
        normalized_path = file_path.replace("\\", "/")

        for allowed in self.allowed_paths:
            if normalized_path.startswith(allowed.replace("\\", "/")):
                return True

        return False

    def is_within_scope(self, file_path: str) -> bool:
        """
        Check if a file path is within the configured scope.

        Args:
            file_path: Relative file path to check

        Returns:
            True if path is within scope or no scope configured, False otherwise
        """
        # If no scope configured, everything is in scope
        if not self.scope_paths:
            return True

        normalized_file = self._normalize_path(file_path).rstrip("/")

        # Normalize scope paths for comparison
        for path in self.scope_paths:
            norm = self._normalize_path(path)
            if not norm:
                continue

            # Check if it's a directory prefix
            raw = str(path or "")
            is_prefix = raw.strip().endswith(("/", "\\"))

            if is_prefix:
                # Directory prefix match
                prefix = norm.rstrip("/") + "/"
                if normalized_file.startswith(prefix):
                    return True
            else:
                # Exact file match
                if normalized_file == norm.rstrip("/"):
                    return True

        return False

    def _normalize_path(self, path: object) -> str:
        """
        Normalize relative paths for comparison.

        Important for Windows drains where scope paths may come from `Path`
        stringification (backslashes) while patch paths are POSIX-style.

        Args:
            path: Path to normalize (can be str, Path, or other)

        Returns:
            Normalized path string
        """
        s = str(path or "").strip()
        s = s.replace("\\", "/")

        # Strip common leading prefixes
        while s.startswith("./"):
            s = s[2:]
        s = s.lstrip("/")  # keep relative

        # Collapse duplicate separators
        s = re.sub(r"/{2,}", "/", s)

        return s
