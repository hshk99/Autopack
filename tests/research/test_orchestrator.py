import unittest
from unittest.mock import MagicMock

from autopack.research.orchestrator import BudgetTracker, ResearchOrchestrator


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
    """Tests for IMP-COST-001: Budget enforcement wiring."""

    def test_orchestrator_accepts_budget_tracker(self):
        """Test that ResearchOrchestrator accepts budget_tracker parameter."""
        mock_tracker = MagicMock(spec=BudgetTracker)
        orchestrator = ResearchOrchestrator(budget_tracker=mock_tracker)

        self.assertIsNotNone(orchestrator._budget_tracker)
        self.assertEqual(orchestrator._budget_tracker, mock_tracker)

    def test_check_budget_before_phase_with_available_budget(self):
        """Test budget check passes when budget is available."""
        mock_tracker = MagicMock(spec=BudgetTracker)
        mock_tracker.can_proceed.return_value = True

        orchestrator = ResearchOrchestrator(budget_tracker=mock_tracker)
        result = orchestrator._check_budget_before_phase("market_research")

        self.assertTrue(result)
        mock_tracker.can_proceed.assert_called_once_with("market_research")

    def test_check_budget_before_phase_with_exhausted_budget(self):
        """Test budget check fails when budget is exhausted."""
        mock_tracker = MagicMock(spec=BudgetTracker)
        mock_tracker.can_proceed.return_value = False

        orchestrator = ResearchOrchestrator(budget_tracker=mock_tracker)
        result = orchestrator._check_budget_before_phase("market_research")

        self.assertFalse(result)
        mock_tracker.can_proceed.assert_called_once_with("market_research")

    def test_check_budget_without_tracker_allows_proceeding(self):
        """Test that research proceeds when no budget tracker is configured."""
        orchestrator = ResearchOrchestrator(budget_tracker=None)
        result = orchestrator._check_budget_before_phase("market_research")

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()

# This test suite validates the functionality of the ResearchOrchestrator,
# ensuring that sessions can be started, validated, and published correctly.

# The tests cover scenarios for starting a session, validating a session,
# publishing a validated session, and attempting to publish an unvalidated
# session, providing comprehensive coverage of the orchestrator's behavior.
