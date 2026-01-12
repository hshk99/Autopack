"""
Patching utilities for Autopack.

This module contains patch sanitization and repair helpers extracted from
governed_apply.py as part of the micro-kernel refactoring (Item 1.1).
"""

from .patch_sanitize import (
    extract_files_from_patch,
    fix_empty_file_diffs,
    repair_hunk_headers,
    sanitize_patch,
)

__all__ = [
    "extract_files_from_patch",
    "fix_empty_file_diffs",
    "repair_hunk_headers",
    "sanitize_patch",
]
