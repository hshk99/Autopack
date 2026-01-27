"""
Diagnostics agent that orchestrates probes, hypothesis tracking, and evidence capture.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

# IMP-LOOP-016: Import for telemetry bridge (TYPE_CHECKING to avoid circular imports)
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import yaml

from autopack.diagnostics.command_runner import CommandResult, GovernedCommandRunner
from autopack.diagnostics.deep_retrieval import DeepRetrieval, DeepRetrievalEngine
from autopack.diagnostics.hypothesis import HypothesisLedger
from autopack.diagnostics.probes import Probe, ProbeLibrary, ProbeRunResult
from autopack.diagnostics.retrieval_triggers import (
    RetrievalTrigger,
    RetrievalTriggerDetector,
)
from autopack.memory import MemoryService

if TYPE_CHECKING:
    from autopack.telemetry.analyzer import TelemetryAnalyzer


@dataclass
class DiagnosticOutcome:
    failure_class: str
    probe_results: List[ProbeRunResult]
    ledger_summary: str
    artifacts: List[str]
    budget_exhausted: bool = False
    deep_retrieval_triggered: bool = False
    deep_retrieval_results: Optional[Dict] = None


class DiagnosticsAgent:
    """
    Governed diagnostic orchestrator.

    Responsibilities:
    - Enforce probe and time budgets (1-at-a-time execution)
    - Run allowlisted commands through GovernedCommandRunner
    - Track hypotheses/evidence, emit summaries to DecisionLog + memory
    - Persist artifacts under .autonomous_runs/<run_id>/diagnostics
    """

    def __init__(
        self,
        run_id: str,
        workspace: Path,
        embedding_model: Optional[Any] = None,
        memory_service: Optional[MemoryService] = None,
        enable_second_opinion: bool = False,
        decision_logger: Optional[
            Callable[[str, str, str, Optional[str], Optional[str]], None]
        ] = None,
        diagnostics_dir: Optional[Path] = None,
        max_probes: int = 8,
        max_seconds: int = 300,
        runner: Optional[GovernedCommandRunner] = None,
        telemetry_analyzer: Optional["TelemetryAnalyzer"] = None,
    ) -> None:
        cfg = self._load_config()
        self.run_id = run_id
        self.workspace = workspace.resolve()
        self.embedding_model = embedding_model
        self.memory_service = memory_service
        self.enable_second_opinion = enable_second_opinion
        self.decision_logger = decision_logger
        self.max_probes = cfg.get("max_probes", max_probes)
        self.max_seconds = cfg.get("max_seconds", max_seconds)
        self._lock = threading.Lock()

        runner_cfg = {
            "max_commands": cfg.get("max_commands", 30),
            "max_seconds": self.max_seconds,
            "allowed_hosts": cfg.get("allowed_hosts", ["localhost", "127.0.0.1"]),
            "sandbox_paths": cfg.get("sandbox_paths", []),
        }

        self.runner = runner or GovernedCommandRunner(
            run_id=run_id,
            workspace=self.workspace,
            diagnostics_dir=diagnostics_dir,
            **runner_cfg,
        )
        self.diagnostics_dir = Path(self.runner.diagnostics_dir)
        self._baseline_logs: List[str] = cfg.get(
            "baseline_logs",
            [
                "logs/autopack/autonomous_executor.log",
                "logs/autopack/builder.log",
                "logs/autopack/auditor.log",
            ],
        )

        # Compatibility: Stage-2 engine hooks expected by BUILD-112 tests.
        self.trigger_detector = RetrievalTriggerDetector()
        self.deep_retrieval_engine = (
            DeepRetrievalEngine(embedding_model=embedding_model) if embedding_model else None
        )

        # IMP-LOOP-016: Telemetry analyzer for bridging diagnostic findings
        self.telemetry_analyzer = telemetry_analyzer

    def retrieve_deep_context_if_needed(
        self, error_context: Dict[str, Any], query: str
    ) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Test-facing helper: return deep context when trigger detector says to escalate."""
        if not self.deep_retrieval_engine:
            return None
        attempt_number = int(error_context.get("attempt_number", 1) or 1)
        previous_errors = error_context.get("errors", []) or []
        stage1_retrieval_count = int(error_context.get("stage1_retrieval_count", 0) or 0)

        if not self.trigger_detector.should_escalate_to_stage2(
            phase_id=str(error_context.get("phase_id", "unknown")),
            attempt_number=attempt_number,
            previous_errors=previous_errors,
            stage1_retrieval_count=stage1_retrieval_count,
        ):
            return None

        return self.deep_retrieval_engine.retrieve_deep_context(
            query=query,
            categories=["implementation", "tests", "config", "docs"],
            max_snippets_per_category=3,
            max_lines_per_snippet=120,
        )

    # ------------------------------------------------------------------ #
    # Public entrypoint
    # ------------------------------------------------------------------ #

    def run_diagnostics(
        self,
        failure_class: str,
        context: Optional[Dict] = None,
        phase_id: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> DiagnosticOutcome:
        if not self._lock.acquire(blocking=False):
            # Only one concurrent diagnostics run
            return DiagnosticOutcome(
                failure_class=failure_class,
                probe_results=[],
                ledger_summary="Diagnostics already running; skipping.",
                artifacts=[],
                budget_exhausted=True,
            )

        try:
            context = context or {}
            ledger = HypothesisLedger()
            ledger.new(f"Investigate {failure_class}", confidence=0.3)

            artifacts: List[str] = []
            probe_results: List[ProbeRunResult] = []
            start = time.monotonic()

            # Always collect baseline signals first
            baseline_results = self._collect_baseline_signals()
            for res in baseline_results:
                artifacts.append(res.artifact_path or "")
                ledger.items[0].add_evidence(
                    f"{res.label or res.command} -> exit {res.exit_code}, timed_out={res.timed_out}"
                )

            probes = ProbeLibrary.for_failure(failure_class, context)
            for probe in probes[: self.max_probes]:
                if time.monotonic() - start >= self.max_seconds:
                    break
                result = self._run_probe(probe)
                probe_results.append(result)
                artifacts.extend(
                    [r.artifact_path or "" for r in result.command_results if r.artifact_path]
                )
                evidence_line = self._summarize_probe_result(result)
                ledger.items[0].add_evidence(evidence_line)
                if result.resolved and probe.stop_on_success:
                    break

            ledger_summary = ledger.summarize()
            self._persist_summary(
                failure_class=failure_class,
                phase_id=phase_id,
                ledger_summary=ledger_summary,
                probe_results=probe_results,
                mode=mode,
            )

            # IMP-LOOP-016: Emit telemetry events for diagnostic findings
            self._emit_telemetry_events(
                failure_class=failure_class,
                phase_id=phase_id,
                probe_results=probe_results,
            )

            # Stage 2: Deep Retrieval Escalation (auto-triggered based on Stage 1 evidence)
            deep_retrieval_triggered = False
            deep_retrieval_results = None

            attempt_number = context.get("builder_attempts", 1)
            handoff_bundle = self._build_handoff_bundle(
                failure_class, phase_id, probe_results, ledger_summary, context
            )

            # Check if deep retrieval should be triggered
            try:
                retrieval_trigger = RetrievalTrigger(self.diagnostics_dir.parent)
                if retrieval_trigger.should_escalate(
                    handoff_bundle, phase_id or "unknown", attempt_number
                ):
                    priority = retrieval_trigger.get_retrieval_priority(handoff_bundle)
                    deep_retrieval = DeepRetrieval(
                        run_dir=self.diagnostics_dir.parent, repo_root=self.workspace
                    )
                    deep_retrieval_results = deep_retrieval.retrieve(
                        phase_id=phase_id or "unknown",
                        handoff_bundle=handoff_bundle,
                        priority=priority,
                    )
                    deep_retrieval_triggered = True

                    # Persist deep retrieval results
                    deep_retrieval_path = self.diagnostics_dir / "deep_retrieval.json"
                    deep_retrieval_path.write_text(
                        json.dumps(deep_retrieval_results, indent=2), encoding="utf-8"
                    )
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"[DiagnosticsAgent] Deep retrieval failed: {e}")

            return DiagnosticOutcome(
                failure_class=failure_class,
                probe_results=probe_results,
                ledger_summary=ledger_summary,
                artifacts=[a for a in artifacts if a],
                budget_exhausted=self.runner.command_count >= self.runner.max_commands
                or (time.monotonic() - start) >= self.max_seconds,
                deep_retrieval_triggered=deep_retrieval_triggered,
                deep_retrieval_results=deep_retrieval_results,
            )
        finally:
            self._lock.release()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _build_handoff_bundle(
        self,
        failure_class: str,
        phase_id: Optional[str],
        probe_results: List[ProbeRunResult],
        ledger_summary: str,
        context: Dict,
    ) -> Dict:
        """Build minimal handoff bundle for retrieval trigger analysis.

        Args:
            failure_class: Classification of failure
            phase_id: Phase identifier
            probe_results: Results from probe execution
            ledger_summary: Hypothesis ledger summary
            context: Additional context from caller

        Returns:
            Handoff bundle dictionary for trigger analysis
        """
        error_message = context.get("error_message", "")
        stack_trace = context.get("stack_trace", "")

        # Extract recent changes from baseline git status
        recent_changes = []
        for pr in probe_results:
            for cr in pr.command_results:
                if cr.label and "git" in cr.label and cr.stdout:
                    recent_changes.extend(cr.stdout.split("\n")[:10])

        # Determine if we have a clear root cause from probes
        root_cause = ""
        resolved_probes = [pr for pr in probe_results if pr.resolved]
        if resolved_probes:
            root_cause = f"Resolved by probe: {resolved_probes[0].probe.name}"
        elif ledger_summary and len(ledger_summary) > 50:
            root_cause = ledger_summary

        return {
            "failure_class": failure_class,
            "phase_id": phase_id,
            "error_message": error_message,
            "stack_trace": stack_trace,
            "recent_changes": recent_changes,
            "root_cause": root_cause,
            "ledger_summary": ledger_summary,
            "probe_count": len(probe_results),
            "resolved_probes": len(resolved_probes),
        }

    def _collect_baseline_signals(self) -> List[CommandResult]:
        commands = [
            ("git status --short", "baseline_git_status"),
            ("git diff --stat", "baseline_git_diff"),
            ("du -sh .", "baseline_disk_usage"),
            ("df -h .", "baseline_df"),
        ]
        # Only tail log files that actually exist
        for log_path in self._baseline_logs:
            full_path = self.workspace / log_path
            if full_path.exists():
                commands.append((f"tail -n 200 {log_path}", f"baseline_tail_{Path(log_path).stem}"))
        results: List[CommandResult] = []
        for cmd, label in commands:
            results.append(self.runner.run(cmd, label=label, sandbox=False))
        return results

    def _run_probe(self, probe: Probe) -> ProbeRunResult:
        results: List[CommandResult] = []
        resolved = False
        for cmd in probe.commands:
            res = self.runner.run(
                cmd.command,
                label=cmd.label,
                allow_network=cmd.allow_network,
                sandbox=cmd.sandbox,
            )
            results.append(res)
            if (
                not res.skipped
                and not res.timed_out
                and res.exit_code == 0
                and probe.stop_on_success
            ):
                resolved = True
                break
        return ProbeRunResult(probe=probe, command_results=results, resolved=resolved)

    def _summarize_probe_result(self, result: ProbeRunResult) -> str:
        exit_codes = [r.exit_code for r in result.command_results if not r.skipped]
        return (
            f"{result.probe.name}: exits={exit_codes or 'n/a'} "
            f"resolved={result.resolved} cmds={len(result.command_results)}"
        )

    def _persist_summary(
        self,
        failure_class: str,
        phase_id: Optional[str],
        ledger_summary: str,
        probe_results: List[ProbeRunResult],
        mode: Optional[str] = None,
    ) -> None:
        summary = {
            "failure_class": failure_class,
            "phase_id": phase_id,
            "mode": mode,
            "ledger": ledger_summary,
            "probes": [
                {
                    "name": pr.probe.name,
                    "commands": [cr.redacted_command for cr in pr.command_results],
                    "resolved": pr.resolved,
                }
                for pr in probe_results
            ],
            "timestamp": time.time(),
        }
        summary_path = self.diagnostics_dir / "diagnostic_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        rationale = f"Diagnostics for {failure_class}: {ledger_summary}"
        if self.decision_logger:
            self.decision_logger(
                "diagnostics",
                f"diagnostics:{failure_class}",
                rationale,
                phase_id,
                "diagnostics",
            )
        elif self.memory_service and self.memory_service.enabled:
            # Fall back to memory-only logging if DB decision logger is unavailable
            try:
                project_id = self.run_id
                self.memory_service.write_decision_log(
                    trigger="diagnostics",
                    choice=f"diagnostics:{failure_class}",
                    rationale=rationale,
                    project_id=project_id,
                    run_id=self.run_id,
                    phase_id=phase_id,
                )
            except Exception:
                # Best-effort; do not raise inside diagnostics path
                pass

    def _emit_telemetry_events(
        self,
        failure_class: str,
        phase_id: Optional[str],
        probe_results: List[ProbeRunResult],
    ) -> None:
        """Emit telemetry events for diagnostic findings (IMP-LOOP-016).

        Bridges diagnostic findings to the telemetry system for automatic
        task generation and tracking. This enables diagnostic-sourced issues
        to be processed through the same improvement pipeline as other
        telemetry-derived insights.

        Args:
            failure_class: Classification of the failure
            phase_id: Phase identifier if available
            probe_results: Results from probe execution
        """
        if not self.telemetry_analyzer:
            return

        if not probe_results:
            return

        try:
            # Import here to avoid circular imports at module load time
            from autopack.telemetry.analyzer import TelemetryAnalyzer

            # Convert probe results to findings format
            findings = TelemetryAnalyzer.convert_probe_results_to_findings(
                probe_results=probe_results,
                failure_class=failure_class,
            )

            # Ingest findings into telemetry system
            self.telemetry_analyzer.ingest_diagnostic_findings(
                findings=findings,
                run_id=self.run_id,
                phase_id=phase_id,
            )
        except Exception as e:
            # Best-effort: do not raise inside diagnostics path
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"[IMP-LOOP-016] Failed to emit telemetry events: {e}")

    def _load_config(self) -> Dict:
        """Load diagnostics config from config/diagnostics.yaml if present."""
        config_path = Path(__file__).parent.parent.parent / "config" / "diagnostics.yaml"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                return {}
        return {}
