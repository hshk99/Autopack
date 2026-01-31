"""Patching utilities for Autopack."""

from .apply_engine import (ApplyResult, execute_git_apply,
                           execute_manual_apply, recover_from_failed_apply)
from .diff_generator import (DiffStats, extract_diff_stats,
                             generate_diff_from_full_file,
                             generate_unified_diff, validate_diff_format)
from .patch_quality import (QualityIssue, QualityValidationResult,
                            validate_patch_quality)
from .patch_sanitize import (HunkHeader, PatchHeader, extract_file_paths,
                             fix_empty_file_diffs, parse_hunk_header,
                             parse_patch_header, repair_hunk_headers,
                             sanitize_patch, validate_patch_format)

__all__ = [
    # apply_engine
    "ApplyResult",
    "execute_git_apply",
    "execute_manual_apply",
    "recover_from_failed_apply",
    # diff_generator
    "DiffStats",
    "extract_diff_stats",
    "generate_diff_from_full_file",
    "generate_unified_diff",
    "validate_diff_format",
    # patch_quality
    "QualityIssue",
    "QualityValidationResult",
    "validate_patch_quality",
    # patch_sanitize
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
