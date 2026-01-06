"""Autonomy module - autopilot controller with safe execution gates.

Public API exports:
    - AutopilotSession: autopilot session schema
    - AutopilotController: autonomous execution controller
    - run_autopilot_session: execute autopilot session
    - ParallelismPolicyGate: parallelism policy enforcement
    - ParallelismPolicyViolation: raised when parallel execution blocked
"""

from .models import AutopilotSessionV1
from .autopilot import AutopilotController, run_autopilot_session
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
]
