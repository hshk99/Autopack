"""Context preflight validation for file size policies.

Extracted from autonomous_executor.py as part of PR-EXE-5 (god file refactoring).

This module implements the file size bucket logic that determines whether files
can be included in full-file mode, should be read-only, or need structured edits.

Per IMPLEMENTATION_PLAN2.md Phase 2.1 and GPT_RESPONSE15:
- Simplified 2-bucket policy:
  - Bucket A: ≤1000 lines → full-file mode
  - Bucket B: >1000 lines → read-only context (structured edit mode)

Policy Goals:
1. Prevent LLM truncation by gating oversized files
2. Enable testable, deterministic file size decisions
3. Support telemetry integration for observability
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class FileSizeBucket(Enum):
    """File size buckets for context preflight decisions.

    Bucket classification:
    - SMALL: Files that fit comfortably in context (≤100 lines)
    - MEDIUM: Files that fit but are substantial (101-500 lines)
    - LARGE: Files that approach limits (501-1000 lines)
    - HUGE: Files that exceed limits (>1000 lines)

    Note: The SMALL/MEDIUM/LARGE/HUGE classification is for observability.
    The actual policy decision is binary: ≤1000 (allowed) vs >1000 (read-only).
    """

    SMALL = "small"  # ≤100 lines
    MEDIUM = "medium"  # 101-500 lines
    LARGE = "large"  # 501-1000 lines
    HUGE = "huge"  # >1000 lines (read-only)


@dataclass
class ReadOnlyDecision:
    """Decision about whether context should be read-only.

    Attributes:
        read_only: True if any files exceed the hard limit
        reason: Human-readable explanation of the decision
        total_size_mb: Total size of all files in MB
        oversized_files: List of (file_path, line_count) tuples for files exceeding limit
    """

    read_only: bool
    reason: str
    total_size_mb: float
    oversized_files: List[Tuple[str, int]]


class ContextPreflight:
    """Context preflight validation for file size policies.

    This class implements the file size bucket logic and read-only decision policy
    extracted from autonomous_executor.py. It provides deterministic, testable
    methods for validating file context before LLM processing.

    Configuration:
        max_files: Maximum number of files to include (for scope limiting)
        max_total_size_mb: Maximum total context size in MB (soft limit)
        read_only_threshold_mb: Size threshold for read-only recommendation

    Usage:
        preflight = ContextPreflight(
            max_files=40,
            max_total_size_mb=5.0,
            read_only_threshold_mb=2.0
        )

        # Check individual file
        bucket = preflight.check_file_size_bucket("path/to/file.py")

        # Make read-only decision for entire context
        decision = preflight.decide_read_only(file_contexts)

        # Filter oversized files
        allowed = preflight.filter_files_by_size(files, max_size_mb=1.0)
    """

    def __init__(
        self,
        max_files: int = 40,
        max_total_size_mb: float = 5.0,
        read_only_threshold_mb: float = 2.0,
        max_lines_hard_limit: int = 1000,
    ):
        """Initialize context preflight validator.

        Args:
            max_files: Maximum number of files to include in context
            max_total_size_mb: Maximum total size of all files (soft limit)
            read_only_threshold_mb: Size threshold for read-only recommendation
            max_lines_hard_limit: Hard limit for line count (default: 1000)
        """
        self.max_files = max_files
        self.max_total_size_mb = max_total_size_mb
        self.read_only_threshold_mb = read_only_threshold_mb
        self.max_lines_hard_limit = max_lines_hard_limit

    def check_file_size_bucket(self, file_path: str, content: str = None) -> FileSizeBucket:
        """Classify a file into a size bucket based on line count.

        This method determines which bucket a file belongs to based on its line count.
        The buckets are used for observability and telemetry, while the actual policy
        decision is binary: files ≤1000 lines are allowed, files >1000 are read-only.

        Bucket thresholds:
        - SMALL: ≤100 lines (fits comfortably)
        - MEDIUM: 101-500 lines (substantial but manageable)
        - LARGE: 501-1000 lines (approaches limit)
        - HUGE: >1000 lines (exceeds limit, read-only)

        Args:
            file_path: Path to the file (for logging)
            content: File content as string. If None, file is read from disk.

        Returns:
            FileSizeBucket enum value

        Raises:
            FileNotFoundError: If file doesn't exist and content is None
        """
        if content is None:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except FileNotFoundError:
                logger.warning(f"File not found: {file_path}")
                raise

        line_count = content.count("\n") + 1

        # Classify into buckets
        if line_count <= 100:
            return FileSizeBucket.SMALL
        elif line_count <= 500:
            return FileSizeBucket.MEDIUM
        elif line_count <= self.max_lines_hard_limit:
            return FileSizeBucket.LARGE
        else:
            return FileSizeBucket.HUGE

    def decide_read_only(self, files: Dict[str, str]) -> ReadOnlyDecision:
        """Decide if the file context should be read-only based on file sizes.

        This method implements the core policy from autonomous_executor.py:
        - Files >1000 lines are marked as read-only (Bucket B from GPT_RESPONSE15)
        - These files can be READ but NOT modified by the LLM
        - The decision is deterministic and based solely on line counts

        Args:
            files: Dictionary mapping file paths to file contents

        Returns:
            ReadOnlyDecision with the verdict and details
        """
        oversized_files: List[Tuple[str, int]] = []
        total_chars = 0

        for file_path, content in files.items():
            if not isinstance(content, str):
                continue

            line_count = content.count("\n") + 1
            total_chars += len(content)

            # Check if file exceeds hard limit
            if line_count > self.max_lines_hard_limit:
                oversized_files.append((file_path, line_count))

        # Calculate total size in MB
        total_size_mb = total_chars / (1024 * 1024)

        # Make decision
        if oversized_files:
            file_list = ", ".join(f"{path} ({lines} lines)" for path, lines in oversized_files)
            reason = f"Large files exceed {self.max_lines_hard_limit} line limit: {file_list}"
            return ReadOnlyDecision(
                read_only=True,
                reason=reason,
                total_size_mb=total_size_mb,
                oversized_files=oversized_files,
            )

        return ReadOnlyDecision(
            read_only=False,
            reason="All files within size limits",
            total_size_mb=total_size_mb,
            oversized_files=[],
        )

    def filter_files_by_size(
        self, files: Dict[str, str], max_size_mb: float = None
    ) -> Dict[str, str]:
        """Filter out files that exceed a size threshold.

        This method removes files from the context that are too large,
        allowing the executor to proceed with smaller files while logging
        which files were filtered out.

        Args:
            files: Dictionary mapping file paths to file contents
            max_size_mb: Maximum size per file in MB (default: use instance config)

        Returns:
            Filtered dictionary with only files under the size threshold
        """
        if max_size_mb is None:
            max_size_mb = self.max_total_size_mb / max(len(files), 1)

        max_chars = int(max_size_mb * 1024 * 1024)
        filtered = {}

        for file_path, content in files.items():
            if not isinstance(content, str):
                filtered[file_path] = content
                continue

            if len(content) <= max_chars:
                filtered[file_path] = content
            else:
                size_mb = len(content) / (1024 * 1024)
                logger.warning(
                    f"Filtering out oversized file {file_path} "
                    f"({size_mb:.2f}MB > {max_size_mb:.2f}MB)"
                )

        return filtered

    def get_file_count_warning(self, file_count: int) -> str | None:
        """Check if file count exceeds recommendation and return warning.

        Args:
            file_count: Number of files in context

        Returns:
            Warning message if count exceeds limit, None otherwise
        """
        if file_count >= self.max_files:
            return (
                f"Large file count ({file_count} files, limit: {self.max_files}). "
                f"Consider using structured edit mode or reducing scope."
            )
        return None

    def validate_context_size(
        self, files: Dict[str, str], phase_id: str = None
    ) -> Tuple[bool, str]:
        """Validate entire context size and provide actionable feedback.

        This is the main entry point for preflight validation, combining
        all checks into a single pass/fail decision with detailed feedback.

        Args:
            files: Dictionary mapping file paths to file contents
            phase_id: Optional phase identifier for logging

        Returns:
            Tuple of (is_valid, message) where is_valid is True if context passes,
            and message explains the decision
        """
        prefix = f"[{phase_id}] " if phase_id else ""

        # Check file count
        file_count = len(files)
        if warning := self.get_file_count_warning(file_count):
            logger.warning(f"{prefix}{warning}")

        # Check for oversized files
        decision = self.decide_read_only(files)

        if decision.read_only:
            logger.warning(f"{prefix}{decision.reason}")
            return False, decision.reason

        # Check total size
        if decision.total_size_mb > self.max_total_size_mb:
            message = (
                f"Total context size ({decision.total_size_mb:.2f}MB) exceeds "
                f"limit ({self.max_total_size_mb:.2f}MB)"
            )
            logger.warning(f"{prefix}{message}")
            return False, message

        # All checks passed
        message = f"Context validated: {file_count} files, {decision.total_size_mb:.2f}MB total"
        logger.info(f"{prefix}{message}")
        return True, message
