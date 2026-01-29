"""Tests for pre-phase gap check integration (IMP-GAP-001).

These tests verify the PhaseOrchestrator's pre-phase gap checking functionality
that detects potential blockers before phase execution.
"""

import tempfile
from unittest.mock import Mock, patch


from autopack.executor.phase_orchestrator import (
    ExecutionContext,
    ExecutionResult,
    PhaseOrchestrator,
    PhaseResult,
    create_default_time_watchdog,
)


class TestPhaseOrchestratorGapCheckInit:
    """Tests for PhaseOrchestrator gap check initialization."""

    def test_gap_check_enabled_by_default(self):
        """Pre-phase gap check should be enabled by default."""
        orchestrator = PhaseOrchestrator()
        assert orchestrator.enable_pre_phase_gap_check is True

    def test_gap_check_can_be_disabled(self):
        """Pre-phase gap check can be disabled via constructor."""
        orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=False)
        assert orchestrator.enable_pre_phase_gap_check is False


class TestPrePhaseGapCheck:
    """Tests for _run_pre_phase_gap_check method."""

    def _create_test_context(self, phase_id: str = "test-phase", workspace: str = None):
        """Create a minimal test execution context."""
        phase = {"phase_id": phase_id, "description": "Test phase"}
        watchdog = create_default_time_watchdog()

        return ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run-123",
            llm_service=Mock(),
            time_watchdog=watchdog,
            workspace_root=workspace,
            mark_phase_failed_in_db=Mock(),
        )

    def test_gap_check_returns_none_when_disabled(self):
        """Gap check should return None when disabled."""
        orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=False)
        context = self._create_test_context()

        result = orchestrator._run_pre_phase_gap_check(context)

        assert result is None

    @patch("autopack.gaps.scanner.GapScanner")
    def test_gap_check_returns_none_on_no_blockers(self, mock_scanner_class):
        """Gap check should return None when no blockers found."""
        # Mock GapScanResult with no blockers
        mock_result = Mock()
        mock_result.has_blockers = False
        mock_result.scan_duration_ms = 10

        mock_scanner = Mock()
        mock_scanner.scan_for_phase.return_value = mock_result
        mock_scanner_class.return_value = mock_scanner

        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=True)
            context = self._create_test_context(workspace=tmpdir)

            result = orchestrator._run_pre_phase_gap_check(context)

            assert result is None
            mock_scanner.scan_for_phase.assert_called_once()

    @patch("autopack.gaps.scanner.GapScanner")
    def test_gap_check_returns_blocked_result_on_blockers(self, mock_scanner_class):
        """Gap check should return BLOCKED result when blockers found."""
        from autopack.gaps.models import Gap

        # Create a blocking gap
        blocking_gap = Gap(
            gap_id="test-blocker",
            gap_type="git_state_corruption",
            title="Git corruption detected",
            detection_signals=["test signal"],
            risk_classification="critical",
            blocks_autopilot=True,
        )

        # Mock GapScanResult with blockers
        mock_result = Mock()
        mock_result.has_blockers = True
        mock_result.blocker_count = 1
        mock_result.blockers = [blocking_gap]
        mock_result.get_blocker_summary.return_value = "- git_state_corruption: Git corruption"
        mock_result.scan_duration_ms = 15

        mock_scanner = Mock()
        mock_scanner.scan_for_phase.return_value = mock_result
        mock_scanner_class.return_value = mock_scanner

        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=True)
            context = self._create_test_context(workspace=tmpdir)

            result = orchestrator._run_pre_phase_gap_check(context)

            assert result is not None
            assert isinstance(result, ExecutionResult)
            assert result.success is False
            assert result.status == "PRE_PHASE_GAP_BLOCKER"
            assert result.phase_result == PhaseResult.BLOCKED
            assert result.should_continue is False

    @patch("autopack.gaps.scanner.GapScanner")
    def test_gap_check_marks_phase_failed_on_blockers(self, mock_scanner_class):
        """Gap check should mark phase failed when blockers found."""
        from autopack.gaps.models import Gap

        blocking_gap = Gap(
            gap_id="test-blocker",
            gap_type="db_lock_contention",
            title="DB lock detected",
            detection_signals=["test signal"],
            risk_classification="high",
            blocks_autopilot=True,
        )

        mock_result = Mock()
        mock_result.has_blockers = True
        mock_result.blocker_count = 1
        mock_result.blockers = [blocking_gap]
        mock_result.get_blocker_summary.return_value = "- db_lock_contention: DB lock"
        mock_result.scan_duration_ms = 10

        mock_scanner = Mock()
        mock_scanner.scan_for_phase.return_value = mock_result
        mock_scanner_class.return_value = mock_scanner

        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=True)
            context = self._create_test_context(workspace=tmpdir)

            orchestrator._run_pre_phase_gap_check(context)

            # Verify mark_phase_failed_in_db was called
            context.mark_phase_failed_in_db.assert_called_once_with(
                "test-phase", "PRE_PHASE_GAP_BLOCKER"
            )

    def test_gap_check_handles_import_error_gracefully(self):
        """Gap check should handle ImportError gracefully."""
        # Simulate ImportError by making the import fail inside the method
        import sys

        # Temporarily remove the module to cause ImportError
        original_module = sys.modules.get("autopack.gaps.scanner")
        sys.modules["autopack.gaps.scanner"] = None

        try:
            orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=True)
            context = self._create_test_context()

            # Should return None and not raise
            result = orchestrator._run_pre_phase_gap_check(context)
            # Should return None due to import error handling
            assert result is None
        finally:
            # Restore the module
            if original_module is not None:
                sys.modules["autopack.gaps.scanner"] = original_module
            elif "autopack.gaps.scanner" in sys.modules:
                del sys.modules["autopack.gaps.scanner"]

    @patch("autopack.gaps.scanner.GapScanner")
    def test_gap_check_handles_scanner_exception_gracefully(self, mock_scanner_class):
        """Gap check should handle scanner exceptions gracefully."""
        mock_scanner_class.side_effect = Exception("Scanner failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=True)
            context = self._create_test_context(workspace=tmpdir)

            # Should return None and not raise
            result = orchestrator._run_pre_phase_gap_check(context)
            assert result is None


class TestGapTelemetryEmission:
    """Tests for gap telemetry emission."""

    @patch("os.getenv")
    @patch("autopack.gaps.scanner.GapScanner")
    def test_telemetry_not_emitted_when_disabled(self, mock_scanner_class, mock_getenv):
        """Telemetry should not be emitted when TELEMETRY_DB_ENABLED is false."""
        mock_getenv.return_value = "false"

        from autopack.gaps.models import Gap

        blocking_gap = Gap(
            gap_id="test-blocker",
            gap_type="test_infra_drift",
            title="Test drift",
            detection_signals=["signal"],
            risk_classification="high",
            blocks_autopilot=True,
        )

        mock_result = Mock()
        mock_result.has_blockers = True
        mock_result.blocker_count = 1
        mock_result.blockers = [blocking_gap]
        mock_result.get_blocker_summary.return_value = "- test_infra_drift: Test drift"
        mock_result.scan_duration_ms = 10

        mock_scanner = Mock()
        mock_scanner.scan_for_phase.return_value = mock_result
        mock_scanner_class.return_value = mock_scanner

        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = PhaseOrchestrator(enable_pre_phase_gap_check=True)
            context = ExecutionContext(
                phase={"phase_id": "test-phase"},
                attempt_index=0,
                max_attempts=5,
                escalation_level=0,
                allowed_paths=[],
                run_id="test-run",
                llm_service=Mock(),
                time_watchdog=create_default_time_watchdog(),
                workspace_root=tmpdir,
                mark_phase_failed_in_db=Mock(),
            )

            # This should not raise even though telemetry is disabled
            orchestrator._run_pre_phase_gap_check(context)


class TestExecutePhaseAttemptWithGapCheck:
    """Tests for execute_phase_attempt with gap check integration."""

    @patch("autopack.gaps.scanner.GapScanner")
    def test_phase_blocked_before_execution_on_gap_blockers(self, mock_scanner_class):
        """Phase should be blocked before execution when gap blockers found."""
        from autopack.gaps.models import Gap

        blocking_gap = Gap(
            gap_id="blocker-1",
            gap_type="git_state_corruption",
            title="Git corruption",
            detection_signals=["signal"],
            risk_classification="critical",
            blocks_autopilot=True,
        )

        mock_result = Mock()
        mock_result.has_blockers = True
        mock_result.blocker_count = 1
        mock_result.blockers = [blocking_gap]
        mock_result.get_blocker_summary.return_value = "- git_state_corruption: Git corruption"
        mock_result.scan_duration_ms = 5

        mock_scanner = Mock()
        mock_scanner.scan_for_phase.return_value = mock_result
        mock_scanner_class.return_value = mock_scanner

        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = PhaseOrchestrator(
                max_retry_attempts=5,
                enable_pre_phase_gap_check=True,
            )

            context = ExecutionContext(
                phase={"phase_id": "test-phase", "category": "implementation"},
                attempt_index=0,
                max_attempts=5,
                escalation_level=0,
                allowed_paths=[],
                run_id="test-run",
                llm_service=Mock(),
                time_watchdog=create_default_time_watchdog(),
                workspace_root=tmpdir,
                mark_phase_failed_in_db=Mock(),
            )

            result = orchestrator.execute_phase_attempt(context)

            assert result.success is False
            assert result.phase_result == PhaseResult.BLOCKED
            assert result.status == "PRE_PHASE_GAP_BLOCKER"

    @patch("autopack.gaps.scanner.GapScanner")
    def test_phase_proceeds_when_no_gap_blockers(self, mock_scanner_class):
        """Phase should proceed when no gap blockers found."""
        mock_result = Mock()
        mock_result.has_blockers = False
        mock_result.scan_duration_ms = 5

        mock_scanner = Mock()
        mock_scanner.scan_for_phase.return_value = mock_result
        mock_scanner_class.return_value = mock_scanner

        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = PhaseOrchestrator(
                max_retry_attempts=5,
                enable_pre_phase_gap_check=True,
            )

            context = ExecutionContext(
                phase={"phase_id": "test-phase"},
                attempt_index=5,  # Already exhausted to trigger quick return
                max_attempts=5,
                escalation_level=0,
                allowed_paths=[],
                run_id="test-run",
                llm_service=Mock(),
                time_watchdog=create_default_time_watchdog(),
                workspace_root=tmpdir,
                mark_phase_failed_in_db=Mock(),
            )

            result = orchestrator.execute_phase_attempt(context)

            # Should get past gap check and hit exhausted attempts
            assert result.phase_result == PhaseResult.FAILED
            assert result.status == "FAILED"  # Exhausted, not blocked
