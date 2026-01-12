"""Patching utilities for Autopack."""

from .diff_generator import (
    DiffStats,
    extract_diff_stats,
    generate_diff_from_full_file,
    generate_unified_diff,
    validate_diff_format,
)
from .patch_sanitize import (
    HunkHeader,
    PatchHeader,
    extract_file_paths,
    fix_empty_file_diffs,
    parse_hunk_header,
    parse_patch_header,
    repair_hunk_headers,
    sanitize_patch,
    validate_patch_format,
)

__all__ = [
    "DiffStats",
    "extract_diff_stats",
    "generate_diff_from_full_file",
    "generate_unified_diff",
    "validate_diff_format",
    "HunkHeader",
    "PatchHeader",
    "extract_file_paths",
    "fix_empty_file_diffs",
    "parse_hunk_header",
    "parse_patch_header",
    "repair_hunk_headers",
    "sanitize_patch",
    "validate_patch_format",
]
