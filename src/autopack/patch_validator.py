"""Patch Validation Module (Phase 2.1)

Validates git diff format patches before application.
Returns structured validation results for proper error handling.
"""

import re
from typing import Tuple, List, Optional


class PatchValidationError:
    """Structured validation error"""

    def __init__(self, error_type: str, message: str, line_number: Optional[int] = None):
        self.error_type = error_type
        self.message = message
        self.line_number = line_number

    def to_dict(self):
        return {
            "error_type": self.error_type,
            "message": self.message,
            "line_number": self.line_number
        }


def check_for_conflict_markers(patch_content: str) -> Tuple[bool, List[PatchValidationError]]:
    """Check if patch content contains merge conflict markers.

    These markers indicate the patch was generated from unresolved conflicts
    or contains code that will cause syntax errors if applied.

    Args:
        patch_content: Raw patch content to check

    Returns:
        Tuple of (has_conflicts, list of conflict errors)
    """
    # Only check for unique conflict markers, not '=======' which is commonly
    # used as a section divider in code comments (e.g., # =========)
    conflict_markers = ['<<<<<<<', '>>>>>>>']
    errors = []

    lines = patch_content.split('\n')
    for line_num, line in enumerate(lines, 1):
        # Skip diff metadata lines
        if line.startswith(('diff --git', '---', '+++', '@@', 'index ')):
            continue

        for marker in conflict_markers:
            if marker in line:
                # Check if it's in a line that would be applied (starts with +)
                if line.startswith('+') or not line.startswith(('-', ' ')):
                    errors.append(PatchValidationError(
                        "conflict_marker_in_patch",
                        f"Merge conflict marker '{marker}' found in patch content",
                        line_num
                    ))

    return len(errors) > 0, errors


def check_for_duplicate_hunks(patch_content: str) -> Tuple[bool, List[PatchValidationError]]:
    """Check if patch content contains duplicate/conflicting hunk headers.

    Detects the common LLM error of generating multiple @@ -N,M headers
    with the same starting line number for the same file.

    Args:
        patch_content: Raw patch content to check

    Returns:
        Tuple of (has_duplicates, list of duplicate errors)
    """
    errors = []
    lines = patch_content.split('\n')

    current_file = None
    hunk_starts_by_file = {}  # {file_path: {start_line: [line_numbers]}}

    for i, line in enumerate(lines, 1):
        # Track current file
        if line.startswith('diff --git '):
            match = re.match(r'diff --git a/(.+) b/(.+)', line)
            if match:
                current_file = match.group(1)
                if current_file not in hunk_starts_by_file:
                    hunk_starts_by_file[current_file] = {}

        # Track hunk headers
        elif line.startswith('@@') and current_file:
            match = re.match(r'^@@ -(\d+)', line)
            if match:
                start_line = int(match.group(1))
                if start_line not in hunk_starts_by_file[current_file]:
                    hunk_starts_by_file[current_file][start_line] = []
                hunk_starts_by_file[current_file][start_line].append(i)

    # Check for duplicates
    for file_path, hunk_starts in hunk_starts_by_file.items():
        for start_line, line_numbers in hunk_starts.items():
            if len(line_numbers) > 1:
                errors.append(PatchValidationError(
                    "duplicate_hunk_header",
                    f"Duplicate hunk header @@ -{start_line} in {file_path} at lines {line_numbers}",
                    line_numbers[0]
                ))

    return len(errors) > 0, errors


def validate_patch(patch_content: str) -> Tuple[bool, List[PatchValidationError]]:
    """Validate git diff format patch

    Checks for:
    1. Proper git diff header format
    2. File path validity
    3. Hunk header format
    4. Line prefix consistency (+/-/ )
    5. No truncation markers (literal ...)
    6. No merge conflict markers (pre-apply detection)
    7. No duplicate hunk headers for the same line range

    Args:
        patch_content: Raw patch content to validate

    Returns:
        Tuple of (is_valid, list of validation errors)
    """
    errors = []

    if not patch_content or not patch_content.strip():
        errors.append(PatchValidationError(
            "empty_patch",
            "Patch content is empty"
        ))
        return False, errors

    # Check for conflict markers in patch content (pre-apply detection)
    has_conflicts, conflict_errors = check_for_conflict_markers(patch_content)
    if has_conflicts:
        errors.extend(conflict_errors)

    # Check for duplicate hunk headers (common LLM error)
    has_duplicates, duplicate_errors = check_for_duplicate_hunks(patch_content)
    if has_duplicates:
        errors.extend(duplicate_errors)

    lines = patch_content.split('\n')

    # Check for git diff headers
    has_diff_header = False
    file_count = 0
    in_hunk = False
    current_file = None
    line_num = 0

    for i, line in enumerate(lines, 1):
        line_num = i

        # Check for diff header
        if line.startswith('diff --git '):
            has_diff_header = True
            file_count += 1
            in_hunk = False

            # Validate file paths in diff header
            match = re.match(r'diff --git a/(.+) b/(.+)', line)
            if not match:
                errors.append(PatchValidationError(
                    "invalid_diff_header",
                    f"Invalid diff header format: {line[:80]}",
                    line_num
                ))
            else:
                current_file = match.group(1)

        # Check for literal ... truncation (prevention rule from DEBUG_JOURNAL)
        elif '...' in line and not line.startswith(('+++', '---', '@@')):
            # Check if it's a literal truncation marker (not part of actual code)
            if re.match(r'^\s*\.\.\.+\s*$', line):
                errors.append(PatchValidationError(
                    "patch_truncation",
                    f"Patch contains literal '...' truncation marker at line {line_num}",
                    line_num
                ))

        # Check hunk headers
        elif line.startswith('@@'):
            in_hunk = True
            # Validate hunk header format: @@ -start,count +start,count @@
            if not re.match(r'^@@ -\d+,\d+ \+\d+,\d+ @@', line):
                errors.append(PatchValidationError(
                    "invalid_hunk_header",
                    f"Invalid hunk header format: {line[:80]}",
                    line_num
                ))

        # Check line prefixes in hunks
        elif in_hunk and line and not line.startswith(('diff ', 'index ', '---', '+++')):
            # Valid line prefixes: +, -, space, or empty
            if line[0] not in ('+', '-', ' '):
                errors.append(PatchValidationError(
                    "invalid_line_prefix",
                    f"Invalid line prefix '{line[0]}' (expected +, -, or space)",
                    line_num
                ))

    # Check that we have at least one diff header
    if not has_diff_header:
        errors.append(PatchValidationError(
            "missing_diff_header",
            "Patch does not contain valid 'diff --git' headers"
        ))

    # Return validation result
    is_valid = len(errors) == 0
    return is_valid, errors


def format_validation_errors(errors: List[PatchValidationError]) -> str:
    """Format validation errors for HTTP response

    Args:
        errors: List of validation errors

    Returns:
        Formatted error message string
    """
    if not errors:
        return "No errors"

    error_lines = ["Patch validation failed:"]
    for error in errors:
        line_info = f" (line {error.line_number})" if error.line_number else ""
        error_lines.append(f"  - [{error.error_type}]{line_info}: {error.message}")

    return "\n".join(error_lines)
