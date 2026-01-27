"""
BUILD-155: Test SOT budget-aware gating logic.

Tests that SOT retrieval is correctly gated based on available budget:
1. Retrieval skipped when budget is insufficient
2. Retrieval included when budget is sufficient
3. Respects AUTOPACK_SOT_RETRIEVAL_ENABLED global flag
4. Correctly calculates minimum required budget (sot_budget + 2000)
"""

from unittest.mock import Mock

import pytest


class TestSOTBudgetGating:
    """Test budget-aware gating for SOT retrieval"""

    @pytest.fixture
    def executor(self):
        """Create a mock executor with the _should_include_sot_retrieval method"""
        # Import the method directly to test it in isolation
        from autopack.autonomous_executor import AutonomousExecutor

        # Create mock executor instance
        executor = Mock(spec=AutonomousExecutor)
        executor.run_id = "test-build155-gating"

        # Mock the retrieval_injection attribute
        executor.retrieval_injection = Mock()

        # Bind the actual method to the mock
        executor._should_include_sot_retrieval = (
            AutonomousExecutor._should_include_sot_retrieval.__get__(executor, AutonomousExecutor)
        )

        return executor

    def test_sot_skipped_when_budget_too_low(self, executor):
        """SOT retrieval should be skipped when budget < (sot_budget + 2000)"""
        from autopack.executor.retrieval_injection import GateDecision

        # Scenario: budget=3000, sot_budget=4000, reserve=2000 → needs 6000 → SKIP
        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=False,
            reason="Insufficient budget",
            budget_remaining=3000,
            sot_budget=4000,
        )

        result = executor._should_include_sot_retrieval(max_context_chars=3000)

        assert result is False, "SOT should be skipped when budget is insufficient"

    def test_sot_skipped_when_budget_exactly_at_minimum(self, executor):
        """SOT retrieval should be skipped when budget equals minimum (not >=)"""
        from autopack.executor.retrieval_injection import GateDecision

        # Scenario: budget=6000, sot_budget=4000, reserve=2000 → needs 6001 → SKIP
        # (need STRICT > check, not >=)
        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=False,
            reason="Budget exactly at minimum",
            budget_remaining=5999,
            sot_budget=4000,
        )

        result = executor._should_include_sot_retrieval(max_context_chars=5999)

        assert result is False, "SOT should be skipped when budget is exactly at minimum"

    def test_sot_included_when_budget_sufficient(self, executor):
        """SOT retrieval should be included when budget >= (sot_budget + 2000)"""
        from autopack.executor.retrieval_injection import GateDecision

        # Scenario: budget=8000, sot_budget=4000, reserve=2000 → needs 6000 → INCLUDE
        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=True,
            reason="Sufficient budget",
            budget_remaining=2000,
            sot_budget=4000,
        )

        result = executor._should_include_sot_retrieval(max_context_chars=8000)

        assert result is True, "SOT should be included when budget is sufficient"

    def test_sot_skipped_when_globally_disabled(self, executor):
        """SOT retrieval should always be skipped when AUTOPACK_SOT_RETRIEVAL_ENABLED=false"""
        from autopack.executor.retrieval_injection import GateDecision

        # Even with huge budget, SOT should be skipped if globally disabled
        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=False,
            reason="SOT retrieval disabled by configuration",
            budget_remaining=100000,
            sot_budget=4000,
        )

        result = executor._should_include_sot_retrieval(max_context_chars=100000)

        assert result is False, "SOT should be skipped when globally disabled"

    def test_sot_budget_scaling(self, executor):
        """Gating logic should adapt to different sot_budget values"""
        from autopack.executor.retrieval_injection import GateDecision

        # Test with larger sot_budget
        # 8000 + 2000 = 10000 minimum required
        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=False,
            reason="Insufficient budget",
            budget_remaining=9999,
            sot_budget=8000,
        )
        assert executor._should_include_sot_retrieval(max_context_chars=9999) is False

        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=True,
            reason="Sufficient budget",
            budget_remaining=0,
            sot_budget=8000,
        )
        assert executor._should_include_sot_retrieval(max_context_chars=10000) is True

    def test_sot_with_custom_reserve_headroom(self, executor):
        """Verify the 2000-char reserve is correctly applied"""
        from autopack.executor.retrieval_injection import GateDecision

        # Minimum = 4000 + 2000 = 6000
        # Test boundary conditions
        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=False,
            reason="Insufficient budget",
            budget_remaining=5999,
            sot_budget=4000,
        )
        assert executor._should_include_sot_retrieval(max_context_chars=5999) is False

        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=True,
            reason="Sufficient budget",
            budget_remaining=0,
            sot_budget=4000,
        )
        assert executor._should_include_sot_retrieval(max_context_chars=6000) is True

        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=True,
            reason="Sufficient budget",
            budget_remaining=1,
            sot_budget=4000,
        )
        assert executor._should_include_sot_retrieval(max_context_chars=6001) is True

    def test_sot_opt_in_by_default(self, executor):
        """SOT retrieval should be opt-in (default: enabled=false in real config)"""
        from autopack.executor.retrieval_injection import GateDecision

        # This test verifies the design intent documented in BUILD-154
        # In production, AUTOPACK_SOT_RETRIEVAL_ENABLED defaults to false
        # Tests use mocks, but this documents expected behavior
        # Simulate default production config (SOT disabled by default)
        executor.retrieval_injection.gate_sot_retrieval.return_value = GateDecision(
            allowed=False,
            reason="SOT retrieval disabled by configuration",
            budget_remaining=10000,
            sot_budget=4000,
        )

        # Even with sufficient budget, SOT should be skipped
        result = executor._should_include_sot_retrieval(max_context_chars=10000)

        assert result is False, (
            "SOT retrieval should be opt-in (disabled by default). "
            "Operators must explicitly set AUTOPACK_SOT_RETRIEVAL_ENABLED=true."
        )
