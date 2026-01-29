"""Tests for IMP-DIAG-004: Deep Retrieval Results Passthrough to Decision Maker.

Tests cover:
- Deep retrieval results are passed to evidence dict
- memory_entries are extracted at top level
- similar_errors are extracted from memory_entries with source='memory:error'
- Logging includes correct statistics
- _outcome_to_dict includes memory_entries and similar_errors
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from autopack.diagnostics.diagnostics_agent import DiagnosticOutcome
from autopack.diagnostics.diagnostics_models import DecisionType, PhaseSpec
from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker
from autopack.diagnostics.iterative_investigator import IterativeInvestigator


class TestDeepRetrievalPassthrough:
    """Tests for deep retrieval passthrough to decision maker (IMP-DIAG-004)."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        """Create a temporary workspace."""
        return tmp_path

    @pytest.fixture
    def mock_diagnostics_agent(self) -> Mock:
        """Create a mock diagnostics agent."""
        agent = Mock()
        return agent

    @pytest.fixture
    def mock_decision_maker(self) -> Mock:
        """Create a mock decision maker that returns CLEAR_FIX."""
        maker = Mock(spec=GoalAwareDecisionMaker)
        decision = Mock()
        decision.type = DecisionType.CLEAR_FIX
        maker.make_decision.return_value = decision
        return maker

    @pytest.fixture
    def sample_phase_spec(self) -> PhaseSpec:
        """Create a sample PhaseSpec for testing."""
        return PhaseSpec(
            phase_id="test-phase",
            deliverables=["fix_bug"],
            acceptance_criteria=["tests pass"],
            allowed_paths=["src/"],
            protected_paths=[".git/"],
            complexity="low",
            category="bugfix",
        )

    @pytest.fixture
    def sample_deep_retrieval_results(self) -> dict:
        """Create sample deep retrieval results with memory entries."""
        return {
            "phase_id": "test-phase",
            "timestamp": "2025-01-29T12:00:00",
            "priority": "high",
            "run_artifacts": [{"path": "run.log", "content": "log content", "size": 11}],
            "sot_files": [{"path": "src/module.py", "content": "code", "size": 4}],
            "memory_entries": [
                {
                    "source": "memory:error",
                    "content": "Previous KeyError in module.py",
                    "size": 30,
                    "relevance_score": 0.95,
                    "metadata": {"collection": "errors", "id": "err-1"},
                },
                {
                    "source": "memory:error",
                    "content": "Another similar error",
                    "size": 21,
                    "relevance_score": 0.85,
                    "metadata": {"collection": "errors", "id": "err-2"},
                },
                {
                    "source": "memory:pattern",
                    "content": "def handle_error(): pass",
                    "size": 25,
                    "relevance_score": 0.80,
                    "metadata": {"collection": "code", "id": "code-1"},
                },
            ],
            "stats": {
                "run_artifacts_count": 1,
                "run_artifacts_size": 11,
                "sot_files_count": 1,
                "sot_files_size": 4,
                "memory_entries_count": 3,
                "memory_entries_size": 76,
            },
        }

    def test_deep_retrieval_passed_to_evidence(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
        sample_phase_spec: PhaseSpec,
        sample_deep_retrieval_results: dict,
    ) -> None:
        """Test that deep retrieval results are included in evidence dict."""
        # Configure mock outcome with deep retrieval
        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=True,
            deep_retrieval_results=sample_deep_retrieval_results,
        )
        mock_diagnostics_agent.run_diagnostics.return_value = outcome

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        result = investigator.investigate_and_resolve(
            failure_context={"failure_class": "test"},
            phase_spec=sample_phase_spec,
        )

        # Verify deep_retrieval is in evidence
        assert "deep_retrieval" in result.evidence
        assert result.evidence["deep_retrieval"] == sample_deep_retrieval_results

    def test_memory_entries_extracted_at_top_level(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
        sample_phase_spec: PhaseSpec,
        sample_deep_retrieval_results: dict,
    ) -> None:
        """Test that memory_entries are extracted as top-level evidence key."""
        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=True,
            deep_retrieval_results=sample_deep_retrieval_results,
        )
        mock_diagnostics_agent.run_diagnostics.return_value = outcome

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        result = investigator.investigate_and_resolve(
            failure_context={"failure_class": "test"},
            phase_spec=sample_phase_spec,
        )

        # Verify memory_entries is at top level
        assert "memory_entries" in result.evidence
        assert len(result.evidence["memory_entries"]) == 3

    def test_similar_errors_extracted_from_memory_entries(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
        sample_phase_spec: PhaseSpec,
        sample_deep_retrieval_results: dict,
    ) -> None:
        """Test that similar_errors contains only memory:error entries."""
        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=True,
            deep_retrieval_results=sample_deep_retrieval_results,
        )
        mock_diagnostics_agent.run_diagnostics.return_value = outcome

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        result = investigator.investigate_and_resolve(
            failure_context={"failure_class": "test"},
            phase_spec=sample_phase_spec,
        )

        # Verify similar_errors only contains error entries
        assert "similar_errors" in result.evidence
        assert len(result.evidence["similar_errors"]) == 2
        for entry in result.evidence["similar_errors"]:
            assert entry["source"] == "memory:error"

    def test_no_memory_entries_no_top_level_keys(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
        sample_phase_spec: PhaseSpec,
    ) -> None:
        """Test that no memory_entries/similar_errors added when empty."""
        deep_retrieval_results = {
            "phase_id": "test-phase",
            "memory_entries": [],
            "run_artifacts": [],
            "sot_files": [],
            "stats": {
                "run_artifacts_count": 0,
                "sot_files_count": 0,
                "memory_entries_count": 0,
            },
        }

        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=True,
            deep_retrieval_results=deep_retrieval_results,
        )
        mock_diagnostics_agent.run_diagnostics.return_value = outcome

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        result = investigator.investigate_and_resolve(
            failure_context={"failure_class": "test"},
            phase_spec=sample_phase_spec,
        )

        # memory_entries should not be added when empty
        assert "memory_entries" not in result.evidence
        assert "similar_errors" not in result.evidence

    def test_no_deep_retrieval_no_extraction(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
        sample_phase_spec: PhaseSpec,
    ) -> None:
        """Test that no extraction happens when deep_retrieval_results is None."""
        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=False,
            deep_retrieval_results=None,
        )
        mock_diagnostics_agent.run_diagnostics.return_value = outcome

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        result = investigator.investigate_and_resolve(
            failure_context={"failure_class": "test"},
            phase_spec=sample_phase_spec,
        )

        # No deep retrieval keys should be present
        assert "deep_retrieval" not in result.evidence
        assert "memory_entries" not in result.evidence
        assert "similar_errors" not in result.evidence

    def test_outcome_to_dict_includes_memory_entries(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
        sample_deep_retrieval_results: dict,
    ) -> None:
        """Test that _outcome_to_dict includes memory_entries and similar_errors."""
        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=True,
            deep_retrieval_results=sample_deep_retrieval_results,
        )

        result = investigator._outcome_to_dict(outcome)

        # Check memory_entries and similar_errors are in dict
        assert "memory_entries" in result
        assert len(result["memory_entries"]) == 3
        assert "similar_errors" in result
        assert len(result["similar_errors"]) == 2
        for entry in result["similar_errors"]:
            assert entry["source"] == "memory:error"

    def test_outcome_to_dict_no_memory_entries(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
    ) -> None:
        """Test _outcome_to_dict when deep_retrieval_results is None."""
        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=False,
            deep_retrieval_results=None,
        )

        result = investigator._outcome_to_dict(outcome)

        # Should not have memory_entries or similar_errors
        assert "memory_entries" not in result
        assert "similar_errors" not in result

    def test_only_pattern_entries_no_similar_errors(
        self,
        workspace: Path,
        mock_diagnostics_agent: Mock,
        mock_decision_maker: Mock,
        sample_phase_spec: PhaseSpec,
    ) -> None:
        """Test that similar_errors is not added when only pattern entries exist."""
        deep_retrieval_results = {
            "phase_id": "test-phase",
            "memory_entries": [
                {
                    "source": "memory:pattern",
                    "content": "Code pattern",
                    "size": 12,
                    "relevance_score": 0.80,
                },
            ],
            "run_artifacts": [],
            "sot_files": [],
            "stats": {
                "run_artifacts_count": 0,
                "sot_files_count": 0,
                "memory_entries_count": 1,
            },
        }

        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            deep_retrieval_triggered=True,
            deep_retrieval_results=deep_retrieval_results,
        )
        mock_diagnostics_agent.run_diagnostics.return_value = outcome

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=workspace,
            diagnostics_agent=mock_diagnostics_agent,
            decision_maker=mock_decision_maker,
        )

        result = investigator.investigate_and_resolve(
            failure_context={"failure_class": "test"},
            phase_spec=sample_phase_spec,
        )

        # memory_entries should exist but similar_errors should not
        assert "memory_entries" in result.evidence
        assert len(result.evidence["memory_entries"]) == 1
        assert "similar_errors" not in result.evidence
