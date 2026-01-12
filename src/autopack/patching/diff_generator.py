"""Diff generation utilities for creating git-compatible unified diffs.

This module provides deterministic, testable diff generation functionality
extracted from anthropic_clients.py (PR-LLM-4).

Per GPT_RESPONSE10: Generate git-compatible diffs locally, not by LLM.
Per GPT_RESPONSE12 Q3: Fixed format for new/deleted files with /dev/null.
"""

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DiffStats:
    """Statistics extracted from a unified diff."""

    insertions: int
    deletions: int
    modifications: int
    files_changed: int


def generate_unified_diff(
    old_content: str,
    new_content: str,
    filepath: str,
    context_lines: int = 3,
) -> str:
    """Generate a git-compatible unified diff from old and new content.

    This function generates deterministic unified diffs using git's diff engine
    to avoid malformed hunks that can occur with pure Python implementations.

    Args:
        old_content: Original file content (empty string for new files)
        new_content: New file content (empty string for deleted files)
        filepath: Path to the file (used in diff headers)
        context_lines: Number of context lines to include (default: 3)

    Returns:
        Unified diff string in git format, or empty string if no changes

    Raises:
        RuntimeError: If git diff command fails
    """
    # Determine file mode: new, deleted, or modified
    is_new_file = not old_content and bool(new_content)
    is_deleted_file = bool(old_content) and not new_content

    # Safety: if we think this is a "new file" but it already exists on disk,
    # treat this as a modification instead of emitting `new file mode`.
    # This avoids governed-apply rejecting the patch as unsafe.
    if is_new_file:
        try:
            existing_path = Path(filepath)
            if existing_path.exists():
                logger.warning(
                    f"[DiffGen] {filepath} exists but old_content empty; "
                    "treating as modify (not new file mode)"
                )
                old_content = existing_path.read_text(encoding="utf-8", errors="ignore")
                is_new_file = False
                is_deleted_file = False
        except Exception as e:
            logger.warning(
                f"[DiffGen] Could not read existing file {filepath} to avoid new-file mode: {e}"
            )

    # Construct git-format diff header (per GPT_RESPONSE12 Q3)
    # Order matters: diff --git, new/deleted file mode, index, ---, +++
    git_header = [f"diff --git a/{filepath} b/{filepath}"]

    if is_new_file:
        git_header.extend(
            [
                "new file mode 100644",
                "index 0000000..1111111",
                "--- /dev/null",
                f"+++ b/{filepath}",
            ]
        )
    elif is_deleted_file:
        git_header.extend(
            [
                "deleted file mode 100644",
                "index 1111111..0000000",
                f"--- a/{filepath}",
                "+++ /dev/null",
            ]
        )
    else:
        git_header.extend(
            [
                "index 1111111..2222222 100644",
                f"--- a/{filepath}",
                f"+++ b/{filepath}",
            ]
        )

    # Generate reliable diff body via git --no-index to avoid malformed hunks
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
            f"--unified={context_lines}",
            "--",
            str(old_file),
            str(new_file),
        ]

        proc = subprocess.run(
            diff_cmd,
            capture_output=True,
            text=False,  # Decode manually to avoid locale-dependent errors
        )

        stderr_text = ""
        if proc.stderr:
            stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode not in (0, 1):
            logger.error(f"[DiffGen] git diff failed: {stderr_text}")
            raise RuntimeError("git diff --no-index failed while generating diff")

        diff_stdout = proc.stdout.decode("utf-8", errors="replace")
        diff_output = diff_stdout.strip()
        if not diff_output:
            return ""

    diff_lines = diff_output.splitlines()

    # Drop git's own metadata lines (diff --git, index, ---/+++)
    body_lines = []
    started = False
    for line in diff_lines:
        if line.startswith("@@") or started:
            started = True
            body_lines.append(line)

    if not body_lines:
        return ""

    full_diff = git_header + body_lines

    return "\n".join(full_diff)


def generate_diff_from_full_file(filepath: str, new_content: str) -> str:
    """Generate a unified diff by reading current file and comparing to new content.

    This is a convenience wrapper around generate_unified_diff that reads
    the current file content from disk.

    Args:
        filepath: Path to the file
        new_content: New file content to compare against

    Returns:
        Unified diff string in git format

    Raises:
        RuntimeError: If git diff command fails
    """
    old_content = ""
    file_path = Path(filepath)

    if file_path.exists():
        try:
            old_content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"[DiffGen] Could not read {filepath}: {e}")
            # Continue with empty old_content

    return generate_unified_diff(old_content, new_content, filepath)


def validate_diff_format(diff_str: str) -> bool:
    """Validate that a diff string is well-formed unified diff format.

    Checks for required elements:
    - diff --git header
    - File path markers (--- and +++)
    - At least one hunk header (@@) or new/deleted file mode

    Args:
        diff_str: Diff string to validate

    Returns:
        True if diff is well-formed, False otherwise
    """
    if not diff_str or not diff_str.strip():
        return False

    lines = diff_str.splitlines()
    if not lines:
        return False

    # Must start with diff --git
    if not lines[0].startswith("diff --git "):
        return False

    # Check for required file markers or new/deleted file mode
    has_file_markers = False
    has_hunk_or_mode = False

    for line in lines:
        # Check for file path markers
        if line.startswith("--- ") or line.startswith("+++ "):
            has_file_markers = True

        # Check for hunk headers or new/deleted file mode
        if line.startswith("@@") or "new file mode" in line or "deleted file mode" in line:
            has_hunk_or_mode = True

    return has_file_markers and has_hunk_or_mode


def extract_diff_stats(diff_str: str) -> DiffStats:
    """Extract statistics from a unified diff.

    Parses the diff to count insertions, deletions, modifications, and files changed.

    Args:
        diff_str: Unified diff string

    Returns:
        DiffStats object with counts
    """
    insertions = 0
    deletions = 0
    modifications = 0
    files_changed = 0

    if not diff_str:
        return DiffStats(
            insertions=0,
            deletions=0,
            modifications=0,
            files_changed=0,
        )

    lines = diff_str.splitlines()
    in_hunk = False
    seen_files = set()

    for line in lines:
        # Count files
        if line.startswith("diff --git "):
            # Extract file path from "diff --git a/path b/path"
            match = re.match(r"diff --git a/(.+?) b/", line)
            if match:
                filepath = match.group(1)
                if filepath not in seen_files:
                    files_changed += 1
                    seen_files.add(filepath)

        # Track when we're in a hunk
        if line.startswith("@@"):
            in_hunk = True
            continue

        # Reset at next file
        if line.startswith("diff --git "):
            in_hunk = False

        # Count changes within hunks
        if in_hunk and line:
            if line.startswith("+") and not line.startswith("+++"):
                insertions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

    # Modifications are lines that were both added and deleted
    # A simple heuristic: min of insertions and deletions
    modifications = min(insertions, deletions)

    return DiffStats(
        insertions=insertions,
        deletions=deletions,
        modifications=modifications,
        files_changed=files_changed,
    )
