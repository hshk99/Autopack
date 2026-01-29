"""Autonomy module - autopilot controller with safe execution gates.

Public API exports:
    - AutopilotSession: autopilot session schema
    - AutopilotController: autonomous execution controller
    - run_autopilot_session: execute autopilot session
    - ParallelismPolicyGate: parallelism policy enforcement
    - ParallelismPolicyViolation: raised when parallel execution blocked
    - run_autopilot: library façade for CLI/programmatic use (BUILD-179)
    - load_anchor: load intention anchor for a run (BUILD-179)
    - AutopilotResult: result type for run_autopilot
"""

from .api import AutopilotResult, load_anchor, run_autopilot
from .autopilot import AutopilotController, run_autopilot_session
from .models import AutopilotSessionV1
from .parallelism_gate import (
    ParallelismPolicyGate,
    ParallelismPolicyViolation,
    check_parallelism_policy,
    load_and_check_parallelism_policy,
)

__all__ = [
    "AutopilotSessionV1",
    "AutopilotController",
    "run_autopilot_session",
    "ParallelismPolicyGate",
    "ParallelismPolicyViolation",
    "check_parallelism_policy",
    "load_and_check_parallelism_policy",
    # Library API (BUILD-179)
    "run_autopilot",
    "load_anchor",
    "AutopilotResult",
]
