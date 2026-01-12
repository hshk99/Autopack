"""Patching utilities for Autopack."""

from .diff_generator import (
    DiffStats,
    extract_diff_stats,
    generate_diff_from_full_file,
    generate_unified_diff,
    validate_diff_format,
)

__all__ = [
    "DiffStats",
    "extract_diff_stats",
    "generate_diff_from_full_file",
    "generate_unified_diff",
    "validate_diff_format",
]
