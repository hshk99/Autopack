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


def validate_patch(patch_content: str) -> Tuple[bool, List[PatchValidationError]]:
    """Validate git diff format patch

    Checks for:
    1. Proper git diff header format
    2. File path validity
    3. Hunk header format
    4. Line prefix consistency (+/-/ )
    5. No truncation markers (literal ...)

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
