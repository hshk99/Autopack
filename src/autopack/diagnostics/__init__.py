"""
Diagnostics toolkit for governed troubleshooting.

Exposes:
- GovernedCommandRunner: safe command execution with budgets and redaction.
- ProbeLibrary: declarative probe sets keyed by failure class.
- DiagnosticsAgent: orchestrates probes, evidence capture, and hypothesis ledger.
"""

from .command_runner import GovernedCommandRunner, CommandResult
from .probes import ProbeLibrary, Probe, ProbeCommand, ProbeRunResult
from .hypothesis import Hypothesis, HypothesisLedger
from .diagnostics_agent import DiagnosticsAgent, DiagnosticOutcome

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

