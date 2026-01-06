"""Coverage metrics handling (BUILD-181 Phase 5).

Returns None for coverage delta when unknown, never 0.0 as placeholder.
Explicit "unknown" state when data unavailable.

Properties:
- None when unknown, not 0.0 placeholder
- Deterministic "unknown" state
- Real values only when CI data is available
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Status values for coverage
CoverageStatus = Literal["unknown", "available"]


class CoverageInfo(BaseModel):
    """Coverage information with explicit status.

    Never uses 0.0 as placeholder for unknown.
    """

    model_config = ConfigDict(extra="forbid")

    status: CoverageStatus = Field(..., description="Whether coverage data is available")
    delta: Optional[float] = Field(default=None, description="Coverage delta (None if unknown)")
    baseline: Optional[float] = Field(default=None, description="Baseline coverage %")
    current: Optional[float] = Field(default=None, description="Current coverage %")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "status": self.status,
            "delta": self.delta,
            "baseline": self.baseline,
            "current": self.current,
        }


def compute_coverage_delta(ci_result: Optional[Dict[str, Any]]) -> Optional[float]:
    """Compute coverage delta from CI result.

    Returns None when coverage data is unavailable.
    NEVER returns 0.0 as a placeholder for unknown.

    Args:
        ci_result: CI result dictionary with optional 'coverage' key

    Returns:
        Coverage delta as float, or None if unknown
    """
    if ci_result is None:
        logger.debug("[CoverageMetrics] No CI result, coverage delta unknown")
        return None

    coverage = ci_result.get("coverage")
    if coverage is None:
        logger.debug("[CoverageMetrics] No coverage data in CI result")
        return None

    if not isinstance(coverage, dict):
        logger.debug(f"[CoverageMetrics] Invalid coverage format: {type(coverage)}")
        return None

    # Check for explicit delta
    delta = coverage.get("delta")
    if delta is not None:
        try:
            return float(delta)
        except (TypeError, ValueError):
            logger.debug(f"[CoverageMetrics] Invalid delta value: {delta}")
            return None

    # Try to compute from baseline and current
    baseline = coverage.get("baseline")
    current = coverage.get("current")

    if baseline is not None and current is not None:
        try:
            return float(current) - float(baseline)
        except (TypeError, ValueError):
            logger.debug(
                f"[CoverageMetrics] Invalid baseline/current: {baseline}/{current}"
            )
            return None

    logger.debug("[CoverageMetrics] Coverage data incomplete")
    return None


def get_coverage_status(ci_result: Optional[Dict[str, Any]]) -> CoverageStatus:
    """Get coverage status (available or unknown).

    Args:
        ci_result: CI result dictionary

    Returns:
        "available" if coverage data present, "unknown" otherwise
    """
    if ci_result is None:
        return "unknown"

    coverage = ci_result.get("coverage")
    if coverage is None or not isinstance(coverage, dict):
        return "unknown"

    # Check if we have meaningful data
    if "delta" in coverage or ("baseline" in coverage and "current" in coverage):
        return "available"

    return "unknown"


def compute_coverage_info(ci_result: Optional[Dict[str, Any]]) -> CoverageInfo:
    """Compute full coverage info from CI result.

    Args:
        ci_result: CI result dictionary

    Returns:
        CoverageInfo with status and optional values
    """
    status = get_coverage_status(ci_result)

    if status == "unknown":
        return CoverageInfo(
            status="unknown",
            delta=None,
            baseline=None,
            current=None,
        )

    # Extract values
    coverage = ci_result.get("coverage", {})  # type: ignore

    delta = compute_coverage_delta(ci_result)
    baseline = None
    current = None

    try:
        if "baseline" in coverage:
            baseline = float(coverage["baseline"])
        if "current" in coverage:
            current = float(coverage["current"])
    except (TypeError, ValueError):
        pass

    return CoverageInfo(
        status="available",
        delta=delta,
        baseline=baseline,
        current=current,
    )


def should_trust_coverage(ci_result: Optional[Dict[str, Any]]) -> bool:
    """Check if coverage data can be trusted for decisions.

    Args:
        ci_result: CI result dictionary

    Returns:
        True only if real coverage data is available
    """
    return get_coverage_status(ci_result) == "available"


def format_coverage_for_display(ci_result: Optional[Dict[str, Any]]) -> str:
    """Format coverage for human-readable display.

    Args:
        ci_result: CI result dictionary

    Returns:
        Human-readable coverage string
    """
    info = compute_coverage_info(ci_result)

    if info.status == "unknown":
        return "Coverage: unknown"

    parts = []

    if info.current is not None:
        parts.append(f"Current: {info.current:.1f}%")

    if info.baseline is not None:
        parts.append(f"Baseline: {info.baseline:.1f}%")

    if info.delta is not None:
        sign = "+" if info.delta >= 0 else ""
        parts.append(f"Delta: {sign}{info.delta:.1f}%")

    return f"Coverage: {', '.join(parts)}" if parts else "Coverage: available (no detail)"
