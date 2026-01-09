"""Executor convergence modules (BUILD-181).

This package contains modules for executor convergence improvements:
- usage_accounting: Real usage event aggregation for stuck handling
- safety_profile: Deterministic safety profile derivation from IntentionAnchorV2
- scope_reduction_flow: Proposal-only scope reduction with schema validation
- patch_correction: One-shot 422 correction with evidence recording
- coverage_metrics: Coverage delta handling (None when unknown)
- state_persistence: Durable state for crash recovery (BUILD-041)
"""

from .usage_accounting import (
    UsageEvent,
    UsageTotals,
    aggregate_usage,
    load_usage_events,
)
from .safety_profile import derive_safety_profile
from .coverage_metrics import (
    CoverageInfo,
    compute_coverage_delta,
    compute_coverage_info,
    get_coverage_status,
)
from .state_persistence import (
    PhaseStatus,
    AttemptRecord,
    PhaseState,
    ExecutorState,
    ExecutorStateManager,
)

__all__ = [
    "UsageEvent",
    "UsageTotals",
    "aggregate_usage",
    "load_usage_events",
    "derive_safety_profile",
    "CoverageInfo",
    "compute_coverage_delta",
    "compute_coverage_info",
    "get_coverage_status",
    # State persistence (BUILD-041)
    "PhaseStatus",
    "AttemptRecord",
    "PhaseState",
    "ExecutorState",
    "ExecutorStateManager",
]
