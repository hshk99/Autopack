"""Tests for IMP-DIAG-002: Second Opinion System Integration with Diagnostics Pipeline

Tests that SecondOpinionTriageSystem is properly invoked from DiagnosticsAgent
when enable_second_opinion=True, and that results flow through to the
IterativeInvestigator's evidence dict for the GoalAwareDecisionMaker.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.diagnostics.command_runner import CommandResult
from autopack.diagnostics.diagnostics_agent import DiagnosticOutcome, DiagnosticsAgent
from autopack.diagnostics.diagnostics_models import DecisionType, PhaseSpec
from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker
from autopack.diagnostics.iterative_investigator import IterativeInvestigator
from autopack.diagnostics.second_opinion import (
    SecondOpinionConfig,
    SecondOpinionTriageSystem,
    TriageReport,
)


class _StubRunner:
    """Stub runner to avoid real subprocess calls in tests."""

    def __init__(self, diagnostics_dir: Path):
        self.diagnostics_dir = diagnostics_dir
        (self.diagnostics_dir / "commands").mkdir(parents=True, exist_ok=True)
        self.command_count = 0
        self.max_commands = 10

    def run(self, command: str, label=None, timeout=None, allow_network=False, sandbox=False):
        self.command_count += 1
        return CommandResult(
            command=command,
            redacted_command=command,
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_sec=0.1,
            timed_out=False,
            skipped=False,
            reason=None,
            artifact_path=str(self.diagnostics_dir / "commands" / f"{label or 'cmd'}.log"),
            label=label,
        )


class TestDiagnosticsAgentSecondOpinionIntegration:
    """Tests for DiagnosticsAgent + SecondOpinionTriageSystem integration."""

    def test_second_opinion_disabled_by_default(self, tmp_path: Path):
        """Test that second opinion is disabled by default."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
        )

        assert agent.enable_second_opinion is False
        assert agent.second_opinion is None

    def test_second_opinion_enabled_when_configured(self, tmp_path: Path):
        """Test that second opinion is created when enable_second_opinion=True."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
            enable_second_opinion=True,
        )

        assert agent.enable_second_opinion is True
        assert agent.second_opinion is not None
        assert isinstance(agent.second_opinion, SecondOpinionTriageSystem)
        assert agent.second_opinion.is_enabled() is True

    def test_run_diagnostics_without_second_opinion(self, tmp_path: Path):
        """Test that diagnostics runs without second opinion when disabled."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
            enable_second_opinion=False,
        )

        outcome = agent.run_diagnostics(
            failure_class="test_failure",
            context={"error_message": "Test error"},
        )

        assert outcome.second_opinion is None

    def test_run_diagnostics_with_second_opinion(self, tmp_path: Path):
        """Test that diagnostics includes second opinion when enabled."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
            enable_second_opinion=True,
        )

        outcome = agent.run_diagnostics(
            failure_class="test_failure",
            context={"error_message": "Test error"},
            phase_id="test-phase-001",
        )

        # Should have second opinion result
        assert outcome.second_opinion is not None
        assert isinstance(outcome.second_opinion, TriageReport)
        assert 0.0 <= outcome.second_opinion.confidence <= 1.0
        assert len(outcome.second_opinion.hypotheses) > 0

    def test_second_opinion_saved_to_file(self, tmp_path: Path):
        """Test that second opinion triage is persisted to file."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
            enable_second_opinion=True,
        )

        outcome = agent.run_diagnostics(
            failure_class="test_failure",
            context={"error_message": "Test error"},
        )

        # Should save second opinion to file
        second_opinion_path = diagnostics_dir / "second_opinion.json"
        assert second_opinion_path.exists()

    def test_diagnostic_outcome_has_second_opinion_field(self):
        """Test that DiagnosticOutcome includes second_opinion field."""
        # Create a mock triage report
        mock_report = TriageReport(
            hypotheses=[{"description": "Test hypothesis", "likelihood": 0.8}],
            missing_evidence=["Missing evidence 1"],
            next_probes=[{"type": "check", "description": "Test probe"}],
            minimal_patch_strategy={"approach": "Test strategy"},
            confidence=0.75,
            reasoning="Test reasoning",
        )

        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test summary",
            artifacts=[],
            second_opinion=mock_report,
        )

        assert outcome.second_opinion is not None
        assert outcome.second_opinion.confidence == 0.75


class TestIterativeInvestigatorSecondOpinionIntegration:
    """Tests for IterativeInvestigator + SecondOpinion evidence passing."""

    def test_evidence_includes_deep_retrieval_results(self, tmp_path: Path):
        """Test that evidence dict includes deep retrieval results."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        # Create mock diagnostics agent that returns deep retrieval results
        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
        )

        # Create mock decision maker
        decision_maker = MagicMock(spec=GoalAwareDecisionMaker)
        decision_maker.make_decision.return_value = MagicMock(
            type=DecisionType.CLEAR_FIX,
            fix_strategy="Test fix",
            rationale="Test rationale",
        )

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_agent=agent,
            decision_maker=decision_maker,
        )

        phase_spec = PhaseSpec(
            phase_id="test-phase",
            deliverables=["test.py"],
            acceptance_criteria=["Tests pass"],
            allowed_paths=["src/"],
            protected_paths=[],
            complexity="LOW",
            category="FIX_BUG",
        )

        failure_context = {
            "failure_class": "test_failure",
            "error_message": "Test error",
        }

        result = investigator.investigate_and_resolve(failure_context, phase_spec)

        # Check that decision maker was called with evidence
        assert decision_maker.make_decision.called
        evidence = decision_maker.make_decision.call_args[0][0]

        assert "failure_context" in evidence
        assert "phase_spec" in evidence
        assert "initial_diagnostics" in evidence

    def test_evidence_includes_second_opinion_when_available(self, tmp_path: Path):
        """Test that evidence dict includes second opinion when available."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        # Create diagnostics agent with second opinion enabled
        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
            enable_second_opinion=True,
        )

        # Create mock decision maker
        decision_maker = MagicMock(spec=GoalAwareDecisionMaker)
        decision_maker.make_decision.return_value = MagicMock(
            type=DecisionType.CLEAR_FIX,
            fix_strategy="Test fix",
            rationale="Test rationale",
        )

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_agent=agent,
            decision_maker=decision_maker,
        )

        phase_spec = PhaseSpec(
            phase_id="test-phase",
            deliverables=["test.py"],
            acceptance_criteria=["Tests pass"],
            allowed_paths=["src/"],
            protected_paths=[],
            complexity="LOW",
            category="FIX_BUG",
        )

        failure_context = {
            "failure_class": "test_failure",
            "error_message": "Test error",
        }

        result = investigator.investigate_and_resolve(failure_context, phase_spec)

        # Check that evidence includes second opinion
        evidence = decision_maker.make_decision.call_args[0][0]

        assert "second_opinion" in evidence
        assert evidence["second_opinion"]["confidence"] > 0
        assert "hypotheses" in evidence["second_opinion"]

    def test_timeline_includes_second_opinion_status(self, tmp_path: Path):
        """Test that investigation timeline mentions second opinion status."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
            enable_second_opinion=True,
        )

        decision_maker = MagicMock(spec=GoalAwareDecisionMaker)
        decision_maker.make_decision.return_value = MagicMock(
            type=DecisionType.CLEAR_FIX,
            fix_strategy="Test fix",
            rationale="Test rationale",
        )

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_agent=agent,
            decision_maker=decision_maker,
        )

        phase_spec = PhaseSpec(
            phase_id="test-phase",
            deliverables=["test.py"],
            acceptance_criteria=["Tests pass"],
            allowed_paths=["src/"],
            protected_paths=[],
            complexity="LOW",
            category="FIX_BUG",
        )

        failure_context = {
            "failure_class": "test_failure",
            "error_message": "Test error",
        }

        result = investigator.investigate_and_resolve(failure_context, phase_spec)

        # Timeline should mention second opinion
        timeline_text = " ".join(result.timeline)
        assert "second_opinion=yes" in timeline_text

    def test_outcome_to_dict_includes_second_opinion(self, tmp_path: Path):
        """Test that _outcome_to_dict includes second opinion data."""
        diagnostics_dir = tmp_path / "diag"
        runner = _StubRunner(diagnostics_dir)

        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_dir=diagnostics_dir,
            runner=runner,
            enable_second_opinion=True,
        )

        decision_maker = MagicMock(spec=GoalAwareDecisionMaker)

        investigator = IterativeInvestigator(
            run_id="test-run",
            workspace=tmp_path,
            diagnostics_agent=agent,
            decision_maker=decision_maker,
        )

        # Create outcome with second opinion
        mock_report = TriageReport(
            hypotheses=[{"description": "Test", "likelihood": 0.9}],
            missing_evidence=["Missing 1"],
            next_probes=[{"type": "check"}],
            minimal_patch_strategy={"approach": "Fix"},
            confidence=0.85,
            reasoning="Test reasoning",
        )

        outcome = DiagnosticOutcome(
            failure_class="test_failure",
            probe_results=[],
            ledger_summary="Test",
            artifacts=[],
            second_opinion=mock_report,
        )

        outcome_dict = investigator._outcome_to_dict(outcome)

        assert "second_opinion" in outcome_dict
        assert outcome_dict["second_opinion"]["confidence"] == 0.85
