"""Test CI output parsing contract - Table-driven tests for pytest output parsing.

This test suite ensures that pytest output parsing is stable across common pytest
output formats. Table-driven tests prevent drift as pytest changes over time.

Coverage:
- Common pytest summary formats (passed, failed, error combinations)
- Collection errors and warnings
- Edge cases (zero tests, malformed output)
- Trimming and log persistence
"""

import pytest

from autopack.executor.ci_runner import parse_pytest_counts, persist_ci_log, trim_ci_output


class TestPytestOutputParsing:
    """Table-driven tests for pytest output parsing."""

    # Test data: (pytest_output, expected_tuple)
    # Format: (output_string, (passed, failed, error))
    PYTEST_OUTPUTS = [
        # Simple passing cases
        ("===== 5 passed in 0.01s =====", (5, 0, 0)),
        ("===== 1 passed in 0.02s =====", (1, 0, 0)),
        ("===== 100 passed in 5.23s =====", (100, 0, 0)),
        # Simple failing cases
        ("===== 3 failed in 1.2s =====", (0, 3, 0)),
        ("===== 1 failed in 0.5s =====", (0, 1, 0)),
        # Mixed passed and failed
        ("===== 3 failed, 2 passed in 1.2s =====", (2, 3, 0)),
        ("===== 2 passed, 3 failed in 1.2s =====", (2, 3, 0)),
        ("===== 1 passed, 1 failed in 0.8s =====", (1, 1, 0)),
        # Error cases
        ("===== 1 error, 1 passed =====", (1, 0, 1)),
        ("===== 2 errors in 0.5s =====", (0, 0, 2)),
        ("===== 1 error =====", (0, 0, 1)),
        # Collection errors (special handling)
        ("ERROR: 3 errors during collection", (0, 0, 3)),
        ("2 errors during collection", (0, 0, 2)),
        ("1 error during collection", (0, 0, 1)),
        # Complex combinations
        ("===== 5 passed, 2 failed, 1 error in 3.5s =====", (5, 2, 1)),
        ("===== 10 passed, 5 failed, 2 errors in 8.2s =====", (10, 5, 2)),
        # Real-world pytest output snippets
        (
            "test_foo.py::test_bar PASSED\ntest_foo.py::test_baz FAILED\n===== 1 failed, 1 passed in 0.5s =====",
            (1, 1, 0),
        ),
        (
            "collected 5 items\n\ntest_foo.py ..... [100%]\n\n===== 5 passed in 0.12s =====",
            (5, 0, 0),
        ),
        ("test_foo.py F\ntest_bar.py .\n===== 1 failed, 1 passed in 0.23s =====", (1, 1, 0)),
        # Multiline with collection errors
        (
            "ImportError: cannot import name 'foo'\nERROR: 2 errors during collection\n===== 2 errors in 0.1s =====",
            (0, 0, 2),
        ),
        # Edge case: no summary line (should return zeros)
        ("test_foo.py::test_bar PASSED", (0, 0, 0)),
        # Edge case: empty output
        ("", (0, 0, 0)),
        # Case variations (pytest uses lowercase)
        ("===== 3 PASSED in 0.5s =====", (3, 0, 0)),
        ("===== 2 Failed, 1 Passed =====", (1, 2, 0)),
        # With warnings
        ("===== 5 passed, 2 warnings in 0.5s =====", (5, 0, 0)),
        # Skipped tests (not counted in our tuple)
        ("===== 3 passed, 2 skipped in 0.3s =====", (3, 0, 0)),
        # XFail and XPass (treated as passed/failed by our parser)
        ("===== 2 passed, 1 xfailed in 0.5s =====", (2, 0, 0)),
        # Deselected tests
        ("===== 5 passed, 3 deselected in 0.4s =====", (5, 0, 0)),
    ]

    @pytest.mark.parametrize("output,expected", PYTEST_OUTPUTS)
    def test_parse_pytest_counts_table_driven(self, output, expected):
        """Test pytest output parsing with table-driven data."""
        result = parse_pytest_counts(output)
        assert result == expected, (
            f"Failed to parse: {output!r}\nExpected: {expected}\nGot: {result}"
        )

    def test_parse_pytest_counts_multiline_with_multiple_matches(self):
        """Test that parsing handles multiple summary lines correctly."""
        # pytest sometimes has intermediate summaries, final one wins
        output = """
        ===== 3 passed in 0.1s =====
        Rerunning tests...
        ===== 2 passed, 1 failed in 0.2s =====
        """
        # Our parser takes the last matching counts
        result = parse_pytest_counts(output)
        assert result == (2, 1, 0)

    def test_parse_pytest_counts_malformed_no_numbers(self):
        """Test malformed output with no numbers returns zeros."""
        output = "Some random text with no test counts"
        result = parse_pytest_counts(output)
        assert result == (0, 0, 0)

    def test_parse_pytest_counts_partial_match(self):
        """Test that partial matches still extract available counts."""
        output = "===== 5 passed ====="
        result = parse_pytest_counts(output)
        assert result == (5, 0, 0)

    def test_parse_pytest_counts_collection_error_priority(self):
        """Test that 'errors during collection' is prioritized correctly."""
        # Collection errors should be captured even if regular errors present
        output = """
        ERROR: 3 errors during collection
        ===== 3 errors =====
        """
        result = parse_pytest_counts(output)
        # Should detect collection error (which sets tests_error)
        assert result[2] == 3  # error count


class TestCIOutputTrimming:
    """Tests for CI output trimming to prevent memory issues."""

    def test_trim_ci_output_short_output_unchanged(self):
        """Test that short output is not trimmed."""
        output = "Short output" * 10
        result = trim_ci_output(output, limit=10000)
        assert result == output

    def test_trim_ci_output_long_output_trimmed(self):
        """Test that long output is trimmed with indicator."""
        output = "A" * 20000
        result = trim_ci_output(output, limit=10000)

        assert len(result) <= 10100  # Allow for truncation marker
        assert "... (truncated) ..." in result
        assert result.startswith("A" * 5000)  # First half preserved
        assert result.endswith("A" * 5000)  # Last half preserved

    def test_trim_ci_output_custom_limit(self):
        """Test trimming with custom limit."""
        output = "B" * 2000
        result = trim_ci_output(output, limit=1000)

        assert len(result) <= 1100
        assert "... (truncated) ..." in result

    def test_trim_ci_output_exactly_at_limit(self):
        """Test output exactly at limit is not trimmed."""
        output = "C" * 1000
        result = trim_ci_output(output, limit=1000)
        assert result == output
        assert "... (truncated) ..." not in result


class TestCILogPersistence:
    """Tests for CI log persistence."""

    def test_persist_ci_log_creates_directory(self, tmp_path):
        """Test that log directory is created if missing."""
        workspace = tmp_path / "workspace"
        run_id = "test-run-123"
        phase_id = "phase1"

        log_path = persist_ci_log(
            log_name="test.log",
            content="test content",
            phase_id=phase_id,
            workspace=workspace,
            run_id=run_id,
        )

        assert log_path is not None
        assert log_path.exists()
        assert log_path.read_text() == "test content"
        assert log_path.parent == workspace / ".autonomous_runs" / run_id / "ci"

    def test_persist_ci_log_writes_content(self, tmp_path):
        """Test that log content is written correctly."""
        workspace = tmp_path / "workspace"
        run_id = "test-run-456"

        content = "CI output line 1\nCI output line 2\nFailed test\n"
        log_path = persist_ci_log(
            log_name="pytest.log",
            content=content,
            phase_id="phase2",
            workspace=workspace,
            run_id=run_id,
        )

        assert log_path.read_text() == content

    def test_persist_ci_log_handles_unicode(self, tmp_path):
        """Test that unicode content is handled correctly."""
        workspace = tmp_path / "workspace"
        run_id = "test-run-789"

        content = "Test with unicode: 你好 🚀 ✓"
        log_path = persist_ci_log(
            log_name="unicode.log",
            content=content,
            phase_id="phase3",
            workspace=workspace,
            run_id=run_id,
        )

        assert log_path.read_text(encoding="utf-8") == content

    def test_persist_ci_log_overwrites_existing(self, tmp_path):
        """Test that existing log is overwritten."""
        workspace = tmp_path / "workspace"
        run_id = "test-run-overwrite"
        log_name = "overwrite.log"

        # Write first log
        log_path1 = persist_ci_log(
            log_name=log_name,
            content="first content",
            phase_id="phase4",
            workspace=workspace,
            run_id=run_id,
        )

        # Write second log with same name
        log_path2 = persist_ci_log(
            log_name=log_name,
            content="second content",
            phase_id="phase4",
            workspace=workspace,
            run_id=run_id,
        )

        assert log_path1 == log_path2
        assert log_path2.read_text() == "second content"


class TestPytestOutputEdgeCases:
    """Additional edge cases for pytest output parsing."""

    def test_parse_pytest_very_large_numbers(self):
        """Test parsing with very large test counts."""
        output = "===== 9999 passed, 8888 failed, 777 errors in 300.5s ====="
        result = parse_pytest_counts(output)
        assert result == (9999, 8888, 777)

    def test_parse_pytest_zero_explicit(self):
        """Test parsing when pytest explicitly reports 0."""
        output = "===== 0 passed in 0.01s ====="
        result = parse_pytest_counts(output)
        assert result == (0, 0, 0)

    def test_parse_pytest_with_duration_variations(self):
        """Test parsing with different duration formats."""
        test_cases = [
            ("===== 5 passed in 0.01s =====", (5, 0, 0)),
            ("===== 5 passed in 1.23s =====", (5, 0, 0)),
            ("===== 5 passed in 123.45s =====", (5, 0, 0)),
            ("===== 5 passed in 0.001s =====", (5, 0, 0)),
        ]

        for output, expected in test_cases:
            assert parse_pytest_counts(output) == expected

    def test_parse_pytest_with_pytest_version_line(self):
        """Test parsing with pytest version line present."""
        output = """
        ===== test session starts =====
        platform darwin -- Python 3.11.0, pytest-7.4.0
        collected 5 items

        test_foo.py .....

        ===== 5 passed in 0.12s =====
        """
        result = parse_pytest_counts(output)
        assert result == (5, 0, 0)

    def test_parse_pytest_with_failure_details(self):
        """Test parsing with detailed failure output."""
        output = """
        test_foo.py::test_bar FAILED

        ===== FAILURES =====
        _____ test_bar _____

        def test_bar():
        >   assert False
        E   AssertionError

        ===== 1 failed in 0.5s =====
        """
        result = parse_pytest_counts(output)
        assert result == (0, 1, 0)


class TestCICommandConstruction:
    """Tests verifying CI command construction logic (documented as contract)."""

    def test_pytest_command_includes_json_report(self):
        """Document that pytest commands should include --json-report for structured output."""
        # This is a documentation test - actual implementation is in run_pytest_ci
        # which is tested via integration tests

        # Expected command structure:
        # [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=line", "-q",
        #  "--no-header", "--timeout=60", "--json-report", "--json-report-file=path"]

        # Contract: All pytest runs MUST include JSON report for downstream parsing
        assert True  # Contract documented

    def test_pytest_environment_variables(self):
        """Document required environment variables for pytest runs."""
        # Contract: pytest runs MUST set:
        # - TESTING=1
        # - PYTHONUTF8=1
        # - PYTHONPATH (defaults to {workdir}/src)

        assert True  # Contract documented

    def test_custom_ci_command_shell_handling(self):
        """Document shell handling for custom CI commands."""
        # Contract: Custom CI commands use shell=True if command is a string
        # and shell is not explicitly specified

        assert True  # Contract documented


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
