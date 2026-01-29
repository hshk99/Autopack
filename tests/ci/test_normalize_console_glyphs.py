"""Tests for normalize_console_glyphs.py (BUILD-186)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "tools"))

from normalize_console_glyphs import (
    GLYPH_REPLACEMENTS,
    check_file,
    find_glyphs_in_file,
    get_critical_scripts,
    normalize_content,
)


class TestNormalizeContent:
    """Tests for normalize_content function."""

    def test_replaces_rightwards_arrow(self) -> None:
        """U+2192 (rightwards arrow) should be replaced with ->."""
        content = 'print("SOT \u2192 DB")'
        result = normalize_content(content)
        assert result == 'print("SOT -> DB")'

    def test_replaces_leftwards_arrow(self) -> None:
        """U+2190 (leftwards arrow) should be replaced with <-."""
        content = 'print("DB \u2190 SOT")'
        result = normalize_content(content)
        assert result == 'print("DB <- SOT")'

    def test_replaces_left_right_arrow(self) -> None:
        """U+2194 (left right arrow) should be replaced with <->."""
        content = 'print("A \u2194 B")'
        result = normalize_content(content)
        assert result == 'print("A <-> B")'

    def test_replaces_multiple_glyphs(self) -> None:
        """Multiple glyphs in same content should all be replaced."""
        content = 'print("A \u2192 B \u2190 C \u2194 D")'
        result = normalize_content(content)
        assert result == 'print("A -> B <- C <-> D")'

    def test_preserves_ascii_arrows(self) -> None:
        """ASCII arrows should not be changed."""
        content = 'print("A -> B <- C <-> D")'
        result = normalize_content(content)
        assert result == content

    def test_idempotent(self) -> None:
        """Running normalize twice should produce same result."""
        content = 'print("SOT \u2192 DB")'
        result1 = normalize_content(content)
        result2 = normalize_content(result1)
        assert result1 == result2

    def test_preserves_other_unicode(self) -> None:
        """Non-target Unicode should be preserved."""
        content = 'print("Hello \u4e16\u754c")'  # Chinese characters
        result = normalize_content(content)
        assert result == content

    def test_replaces_check_mark(self) -> None:
        """U+2713 (check mark) should be replaced with [x]."""
        content = 'print("Done \u2713")'
        result = normalize_content(content)
        assert result == 'print("Done [x]")'

    def test_replaces_bullet(self) -> None:
        """U+2022 (bullet) should be replaced with *."""
        content = 'print("\u2022 Item 1")'
        result = normalize_content(content)
        assert result == 'print("* Item 1")'

    def test_replaces_heavy_check_emoji(self) -> None:
        """U+2705 (white heavy check emoji) should be replaced with [OK]."""
        content = 'print("\u2705 SUCCESS")'
        result = normalize_content(content)
        assert result == 'print("[OK] SUCCESS")'

    def test_replaces_cross_mark_emoji(self) -> None:
        """U+274C (cross mark emoji) should be replaced with [X]."""
        content = 'print("\u274c FAILED")'
        result = normalize_content(content)
        assert result == 'print("[X] FAILED")'

    def test_replaces_warning_sign(self) -> None:
        """U+26A0 (warning sign) should be replaced with [!]."""
        content = 'print("\u26a0 WARNING")'
        result = normalize_content(content)
        assert result == 'print("[!] WARNING")'


class TestCheckFile:
    """Tests for check_file function."""

    def test_detects_changes_needed(self, tmp_path: Path) -> None:
        """File with Unicode glyphs should report changes needed."""
        test_file = tmp_path / "test.py"
        test_file.write_text('print("A \u2192 B")\n', encoding="utf-8")

        needs_changes, content = check_file(test_file)
        assert needs_changes is True
        assert content == 'print("A -> B")\n'

    def test_no_changes_for_clean_file(self, tmp_path: Path) -> None:
        """File without Unicode glyphs should report no changes needed."""
        test_file = tmp_path / "test.py"
        test_file.write_text('print("A -> B")\n', encoding="utf-8")

        needs_changes, content = check_file(test_file)
        assert needs_changes is False
        assert content == 'print("A -> B")\n'

    def test_handles_missing_file(self, tmp_path: Path) -> None:
        """Missing file should be handled gracefully."""
        test_file = tmp_path / "nonexistent.py"

        needs_changes, content = check_file(test_file)
        assert needs_changes is False
        assert "not found" in content

    def test_handles_invalid_utf8(self, tmp_path: Path) -> None:
        """Invalid UTF-8 file should be handled gracefully."""
        test_file = tmp_path / "invalid.py"
        test_file.write_bytes(b'print("x")\n\xff\xfe')

        needs_changes, content = check_file(test_file)
        assert needs_changes is False
        assert "UTF-8" in content


class TestFindGlyphsInFile:
    """Tests for find_glyphs_in_file function."""

    def test_finds_glyphs_with_line_numbers(self, tmp_path: Path) -> None:
        """Should report glyphs with correct line numbers."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            'x = 1\nprint("A \u2192 B")\ny = 2\nprint("C \u2190 D")\n',
            encoding="utf-8",
        )

        findings = find_glyphs_in_file(test_file)
        assert len(findings) == 2
        assert findings[0] == (2, "\u2192", "->")
        assert findings[1] == (4, "\u2190", "<-")

    def test_multiple_glyphs_on_same_line(self, tmp_path: Path) -> None:
        """Should find multiple glyphs on same line."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            'print("A \u2192 B \u2190 C")\n',
            encoding="utf-8",
        )

        findings = find_glyphs_in_file(test_file)
        assert len(findings) == 2
        assert all(line_num == 1 for line_num, _, _ in findings)

    def test_empty_for_clean_file(self, tmp_path: Path) -> None:
        """Clean file should have no findings."""
        test_file = tmp_path / "test.py"
        test_file.write_text('print("A -> B")\n', encoding="utf-8")

        findings = find_glyphs_in_file(test_file)
        assert findings == []


class TestGetCriticalScripts:
    """Tests for get_critical_scripts function."""

    def test_includes_sot_db_sync(self) -> None:
        """scripts/tidy/sot_db_sync.py should be in critical set (test-invoked)."""
        repo_root = Path(__file__).parent.parent.parent
        critical = get_critical_scripts(repo_root)

        # sot_db_sync.py is invoked by tests/tidy/test_sot_db_sync.py
        assert "scripts/tidy/sot_db_sync.py" in critical

    def test_includes_ci_invoked_scripts(self) -> None:
        """CI-invoked scripts should be in critical set."""
        repo_root = Path(__file__).parent.parent.parent
        critical = get_critical_scripts(repo_root)

        # These are referenced in .github/workflows/ci.yml
        assert "scripts/check_ci_drift.py" in critical
        assert "scripts/check_doc_links.py" in critical

    def test_returns_set(self) -> None:
        """Should return a set (no duplicates)."""
        repo_root = Path(__file__).parent.parent.parent
        critical = get_critical_scripts(repo_root)

        assert isinstance(critical, set)


class TestIdempotency:
    """Tests for idempotency of the tool."""

    def test_fix_is_idempotent(self, tmp_path: Path) -> None:
        """Fixing a file twice should produce identical results."""
        test_file = tmp_path / "test.py"
        test_file.write_text('print("A \u2192 B")\n', encoding="utf-8")

        # First pass
        _, content1 = check_file(test_file)
        test_file.write_text(content1, encoding="utf-8")

        # Second pass
        needs_changes, content2 = check_file(test_file)

        assert needs_changes is False
        assert content1 == content2


class TestOutputIsAsciiSafe:
    """Tests that tool output is ASCII-safe."""

    def test_normalized_content_is_ascii_printable(self) -> None:
        """Normalized content of target glyphs should be ASCII-printable."""
        for glyph in GLYPH_REPLACEMENTS:
            content = f'print("{glyph}")'
            result = normalize_content(content)

            # The replacement should be ASCII-encodable
            try:
                result.encode("ascii")
            except UnicodeEncodeError:
                pytest.fail(f"Replacement for U+{ord(glyph):04X} is not ASCII-safe: {result!r}")
