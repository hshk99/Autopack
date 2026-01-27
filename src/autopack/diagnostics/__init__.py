"""
Diagnostics toolkit for governed troubleshooting.

Exposes:
- GovernedCommandRunner: safe command execution with budgets and redaction.
- ProbeLibrary: declarative probe sets keyed by failure class.
- DiagnosticsAgent: orchestrates probes, evidence capture, and hypothesis ledger.
"""

from .command_runner import CommandResult, GovernedCommandRunner
from .diagnostics_agent import DiagnosticOutcome, DiagnosticsAgent
from .hypothesis import Hypothesis, HypothesisLedger
from .probes import Probe, ProbeCommand, ProbeLibrary, ProbeRunResult

__all__ = [
    "CommandResult",
    "GovernedCommandRunner",
    "Probe",
    "ProbeCommand",
    "ProbeLibrary",
    "ProbeRunResult",
    "Hypothesis",
    "HypothesisLedger",
    "DiagnosticsAgent",
    "DiagnosticOutcome",
]
