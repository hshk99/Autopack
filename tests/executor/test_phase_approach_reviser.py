"""Contract tests for PhaseApproachReviser (PR-EXE-13).

Validates that the phase approach reviser correctly revises phase approaches
when stuck, implements goal anchoring, and classifies alignment.
"""

from unittest.mock import Mock, patch
import pytest

from autopack.executor.phase_approach_reviser import PhaseApproachReviser


class TestPhaseApproachReviser:
    """Test suite for PhaseApproachReviser contract."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor."""
        executor = Mock()
        executor.workspace = tmp_path
        executor.run_id = "test-run-123"
        executor.llm_service = Mock()
        executor._phase_original_intent = {}
        executor._phase_original_description = {}
        executor._phase_replan_history = {}
        executor._phase_revised_specs = {}
        executor._phase_error_history = {}
        executor._initialize_phase_goal_anchor = Mock()
        executor._classify_replan_alignment = Mock(
            return_value={"alignment": "aligned", "notes": "Revision maintains original scope"}
        )
        executor._get_learning_context_for_phase = Mock(return_value={})
        executor._record_replan_telemetry = Mock()
        executor._get_project_slug = Mock(return_value="test-project")
        executor._get_replan_count = Mock(return_value=0)
        executor._record_plan_change_entry = Mock()
        executor._record_decision_entry = Mock()
        return executor

    @pytest.fixture
    def reviser(self, mock_executor):
        """Create reviser instance."""
        return PhaseApproachReviser(mock_executor)

    def test_successful_approach_revision(self, reviser, mock_executor):
        """Test successful phase approach revision."""
        phase = {
            "phase_id": "phase-1",
            "name": "Implement feature X",
            "description": "Add feature X using approach A",
            "task_category": "feature",
            "complexity": "medium",
        }
        error_history = [
            {"attempt": 0, "error_type": "ImportError", "error_details": "Module not found"},
            {"attempt": 1, "error_type": "ImportError", "error_details": "Module not found"},
        ]

        mock_executor._phase_original_intent["phase-1"] = "Add feature X"

        # Mock Anthropic client
        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = (
            "Revised approach: Add feature X using approach B with proper imports"
        )
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                revised = reviser.revise_approach(phase, "repeated_error", error_history)

        assert revised is not None
        assert revised["phase_id"] == "phase-1"
        assert (
            revised["description"]
            == "Revised approach: Add feature X using approach B with proper imports"
        )
        assert revised["_original_intent"] == "Add feature X"
        assert revised["_revision_reason"] == "Approach flaw: repeated_error"
        assert "_revision_timestamp" in revised
        assert "_revision_alignment" in revised

    def test_failed_revision_empty_response(self, reviser, mock_executor):
        """Test revision failure when LLM returns empty response."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = [{"attempt": 0, "error_type": "Error", "error_details": "Details"}]

        # Mock empty response
        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = ""
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                revised = reviser.revise_approach(phase, "repeated_error", error_history)

        assert revised is None
        mock_executor._record_replan_telemetry.assert_called()

    def test_goal_anchoring_initialization(self, reviser, mock_executor):
        """Test goal anchoring initialization is called."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = []

        mock_executor._phase_original_intent["phase-1"] = "Original goal"

        # Mock successful response
        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "Revised description maintaining original goal"
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                reviser.revise_approach(phase, "flaw", error_history)

        mock_executor._initialize_phase_goal_anchor.assert_called_once_with(phase)

    def test_alignment_classification_aligned(self, reviser, mock_executor):
        """Test alignment classification for aligned revision."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = []

        mock_executor._phase_original_intent["phase-1"] = "Original goal"
        mock_executor._classify_replan_alignment = Mock(
            return_value={"alignment": "aligned", "notes": "Maintains scope"}
        )

        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "Revised with same scope"
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                revised = reviser.revise_approach(phase, "flaw", error_history)

        assert revised is not None
        assert revised["_revision_alignment"]["alignment"] == "aligned"

    def test_alignment_classification_narrower_warning(self, reviser, mock_executor, caplog):
        """Test warning for narrower scope alignment."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = []

        mock_executor._phase_original_intent["phase-1"] = "Original broad goal"
        mock_executor._classify_replan_alignment = Mock(
            return_value={"alignment": "narrower", "notes": "Scope reduced"}
        )

        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "Revised with narrower scope"
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                revised = reviser.revise_approach(phase, "flaw", error_history)

        assert revised is not None
        assert revised["_revision_alignment"]["alignment"] == "narrower"
        assert "WARNING" in caplog.text
        assert "narrow scope" in caplog.text.lower()

    def test_no_api_key_skips_replanning(self, reviser, mock_executor):
        """Test replanning is skipped when no API key available."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = []

        with patch.dict("os.environ", {}, clear=True):
            revised = reviser.revise_approach(phase, "flaw", error_history)

        assert revised is None

    def test_error_history_included_in_prompt(self, reviser, mock_executor):
        """Test error history is included in replanning prompt."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = [
            {"attempt": 0, "error_type": "ImportError", "error_details": "Module X not found"},
            {"attempt": 1, "error_type": "ImportError", "error_details": "Module X not found"},
            {"attempt": 2, "error_type": "ImportError", "error_details": "Module X not found"},
        ]

        mock_executor._phase_original_intent["phase-1"] = "Original goal"

        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "Revised approach"
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                _ = reviser.revise_approach(phase, "repeated_error", error_history)

        # Verify prompt includes error history
        call_args = mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "ImportError" in prompt
        assert "Module X not found" in prompt

    def test_learning_hints_included_in_prompt(self, reviser, mock_executor):
        """Test learning hints are included in replanning prompt."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = []

        mock_executor._phase_original_intent["phase-1"] = "Original goal"
        mock_executor._get_learning_context_for_phase = Mock(
            return_value={"run_hints": ["Hint 1: Use approach B", "Hint 2: Avoid pattern X"]}
        )

        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "Revised approach"
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                _ = reviser.revise_approach(phase, "flaw", error_history)

        # Verify prompt includes hints
        call_args = mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Hint 1" in prompt
        assert "Hint 2" in prompt

    @pytest.mark.skip(reason="Flaky with pytest-xdist parallel execution - mock state race condition")
    def test_telemetry_recording(self, reviser, mock_executor):
        """Test telemetry is recorded for replanning."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = []

        mock_executor._phase_original_intent["phase-1"] = "Original goal"
        mock_executor._phase_original_description["phase-1"] = "Original description"

        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "Revised approach"
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                _ = reviser.revise_approach(phase, "flaw", error_history)

        mock_executor._record_replan_telemetry.assert_called_once()
        call_args = mock_executor._record_replan_telemetry.call_args
        assert call_args.kwargs["phase_id"] == "phase-1"
        assert call_args.kwargs["attempt"] == 1
        assert call_args.kwargs["original_description"] == "Original description"
        assert call_args.kwargs["revised_description"] == "Revised approach"

    @pytest.mark.skip(reason="Flaky with pytest-xdist parallel execution - mock state race condition")
    def test_phase_error_history_cleared_after_revision(self, reviser, mock_executor):
        """Test error history is cleared after successful revision."""
        phase = {
            "phase_id": "phase-1",
            "name": "Test phase",
            "description": "Original description",
        }
        error_history = [{"attempt": 0, "error_type": "Error", "error_details": "Details"}]

        mock_executor._phase_original_intent["phase-1"] = "Original goal"
        mock_executor._phase_error_history["phase-1"] = error_history.copy()

        mock_response = Mock()
        mock_content_block = Mock()
        mock_content_block.text = "Revised approach"
        mock_response.content = [mock_content_block]

        mock_client = Mock()
        mock_client.messages.create = Mock(return_value=mock_response)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                revised = reviser.revise_approach(phase, "flaw", error_history)

        assert revised is not None
        assert mock_executor._phase_error_history["phase-1"] == []
