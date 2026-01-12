"""Patch sanitization and normalization functions.

Extracted from governed_apply.py for PR-APPLY-1.

This module handles:
- Fixing common LLM patch formatting issues
- Repairing hunk headers with incorrect line numbers
- Fixing empty/incomplete file diffs
- Normalizing patch content for git apply
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def fix_empty_file_diffs(patch_content: str) -> str:
    """
    Fix incomplete diff headers for empty new files / header-only new files.

    LLMs often generate incomplete diffs for empty __init__.py files like:
        diff --git a/path/__init__.py b/path/__init__.py
        new file mode 100644
        index 0000000..e69de29
        diff --git ...  (next file)

    This is missing the --- /dev/null and +++ b/path lines.

    Additionally, some LLMs emit *header-only* new file diffs without an index line.
    We treat those similarly: ensure each `diff --git` + `new file mode` block has
    `--- /dev/null` and `+++ b/<path>` before the next diff begins.

    Args:
        patch_content: Patch content that may have incomplete empty file diffs

    Returns:
        Patch with fixed empty file headers
    """
    lines = patch_content.split("\n")
    result = []
    last_diff_line = None
    pending_new_file_headers: Optional[str] = None  # stores "b/path"

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("diff --git"):
            # If we were in a new-file block missing headers, insert them before starting next diff.
            if pending_new_file_headers:
                result.append("--- /dev/null")
                result.append(f"+++ {pending_new_file_headers}")
                logger.debug(f"Fixed missing new-file headers for {pending_new_file_headers}")
                pending_new_file_headers = None
            last_diff_line = line
            result.append(line)
            i += 1
            continue

        # Detect new file mode; if headers are missing by the time we reach next diff, we'll insert them.
        if line.startswith("new file mode"):
            # Infer b/path from last diff --git line.
            if last_diff_line:
                parts = last_diff_line.split()
                if len(parts) >= 4:
                    pending_new_file_headers = parts[3]  # b/path
            result.append(line)
            i += 1
            continue

        # If the model *did* provide headers, clear pending flag.
        if line.startswith("--- ") or line.startswith("+++ "):
            pending_new_file_headers = None

        # Check for incomplete empty file pattern
        if line.startswith("index ") and "e69de29" in line:
            # e69de29 is the git hash for empty content
            result.append(line)
            # Check if next line is another diff (missing --- and +++)
            if i + 1 < len(lines) and lines[i + 1].startswith("diff --git"):
                # Find the file path from the previous diff --git line
                for j in range(len(result) - 1, -1, -1):
                    if result[j].startswith("diff --git"):
                        # Extract file path: diff --git a/path b/path
                        parts = result[j].split()
                        if len(parts) >= 4:
                            file_path = parts[3]  # b/path
                            # Insert missing headers
                            result.append("--- /dev/null")
                            result.append(f"+++ {file_path}")
                            logger.debug(f"Fixed empty file diff for {file_path}")
                            pending_new_file_headers = None
                        break
            i += 1
            continue

        result.append(line)
        i += 1

    # If patch ended while still pending headers for a new file, flush them.
    if pending_new_file_headers:
        result.append("--- /dev/null")
        result.append(f"+++ {pending_new_file_headers}")
        logger.debug(f"Fixed missing new-file headers for {pending_new_file_headers}")

    return "\n".join(result)


def repair_hunk_headers(patch_content: str, workspace: Path) -> str:
    """
    Repair @@ hunk headers with incorrect line numbers and counts.

    LLMs often generate patches with wrong line numbers and counts. This function:
    1. For existing files, finds actual line number by matching context
    2. Recounts actual additions/deletions/context lines
    3. Rewrites the @@ headers with correct values

    Args:
        patch_content: Patch content that may have incorrect headers
        workspace: Path to workspace root for reading existing files

    Returns:
        Patch with repaired headers
    """
    result_lines = []
    current_file = None
    current_file_content = None
    is_new_file = False

    lines = patch_content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Track which file we're patching
        if line.startswith("--- a/"):
            file_path = line[6:]
            current_file = workspace / file_path
            is_new_file = False
            if current_file.exists():
                try:
                    current_file_content = current_file.read_text(
                        encoding="utf-8", errors="ignore"
                    ).split("\n")
                except Exception:
                    current_file_content = None
            else:
                current_file_content = None
            result_lines.append(line)
            i += 1
            continue

        # For new files, track that it's a new file
        if line.startswith("--- /dev/null"):
            is_new_file = True
            current_file_content = None
            result_lines.append(line)
            i += 1
            continue

        # Repair @@ headers
        if line.startswith("@@"):
            # Parse the hunk header: @@ -OLD_START,OLD_COUNT +NEW_START,NEW_COUNT @@
            match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@(.*)", line)
            if match:
                suffix = match.group(5)

                # Collect all hunk content lines first
                hunk_content = []
                j = i + 1
                while (
                    j < len(lines)
                    and not lines[j].startswith("@@")
                    and not lines[j].startswith("diff --git")
                ):
                    hunk_content.append(lines[j])
                    j += 1

                # Remove trailing empty lines from hunk (common LLM artifact)
                while hunk_content and (hunk_content[-1] == "" or hunk_content[-1] == " "):
                    hunk_content.pop()

                # Count actual lines in the hunk
                additions = 0
                deletions = 0
                context = 0
                for hunk_line in hunk_content:
                    if hunk_line.startswith("+") and not hunk_line.startswith("+++"):
                        additions += 1
                    elif hunk_line.startswith("-") and not hunk_line.startswith("---"):
                        deletions += 1
                    elif hunk_line.startswith(" "):
                        context += 1
                    elif hunk_line.startswith("\\ No newline"):
                        pass  # Don't count this

                if is_new_file:
                    # New file: old is 0,0, new is 1,additions
                    new_count = additions
                    repaired_line = f"@@ -0,0 +1,{new_count} @@{suffix}"
                elif current_file_content is not None:
                    # Existing file - try to find context position
                    old_count = deletions + context
                    new_count = additions + context

                    # Try to find actual start line by matching context
                    context_lines = []
                    k = i + 1
                    while (
                        k < len(lines)
                        and not lines[k].startswith("@@")
                        and not lines[k].startswith("diff --git")
                    ):
                        hunk_line = lines[k]
                        if hunk_line.startswith(" ") or hunk_line.startswith("-"):
                            context_lines.append(hunk_line[1:] if len(hunk_line) > 1 else "")
                        k += 1

                    actual_start = 1  # Default
                    if context_lines:
                        first_context = context_lines[0]
                        for line_num, file_line in enumerate(current_file_content, 1):
                            if file_line.strip() == first_context.strip():
                                actual_start = line_num
                                break

                    repaired_line = (
                        f"@@ -{actual_start},{old_count} +{actual_start},{new_count} @@{suffix}"
                    )
                else:
                    # Can't determine file content, use counted values
                    old_start = int(match.group(1))
                    old_count = deletions + context
                    new_count = additions + context
                    repaired_line = (
                        f"@@ -{old_start},{old_count} +{old_start},{new_count} @@{suffix}"
                    )

                if repaired_line != line:
                    logger.debug(f"Repaired hunk header: {line} -> {repaired_line}")
                result_lines.append(repaired_line)
                i += 1
                continue

        result_lines.append(line)
        i += 1

    return "\n".join(result_lines)


def sanitize_patch(patch_content: str) -> str:
    """
    Sanitize a patch to fix common formatting issues from LLM output.

    Common issues:
    - Lines in new file content missing the '+' prefix
    - Context lines missing the leading space
    - Hunk headers with incorrect line counts

    Args:
        patch_content: Raw patch content

    Returns:
        Sanitized patch content
    """
    # First fix empty file diffs
    patch_content = fix_empty_file_diffs(patch_content)

    lines = patch_content.split("\n")
    sanitized = []
    in_hunk = False
    in_new_file = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Track diff headers
        if line.startswith("diff --git"):
            sanitized.append(line)
            in_hunk = False
            in_new_file = False
            i += 1
            continue

        # Track new file mode
        if line.startswith("new file mode"):
            in_new_file = True
            sanitized.append(line)
            i += 1
            continue

        # Standard diff metadata lines
        if line.startswith(("index ", "---", "+++", "similarity", "rename ", "deleted file")):
            sanitized.append(line)
            i += 1
            continue

        # Hunk header - we're now in a hunk
        if line.startswith("@@"):
            in_hunk = True
            sanitized.append(line)
            i += 1
            continue

        # Inside a hunk - content lines should start with +, -, or space
        if in_hunk:
            # Already properly formatted
            if line.startswith(("+", "-", " ")):
                sanitized.append(line)
            elif line == "":
                # Blank lines inside hunks must carry a context prefix
                sanitized.append(" ")
                logger.debug("[PatchSanitize] Added context prefix to blank line inside hunk")
            elif line.isspace():
                sanitized.append(" ")
                logger.debug("[PatchSanitize] Normalized whitespace-only line inside hunk")
            # No newline at end of file marker
            elif line.startswith("\\ No newline"):
                sanitized.append(line)
            # Line missing prefix - for new files, add +, otherwise add space (context)
            elif in_new_file or line.strip():
                # For new files being created, all content lines should be additions
                sanitized.append("+" + line)
                logger.debug(f"Sanitized line (added +): {line[:50]}...")
            else:
                sanitized.append(line)
        else:
            sanitized.append(line)

        i += 1

    return "\n".join(sanitized)


def classify_patch_files(patch_content: str) -> Tuple[Set[str], Set[str]]:
    """
    Identify which files in a patch are new vs. existing.

    Args:
        patch_content: Patch content to analyze

    Returns:
        Tuple of (new_files, existing_files) as relative paths
    """
    new_files: Set[str] = set()
    existing_files: Set[str] = set()
    current_file = None

    lines = patch_content.split("\n")
    for line in lines:
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3][2:]  # b/path -> path
            continue

        if current_file is None:
            continue

        if line.startswith("new file mode") or line.startswith("--- /dev/null"):
            new_files.add(current_file)
        elif line.startswith("deleted file mode") or line.startswith("+++ /dev/null"):
            existing_files.add(current_file)
        elif line.startswith("--- a/") and "/dev/null" not in line:
            existing_files.add(current_file)

    return new_files, existing_files


def extract_files_from_patch(patch_content: str) -> List[str]:
    """
    Extract list of files modified from patch content.

    Args:
        patch_content: Git diff/patch content

    Returns:
        List of file paths that were modified
    """
    files = []
    for line in patch_content.split("\n"):
        # Look for diff --git a/path b/path lines
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                # Extract file path from 'a/path/to/file'
                file_path = parts[2][2:]  # Remove 'a/' prefix
                files.append(file_path)
        # Also look for +++ b/path lines as backup
        elif line.startswith("+++") and not line.startswith("+++ /dev/null"):
            file_path = line[6:].strip()  # Remove '+++ b/'
            if file_path and file_path not in files:
                files.append(file_path)

    return files


def normalize_patch(patch_content: str) -> str:
    """
    Normalize line endings and ensure trailing newline.

    Args:
        patch_content: Patch content to normalize

    Returns:
        Normalized patch content
    """
    # Normalize line endings to LF
    patch_content = patch_content.replace("\r\n", "\n").replace("\r", "\n")
    # Ensure trailing newline
    if not patch_content.endswith("\n"):
        patch_content += "\n"
    return patch_content


def parse_patch_stats(patch_content: str) -> Tuple[List[str], int, int]:
    """
    Parse patch to extract statistics.

    Returns:
        Tuple of (files_changed, lines_added, lines_removed)
    """
    files_changed: List[str] = []
    seen: Set[str] = set()
    for line in (patch_content or "").split("\n"):
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4 and parts[2].startswith("a/"):
                p = parts[2][2:]
                if p and p not in seen:
                    seen.add(p)
                    files_changed.append(p)
        elif line.startswith("+++") and not line.startswith("+++ /dev/null"):
            # Handles both "+++ b/<path>" and (rare) malformed variants by stripping common prefix
            p = line.replace("+++ b/", "", 1).strip()
            if p and p not in seen:
                seen.add(p)
                files_changed.append(p)

    lines_added = 0
    lines_removed = 0
    for line in (patch_content or "").split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            lines_added += 1
        elif line.startswith("-") and not line.startswith("---"):
            lines_removed += 1

    return files_changed, lines_added, lines_removed
