"""Tests for SOT retrieval injection budget gating.

Tests the RetrievalInjection class extracted from autonomous_executor.py
as part of PR-EXE-5 (god file refactoring).

Test Coverage:
1. SOT budget gating (within budget → allowed, over budget → denied)
2. Global kill switch (enabled/disabled)
3. Telemetry recording (success/failure tracking)
4. Remaining budget calculation
5. Multi-phase budget tracking
6. Budget utilization and warnings
"""

from autopack.executor.retrieval_injection import RetrievalInjection


class TestSOTBudgetGating:
    """Tests for SOT retrieval budget gating logic."""

    def test_gate_allows_with_sufficient_budget(self):
        """Test gate allows retrieval when budget is sufficient."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=10000, phase_id="test_phase")

        assert gate.allowed is True
        assert gate.sot_budget == 4000
        assert gate.reserve_budget == 2000
        assert gate.budget_remaining == 6000  # 10000 - 4000

    def test_gate_denies_with_insufficient_budget(self):
        """Test gate denies retrieval when budget is insufficient."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        # Need 6000 (4000 + 2000), but only have 5000
        gate = injection.gate_sot_retrieval(max_context_chars=5000, phase_id="test_phase")

        assert gate.allowed is False
        assert "insufficient budget" in gate.reason.lower()
        assert gate.budget_remaining == 5000

    def test_gate_exactly_at_minimum(self):
        """Test gate behavior when budget exactly meets minimum."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        # Exactly 6000 (4000 + 2000)
        gate = injection.gate_sot_retrieval(max_context_chars=6000, phase_id="test_phase")

        assert gate.allowed is True
        assert gate.budget_remaining == 2000

    def test_gate_one_char_below_minimum(self):
        """Test gate denies when one char below minimum."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        # One char below minimum
        gate = injection.gate_sot_retrieval(max_context_chars=5999, phase_id="test_phase")

        assert gate.allowed is False

    def test_gate_with_zero_budget(self):
        """Test gate behavior with zero budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=0)

        assert gate.allowed is False

    def test_gate_with_large_budget(self):
        """Test gate allows retrieval with very large budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, reserve_budget=2000, enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=100_000)

        assert gate.allowed is True
        assert gate.budget_remaining == 96_000


class TestGlobalKillSwitch:
    """Tests for global SOT retrieval kill switch."""

    def test_disabled_denies_even_with_budget(self):
        """Test that disabled state denies retrieval regardless of budget."""
        injection = RetrievalInjection(sot_budget_limit=4000, enabled=False)  # Disabled

        gate = injection.gate_sot_retrieval(max_context_chars=100_000)

        assert gate.allowed is False
        assert "disabled" in gate.reason.lower()

    def test_enabled_allows_with_budget(self):
        """Test that enabled state allows retrieval with sufficient budget."""
        injection = RetrievalInjection(
            sot_budget_limit=4000,
            reserve_budget=2000,
            enabled=True,  # Enabled
        )

        gate = injection.gate_sot_retrieval(max_context_chars=10_000)

        assert gate.allowed is True

    def test_default_enabled(self):
        """Test that default state is enabled (IMP-AUTO-001)."""
        injection = RetrievalInjection()

        gate = injection.gate_sot_retrieval(max_context_chars=100_000)

        assert gate.allowed is True
        assert "budget available" in gate.reason.lower()


class TestTelemetryRecording:
    """Tests for telemetry recording."""

    def test_record_success(self):
        """Test recording successful retrieval."""
        injection = RetrievalInjection(telemetry_enabled=True)

        # Should not raise
        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=3, success=True, chars_retrieved=2500
        )

        # Check cumulative usage was updated
        assert injection._run_usage["run_123"] == 2500

    def test_record_failure(self):
        """Test recording failed retrieval."""
        injection = RetrievalInjection(telemetry_enabled=True)

        # Should not raise
        injection.record_retrieval_telemetry(
            run_id="run_123",
            phase_id="phase_1",
            entries=0,
            success=False,
            chars_retrieved=0,
            error="Database connection failed",
        )

        # Failed retrieval should not update usage
        assert injection._run_usage.get("run_123", 0) == 0

    def test_telemetry_disabled_no_op(self):
        """Test that disabled telemetry is a no-op."""
        injection = RetrievalInjection(telemetry_enabled=False)

        # Should not raise or update usage
        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=3, success=True, chars_retrieved=2500
        )

        # Usage should not be tracked when telemetry disabled
        assert "run_123" not in injection._run_usage

    def test_multiple_telemetry_records_accumulate(self):
        """Test that multiple successful records accumulate usage."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=2, success=True, chars_retrieved=1000
        )

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_2", entries=3, success=True, chars_retrieved=1500
        )

        assert injection._run_usage["run_123"] == 2500

    def test_separate_runs_tracked_independently(self):
        """Test that different runs are tracked independently."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_1", phase_id="phase_1", entries=2, success=True, chars_retrieved=1000
        )

        injection.record_retrieval_telemetry(
            run_id="run_2", phase_id="phase_1", entries=3, success=True, chars_retrieved=2000
        )

        assert injection._run_usage["run_1"] == 1000
        assert injection._run_usage["run_2"] == 2000


class TestBudgetCalculation:
    """Tests for remaining budget calculation."""

    def test_get_remaining_budget_no_usage(self):
        """Test remaining budget with no usage."""
        injection = RetrievalInjection(telemetry_enabled=True)

        remaining = injection.get_remaining_budget("run_123", total_budget=50_000)

        assert remaining == 50_000

    def test_get_remaining_budget_with_usage(self):
        """Test remaining budget after some usage."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=3, success=True, chars_retrieved=10_000
        )

        remaining = injection.get_remaining_budget("run_123", total_budget=50_000)

        assert remaining == 40_000

    def test_get_remaining_budget_exhausted(self):
        """Test remaining budget when exhausted."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=10, success=True, chars_retrieved=60_000
        )

        remaining = injection.get_remaining_budget("run_123", total_budget=50_000)

        # Should not go negative
        assert remaining == 0

    def test_get_remaining_budget_exactly_exhausted(self):
        """Test remaining budget when exactly exhausted."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=5, success=True, chars_retrieved=50_000
        )

        remaining = injection.get_remaining_budget("run_123", total_budget=50_000)

        assert remaining == 0

    def test_reset_run_budget(self):
        """Test resetting budget for a run."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=3, success=True, chars_retrieved=10_000
        )

        injection.reset_run_budget("run_123")

        remaining = injection.get_remaining_budget("run_123", total_budget=50_000)
        assert remaining == 50_000

    def test_reset_nonexistent_run(self):
        """Test resetting budget for run that doesn't exist."""
        injection = RetrievalInjection(telemetry_enabled=True)

        # Should not raise
        injection.reset_run_budget("nonexistent_run")


class TestBudgetUtilization:
    """Tests for budget utilization tracking."""

    def test_utilization_zero_with_no_usage(self):
        """Test utilization is zero with no usage."""
        injection = RetrievalInjection(telemetry_enabled=True)

        utilization = injection.get_budget_utilization("run_123", total_budget=50_000)

        assert utilization == 0.0

    def test_utilization_with_partial_usage(self):
        """Test utilization calculation with partial usage."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=3, success=True, chars_retrieved=25_000
        )

        utilization = injection.get_budget_utilization("run_123", total_budget=50_000)

        assert utilization == 50.0

    def test_utilization_fully_used(self):
        """Test utilization when budget is fully used."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=5, success=True, chars_retrieved=50_000
        )

        utilization = injection.get_budget_utilization("run_123", total_budget=50_000)

        assert utilization == 100.0

    def test_utilization_over_budget(self):
        """Test utilization when over budget."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=10, success=True, chars_retrieved=75_000
        )

        utilization = injection.get_budget_utilization("run_123", total_budget=50_000)

        assert utilization == 150.0

    def test_should_warn_budget_below_threshold(self):
        """Test no warning below threshold."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=2, success=True, chars_retrieved=30_000
        )

        should_warn = injection.should_warn_budget(
            run_id="run_123", total_budget=50_000, warning_threshold=80.0
        )

        assert should_warn is False  # 60% < 80%

    def test_should_warn_budget_at_threshold(self):
        """Test warning exactly at threshold."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=4, success=True, chars_retrieved=40_000
        )

        should_warn = injection.should_warn_budget(
            run_id="run_123", total_budget=50_000, warning_threshold=80.0
        )

        assert should_warn is True  # 80% >= 80%

    def test_should_warn_budget_above_threshold(self):
        """Test warning above threshold."""
        injection = RetrievalInjection(telemetry_enabled=True)

        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=5, success=True, chars_retrieved=45_000
        )

        should_warn = injection.should_warn_budget(
            run_id="run_123", total_budget=50_000, warning_threshold=80.0
        )

        assert should_warn is True  # 90% >= 80%


class TestFromSettings:
    """Tests for creating instance from settings."""

    def test_from_settings_with_mock(self):
        """Test creating instance from settings object."""

        class MockSettings:
            autopack_sot_retrieval_max_chars = 5000
            TELEMETRY_DB_ENABLED = True
            autopack_sot_retrieval_enabled = True

        injection = RetrievalInjection.from_settings(MockSettings())

        assert injection.sot_budget_limit == 5000
        assert injection.telemetry_enabled is True
        assert injection.enabled is True
        assert injection.reserve_budget == 2000

    def test_from_settings_defaults(self):
        """Test from_settings with missing attributes uses defaults (IMP-AUTO-001)."""

        class MinimalSettings:
            pass

        injection = RetrievalInjection.from_settings(MinimalSettings())

        assert injection.sot_budget_limit == 4000
        assert injection.telemetry_enabled is False
        assert injection.enabled is True  # IMP-AUTO-001: enabled by default


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_negative_budget(self):
        """Test handling of negative budget (should deny)."""
        injection = RetrievalInjection(enabled=True)

        gate = injection.gate_sot_retrieval(max_context_chars=-1000)

        assert gate.allowed is False

    def test_zero_sot_budget_limit(self):
        """Test with zero SOT budget limit."""
        injection = RetrievalInjection(sot_budget_limit=0, reserve_budget=2000, enabled=True)

        # Should need 2000 for reserve
        gate = injection.gate_sot_retrieval(max_context_chars=2000)

        assert gate.allowed is True
        assert gate.budget_remaining == 2000

    def test_custom_reserve_budget(self):
        """Test with custom reserve budget."""
        injection = RetrievalInjection(
            sot_budget_limit=4000,
            reserve_budget=5000,
            enabled=True,  # Custom reserve
        )

        gate = injection.gate_sot_retrieval(max_context_chars=8000)

        # Should deny: need 9000 (4000 + 5000), have 8000
        assert gate.allowed is False

    def test_phase_id_optional(self):
        """Test that phase_id is optional."""
        injection = RetrievalInjection(enabled=True)

        # Should not raise without phase_id
        gate = injection.gate_sot_retrieval(max_context_chars=10_000)

        assert gate.allowed is True


class TestMultiPhaseScenario:
    """Integration tests for multi-phase budget tracking."""

    def test_multi_phase_budget_tracking(self):
        """Test budget tracking across multiple phases."""
        injection = RetrievalInjection(sot_budget_limit=4000, telemetry_enabled=True, enabled=True)

        # Phase 1: Use 3000 chars
        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=2, success=True, chars_retrieved=3000
        )

        # Phase 2: Use 2000 chars
        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_2", entries=2, success=True, chars_retrieved=2000
        )

        # Total usage should be 5000
        remaining = injection.get_remaining_budget("run_123", total_budget=10_000)
        assert remaining == 5_000

        utilization = injection.get_budget_utilization("run_123", total_budget=10_000)
        assert utilization == 50.0

    def test_budget_warning_after_multiple_phases(self):
        """Test warning triggers after cumulative usage."""
        injection = RetrievalInjection(sot_budget_limit=4000, telemetry_enabled=True, enabled=True)

        # Phase 1: 30% usage
        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_1", entries=2, success=True, chars_retrieved=15_000
        )

        # No warning yet
        assert not injection.should_warn_budget("run_123", 50_000, 80.0)

        # Phase 2: Another 30% usage (total 60%)
        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_2", entries=2, success=True, chars_retrieved=15_000
        )

        # Still no warning
        assert not injection.should_warn_budget("run_123", 50_000, 80.0)

        # Phase 3: Another 25% usage (total 85%)
        injection.record_retrieval_telemetry(
            run_id="run_123", phase_id="phase_3", entries=2, success=True, chars_retrieved=12_500
        )

        # Now should warn
        assert injection.should_warn_budget("run_123", 50_000, 80.0)
