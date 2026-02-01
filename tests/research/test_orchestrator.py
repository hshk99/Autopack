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


if __name__ == "__main__":
    unittest.main()

# This test suite validates the functionality of the ResearchOrchestrator,
# ensuring that sessions can be started, validated, and published correctly.

# The tests cover scenarios for starting a session, validating a session,
# publishing a validated session, and attempting to publish an unvalidated
# session, providing comprehensive coverage of the orchestrator's behavior.
