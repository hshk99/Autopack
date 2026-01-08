"""Feature flag registry for Autopack.

Single source of truth for all AUTOPACK_ENABLE_* flags.
Each flag has documented defaults, risk classification, and scope.

Contract (P1-FLAGS-001):
- All AUTOPACK_ENABLE_* flags in code must be registered here
- Defaults match documented/desired posture by environment
- Tests validate code uses only registered flags
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RiskLevel(Enum):
    """Risk classification for feature flags."""

    SAFE = "safe"  # No external side effects, safe to enable
    CAUTION = "caution"  # May affect behavior, review before enabling
    EXTERNAL = "external"  # Has external side effects (API calls, DB writes)


class Scope(Enum):
    """Scope of effect for feature flags."""

    RUNTIME = "runtime"  # Affects runtime execution
    API = "api"  # Affects API endpoints
    TOOLING = "tooling"  # Affects tooling/scripts only
    METRICS = "metrics"  # Affects metrics collection


@dataclass(frozen=True)
class FeatureFlag:
    """Feature flag definition."""

    name: str
    default: bool
    description: str
    risk: RiskLevel
    scope: Scope
    doc_url: Optional[str] = None
    owner: str = "autopack-core"


# ============================================================================
# FEATURE FLAG REGISTRY
# ============================================================================

FEATURE_FLAGS: dict[str, FeatureFlag] = {
    # Metrics flags
    "AUTOPACK_ENABLE_PHASE6_METRICS": FeatureFlag(
        name="AUTOPACK_ENABLE_PHASE6_METRICS",
        default=False,
        description="Enable Phase 6 metrics collection and reporting",
        risk=RiskLevel.SAFE,
        scope=Scope.METRICS,
    ),
    "AUTOPACK_ENABLE_CONSOLIDATED_METRICS": FeatureFlag(
        name="AUTOPACK_ENABLE_CONSOLIDATED_METRICS",
        default=False,
        description="Enable consolidated metrics endpoint (/consolidated-metrics)",
        risk=RiskLevel.SAFE,
        scope=Scope.API,
    ),
    # Runtime behavior flags
    "AUTOPACK_ENABLE_FAILURE_HARDENING": FeatureFlag(
        name="AUTOPACK_ENABLE_FAILURE_HARDENING",
        default=False,
        description="Enable failure hardening logic in autonomous executor",
        risk=RiskLevel.CAUTION,
        scope=Scope.RUNTIME,
        doc_url="docs/PHASE6_FEATURES.md",
    ),
    "AUTOPACK_ENABLE_INTENTION_CONTEXT": FeatureFlag(
        name="AUTOPACK_ENABLE_INTENTION_CONTEXT",
        default=False,
        description="Enable intention context in prompts for better coherence",
        risk=RiskLevel.CAUTION,
        scope=Scope.RUNTIME,
    ),
    "AUTOPACK_ENABLE_PLAN_NORMALIZATION": FeatureFlag(
        name="AUTOPACK_ENABLE_PLAN_NORMALIZATION",
        default=False,
        description="Enable plan normalization for consistent execution",
        risk=RiskLevel.CAUTION,
        scope=Scope.RUNTIME,
    ),
    # Memory subsystem flags
    "AUTOPACK_ENABLE_MEMORY": FeatureFlag(
        name="AUTOPACK_ENABLE_MEMORY",
        default=False,
        description="Enable vector memory service (requires Qdrant)",
        risk=RiskLevel.EXTERNAL,
        scope=Scope.RUNTIME,
    ),
    "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": FeatureFlag(
        name="AUTOPACK_ENABLE_SOT_MEMORY_INDEXING",
        default=False,
        description="Enable SOT document memory indexing",
        risk=RiskLevel.EXTERNAL,
        scope=Scope.RUNTIME,
    ),
    # API feature flags
    "AUTOPACK_ENABLE_RESEARCH_API": FeatureFlag(
        name="AUTOPACK_ENABLE_RESEARCH_API",
        default=False,
        description="Enable /research/* API endpoints (uses mock in-memory state)",
        risk=RiskLevel.CAUTION,
        scope=Scope.API,
        doc_url="docs/FURTHER_IMPROVEMENTS_COMPREHENSIVE_SCAN_2026-01-08.md",
    ),
    # PR/governance flags
    "AUTOPACK_ENABLE_PR_APPROVAL": FeatureFlag(
        name="AUTOPACK_ENABLE_PR_APPROVAL",
        default=False,
        description="Enable PR approval pipeline for Telegram-based reviews",
        risk=RiskLevel.EXTERNAL,
        scope=Scope.RUNTIME,
    ),
}


def get_flag(name: str) -> Optional[FeatureFlag]:
    """Get a feature flag definition by name."""
    return FEATURE_FLAGS.get(name)


def is_enabled(name: str) -> bool:
    """Check if a feature flag is enabled.

    Uses environment variable, falling back to registered default.

    Args:
        name: Feature flag name (e.g., "AUTOPACK_ENABLE_PHASE6_METRICS")

    Returns:
        True if flag is enabled, False otherwise
    """
    flag = FEATURE_FLAGS.get(name)
    if not flag:
        # Unregistered flag - log warning and return False
        import logging

        logging.getLogger(__name__).warning(
            f"Unknown feature flag: {name}. Register in feature_flags.py"
        )
        return False

    # Check environment variable
    env_value = os.getenv(name, "").lower()
    if env_value in ("true", "1", "yes"):
        return True
    if env_value in ("false", "0", "no"):
        return False

    # Fall back to default
    return flag.default


def get_all_flags() -> dict[str, FeatureFlag]:
    """Get all registered feature flags."""
    return FEATURE_FLAGS.copy()


def get_production_posture() -> dict[str, bool]:
    """Get recommended production posture for all flags.

    Returns dict of flag_name -> recommended_value for production.
    """
    posture = {}
    for name, flag in FEATURE_FLAGS.items():
        # Most flags should be OFF in production unless explicitly enabled
        if flag.risk == RiskLevel.EXTERNAL:
            posture[name] = False  # External side effects - OFF by default
        elif flag.scope == Scope.API:
            posture[name] = False  # API changes - explicit opt-in
        else:
            posture[name] = flag.default
    return posture
