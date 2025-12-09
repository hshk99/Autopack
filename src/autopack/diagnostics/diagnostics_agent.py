"""
Diagnostics agent that orchestrates probes, hypothesis tracking, and evidence capture.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import yaml

from autopack.diagnostics.command_runner import CommandResult, GovernedCommandRunner
from autopack.diagnostics.hypothesis import HypothesisLedger
from autopack.diagnostics.probes import Probe, ProbeLibrary, ProbeRunResult
from autopack.memory import MemoryService


@dataclass
class DiagnosticOutcome:
    failure_class: str
    probe_results: List[ProbeRunResult]
    ledger_summary: str
    artifacts: List[str]
    budget_exhausted: bool = False


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
        memory_service: Optional[MemoryService] = None,
        decision_logger: Optional[Callable[[str, str, str, Optional[str], Optional[str]], None]] = None,
        diagnostics_dir: Optional[Path] = None,
        max_probes: int = 8,
        max_seconds: int = 300,
        runner: Optional[GovernedCommandRunner] = None,
    ) -> None:
        cfg = self._load_config()
        self.run_id = run_id
        self.workspace = workspace.resolve()
        self.memory_service = memory_service
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
                artifacts.extend([r.artifact_path or "" for r in result.command_results if r.artifact_path])
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

            return DiagnosticOutcome(
                failure_class=failure_class,
                probe_results=probe_results,
                ledger_summary=ledger_summary,
                artifacts=[a for a in artifacts if a],
                budget_exhausted=self.runner.command_count >= self.runner.max_commands
                or (time.monotonic() - start) >= self.max_seconds,
            )
        finally:
            self._lock.release()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _collect_baseline_signals(self) -> List[CommandResult]:
        commands = [
            ("git status --short", "baseline_git_status"),
            ("git diff --stat", "baseline_git_diff"),
            ("du -sh .", "baseline_disk_usage"),
            ("df -h .", "baseline_df"),
        ]
        for log_path in self._baseline_logs:
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
            if not res.skipped and not res.timed_out and res.exit_code == 0 and probe.stop_on_success:
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

