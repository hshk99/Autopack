"""Iterative Autonomous Investigation

Implements multi-round evidence collection with goal-aware decision making.
Autopack iteratively runs probes, analyzes gaps, and collects evidence until
a decision can be made (auto-fix, escalate to human, or continue investigating).

Design Goals:
- Multi-round investigation (no human copy/paste)
- Evidence gap analysis (what's missing?)
- Targeted probe generation (fill gaps autonomously)
- Integration with goal-aware decision making
- Token-efficient (max 5 rounds, max 3 probes/round)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from autopack.diagnostics.diagnostics_agent import DiagnosticOutcome, DiagnosticsAgent
from autopack.diagnostics.diagnostics_models import (
    Decision,
    DecisionType,
    EvidenceGap,
    EvidenceGapType,
    InvestigationResult,
    PhaseSpec,
)
from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker
from autopack.diagnostics.probes import Probe, ProbeCommand, ProbeRunResult
from autopack.memory import MemoryService

logger = logging.getLogger(__name__)


class IterativeInvestigator:
    """
    Multi-round autonomous investigation orchestrator.

    Responsibilities:
    - Run initial diagnostics (DiagnosticsAgent)
    - Analyze evidence gaps
    - Generate targeted probes to fill gaps
    - Iteratively collect evidence (max 5 rounds)
    - Invoke goal-aware decision making when sufficient evidence
    - Return investigation result with decision or escalation
    """

    def __init__(
        self,
        run_id: str,
        workspace: Path,
        diagnostics_agent: DiagnosticsAgent,
        decision_maker: GoalAwareDecisionMaker,
        memory_service: Optional[MemoryService] = None,
        max_rounds: int = 5,
        max_probes_per_round: int = 3,
    ):
        """
        Initialize iterative investigator.

        Args:
            run_id: Run identifier
            workspace: Workspace root
            diagnostics_agent: Existing diagnostics agent for probe execution
            decision_maker: Goal-aware decision maker
            memory_service: Optional memory service for logging
            max_rounds: Maximum investigation rounds (default: 5)
            max_probes_per_round: Maximum probes per round (default: 3)
        """
        self.run_id = run_id
        self.workspace = workspace
        self.diagnostics_agent = diagnostics_agent
        self.decision_maker = decision_maker
        self.memory_service = memory_service
        self.max_rounds = max_rounds
        self.max_probes_per_round = max_probes_per_round

    def investigate_and_resolve(
        self, failure_context: Dict[str, Any], phase_spec: PhaseSpec
    ) -> InvestigationResult:
        """
        Multi-round investigation until resolved or escalation needed.

        Args:
            failure_context: Error details, stack trace, attempt number
            phase_spec: Deliverables, acceptance criteria, path constraints

        Returns:
            InvestigationResult with decision, evidence, audit trail
        """
        start_time = time.monotonic()
        timeline = []
        evidence = {
            "failure_context": failure_context,
            "phase_spec": self._phase_spec_to_dict(phase_spec),
        }
        all_probes: List[ProbeRunResult] = []
        all_gaps: List[EvidenceGap] = []

        logger.info(f"[IterativeInvestigator] Starting investigation for {phase_spec.phase_id}")
        timeline.append(f"Investigation started for {phase_spec.phase_id}")

        # Round 1: Initial diagnostics (standard probes + deep retrieval)
        logger.info("[IterativeInvestigator] Round 1: Initial diagnostics")
        timeline.append("Round 1: Initial diagnostics")

        initial_outcome = self.diagnostics_agent.run_diagnostics(
            failure_class=failure_context.get("failure_class", "unknown"),
            context=failure_context,
            phase_id=phase_spec.phase_id,
        )

        # Store initial evidence
        evidence["initial_diagnostics"] = self._outcome_to_dict(initial_outcome)
        all_probes.extend(initial_outcome.probe_results)

        # IMP-DIAG-002: Include deep retrieval results in evidence for decision maker
        # IMP-DIAG-004: Also extract memory_entries and similar_errors at top level
        if initial_outcome.deep_retrieval_results:
            evidence["deep_retrieval"] = initial_outcome.deep_retrieval_results

            # IMP-DIAG-004: Extract memory_entries for easier access by decision maker
            memory_entries = initial_outcome.deep_retrieval_results.get("memory_entries", [])
            if memory_entries:
                evidence["memory_entries"] = memory_entries
                # Extract similar_errors (memory entries from error collection)
                similar_errors = [e for e in memory_entries if e.get("source") == "memory:error"]
                if similar_errors:
                    evidence["similar_errors"] = similar_errors

            # Log retrieval statistics for debugging
            stats = initial_outcome.deep_retrieval_results.get("stats", {})
            total_entries = (
                stats.get("run_artifacts_count", 0)
                + stats.get("sot_files_count", 0)
                + stats.get("memory_entries_count", 0)
            )
            logger.debug(
                f"[IterativeInvestigator] Passing {total_entries} deep retrieval entries "
                f"to decision maker (memory_entries={len(memory_entries)}, "
                f"similar_errors={len(evidence.get('similar_errors', []))})"
            )

        # IMP-DIAG-002: Include second opinion triage in evidence for decision maker
        if initial_outcome.second_opinion:
            evidence["second_opinion"] = initial_outcome.second_opinion.to_dict()
            logger.debug(
                f"[IterativeInvestigator] Passing second opinion triage "
                f"(confidence: {initial_outcome.second_opinion.confidence:.2f}) to decision maker"
            )

        timeline.append(
            f"Round 1 complete: {len(initial_outcome.probe_results)} probes, "
            f"deep_retrieval={'yes' if initial_outcome.deep_retrieval_triggered else 'no'}, "
            f"second_opinion={'yes' if initial_outcome.second_opinion else 'no'}"
        )

        # Analyze evidence and decide if we can proceed
        decision = self.decision_maker.make_decision(evidence, phase_spec)

        if decision.type in [DecisionType.CLEAR_FIX, DecisionType.RISKY, DecisionType.AMBIGUOUS]:
            # Sufficient evidence to make a decision
            logger.info(f"[IterativeInvestigator] Decision after round 1: {decision.type.value}")
            timeline.append(f"Decision: {decision.type.value} (sufficient evidence)")

            return InvestigationResult(
                decision=decision,
                evidence=evidence,
                rounds=1,
                probes_executed=all_probes,
                timeline=timeline,
                total_time_seconds=time.monotonic() - start_time,
                gaps_identified=all_gaps,
            )

        # Need more evidence - continue investigation
        round_num = 2
        while round_num <= self.max_rounds:
            logger.info(f"[IterativeInvestigator] Round {round_num}: Analyzing evidence gaps")
            timeline.append(f"Round {round_num}: Analyzing evidence gaps")

            # Identify what's missing
            gaps = self._analyze_evidence_gaps(evidence, failure_context, phase_spec)
            all_gaps.extend(gaps)

            if not gaps:
                # No more gaps identified, but still NEED_MORE_EVIDENCE
                # This means we've collected all obvious evidence but root cause unclear
                logger.info("[IterativeInvestigator] No more evidence gaps, escalating")
                timeline.append("No more evidence gaps identified - escalating to human")

                decision = Decision(
                    type=DecisionType.AMBIGUOUS,
                    fix_strategy="",
                    rationale=f"After {round_num - 1} investigation rounds, root cause remains unclear. "
                    f"All standard evidence collected but no clear fix identified.",
                    alternatives_considered=[
                        "Continue investigation (rejected: no more obvious evidence to collect)",
                        "Auto-fix anyway (rejected: risk of incorrect fix)",
                        "Escalate to human (selected: requires human judgment)",
                    ],
                    risk_level="UNKNOWN",
                    deliverables_met=[],
                    files_modified=[],
                    net_deletion=0,
                    questions_for_human=[
                        "What is the root cause of this failure?",
                        "Which approach should be taken to fix it?",
                        "Are there any additional constraints or requirements?",
                    ],
                )

                return InvestigationResult(
                    decision=decision,
                    evidence=evidence,
                    rounds=round_num - 1,
                    probes_executed=all_probes,
                    timeline=timeline,
                    total_time_seconds=time.monotonic() - start_time,
                    gaps_identified=all_gaps,
                )

            # Generate targeted probes to fill gaps
            targeted_probes = self._generate_targeted_probes(gaps)
            timeline.append(f"Round {round_num}: Generated {len(targeted_probes)} targeted probes")

            # Execute probes (limited to max_probes_per_round)
            probes_to_run = targeted_probes[: self.max_probes_per_round]
            logger.info(
                f"[IterativeInvestigator] Round {round_num}: Running {len(probes_to_run)} probes"
            )

            for probe in probes_to_run:
                probe_result = self.diagnostics_agent._run_probe(probe)
                all_probes.append(probe_result)

                # Update evidence with probe results
                probe_key = f"round_{round_num}_{probe.name}"
                evidence[probe_key] = {
                    "probe": probe.name,
                    "results": [
                        {
                            "command": cr.redacted_command,
                            "exit_code": cr.exit_code,
                            "stdout_preview": cr.stdout[:500] if cr.stdout else "",
                            "stderr_preview": cr.stderr[:500] if cr.stderr else "",
                        }
                        for cr in probe_result.command_results
                    ],
                    "resolved": probe_result.resolved,
                }

            timeline.append(f"Round {round_num} complete: {len(probes_to_run)} probes executed")

            # Re-evaluate with new evidence
            decision = self.decision_maker.make_decision(evidence, phase_spec)

            if decision.type != DecisionType.NEED_MORE_EVIDENCE:
                # Sufficient evidence now
                logger.info(
                    f"[IterativeInvestigator] Decision after round {round_num}: {decision.type.value}"
                )
                timeline.append(f"Decision: {decision.type.value} (sufficient evidence)")

                return InvestigationResult(
                    decision=decision,
                    evidence=evidence,
                    rounds=round_num,
                    probes_executed=all_probes,
                    timeline=timeline,
                    total_time_seconds=time.monotonic() - start_time,
                    gaps_identified=all_gaps,
                )

            round_num += 1

        # Max rounds reached - escalate
        logger.warning(
            f"[IterativeInvestigator] Max rounds ({self.max_rounds}) reached, escalating"
        )
        timeline.append(f"Max rounds ({self.max_rounds}) reached - escalating to human")

        decision = Decision(
            type=DecisionType.AMBIGUOUS,
            fix_strategy="",
            rationale=f"Investigation reached maximum {self.max_rounds} rounds without clear resolution. "
            f"Collected {len(all_probes)} probe results across {len(all_gaps)} evidence gaps.",
            alternatives_considered=[
                "Continue investigation (rejected: max rounds reached)",
                "Auto-fix anyway (rejected: insufficient evidence for safe fix)",
                "Escalate to human (selected: complex failure requiring human judgment)",
            ],
            risk_level="UNKNOWN",
            deliverables_met=[],
            files_modified=[],
            net_deletion=0,
            questions_for_human=[
                f"Investigation collected {len(all_probes)} probe results - what is the root cause?",
                "What approach should be taken to resolve this failure?",
                "Are there additional evidence sources to check?",
            ],
        )

        return InvestigationResult(
            decision=decision,
            evidence=evidence,
            rounds=self.max_rounds,
            probes_executed=all_probes,
            timeline=timeline,
            total_time_seconds=time.monotonic() - start_time,
            gaps_identified=all_gaps,
        )

    def _analyze_evidence_gaps(
        self, evidence: Dict[str, Any], failure_context: Dict[str, Any], phase_spec: PhaseSpec
    ) -> List[EvidenceGap]:
        """
        Identify what evidence is missing.

        Strategy:
        - Check for common failure patterns and their required evidence
        - Analyze existing evidence for hints about what's needed
        - Prioritize gaps based on failure type and context

        Returns:
            List of evidence gaps, sorted by priority
        """
        gaps: List[EvidenceGap] = []
        failure_class = failure_context.get("failure_class", "unknown").lower()
        error_message = failure_context.get("error_message", "")

        # Gap 1: Missing test output for test failures
        if "test" in failure_class or "ci_fail" in failure_class:
            has_test_output = any(
                "pytest" in str(evidence.get(key, "")) or "test" in str(evidence.get(key, ""))
                for key in evidence.keys()
            )
            if not has_test_output:
                gaps.append(
                    EvidenceGap(
                        gap_type=EvidenceGapType.MISSING_TEST_OUTPUT,
                        description="Missing pytest output for test failure",
                        priority=1,
                        probe_suggestion=ProbeCommand(
                            "pytest -v --tb=short", label="pytest_detailed_output"
                        ),
                        rationale="Test failures require full pytest output to identify root cause",
                    )
                )

        # Gap 2: Missing file content for import errors
        if (
            "import" in failure_class
            or "ImportError" in error_message
            or "ModuleNotFoundError" in error_message
        ):
            # Try to extract module name from error message
            has_file_content = any(
                "file_content" in str(key) or "read_file" in str(key) for key in evidence.keys()
            )
            if not has_file_content:
                gaps.append(
                    EvidenceGap(
                        gap_type=EvidenceGapType.MISSING_FILE_CONTENT,
                        description="Missing __init__.py or module file content",
                        priority=1,
                        rationale="Import errors often caused by missing imports in __init__.py",
                    )
                )

        # Gap 3: Missing dependency information
        if (
            "dependency" in failure_class
            or "pip" in error_message
            or "package" in error_message.lower()
        ):
            has_pip_info = any("pip" in str(evidence.get(key, "")) for key in evidence.keys())
            if not has_pip_info:
                gaps.append(
                    EvidenceGap(
                        gap_type=EvidenceGapType.MISSING_DEPENDENCY_INFO,
                        description="Missing pip list or dependency information",
                        priority=2,
                        probe_suggestion=ProbeCommand(
                            "pip list --format=columns", label="pip_list_full"
                        ),
                        rationale="Dependency issues require full package list",
                    )
                )

        # Gap 4: Missing patch/diff context for patch failures
        if "patch" in failure_class or "git apply" in error_message:
            has_git_state = any("git" in str(evidence.get(key, "")) for key in evidence.keys())
            if not has_git_state:
                gaps.append(
                    EvidenceGap(
                        gap_type=EvidenceGapType.MISSING_COMMAND_OUTPUT,
                        description="Missing git status and diff output",
                        priority=1,
                        probe_suggestion=ProbeCommand("git diff --stat", label="git_diff_detailed"),
                        rationale="Patch failures require current git state",
                    )
                )

        # Gap 5: Missing error details
        if not error_message or len(error_message) < 50:
            gaps.append(
                EvidenceGap(
                    gap_type=EvidenceGapType.MISSING_ERROR_DETAILS,
                    description="Error message too short or missing",
                    priority=1,
                    rationale="Need full error traceback for root cause analysis",
                )
            )

        # Sort by priority (critical first)
        gaps.sort(key=lambda g: g.priority)

        logger.info(f"[IterativeInvestigator] Identified {len(gaps)} evidence gaps")
        return gaps

    def _generate_targeted_probes(self, gaps: List[EvidenceGap]) -> List[Probe]:
        """
        Convert evidence gaps into executable probes.

        Returns:
            List of probes to fill gaps
        """
        probes: List[Probe] = []

        for gap in gaps:
            if gap.probe_suggestion:
                # Use suggested probe
                probe = Probe(
                    name=f"gap_fill_{gap.gap_type.value}",
                    description=gap.description,
                    commands=[gap.probe_suggestion],
                    stop_on_success=False,
                )
                probes.append(probe)

            elif gap.gap_type == EvidenceGapType.MISSING_FILE_CONTENT:
                # Generate file read probes for common locations
                probe = Probe(
                    name="read_init_files",
                    description="Read __init__.py files for import investigation",
                    commands=[
                        ProbeCommand(
                            "find . -name '__init__.py' -type f | head -5", label="find_init_files"
                        ),
                    ],
                    stop_on_success=False,
                )
                probes.append(probe)

            elif gap.gap_type == EvidenceGapType.MISSING_TEST_OUTPUT:
                # Generate pytest probe
                probe = Probe(
                    name="run_tests",
                    description="Run tests to capture failure details",
                    commands=[
                        ProbeCommand("pytest -v --tb=short -x", label="pytest_first_failure"),
                    ],
                    stop_on_success=False,
                )
                probes.append(probe)

        logger.info(
            f"[IterativeInvestigator] Generated {len(probes)} targeted probes from {len(gaps)} gaps"
        )
        return probes

    def _phase_spec_to_dict(self, spec: PhaseSpec) -> Dict[str, Any]:
        """Convert PhaseSpec to dictionary for evidence storage."""
        return {
            "phase_id": spec.phase_id,
            "deliverables": spec.deliverables,
            "acceptance_criteria": spec.acceptance_criteria,
            "allowed_paths": spec.allowed_paths,
            "protected_paths": spec.protected_paths,
            "complexity": spec.complexity,
            "category": spec.category,
        }

    def _outcome_to_dict(self, outcome: DiagnosticOutcome) -> Dict[str, Any]:
        """Convert DiagnosticOutcome to dictionary for evidence storage."""
        result = {
            "failure_class": outcome.failure_class,
            "probe_count": len(outcome.probe_results),
            "ledger_summary": outcome.ledger_summary,
            "artifacts": outcome.artifacts,
            "budget_exhausted": outcome.budget_exhausted,
            "deep_retrieval_triggered": outcome.deep_retrieval_triggered,
        }

        # IMP-DIAG-002: Include deep retrieval results if available
        # IMP-DIAG-004: Also extract memory_entries and similar_errors at top level
        if outcome.deep_retrieval_results:
            result["deep_retrieval_results"] = outcome.deep_retrieval_results
            # Extract memory entries for easier access
            memory_entries = outcome.deep_retrieval_results.get("memory_entries", [])
            if memory_entries:
                result["memory_entries"] = memory_entries
                # Extract similar errors (memory entries from error collection)
                result["similar_errors"] = [
                    e for e in memory_entries if e.get("source") == "memory:error"
                ]

        # IMP-DIAG-002: Include second opinion if available
        if outcome.second_opinion:
            result["second_opinion"] = outcome.second_opinion.to_dict()

        return result
