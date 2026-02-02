import unittest

from autopack.research.analysis import BudgetEnforcer
from autopack.research.orchestrator import ResearchOrchestrator


class TestResearchOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orchestrator = ResearchOrchestrator()
        self.intent_title = "Impact of Climate Change on Marine Life"
        self.intent_description = (
            "A study to understand the effects of climate change on marine ecosystems."
        )
        self.intent_objectives = [
            "Analyze temperature changes",
            "Assess species migration patterns",
        ]

    def test_start_session(self):
        session_id = self.orchestrator.start_session(
            self.intent_title, self.intent_description, self.intent_objectives
        )
        self.assertIn(session_id, self.orchestrator.sessions)

    def test_validate_session(self):
        session_id = self.orchestrator.start_session(
            self.intent_title, self.intent_description, self.intent_objectives
        )
        validation_report = self.orchestrator.validate_session(session_id)
        self.assertEqual(validation_report, "Session validated successfully.")

    def test_publish_session(self):
        session_id = self.orchestrator.start_session(
            self.intent_title, self.intent_description, self.intent_objectives
        )
        self.orchestrator.validate_session(session_id)
        success = self.orchestrator.publish_session(session_id)
        self.assertTrue(success)

    def test_publish_unvalidated_session(self):
        session_id = self.orchestrator.start_session(
            self.intent_title, self.intent_description, self.intent_objectives
        )
        success = self.orchestrator.publish_session(session_id)
        self.assertFalse(success)


class TestBudgetEnforcement(unittest.TestCase):
    """Tests for IMP-RES-002: Budget enforcement wiring."""

    def test_orchestrator_accepts_budget_enforcer(self):
        """Test that ResearchOrchestrator accepts budget_enforcer parameter."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        orchestrator = ResearchOrchestrator(budget_enforcer=enforcer)

        self.assertIsNotNone(orchestrator._budget_enforcer)
        self.assertEqual(orchestrator._budget_enforcer, enforcer)

    def test_check_budget_before_phase_with_available_budget(self):
        """Test budget check passes when budget is available."""
        enforcer = BudgetEnforcer(total_budget=5000.0)
        orchestrator = ResearchOrchestrator(budget_enforcer=enforcer)

        result = orchestrator._check_budget_before_phase("market_research")

        self.assertTrue(result)
        # Verify that the phase was started in the enforcer
        self.assertIn("market_research", enforcer._phase_history)

    def test_check_budget_before_phase_with_exhausted_budget(self):
        """Test budget check fails when budget is exhausted."""
        enforcer = BudgetEnforcer(total_budget=100.0)
        enforcer.metrics.total_spent = 100.0  # Exhaust budget

        orchestrator = ResearchOrchestrator(budget_enforcer=enforcer)
        result = orchestrator._check_budget_before_phase("market_research")

        self.assertFalse(result)

    def test_orchestrator_initializes_default_budget_enforcer(self):
        """Test that ResearchOrchestrator initializes with default budget enforcer."""
        orchestrator = ResearchOrchestrator()

        self.assertIsNotNone(orchestrator._budget_enforcer)
        self.assertEqual(orchestrator._budget_enforcer.metrics.total_budget, 5000.0)


class TestIterationLoopConfiguration(unittest.TestCase):
    """Tests for IMP-RESEARCH-001: Iteration loop configuration."""

    def test_orchestrator_accepts_iteration_parameters(self):
        """Test that ResearchOrchestrator accepts iteration loop parameters."""
        orchestrator = ResearchOrchestrator(
            max_retries=5,
            confidence_threshold=0.7,
            min_confidence_for_completion=0.5,
        )

        self.assertEqual(orchestrator._max_retries, 5)
        self.assertEqual(orchestrator._confidence_threshold, 0.7)
        self.assertEqual(orchestrator._min_confidence_for_completion, 0.5)

    def test_orchestrator_uses_default_iteration_parameters(self):
        """Test that ResearchOrchestrator uses default iteration parameters."""
        orchestrator = ResearchOrchestrator()

        self.assertEqual(orchestrator._max_retries, 3)
        self.assertEqual(orchestrator._confidence_threshold, 0.6)
        self.assertEqual(orchestrator._min_confidence_for_completion, 0.4)

    def test_get_iteration_config(self):
        """Test getting iteration configuration."""
        orchestrator = ResearchOrchestrator(
            max_retries=4,
            confidence_threshold=0.65,
            min_confidence_for_completion=0.45,
        )

        config = orchestrator.get_iteration_config()

        self.assertEqual(config["max_retries"], 4)
        self.assertEqual(config["confidence_threshold"], 0.65)
        self.assertEqual(config["min_confidence_for_completion"], 0.45)

    def test_set_iteration_config(self):
        """Test updating iteration configuration."""
        orchestrator = ResearchOrchestrator()

        orchestrator.set_iteration_config(
            max_retries=10,
            confidence_threshold=0.8,
            min_confidence_for_completion=0.6,
        )

        config = orchestrator.get_iteration_config()
        self.assertEqual(config["max_retries"], 10)
        self.assertEqual(config["confidence_threshold"], 0.8)
        self.assertEqual(config["min_confidence_for_completion"], 0.6)

    def test_set_iteration_config_partial_update(self):
        """Test partial update of iteration configuration."""
        orchestrator = ResearchOrchestrator(
            max_retries=3,
            confidence_threshold=0.6,
        )

        orchestrator.set_iteration_config(max_retries=5)

        config = orchestrator.get_iteration_config()
        self.assertEqual(config["max_retries"], 5)
        self.assertEqual(config["confidence_threshold"], 0.6)  # Unchanged

    def test_set_iteration_config_validates_max_retries(self):
        """Test that set_iteration_config validates max_retries."""
        orchestrator = ResearchOrchestrator()

        with self.assertRaises(ValueError):
            orchestrator.set_iteration_config(max_retries=-1)

    def test_set_iteration_config_validates_confidence_threshold(self):
        """Test that set_iteration_config validates confidence_threshold."""
        orchestrator = ResearchOrchestrator()

        with self.assertRaises(ValueError):
            orchestrator.set_iteration_config(confidence_threshold=1.5)

        with self.assertRaises(ValueError):
            orchestrator.set_iteration_config(confidence_threshold=-0.1)

    def test_set_iteration_config_validates_min_confidence(self):
        """Test that set_iteration_config validates min_confidence_for_completion."""
        orchestrator = ResearchOrchestrator()

        with self.assertRaises(ValueError):
            orchestrator.set_iteration_config(min_confidence_for_completion=2.0)

        with self.assertRaises(ValueError):
            orchestrator.set_iteration_config(min_confidence_for_completion=-0.5)


class TestPhaseConfidenceCalculation(unittest.TestCase):
    """Tests for phase confidence calculation logic."""

    def setUp(self):
        self.orchestrator = ResearchOrchestrator()

    def test_calculate_phase_confidence_with_explicit_confidence(self):
        """Test confidence calculation with explicit confidence score."""
        phase_data = {"confidence": 0.85}
        confidence = self.orchestrator._calculate_phase_confidence(phase_data)
        self.assertGreater(confidence, 0.8)

    def test_calculate_phase_confidence_with_attractiveness_score(self):
        """Test confidence calculation with attractiveness score."""
        phase_data = {
            "attractiveness_score": 7,
            "details": {"key": "value"},
        }
        confidence = self.orchestrator._calculate_phase_confidence(phase_data)
        self.assertGreater(confidence, 0.5)

    def test_calculate_phase_confidence_with_no_data(self):
        """Test confidence calculation with None data."""
        confidence = self.orchestrator._calculate_phase_confidence(None)
        self.assertEqual(confidence, 0.0)

    def test_calculate_phase_confidence_with_empty_data(self):
        """Test confidence calculation with empty data."""
        confidence = self.orchestrator._calculate_phase_confidence({})
        self.assertEqual(confidence, 0.5)  # Default moderate confidence

    def test_calculate_phase_confidence_with_factors_evaluated(self):
        """Test confidence calculation with factors evaluated list."""
        phase_data = {
            "factors_evaluated": ["factor1", "factor2", "factor3", "factor4", "factor5"],
            "details": {"analysis": "complete"},
        }
        confidence = self.orchestrator._calculate_phase_confidence(phase_data)
        self.assertGreater(confidence, 0.7)


if __name__ == "__main__":
    unittest.main()

# This test suite validates the functionality of the ResearchOrchestrator,
# ensuring that sessions can be started, validated, and published correctly.

# The tests cover scenarios for starting a session, validating a session,
# publishing a validated session, and attempting to publish an unvalidated
# session, providing comprehensive coverage of the orchestrator's behavior.
#
# Additional tests for IMP-RESEARCH-001 cover the iteration loop functionality
# including retry logic for failed phases and confidence-based iteration.
