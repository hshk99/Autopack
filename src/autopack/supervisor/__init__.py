"""Supervisor module - parallel run orchestration with policy gates (BUILD-179).

Public API exports:
    - ParallelRunSupervisor: orchestrates parallel autonomous run execution
    - SupervisorError: supervisor-specific errors
    - SupervisorResult: typed result for supervisor operations
    - run_parallel_supervised: library façade for CLI/programmatic use
"""

from .parallel_run_supervisor import (
    ParallelRunSupervisor,
    SupervisorError,
)
from .api import run_parallel_supervised, SupervisorResult

__all__ = [
    "ParallelRunSupervisor",
    "SupervisorError",
    "run_parallel_supervised",
    "SupervisorResult",
]
