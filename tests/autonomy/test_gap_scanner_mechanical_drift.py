"""Tests for mechanical doc drift detection (BUILD-180 Phase 0/2).

Validates that gap scanner uses existing mechanical checks for doc drift
instead of heuristics. Evidence should include command run and exit code.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from autopack.gaps.doc_drift import DocDriftResult, run_doc_drift_check, run_sot_summary_check
from autopack.gaps.scanner import GapScanner


class TestDocDriftMechanicalChecks:
    """Test that doc drift uses mechanical checks."""

    def test_doc_drift_runs_check_script(self):
        """Doc drift should run scripts/check_docs_drift.py."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="SUCCESS: No documentation drift detected!", stderr=""
            )

            run_doc_drift_check(Path("."))

            # Verify the script was called
            call_args = mock_run.call_args
            assert "check_docs_drift.py" in str(call_args)

    def test_doc_drift_captures_exit_code(self):
        """Doc drift result should include exit code."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="FAILURE: Documentation drift detected!", stderr=""
            )

            result = run_doc_drift_check(Path("."))

            assert result.exit_code == 1
            assert result.passed is False

    def test_doc_drift_captures_command_in_evidence(self):
        """Doc drift evidence should include command run."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")

            result = run_doc_drift_check(Path("."))

            assert result.command is not None
            assert "check_docs_drift" in result.command

    def test_sot_summary_check_runs_tidy_check(self):
        """SOT summary check should run tidy with --check flag."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="No drift", stderr="")

            run_sot_summary_check(Path("."))

            call_args = mock_run.call_args
            cmd_str = str(call_args)
            assert "sot_summary_refresh" in cmd_str
            assert "--check" in cmd_str

    def test_sot_summary_check_captures_exit_code(self):
        """SOT summary check should capture exit code."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="Drift detected", stderr="")

            result = run_sot_summary_check(Path("."))

            assert result.exit_code == 1
            assert result.passed is False


class TestGapScannerDocDriftIntegration:
    """Test gap scanner integration with mechanical doc drift."""

    def test_scanner_calls_mechanical_checks(self):
        """Gap scanner should call mechanical doc drift checks."""
        with (
            patch("autopack.gaps.scanner.run_doc_drift_check") as mock_drift,
            patch("autopack.gaps.scanner.run_sot_summary_check") as mock_sot,
            patch("autopack.gaps.scanner.run_doc_tests") as mock_doc_tests,
        ):
            mock_drift.return_value = DocDriftResult(
                passed=True,
                exit_code=0,
                command="python scripts/check_docs_drift.py",
                stdout="OK",
                stderr="",
            )
            mock_sot.return_value = DocDriftResult(
                passed=True,
                exit_code=0,
                command="python scripts/tidy/sot_summary_refresh.py --check",
                stdout="OK",
                stderr="",
            )
            mock_doc_tests.return_value = DocDriftResult(
                passed=True,
                exit_code=0,
                command="pytest tests/docs/",
                stdout="OK",
                stderr="",
            )

            scanner = GapScanner(Path("."))
            scanner._detect_doc_drift()

            mock_drift.assert_called_once()
            mock_sot.assert_called_once()

    def test_scanner_creates_gap_on_drift_failure(self):
        """Scanner should create gap when drift check fails."""
        with (
            patch("autopack.gaps.scanner.run_doc_drift_check") as mock_drift,
            patch("autopack.gaps.scanner.run_sot_summary_check") as mock_sot,
            patch("autopack.gaps.scanner.run_doc_tests") as mock_doc_tests,
        ):
            mock_drift.return_value = DocDriftResult(
                passed=False,
                exit_code=1,
                command="python scripts/check_docs_drift.py",
                stdout="FAILURE: Drift detected",
                stderr="",
            )
            mock_sot.return_value = DocDriftResult(
                passed=True,
                exit_code=0,
                command="python scripts/tidy/sot_summary_refresh.py --check",
                stdout="OK",
                stderr="",
            )
            mock_doc_tests.return_value = DocDriftResult(
                passed=True,
                exit_code=0,
                command="pytest tests/docs/",
                stdout="OK",
                stderr="",
            )

            scanner = GapScanner(Path("."))
            gaps = scanner._detect_doc_drift()

            assert len(gaps) >= 1
            gap = gaps[0]
            assert gap.gap_type == "doc_drift"
            assert "check_docs_drift" in str(gap.evidence.command_evidence)

    def test_gap_evidence_includes_exit_code(self):
        """Gap evidence should include exit code."""
        with (
            patch("autopack.gaps.scanner.run_doc_drift_check") as mock_drift,
            patch("autopack.gaps.scanner.run_sot_summary_check") as mock_sot,
            patch("autopack.gaps.scanner.run_doc_tests") as mock_doc_tests,
        ):
            mock_drift.return_value = DocDriftResult(
                passed=False,
                exit_code=1,
                command="python scripts/check_docs_drift.py",
                stdout="FAILURE",
                stderr="",
            )
            mock_sot.return_value = DocDriftResult(
                passed=True, exit_code=0, command="check", stdout="OK", stderr=""
            )
            mock_doc_tests.return_value = DocDriftResult(
                passed=True, exit_code=0, command="pytest tests/docs/", stdout="OK", stderr=""
            )

            scanner = GapScanner(Path("."))
            gaps = scanner._detect_doc_drift()

            assert len(gaps) >= 1
            gap = gaps[0]
            assert gap.evidence.command_evidence is not None
            assert gap.evidence.command_evidence.exit_code == 1


class TestDocDriftScriptNotFound:
    """Test behavior when drift scripts are not found."""

    def test_missing_script_creates_gap(self):
        """Missing drift script should create a gap with evidence."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("Script not found")

            result = run_doc_drift_check(Path("."))

            assert result.passed is False
            assert "not found" in result.error.lower() or result.exit_code != 0

    def test_scanner_handles_missing_scripts_gracefully(self):
        """Scanner should handle missing scripts without crashing."""
        with (
            patch("autopack.gaps.scanner.run_doc_drift_check") as mock_drift,
            patch("autopack.gaps.scanner.run_sot_summary_check") as mock_sot,
            patch("autopack.gaps.scanner.run_doc_tests") as mock_doc_tests,
        ):
            mock_drift.return_value = DocDriftResult(
                passed=False,
                exit_code=-1,
                command="python scripts/check_docs_drift.py",
                stdout="",
                stderr="",
                error="Script not found",
            )
            mock_sot.return_value = DocDriftResult(
                passed=True, exit_code=0, command="check", stdout="OK", stderr=""
            )
            mock_doc_tests.return_value = DocDriftResult(
                passed=True, exit_code=0, command="pytest tests/docs/", stdout="OK", stderr=""
            )

            scanner = GapScanner(Path("."))
            # Should not raise
            gaps = scanner._detect_doc_drift()

            # Should create a gap indicating the issue
            assert len(gaps) >= 1
