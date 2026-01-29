"""Tests for GapScanner integration (IMP-GAP-001).

These tests verify the gap scanner's lightweight mode for pre-phase checks.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from autopack.gaps.scanner import GapScanner, GapScanResult


class TestGapScanResult:
    """Tests for GapScanResult class."""

    def test_empty_result_has_no_blockers(self):
        """Empty gap list should have no blockers."""
        result = GapScanResult(gaps=[], scan_duration_ms=10)
        assert not result.has_blockers
        assert result.blocker_count == 0
        assert result.blockers == []
        assert result.get_blocker_summary() == ""

    def test_result_with_non_blocking_gaps(self):
        """Non-blocking gaps should not be counted as blockers."""
        from autopack.gaps.models import Gap

        gap = Gap(
            gap_id="test-gap-1",
            gap_type="doc_drift",
            detection_signals=["test signal"],
            risk_classification="medium",
            blocks_autopilot=False,
        )
        result = GapScanResult(gaps=[gap], scan_duration_ms=10)

        assert not result.has_blockers
        assert result.blocker_count == 0
        assert result.blockers == []

    def test_result_with_blocking_gaps(self):
        """Blocking gaps should be counted and accessible."""
        from autopack.gaps.models import Gap

        gap = Gap(
            gap_id="test-gap-1",
            gap_type="git_state_corruption",
            title="Git corruption detected",
            detection_signals=["test signal"],
            risk_classification="critical",
            blocks_autopilot=True,
        )
        result = GapScanResult(gaps=[gap], scan_duration_ms=10)

        assert result.has_blockers
        assert result.blocker_count == 1
        assert len(result.blockers) == 1
        assert "git_state_corruption" in result.get_blocker_summary()

    def test_result_with_mixed_gaps(self):
        """Mixed blocking and non-blocking gaps should filter correctly."""
        from autopack.gaps.models import Gap

        blocking_gap = Gap(
            gap_id="test-gap-1",
            gap_type="git_state_corruption",
            title="Git corruption",
            detection_signals=["test signal"],
            risk_classification="critical",
            blocks_autopilot=True,
        )
        non_blocking_gap = Gap(
            gap_id="test-gap-2",
            gap_type="doc_drift",
            title="Doc drift",
            detection_signals=["test signal"],
            risk_classification="medium",
            blocks_autopilot=False,
        )
        result = GapScanResult(gaps=[blocking_gap, non_blocking_gap], scan_duration_ms=15)

        assert result.has_blockers
        assert result.blocker_count == 1
        assert len(result.gaps) == 2
        assert result.blockers[0].gap_type == "git_state_corruption"


class TestGapScannerLightweightMode:
    """Tests for GapScanner lightweight mode (IMP-GAP-001)."""

    def test_scanner_default_is_not_lightweight(self):
        """Scanner should default to full mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = GapScanner(Path(tmpdir))
            assert not scanner.lightweight

    def test_scanner_lightweight_mode_enabled(self):
        """Scanner should accept lightweight=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = GapScanner(Path(tmpdir), lightweight=True)
            assert scanner.lightweight

    def test_blocker_gap_types_defined(self):
        """BLOCKER_GAP_TYPES should be defined."""
        expected_types = {
            "git_state_corruption",
            "db_lock_contention",
            "protected_path_violation",
            "test_infra_drift",
            "windows_encoding_issue",
        }
        assert GapScanner.BLOCKER_GAP_TYPES == expected_types

    @patch("autopack.gaps.scanner.GapTelemetryRecorder")
    def test_lightweight_scan_runs_subset_of_detectors(self, mock_recorder):
        """Lightweight mode should only run critical blocker detectors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = GapScanner(Path(tmpdir), lightweight=True)

            # Mock detector methods to track which are called
            called_detectors = []

            def make_mock_detector(name):
                def mock_detector():
                    called_detectors.append(name)
                    return []

                return mock_detector

            # Patch all detectors
            scanner._detect_doc_drift = make_mock_detector("doc_drift")
            scanner._detect_root_clutter = make_mock_detector("root_clutter")
            scanner._detect_sot_duplicates = make_mock_detector("sot_duplicates")
            scanner._detect_test_infra_drift = make_mock_detector("test_infra_drift")
            scanner._detect_memory_budget_issues = make_mock_detector("memory_budget")
            scanner._detect_windows_encoding_issues = make_mock_detector("windows_encoding")
            scanner._detect_baseline_policy_drift = make_mock_detector("baseline_policy")
            scanner._detect_protected_path_violations = make_mock_detector("protected_path")
            scanner._detect_db_lock_contention = make_mock_detector("db_lock")
            scanner._detect_git_state_corruption = make_mock_detector("git_state")
            scanner._run_plugin_detectors = make_mock_detector("plugins")

            scanner.scan()

            # In lightweight mode, only critical blocker detectors should be called
            assert "git_state" in called_detectors
            assert "db_lock" in called_detectors
            assert "protected_path" in called_detectors
            assert "test_infra_drift" in called_detectors
            assert "windows_encoding" in called_detectors

            # Non-critical detectors should NOT be called
            assert "doc_drift" not in called_detectors
            assert "root_clutter" not in called_detectors
            assert "sot_duplicates" not in called_detectors
            assert "memory_budget" not in called_detectors
            assert "baseline_policy" not in called_detectors
            assert "plugins" not in called_detectors

    @patch("autopack.gaps.scanner.GapTelemetryRecorder")
    def test_full_scan_runs_all_detectors(self, mock_recorder):
        """Full mode should run all detectors including plugins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = GapScanner(Path(tmpdir), lightweight=False)

            called_detectors = []

            def make_mock_detector(name):
                def mock_detector():
                    called_detectors.append(name)
                    return []

                return mock_detector

            # Patch all detectors
            scanner._detect_doc_drift = make_mock_detector("doc_drift")
            scanner._detect_root_clutter = make_mock_detector("root_clutter")
            scanner._detect_sot_duplicates = make_mock_detector("sot_duplicates")
            scanner._detect_test_infra_drift = make_mock_detector("test_infra_drift")
            scanner._detect_memory_budget_issues = make_mock_detector("memory_budget")
            scanner._detect_windows_encoding_issues = make_mock_detector("windows_encoding")
            scanner._detect_baseline_policy_drift = make_mock_detector("baseline_policy")
            scanner._detect_protected_path_violations = make_mock_detector("protected_path")
            scanner._detect_db_lock_contention = make_mock_detector("db_lock")
            scanner._detect_git_state_corruption = make_mock_detector("git_state")
            scanner._run_plugin_detectors = make_mock_detector("plugins")

            scanner.scan()

            # All detectors should be called in full mode
            assert len(called_detectors) == 11


class TestScanForPhase:
    """Tests for scan_for_phase method (IMP-GAP-001)."""

    @patch("autopack.gaps.scanner.GapTelemetryRecorder")
    def test_scan_for_phase_uses_lightweight_mode(self, mock_recorder):
        """scan_for_phase should use lightweight mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = GapScanner(Path(tmpdir))

            # Initially not lightweight
            assert not scanner.lightweight

            phase = {"phase_id": "test-phase-1"}
            result = scanner.scan_for_phase(phase)

            # After scan_for_phase, should be in lightweight mode
            assert scanner.lightweight
            assert isinstance(result, GapScanResult)

    @patch("autopack.gaps.scanner.GapTelemetryRecorder")
    def test_scan_for_phase_returns_gap_scan_result(self, mock_recorder):
        """scan_for_phase should return a GapScanResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = GapScanner(Path(tmpdir))
            phase = {"phase_id": "test-phase-1", "description": "Test phase"}

            result = scanner.scan_for_phase(phase)

            assert isinstance(result, GapScanResult)
            assert result.scan_duration_ms >= 0

    @patch("autopack.gaps.scanner.GapTelemetryRecorder")
    def test_scan_for_phase_captures_duration(self, mock_recorder):
        """scan_for_phase should capture scan duration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scanner = GapScanner(Path(tmpdir))
            phase = {"phase_id": "test-phase-1"}

            result = scanner.scan_for_phase(phase)

            # Duration should be captured (>= 0ms)
            assert result.scan_duration_ms >= 0


class TestGapScannerIntegration:
    """Integration tests for gap scanner."""

    @patch("autopack.gaps.scanner.GapTelemetryRecorder")
    @patch("subprocess.run")
    def test_scanner_detects_no_gaps_in_clean_workspace(self, mock_subprocess, mock_recorder):
        """Clean workspace should have no gaps when git commands succeed."""
        # Mock git commands to simulate a clean git workspace
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create minimal structure
            (workspace / ".git").mkdir()
            (workspace / "docs").mkdir()
            (workspace / "src").mkdir()

            scanner = GapScanner(workspace, lightweight=True)
            gaps = scanner.scan()

            # Should not have critical blockers in clean workspace with mocked git
            blockers = [g for g in gaps if g.blocks_autopilot]
            # May have some gaps (like missing config), but should be non-blocking
            assert len(blockers) == 0 or all(
                g.gap_type not in GapScanner.BLOCKER_GAP_TYPES for g in blockers
            )
