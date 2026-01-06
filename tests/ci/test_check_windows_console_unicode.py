"""Tests for Windows console Unicode guard (BUILD-185 follow-up to BUILD-184)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.check_windows_console_unicode import (
    PRAGMA_ALLOW,
    UNICODE_ARROW_CHARS,
    check_file,
    check_python_source_for_violations,
)


class TestCheckPythonSourceForViolations:
    def test_allows_ascii_print(self) -> None:
        src = 'print("hello -> world")\n'
        v = check_python_source_for_violations(src, "x.py")
        assert v == []

    def test_flags_unicode_in_print_literal(self) -> None:
        arrow = next(iter(UNICODE_ARROW_CHARS))
        src = f'print("SOT {arrow} DB")\n'
        v = check_python_source_for_violations(src, "x.py")
        assert len(v) == 1
        assert "Unicode arrow" in v[0].reason

    def test_flags_unicode_in_print_fstring_literal_part(self) -> None:
        arrow = next(iter(UNICODE_ARROW_CHARS))
        src = f'print(f"SOT {arrow} {{42}}")\n'
        v = check_python_source_for_violations(src, "x.py")
        assert len(v) == 1

    def test_allows_safe_print_with_unicode(self) -> None:
        arrow = next(iter(UNICODE_ARROW_CHARS))
        src = f'safe_print("SOT {arrow} DB")\n'
        v = check_python_source_for_violations(src, "x.py")
        assert v == []

    def test_allows_print_with_explicit_pragma_same_line(self) -> None:
        arrow = next(iter(UNICODE_ARROW_CHARS))
        src = f'print("SOT {arrow} DB")  # {PRAGMA_ALLOW}\n'
        v = check_python_source_for_violations(src, "x.py")
        assert v == []

    def test_allows_print_with_explicit_pragma_previous_line(self) -> None:
        arrow = next(iter(UNICODE_ARROW_CHARS))
        src = f"# {PRAGMA_ALLOW}\nprint(\"SOT {arrow} DB\")\n"
        v = check_python_source_for_violations(src, "x.py")
        assert v == []


class TestCheckFile:
    def test_check_file_reads_utf8(self, tmp_path: Path) -> None:
        p = tmp_path / "a.py"
        arrow = next(iter(UNICODE_ARROW_CHARS))
        p.write_text(f'print("SOT {arrow} DB")\n', encoding="utf-8")
        v = check_file(p)
        assert len(v) == 1

    def test_check_file_reports_non_utf8(self, tmp_path: Path) -> None:
        p = tmp_path / "b.py"
        # Write bytes that are invalid UTF-8.
        p.write_bytes(b"print('x')\n\xff\xfe")
        v = check_file(p)
        assert len(v) == 1
        assert "not valid UTF-8" in v[0].reason


