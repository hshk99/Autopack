"""Feature Quarantine/Enablement API for IMP-REL-001.

Provides runtime feature toggle management with:
- Centralized feature gate registry
- Environment variable-based kill switches (default: OFF)
- Runtime feature state queries and updates
- Graceful degradation helpers
- Kill switch states tracking

Usage:
    # Enable a feature via environment variable
    os.environ["AUTOPACK_ENABLE_RESEARCH_CYCLE"] = "1"

    # Check if feature is enabled
    if is_feature_enabled("research_cycle_triggering"):
        # Feature is enabled, proceed with research cycle

    # Get all feature states
    states = get_feature_states()

    # Graceful degradation
    try:
        result = expensive_operation()
    except FeatureDisabledError:
        result = fallback_operation()
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class FeatureDisabledError(Exception):
    """Raised when a disabled feature is accessed without graceful degradation."""

    pass


@dataclass
class FeatureInfo:
    """Feature gate configuration and status."""

    feature_id: str
    name: str
    enabled: bool
    wave: str
    imp_id: str
    description: str
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    kill_switch_env: str
    requires: Optional[list] = None  # List of feature IDs this depends on


# Feature gate registry with all Wave 4 and prior features
FEATURE_REGISTRY = {
    # Phase 6 & Earlier Features (Pre-Wave 4)
    "phase6_metrics": FeatureInfo(
        feature_id="phase6_metrics",
        name="Phase 6 Telemetry Collection",
        enabled=os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") == "1",
        wave="pre-wave4",
        imp_id="PHASE-6",
        description="Token and performance telemetry tracking for Phase 6",
        risk_level="LOW",
        kill_switch_env="AUTOPACK_ENABLE_PHASE6_METRICS",
    ),
    "consolidated_metrics": FeatureInfo(
        feature_id="consolidated_metrics",
        name="Consolidated Metrics Dashboard",
        enabled=os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1",
        wave="pre-wave4",
        imp_id="PHASE-6",
        description="Unified metrics dashboard endpoint",
        risk_level="LOW",
        kill_switch_env="AUTOPACK_ENABLE_CONSOLIDATED_METRICS",
    ),
    "intention_context": FeatureInfo(
        feature_id="intention_context",
        name="Intention Context Injection",
        enabled=os.getenv("AUTOPACK_ENABLE_INTENTION_CONTEXT") == "1",
        wave="pre-wave4",
        imp_id="PHASE-6",
        description="Inject intention anchor context into prompts",
        risk_level="LOW",
        kill_switch_env="AUTOPACK_ENABLE_INTENTION_CONTEXT",
    ),
    "failure_hardening": FeatureInfo(
        feature_id="failure_hardening",
        name="Failure Hardening Patterns",
        enabled=os.getenv("AUTOPACK_ENABLE_FAILURE_HARDENING") == "1",
        wave="pre-wave4",
        imp_id="PHASE-6",
        description="Doctor call optimization via failure patterns",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_FAILURE_HARDENING",
    ),
    "event_driven_triggers": FeatureInfo(
        feature_id="event_driven_triggers",
        name="Event-Driven Workflow Triggers",
        enabled=os.getenv("AUTOPACK_ENABLE_EVENT_DRIVEN_TRIGGERS") == "1",
        wave="pre-wave4",
        imp_id="IMP-AUTO-002",
        description="Trigger phases based on event patterns",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_EVENT_DRIVEN_TRIGGERS",
    ),
    # Wave 1: Research Foundation & Budget Enforcement
    "research_budget_enforcement": FeatureInfo(
        feature_id="research_budget_enforcement",
        name="Budget Enforcement in Research Pipeline",
        enabled=os.getenv("AUTOPACK_ENABLE_RESEARCH_BUDGET_ENFORCEMENT") == "1",
        wave="wave1",
        imp_id="IMP-RES-002",
        description="Budget gates before expensive research phases",
        risk_level="HIGH",
        kill_switch_env="AUTOPACK_ENABLE_RESEARCH_BUDGET_ENFORCEMENT",
    ),
    "mcp_registry_scanner": FeatureInfo(
        feature_id="mcp_registry_scanner",
        name="MCP Registry Scanner",
        enabled=os.getenv("AUTOPACK_ENABLE_MCP_SCANNER") == "1",
        wave="wave1",
        imp_id="IMP-RES-005",
        description="Scan MCP registry for available tools/servers",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_MCP_SCANNER",
    ),
    "research_api_fullmode": FeatureInfo(
        feature_id="research_api_fullmode",
        name="Research API Full Mode",
        enabled=os.getenv("AUTOPACK_ENABLE_RESEARCH_API_FULLMODE") == "1",
        wave="wave1",
        imp_id="IMP-RES-007",
        description="Full REST API for all research analysis results",
        risk_level="LOW",
        kill_switch_env="AUTOPACK_ENABLE_RESEARCH_API_FULLMODE",
    ),
    # Wave 2: Artifact Generation & Deployment
    "monetization_guidance": FeatureInfo(
        feature_id="monetization_guidance",
        name="Monetization Guidance Generator",
        enabled=os.getenv("AUTOPACK_ENABLE_MONETIZATION_GUIDANCE") == "1",
        wave="wave2",
        imp_id="IMP-RES-001",
        description="Generate monetization guidance for projects",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_MONETIZATION_GUIDANCE",
        requires=["research_budget_enforcement"],
    ),
    "deployment_guidance": FeatureInfo(
        feature_id="deployment_guidance",
        name="Deployment Guidance Generator",
        enabled=os.getenv("AUTOPACK_ENABLE_DEPLOYMENT_GUIDANCE") == "1",
        wave="wave2",
        imp_id="IMP-RES-003",
        description="Generate deployment architecture recommendations",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_DEPLOYMENT_GUIDANCE",
        requires=["research_budget_enforcement"],
    ),
    "cicd_pipeline_generator": FeatureInfo(
        feature_id="cicd_pipeline_generator",
        name="CI/CD Pipeline Generator",
        enabled=os.getenv("AUTOPACK_ENABLE_CICD_GENERATOR") == "1",
        wave="wave2",
        imp_id="IMP-RES-004",
        description="Generate CI/CD pipeline configs based on tech stack",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_CICD_GENERATOR",
        requires=["deployment_guidance"],
    ),
    "cross_project_learning": FeatureInfo(
        feature_id="cross_project_learning",
        name="Cross-Project Learning and Pattern Reuse",
        enabled=os.getenv("AUTOPACK_ENABLE_CROSS_PROJECT_LEARNING") == "1",
        wave="wave2",
        imp_id="IMP-RES-006",
        description="Identify and reuse successful patterns across projects",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_CROSS_PROJECT_LEARNING",
    ),
    # Wave 3: Research Integration & Post-Build Automation
    "research_cycle_triggering": FeatureInfo(
        feature_id="research_cycle_triggering",
        name="Research Cycle Triggering in Autopilot",
        enabled=os.getenv("AUTOPACK_ENABLE_RESEARCH_CYCLE_TRIGGERING") == "1",
        wave="wave3",
        imp_id="IMP-AUT-001",
        description="Trigger research cycles from autopilot health gates",
        risk_level="HIGH",
        kill_switch_env="AUTOPACK_ENABLE_RESEARCH_CYCLE_TRIGGERING",
        requires=["research_budget_enforcement"],
    ),
    "sot_artifact_substitution": FeatureInfo(
        feature_id="sot_artifact_substitution",
        name="SOT Artifact Substitution (SOT Doc Summaries)",
        enabled=os.getenv("AUTOPACK_ENABLE_SOT_ARTIFACT_SUBSTITUTION") == "1",
        wave="wave3",
        imp_id="IMP-INT-001",
        description="Substitute SOT document summaries in project briefs",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_SOT_ARTIFACT_SUBSTITUTION",
    ),
    "build_history_feedback": FeatureInfo(
        feature_id="build_history_feedback",
        name="Build History Feedback to Research",
        enabled=os.getenv("AUTOPACK_ENABLE_BUILD_HISTORY_FEEDBACK") == "1",
        wave="wave3",
        imp_id="IMP-INT-002",
        description="Feed build outcomes to research pipeline",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_BUILD_HISTORY_FEEDBACK",
        requires=["research_budget_enforcement"],
    ),
    "post_build_artifacts": FeatureInfo(
        feature_id="post_build_artifacts",
        name="Post-Build Artifact Generation",
        enabled=os.getenv("AUTOPACK_ENABLE_POST_BUILD_ARTIFACTS") == "1",
        wave="wave3",
        imp_id="IMP-INT-003",
        description="Generate artifacts after successful builds",
        risk_level="MEDIUM",
        kill_switch_env="AUTOPACK_ENABLE_POST_BUILD_ARTIFACTS",
        requires=["deployment_guidance", "cicd_pipeline_generator"],
    ),
}

# In-memory feature gate state overrides (for runtime toggling)
_feature_overrides: Dict[str, bool] = {}


def is_feature_enabled(feature_id: str) -> bool:
    """Check if a feature is enabled.

    Args:
        feature_id: Feature identifier from FEATURE_REGISTRY

    Returns:
        True if feature is enabled, False otherwise

    Raises:
        ValueError: If feature_id not found in registry
    """
    if feature_id not in FEATURE_REGISTRY:
        logger.warning(f"Unknown feature queried: {feature_id}")
        return False

    # Check runtime overrides first
    if feature_id in _feature_overrides:
        return _feature_overrides[feature_id]

    # Check environment variable
    feature_info = FEATURE_REGISTRY[feature_id]
    return os.getenv(feature_info.kill_switch_env) == "1"


def set_feature_enabled(feature_id: str, enabled: bool) -> None:
    """Set feature enabled state at runtime.

    Args:
        feature_id: Feature identifier from FEATURE_REGISTRY
        enabled: Whether to enable or disable the feature

    Raises:
        ValueError: If feature_id not found in registry
    """
    if feature_id not in FEATURE_REGISTRY:
        raise ValueError(f"Unknown feature: {feature_id}")

    _feature_overrides[feature_id] = enabled
    logger.info(f"Feature {feature_id} {'enabled' if enabled else 'disabled'} at runtime")


def reset_feature_overrides() -> None:
    """Reset all runtime feature overrides (for testing)."""
    _feature_overrides.clear()
    logger.debug("Feature overrides reset")


def get_feature_info(feature_id: str) -> Optional[FeatureInfo]:
    """Get detailed information about a feature.

    Args:
        feature_id: Feature identifier from FEATURE_REGISTRY

    Returns:
        FeatureInfo object or None if not found
    """
    return FEATURE_REGISTRY.get(feature_id)


def get_feature_states() -> Dict[str, dict]:
    """Get enabled/disabled state for all registered features.

    Returns:
        Dict mapping feature_id to status object with enabled state and metadata
    """
    states = {}
    for feature_id, feature_info in FEATURE_REGISTRY.items():
        enabled = is_feature_enabled(feature_id)
        states[feature_id] = {
            "feature_id": feature_id,
            "name": feature_info.name,
            "enabled": enabled,
            "wave": feature_info.wave,
            "imp_id": feature_info.imp_id,
            "risk_level": feature_info.risk_level,
            "requires": feature_info.requires or [],
        }
    return states


def get_enabled_features() -> Dict[str, dict]:
    """Get all currently enabled features.

    Returns:
        Dict mapping feature_id to status object (enabled features only)
    """
    return {
        fid: info
        for fid, info in get_feature_states().items()
        if info["enabled"]
    }


def get_disabled_features() -> Dict[str, dict]:
    """Get all currently disabled features.

    Returns:
        Dict mapping feature_id to status object (disabled features only)
    """
    return {
        fid: info
        for fid, info in get_feature_states().items()
        if not info["enabled"]
    }


def check_feature_dependencies(feature_id: str) -> tuple[bool, list[str]]:
    """Check if a feature's dependencies are satisfied.

    Args:
        feature_id: Feature identifier from FEATURE_REGISTRY

    Returns:
        Tuple of (all_deps_satisfied: bool, missing_deps: list of feature_ids)
    """
    feature_info = get_feature_info(feature_id)
    if not feature_info or not feature_info.requires:
        return True, []

    missing = []
    for dep_id in feature_info.requires:
        if not is_feature_enabled(dep_id):
            missing.append(dep_id)

    return len(missing) == 0, missing


def require_feature(feature_id: str, graceful: bool = False) -> None:
    """Check that a feature is enabled, raise error or log warning if not.

    Args:
        feature_id: Feature identifier from FEATURE_REGISTRY
        graceful: If True, log warning instead of raising FeatureDisabledError

    Raises:
        FeatureDisabledError: If feature not enabled and graceful=False
    """
    if not is_feature_enabled(feature_id):
        error_msg = f"Feature '{feature_id}' is disabled"
        if graceful:
            logger.warning(error_msg)
        else:
            logger.error(error_msg)
            raise FeatureDisabledError(error_msg)


def get_disabled_graceful(feature_id: str) -> bool:
    """Check if feature is disabled, with graceful fallback (no exception).

    This is a convenience method for conditional logic in code that should
    handle disabled features gracefully.

    Args:
        feature_id: Feature identifier from FEATURE_REGISTRY

    Returns:
        True if feature is disabled (failed gracefully), False if enabled
    """
    enabled = is_feature_enabled(feature_id)
    if not enabled:
        logger.debug(f"Feature '{feature_id}' is disabled, using graceful fallback")
    return not enabled


def validate_feature_state() -> dict:
    """Validate feature gate state and return diagnostics.

    Checks for:
    - Features with unmet dependencies
    - Features with invalid configuration
    - Inconsistencies in kill switches

    Returns:
        Dict with 'valid' bool and 'issues' list of diagnostic messages
    """
    issues = []

    for feature_id, feature_info in FEATURE_REGISTRY.items():
        # Check dependencies
        if feature_info.requires:
            deps_ok, missing = check_feature_dependencies(feature_id)
            if not deps_ok:
                if is_feature_enabled(feature_id):
                    issues.append(
                        f"Feature '{feature_id}' enabled but missing dependencies: {missing}"
                    )

        # Check that kill switch env var is not empty/None
        env_value = os.getenv(feature_info.kill_switch_env)
        if env_value and env_value not in ("0", "1"):
            issues.append(
                f"Feature '{feature_id}' kill switch has invalid value: {env_value} "
                f"(expected: '0', '1', or unset)"
            )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "total_features": len(FEATURE_REGISTRY),
        "enabled_count": len(get_enabled_features()),
        "disabled_count": len(get_disabled_features()),
    }


# Graceful degradation decorators and helpers
def graceful_degradation_context(feature_id: str, default_return=None):
    """Context manager for graceful degradation when feature is disabled.

    Usage:
        with graceful_degradation_context("research_cycle_triggering") as ctx:
            if ctx.feature_disabled:
                return default_behavior()
            # Feature is enabled, proceed with main logic

    Args:
        feature_id: Feature identifier
        default_return: Default value to return if feature disabled

    Yields:
        Object with 'feature_disabled' bool attribute
    """
    from contextlib import contextmanager

    @contextmanager
    def _context():
        class DegradationContext:
            feature_disabled = not is_feature_enabled(feature_id)

        yield DegradationContext()

    return _context()


def handle_disabled_feature(feature_id: str, error_msg: str = None) -> dict:
    """Generate a graceful degradation response for a disabled feature.

    Usage in API endpoints:
        if get_disabled_graceful("research_cycle_triggering"):
            return handle_disabled_feature("research_cycle_triggering")
        # Feature enabled, proceed with logic

    Args:
        feature_id: Feature identifier
        error_msg: Optional custom error message

    Returns:
        Dict with 'error', 'feature_id', 'status_code' for HTTP responses
    """
    feature_info = get_feature_info(feature_id)
    if not feature_info:
        return {
            "error": f"Unknown feature: {feature_id}",
            "feature_id": feature_id,
            "status_code": 404,
        }

    return {
        "error": error_msg or f"Feature '{feature_info.name}' is currently disabled",
        "feature_id": feature_id,
        "feature_name": feature_info.name,
        "status_code": 503,  # Service Unavailable
        "details": {
            "imp_id": feature_info.imp_id,
            "wave": feature_info.wave,
            "kill_switch_env": feature_info.kill_switch_env,
            "message": "This feature can be enabled by setting the appropriate environment variable",
        },
    }


def log_feature_usage(feature_id: str, action: str = "accessed"):
    """Log when a feature is accessed (for telemetry).

    Usage:
        log_feature_usage("research_cycle_triggering", "started")

    Args:
        feature_id: Feature identifier
        action: Description of action (e.g., 'accessed', 'started', 'completed')
    """
    enabled = is_feature_enabled(feature_id)
    status = "enabled" if enabled else "disabled"
    logger.info(f"Feature '{feature_id}' ({status}) {action}")
