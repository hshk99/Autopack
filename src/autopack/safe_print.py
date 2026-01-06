"""
Safe print utilities for Windows console compatibility.

BUILD-184: Provides Unicode-safe output to avoid 'charmap' codec errors
on Windows consoles using legacy codepages (cp1252, cp437, etc.).

Usage:
    from autopack.safe_print import safe_print
    safe_print("SOT -> DB Sync")  # Use ASCII arrows directly
    safe_print("Unicode: \u2192")  # Will fallback to -> on Windows

The module provides:
    - safe_print(): Drop-in replacement for print() that handles encoding errors
    - ASCII_REPLACEMENTS: Mapping of common Unicode chars to ASCII equivalents
    - configure_utf8_stdout(): Reconfigure stdout/stderr to use UTF-8
"""

from __future__ import annotations

import io
import sys
from typing import Any, TextIO

# Mapping of Unicode characters to ASCII-safe replacements
# Add new mappings here as needed
ASCII_REPLACEMENTS: dict[str, str] = {
    "\u2192": "->",  # → RIGHTWARDS ARROW
    "\u2190": "<-",  # ← LEFTWARDS ARROW
    "\u2194": "<->",  # ↔ LEFT RIGHT ARROW
    "\u2713": "[x]",  # ✓ CHECK MARK
    "\u2717": "[X]",  # ✗ BALLOT X
    "\u2022": "*",  # • BULLET
    "\u2023": ">",  # ‣ TRIANGULAR BULLET
    "\u2219": "*",  # ∙ BULLET OPERATOR
    "\u25cf": "(o)",  # ● BLACK CIRCLE
    "\u25cb": "( )",  # ○ WHITE CIRCLE
    "\u2500": "-",  # ─ BOX DRAWINGS LIGHT HORIZONTAL
    "\u2502": "|",  # │ BOX DRAWINGS LIGHT VERTICAL
    "\u250c": "+",  # ┌ BOX DRAWINGS LIGHT DOWN AND RIGHT
    "\u2510": "+",  # ┐ BOX DRAWINGS LIGHT DOWN AND LEFT
    "\u2514": "+",  # └ BOX DRAWINGS LIGHT UP AND RIGHT
    "\u2518": "+",  # ┘ BOX DRAWINGS LIGHT UP AND LEFT
    "\u251c": "+",  # ├ BOX DRAWINGS LIGHT VERTICAL AND RIGHT
    "\u2524": "+",  # ┤ BOX DRAWINGS LIGHT VERTICAL AND LEFT
    "\u252c": "+",  # ┬ BOX DRAWINGS LIGHT DOWN AND HORIZONTAL
    "\u2534": "+",  # ┴ BOX DRAWINGS LIGHT UP AND HORIZONTAL
    "\u253c": "+",  # ┼ BOX DRAWINGS LIGHT VERTICAL AND HORIZONTAL
    "\u2550": "=",  # ═ BOX DRAWINGS DOUBLE HORIZONTAL
    "\u2551": "||",  # ║ BOX DRAWINGS DOUBLE VERTICAL
    "\u2605": "*",  # ★ BLACK STAR
    "\u2606": "*",  # ☆ WHITE STAR
    "\u2728": "*",  # ✨ SPARKLES
    "\u26a0": "(!)",  # ⚠ WARNING SIGN
    "\U0001f4a5": "!",  # 💥 COLLISION SYMBOL
    "\U0001f494": "X",  # 💔 BROKEN HEART
    "\U0001f370": "*",  # 🍰 SHORTCAKE
}


def make_ascii_safe(text: str) -> str:
    """
    Convert a string to ASCII-safe representation.

    Replaces known Unicode characters with ASCII equivalents,
    and escapes any remaining non-ASCII characters.

    Args:
        text: The input string that may contain Unicode characters.

    Returns:
        An ASCII-safe string suitable for Windows console output.
    """
    result = text

    # First, apply known replacements
    for unicode_char, ascii_replacement in ASCII_REPLACEMENTS.items():
        result = result.replace(unicode_char, ascii_replacement)

    # Then, escape any remaining non-ASCII characters
    try:
        # Try to encode as ASCII, replacing failures with backslash escapes
        result.encode("ascii")
        return result
    except UnicodeEncodeError:
        # Still has non-ASCII chars - escape them
        return result.encode("ascii", errors="backslashreplace").decode("ascii")


def safe_print(
    *args: Any,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    """
    Safe print function that handles Unicode encoding errors gracefully.

    This is a drop-in replacement for print() that:
    1. Tries normal print first
    2. On UnicodeEncodeError, converts to ASCII-safe representation

    Args:
        *args: Objects to print (same as print()).
        sep: Separator between arguments (default: " ").
        end: String appended after the last value (default: "\\n").
        file: A file-like object (stream); defaults to sys.stdout.
        flush: Whether to forcibly flush the stream.

    Example:
        safe_print("Processing: path1 -> path2")  # Works on all platforms
        safe_print("Status: \u2713")              # Falls back to [x] on Windows
    """
    output_file = file if file is not None else sys.stdout

    # Build the full output string
    str_args = [str(arg) for arg in args]
    output = sep.join(str_args) + end

    try:
        # Try normal write first
        output_file.write(output)
        if flush:
            output_file.flush()
    except UnicodeEncodeError:
        # Fall back to ASCII-safe version
        safe_output = make_ascii_safe(output)
        output_file.write(safe_output)
        if flush:
            output_file.flush()


def configure_utf8_stdout() -> tuple[TextIO, TextIO]:
    """
    Reconfigure stdout and stderr to use UTF-8 encoding.

    This is useful when running scripts that need full Unicode support
    on Windows. Call this at the start of a script if you need to
    output Unicode characters.

    Returns:
        Tuple of (original_stdout, original_stderr) for restoration if needed.

    Note:
        This may not work in all Windows console configurations.
        For guaranteed safety, use safe_print() instead.
    """
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        # Reconfigure stdout
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        else:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="backslashreplace",
                line_buffering=True,
            )

        # Reconfigure stderr
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
        else:
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding="utf-8",
                errors="backslashreplace",
                line_buffering=True,
            )
    except Exception:
        # If reconfiguration fails, restore originals
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    return original_stdout, original_stderr


def is_windows_legacy_console() -> bool:
    """
    Check if running on Windows with a legacy console encoding.

    Returns:
        True if on Windows with non-UTF-8 console encoding.
    """
    if sys.platform != "win32":
        return False

    try:
        encoding = sys.stdout.encoding or ""
        # Common legacy Windows codepages
        legacy_codepages = {"cp1252", "cp437", "cp850", "mbcs", "ascii"}
        return encoding.lower() in legacy_codepages
    except Exception:
        return True  # Assume legacy if we can't determine
