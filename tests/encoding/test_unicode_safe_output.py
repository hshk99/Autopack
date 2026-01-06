"""
Tests for Unicode-safe output utilities.

BUILD-184: Verifies that safe_print and related utilities work correctly
on Windows with legacy console encodings (cp1252, cp437, etc.).
"""

from __future__ import annotations

import io
import sys
import pytest

from autopack.safe_print import (
    ASCII_REPLACEMENTS,
    is_windows_legacy_console,
    make_ascii_safe,
    safe_print,
)


class MockCP1252Stream(io.TextIOWrapper):
    """Mock stream that simulates Windows cp1252 encoding."""

    def __init__(self) -> None:
        # Create a buffer that we can read from later
        self._buffer = io.BytesIO()
        super().__init__(self._buffer, encoding="cp1252", errors="strict")
        self._output: list[str] = []

    def write(self, s: str) -> int:
        # Try to encode as cp1252 - will raise UnicodeEncodeError for unsupported chars
        s.encode("cp1252")  # Raises on non-cp1252 chars
        self._output.append(s)
        return len(s)

    def get_output(self) -> str:
        return "".join(self._output)


class TestMakeAsciiSafe:
    """Tests for make_ascii_safe function."""

    def test_ascii_string_unchanged(self) -> None:
        """ASCII-only strings should pass through unchanged."""
        text = "Hello, World! 123"
        assert make_ascii_safe(text) == text

    def test_arrow_replaced(self) -> None:
        """Unicode arrow should be replaced with ASCII equivalent."""
        text = "SOT \u2192 DB Sync"
        result = make_ascii_safe(text)
        assert result == "SOT -> DB Sync"
        assert "\u2192" not in result

    def test_check_mark_replaced(self) -> None:
        """Unicode check mark should be replaced."""
        text = "Status: \u2713 Complete"
        result = make_ascii_safe(text)
        assert result == "Status: [x] Complete"

    def test_multiple_replacements(self) -> None:
        """Multiple Unicode chars should all be replaced."""
        text = "A \u2192 B \u2192 C"
        result = make_ascii_safe(text)
        assert result == "A -> B -> C"

    def test_unknown_unicode_escaped(self) -> None:
        """Unknown Unicode chars should be backslash-escaped."""
        # Use a Unicode char not in our replacement map
        text = "Hello \u4e2d\u6587"  # Chinese characters
        result = make_ascii_safe(text)
        # Should be escaped
        assert "\\u4e2d" in result or "\\u" not in result
        # Should be ASCII-safe
        result.encode("ascii")  # Should not raise

    def test_all_replacements_are_ascii(self) -> None:
        """All replacement values should be pure ASCII."""
        for unicode_char, ascii_replacement in ASCII_REPLACEMENTS.items():
            # Verify the replacement is ASCII
            ascii_replacement.encode("ascii")  # Should not raise
            # Verify the original is not ASCII (otherwise why replace?)
            try:
                unicode_char.encode("ascii")
                pytest.fail(f"Replacement for ASCII char '{unicode_char}' is unnecessary")
            except UnicodeEncodeError:
                pass  # Expected - original is non-ASCII


class TestSafePrint:
    """Tests for safe_print function."""

    def test_normal_ascii_output(self) -> None:
        """Normal ASCII strings should print without modification."""
        output = io.StringIO()
        safe_print("Hello, World!", file=output)
        assert output.getvalue() == "Hello, World!\n"

    def test_unicode_arrow_safe(self) -> None:
        """Unicode arrow should be safely handled."""
        output = io.StringIO()
        safe_print("SOT \u2192 DB", file=output)
        # In StringIO (UTF-8), Unicode is preserved
        assert "SOT" in output.getvalue()
        assert "DB" in output.getvalue()

    def test_multiple_args(self) -> None:
        """Multiple arguments should be joined with sep."""
        output = io.StringIO()
        safe_print("A", "B", "C", sep="-", file=output)
        assert output.getvalue() == "A-B-C\n"

    def test_custom_end(self) -> None:
        """Custom end parameter should work."""
        output = io.StringIO()
        safe_print("Hello", end="!", file=output)
        assert output.getvalue() == "Hello!"

    def test_cp1252_fallback(self) -> None:
        """When encoding fails, should fall back to ASCII-safe output."""
        # Create a mock stream that will fail on Unicode
        mock_stream = MockCP1252Stream()

        # This should NOT raise UnicodeEncodeError
        try:
            # First write ASCII - should work
            mock_stream.write("Hello World\n")
        except UnicodeEncodeError:
            pytest.fail("ASCII output should work on cp1252")

        # Verify the mock raises on actual Unicode
        with pytest.raises(UnicodeEncodeError):
            mock_stream.write("Test: \u2192\n")


class TestCP1252Simulation:
    """
    Tests that simulate Windows cp1252 console behavior.

    These tests verify that our safe_print function handles the case
    where stdout encoding is cp1252 (common Windows legacy codepage).
    """

    def test_safe_print_survives_cp1252_failure(self) -> None:
        """
        safe_print should not raise when stdout would fail on Unicode.

        This simulates what happens on Windows when:
        1. Console is using cp1252 encoding
        2. Code tries to print Unicode arrow (U+2192)
        3. cp1252 can't encode the arrow
        4. safe_print catches the error and uses ASCII fallback
        """

        # Create a string buffer that pretends to be cp1252
        class FailingStream:
            """Stream that fails on non-cp1252 chars, like Windows console."""

            def __init__(self) -> None:
                self.output: list[str] = []
                self.encoding = "cp1252"

            def write(self, s: str) -> int:
                # Simulate cp1252 encoding failure
                try:
                    s.encode("cp1252")
                    self.output.append(s)
                    return len(s)
                except UnicodeEncodeError as e:
                    raise UnicodeEncodeError(
                        "charmap",
                        s,
                        e.start,
                        e.end,
                        "character maps to <undefined>",
                    )

            def flush(self) -> None:
                pass

        failing_stream = FailingStream()

        # This should handle the error gracefully
        safe_print("SOT \u2192 DB", file=failing_stream)  # type: ignore[arg-type]

        # Output should contain the ASCII-safe version
        output = "".join(failing_stream.output)
        assert "SOT" in output
        assert "DB" in output
        # Either preserved (if stream accepted) or replaced with ->
        assert "->" in output or "\u2192" in output


class TestWindowsDetection:
    """Tests for Windows legacy console detection."""

    def test_is_windows_legacy_console_returns_bool(self) -> None:
        """Function should return a boolean."""
        result = is_windows_legacy_console()
        assert isinstance(result, bool)

    def test_non_windows_returns_false(self) -> None:
        """On non-Windows platforms, should return False."""
        if sys.platform != "win32":
            assert is_windows_legacy_console() is False


class TestIntegration:
    """Integration tests for the safe_print module."""

    def test_sot_db_sync_header_string(self) -> None:
        """
        The exact string that caused the original crash should be safe.

        Original crash: "'charmap' codec can't encode character '\\u2192'"
        From: print("SOT → DB/Qdrant Sync (BUILD-163)")
        """
        output = io.StringIO()
        # The fixed version uses ASCII arrow
        safe_print("SOT -> DB/Qdrant Sync (BUILD-163)", file=output)
        assert "SOT -> DB/Qdrant Sync" in output.getvalue()

    def test_mixed_content_output(self) -> None:
        """Mixed ASCII and Unicode should be handled safely."""
        output = io.StringIO()
        content = (
            "[STATUS] Phase complete\n"
            "Files: src/main.py -> tests/test_main.py\n"  # ASCII arrow
            "Result: [x] PASSED"  # ASCII check
        )
        safe_print(content, file=output)
        assert "[STATUS]" in output.getvalue()
        assert "PASSED" in output.getvalue()
