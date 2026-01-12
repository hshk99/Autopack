"""Patch sanitization and repair utilities.

Extracted from governed_apply.py as part of Item 1.1 god file refactoring (PR-APPLY-1).

Handles malformed patches from LLMs including:
- Missing file headers
- Incorrect hunk line numbers
- Empty file diffs with wrong markers
- Whitespace issues
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class PatchHeader:
    """Parsed patch file header information."""

    old_file: str
    new_file: str
    is_new_file: bool
    is_deleted_file: bool


@dataclass
class HunkHeader:
    """Parsed hunk header information."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    context: Optional[str] = None


def sanitize_patch(patch_content: str) -> str:
    """Sanitize and repair a potentially malformed patch.

    Applies multiple repair strategies:
    1. Fix missing file headers
    2. Repair hunk headers with wrong line numbers
    3. Fix empty file diffs (new/deleted files)
    4. Normalize whitespace

    Args:
        patch_content: Raw patch content from LLM

    Returns:
        Sanitized patch content that git can apply

    Raises:
        ValueError: If patch is too malformed to repair
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


def fix_empty_file_diffs(patch_content: str) -> str:
    """Fix empty file diffs (new file creation, file deletion).

    LLMs sometimes generate:
    - New files without proper headers
    - Deleted files with wrong diff markers
    - Empty diffs without content

    Args:
        patch_content: Patch with potential empty file issues

    Returns:
        Repaired patch with correct empty file markers
    """
    lines = patch_content.split("\n")
    result = []
    i = 0
    last_diff_line = None
    pending_new_file_headers: Optional[str] = None  # stores "b/path"

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


def repair_hunk_headers(
    patch_content: str, workspace_path: Optional[str] = None
) -> str:
    """Repair hunk headers with incorrect line numbers.

    LLMs sometimes generate incorrect @@ -X,Y +A,B @@ headers.
    This attempts to fix them by:
    1. Counting actual context/add/remove lines
    2. Recalculating correct line numbers
    3. Preserving context information

    Args:
        patch_content: Patch with potentially wrong hunk headers
        workspace_path: Optional workspace path for file content validation

    Returns:
        Patch with repaired hunk headers
    """
    from pathlib import Path

    result_lines = []
    current_file = None
    current_file_content = None
    is_new_file = False
    workspace = Path(workspace_path) if workspace_path else None

    lines = patch_content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Track which file we're patching
        if line.startswith("--- a/"):
            file_path = line[6:]
            if workspace:
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


def extract_file_paths(patch_content: str) -> Tuple[str, str]:
    """Extract old and new file paths from patch header.

    Parses:
        --- a/path/to/file.py
        +++ b/path/to/file.py

    Args:
        patch_content: Patch content with file headers

    Returns:
        Tuple of (old_path, new_path)

    Raises:
        ValueError: If file headers not found or malformed
    """
    lines = patch_content.split("\n")
    old_path = None
    new_path = None

    for line in lines:
        if line.startswith("--- "):
            if line.startswith("--- /dev/null"):
                old_path = "/dev/null"
            elif line.startswith("--- a/"):
                old_path = line[6:]
            else:
                # Handle other formats
                old_path = line[4:].strip()
        elif line.startswith("+++ "):
            if line.startswith("+++ /dev/null"):
                new_path = "/dev/null"
            elif line.startswith("+++ b/"):
                new_path = line[6:]
            else:
                # Handle other formats
                new_path = line[4:].strip()

        if old_path and new_path:
            return old_path, new_path

    if old_path is None or new_path is None:
        raise ValueError("Could not find file headers (--- and +++) in patch")

    return old_path, new_path


def parse_patch_header(header_lines: List[str]) -> PatchHeader:
    """Parse patch file header into structured format.

    Args:
        header_lines: Lines from the patch header (before first hunk)

    Returns:
        PatchHeader with parsed information
    """
    old_file = ""
    new_file = ""
    is_new_file = False
    is_deleted_file = False

    for line in header_lines:
        if line.startswith("--- "):
            if line.startswith("--- /dev/null"):
                old_file = "/dev/null"
                is_new_file = True
            elif line.startswith("--- a/"):
                old_file = line[6:]
            else:
                old_file = line[4:].strip()

        elif line.startswith("+++ "):
            if line.startswith("+++ /dev/null"):
                new_file = "/dev/null"
                is_deleted_file = True
            elif line.startswith("+++ b/"):
                new_file = line[6:]
            else:
                new_file = line[4:].strip()

        elif line.startswith("new file mode"):
            is_new_file = True

        elif line.startswith("deleted file mode"):
            is_deleted_file = True

    return PatchHeader(
        old_file=old_file,
        new_file=new_file,
        is_new_file=is_new_file,
        is_deleted_file=is_deleted_file,
    )


def parse_hunk_header(hunk_line: str) -> HunkHeader:
    """Parse hunk header line into structured format.

    Example: "@@ -10,5 +12,6 @@ def function():"
    -> HunkHeader(old_start=10, old_count=5, new_start=12, new_count=6, context="def function():")

    Args:
        hunk_line: Hunk header line starting with @@

    Returns:
        HunkHeader with parsed values

    Raises:
        ValueError: If hunk header format is invalid
    """
    match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@(.*)", hunk_line)
    if not match:
        raise ValueError(f"Invalid hunk header format: {hunk_line}")

    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) else 1
    new_start = int(match.group(3))
    new_count = int(match.group(4)) if match.group(4) else 1
    context = match.group(5).strip() if match.group(5) else None

    return HunkHeader(
        old_start=old_start,
        old_count=old_count,
        new_start=new_start,
        new_count=new_count,
        context=context,
    )


def validate_patch_format(patch_content: str) -> Tuple[bool, List[str]]:
    """Validate that patch has correct unified diff format.

    Args:
        patch_content: Patch content to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    lines = patch_content.split("\n")

    # Check for basic structure
    has_diff_header = False
    has_file_headers = False
    has_hunk_header = False

    for line in lines:
        if line.startswith("diff --git"):
            has_diff_header = True
        elif line.startswith("---") or line.startswith("+++"):
            has_file_headers = True
        elif line.startswith("@@"):
            has_hunk_header = True

            # Validate hunk header format
            try:
                parse_hunk_header(line)
            except ValueError as e:
                errors.append(str(e))

    if not has_diff_header:
        errors.append("Missing diff --git header")

    if not has_file_headers:
        errors.append("Missing file headers (--- and +++)")

    if not has_hunk_header and has_file_headers:
        # File headers present but no hunks - might be empty file or metadata-only change
        # This is actually valid for some cases (empty files, mode changes)
        pass

    is_valid = len(errors) == 0
    return is_valid, errors
