"""Unified diff generation utilities for LLM outputs.

Provides:
- Git-compatible unified diff generation
- File churn calculation
- Symbol validation for Python files
- Change type classification

This module extracts diff generation logic from anthropic_clients.py.
"""

from __future__ import annotations

import difflib
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    """Result of diff generation.

    Attributes:
        diff_content: Generated unified diff
        is_new_file: Whether this is a new file
        is_deleted_file: Whether this is a deleted file
        lines_added: Number of lines added
        lines_removed: Number of lines removed
    """

    diff_content: str
    is_new_file: bool = False
    is_deleted_file: bool = False
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class ChurnMetrics:
    """Metrics about code churn.

    Attributes:
        churn_percent: Percentage of lines changed (0-100)
        lines_changed: Total number of changed lines
        original_lines: Number of lines in original file
        new_lines: Number of lines in new file
    """

    churn_percent: float
    lines_changed: int
    original_lines: int
    new_lines: int


@dataclass
class SymbolValidation:
    """Result of symbol validation.

    Attributes:
        missing_symbols: Set of symbols that were removed
        has_missing: Whether any required symbols are missing
        message: Human-readable message about missing symbols
    """

    missing_symbols: Set[str]
    has_missing: bool
    message: Optional[str] = None


class DiffGenerator:
    """Generator for git-compatible unified diffs.

    Converts old and new file content into git-format unified diffs
    suitable for application with `git apply`.

    Example:
        generator = DiffGenerator()
        result = generator.generate(
            file_path="src/module.py",
            old_content="def hello():\\n    pass\\n",
            new_content="def hello():\\n    print('hi')\\n",
        )
        print(result.diff_content)
    """

    def generate(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        check_exists: bool = True,
    ) -> DiffResult:
        """Generate a unified diff from old and new file content.

        Args:
            file_path: Path to the file
            old_content: Original file content (empty for new files)
            new_content: New file content (empty for deleted files)
            check_exists: Whether to check if file exists on disk

        Returns:
            DiffResult with generated diff
        """
        # Determine file mode
        is_new_file = not old_content and bool(new_content)
        is_deleted_file = bool(old_content) and not new_content

        # Safety: if we think this is a "new file" but it already exists on disk,
        # treat this as a modification instead
        if is_new_file and check_exists:
            try:
                existing_path = Path(file_path)
                if existing_path.exists():
                    logger.warning(
                        f"[DiffGenerator] {file_path} exists but old_content empty; "
                        "treating as modify (not new file mode)"
                    )
                    old_content = existing_path.read_text(encoding="utf-8", errors="ignore")
                    is_new_file = False
                    is_deleted_file = False
            except Exception as e:
                logger.warning(
                    f"[DiffGenerator] Could not read existing file {file_path}: {e}"
                )

        # Construct git-format diff header
        git_header = self._build_git_header(file_path, is_new_file, is_deleted_file)

        # Generate diff body
        diff_body, lines_added, lines_removed = self._generate_diff_body(
            old_content, new_content
        )

        if not diff_body:
            return DiffResult(
                diff_content="",
                is_new_file=is_new_file,
                is_deleted_file=is_deleted_file,
                lines_added=0,
                lines_removed=0,
            )

        full_diff = git_header + diff_body
        diff_content = "\n".join(full_diff)

        return DiffResult(
            diff_content=diff_content,
            is_new_file=is_new_file,
            is_deleted_file=is_deleted_file,
            lines_added=lines_added,
            lines_removed=lines_removed,
        )

    def _build_git_header(
        self,
        file_path: str,
        is_new_file: bool,
        is_deleted_file: bool,
    ) -> List[str]:
        """Build git-format diff header.

        Args:
            file_path: Path to the file
            is_new_file: Whether this is a new file
            is_deleted_file: Whether this is a deleted file

        Returns:
            List of header lines
        """
        header = [f"diff --git a/{file_path} b/{file_path}"]

        if is_new_file:
            header.extend(
                [
                    "new file mode 100644",
                    "index 0000000..1111111",
                    "--- /dev/null",
                    f"+++ b/{file_path}",
                ]
            )
        elif is_deleted_file:
            header.extend(
                [
                    "deleted file mode 100644",
                    "index 1111111..0000000",
                    f"--- a/{file_path}",
                    "+++ /dev/null",
                ]
            )
        else:
            header.extend(
                [
                    "index 1111111..2222222 100644",
                    f"--- a/{file_path}",
                    f"+++ b/{file_path}",
                ]
            )

        return header

    def _generate_diff_body(
        self,
        old_content: str,
        new_content: str,
    ) -> Tuple[List[str], int, int]:
        """Generate diff body using git diff --no-index.

        Args:
            old_content: Original content
            new_content: New content

        Returns:
            Tuple of (body_lines, lines_added, lines_removed)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            old_file = temp_dir / "old_file"
            new_file = temp_dir / "new_file"

            old_file.write_text(old_content, encoding="utf-8")
            new_file.write_text(new_content, encoding="utf-8")

            diff_cmd = [
                "git",
                "--no-pager",
                "diff",
                "--no-index",
                "--text",
                "--unified=3",
                "--",
                str(old_file),
                str(new_file),
            ]

            proc = subprocess.run(
                diff_cmd,
                capture_output=True,
                text=False,
            )

            stderr_text = ""
            if proc.stderr:
                stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode not in (0, 1):
                logger.error(f"[DiffGenerator] git diff failed: {stderr_text}")
                raise RuntimeError("git diff --no-index failed")

            diff_stdout = proc.stdout.decode("utf-8", errors="replace")
            diff_output = diff_stdout.strip()
            if not diff_output:
                return [], 0, 0

        # Extract body (drop git's own headers)
        diff_lines = diff_output.splitlines()
        body_lines = []
        started = False
        lines_added = 0
        lines_removed = 0

        for line in diff_lines:
            if line.startswith("@@") or started:
                started = True
                body_lines.append(line)
                if line.startswith("+") and not line.startswith("+++"):
                    lines_added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    lines_removed += 1

        return body_lines, lines_added, lines_removed

    def generate_multiple(
        self,
        file_changes: List[Tuple[str, str, str]],
    ) -> str:
        """Generate combined diff for multiple file changes.

        Args:
            file_changes: List of (file_path, old_content, new_content) tuples

        Returns:
            Combined diff string
        """
        diff_parts = []

        for file_path, old_content, new_content in file_changes:
            result = self.generate(file_path, old_content, new_content)
            if result.diff_content:
                diff_parts.append(result.diff_content)

        if not diff_parts:
            return ""

        # Join diffs with double newline for clean separation
        patch_content = "\n\n".join(d.rstrip("\n") for d in diff_parts).rstrip("\n") + "\n"
        return patch_content


class ChurnCalculator:
    """Calculator for code churn metrics."""

    def calculate(self, old_content: str, new_content: str) -> ChurnMetrics:
        """Calculate churn percentage between old and new content.

        Args:
            old_content: Original file content
            new_content: New file content

        Returns:
            ChurnMetrics with calculated values
        """
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        if not old_lines:
            return ChurnMetrics(
                churn_percent=100.0,
                lines_changed=len(new_lines),
                original_lines=0,
                new_lines=len(new_lines),
            )

        # Use SequenceMatcher to count changed lines
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

        changed_lines = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                changed_lines += max(i2 - i1, j2 - j1)
            elif tag == "delete":
                changed_lines += i2 - i1
            elif tag == "insert":
                changed_lines += j2 - j1

        churn_percent = 100.0 * changed_lines / max(len(old_lines), 1)

        return ChurnMetrics(
            churn_percent=churn_percent,
            lines_changed=changed_lines,
            original_lines=len(old_lines),
            new_lines=len(new_lines),
        )

    def is_high_churn(
        self,
        old_content: str,
        new_content: str,
        threshold: float = 50.0,
    ) -> bool:
        """Check if churn exceeds threshold.

        Args:
            old_content: Original file content
            new_content: New file content
            threshold: Churn percentage threshold (default 50%)

        Returns:
            True if churn >= threshold
        """
        metrics = self.calculate(old_content, new_content)
        return metrics.churn_percent >= threshold


class SymbolValidator:
    """Validator for checking symbol preservation in code changes."""

    def validate_python(
        self,
        old_content: str,
        new_content: str,
        file_path: str,
    ) -> SymbolValidation:
        """Validate that Python symbols are preserved.

        Checks that top-level function and class definitions in the old
        content are still present in the new content.

        Args:
            old_content: Original Python file content
            new_content: New Python file content
            file_path: File path for logging

        Returns:
            SymbolValidation with missing symbols
        """
        if not file_path.endswith(".py"):
            return SymbolValidation(
                missing_symbols=set(),
                has_missing=False,
            )

        old_symbols = self._extract_python_symbols(old_content)
        new_symbols = self._extract_python_symbols(new_content)

        missing = old_symbols - new_symbols

        if missing:
            logger.warning(f"[SymbolValidator] Symbols removed from {file_path}: {missing}")
            return SymbolValidation(
                missing_symbols=missing,
                has_missing=True,
                message=", ".join(sorted(missing)),
            )

        return SymbolValidation(
            missing_symbols=set(),
            has_missing=False,
        )

    def _extract_python_symbols(self, content: str) -> Set[str]:
        """Extract top-level function and class names.

        Args:
            content: Python source code

        Returns:
            Set of symbol names
        """
        symbols = set()
        # Match top-level def and class (not indented)
        for match in re.finditer(r"^(def|class)\s+(\w+)", content, re.MULTILINE):
            symbols.add(match.group(2))
        return symbols


class ChangeClassifier:
    """Classifier for change types based on phase metadata."""

    def classify(
        self,
        phase_spec: Optional[Dict],
        scope_paths: Optional[List[str]] = None,
    ) -> str:
        """Classify whether a phase is a small fix or large refactor.

        Args:
            phase_spec: Phase specification
            scope_paths: List of scope paths

        Returns:
            "small_fix" or "large_refactor"
        """
        if not phase_spec:
            return "small_fix"

        scope_paths = scope_paths or []

        # Scope-driven overrides
        if any("package-lock" in p or "yarn.lock" in p for p in scope_paths):
            return "large_refactor"
        if any("package.json" in p for p in scope_paths):
            return "large_refactor"
        if any("/packs/" in p or p.endswith((".yaml", ".yml")) for p in scope_paths):
            return "large_refactor"

        # Explicit override
        if phase_spec.get("change_size") == "large_refactor":
            return "large_refactor"
        if phase_spec.get("allow_symbol_removal"):
            return "large_refactor"

        # Heuristic based on complexity and criteria
        complexity = phase_spec.get("complexity", "medium")
        num_criteria = len(phase_spec.get("acceptance_criteria", []) or [])

        if complexity == "low":
            return "small_fix"
        elif complexity == "medium" and num_criteria <= 3:
            return "small_fix"
        else:
            return "large_refactor"

    def get_churn_threshold(self, change_type: str) -> float:
        """Get appropriate churn threshold for change type.

        Args:
            change_type: "small_fix" or "large_refactor"

        Returns:
            Churn percentage threshold
        """
        if change_type == "small_fix":
            return 30.0  # Small fixes should have low churn
        else:
            return 80.0  # Large refactors can have higher churn
