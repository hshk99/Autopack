"""Dashboard API endpoints for BUILD-146 observability.

Provides consolidated token metrics that prevent double-counting:
1. Total tokens spent (actual from llm_usage_events)
2. Artifact tokens avoided (from token_efficiency_metrics)
3. Doctor tokens avoided estimate (counterfactual from phase6_metrics)
4. A/B delta tokens saved (actual measured difference, when available)

Each category is independent - no overlap or double-counting.
"""

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from autopack.database import get_db
from autopack.dashboard_schemas import (
    TokenEfficiencyStats,
    Phase6Stats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class ConsolidatedTokenMetrics:
    """Consolidated token metrics that prevent double-counting.

    BUILD-146 P11 Observability: This response model clearly separates
    four independent token categories:

    1. total_tokens_spent: Actual tokens spent on LLM calls (llm_usage_events)
    2. artifact_tokens_avoided: Tokens saved by using artifacts instead of full files
    3. doctor_tokens_avoided_estimate: Counterfactual estimate of what Doctor would have cost
    4. ab_delta_tokens_saved: Actual measured savings from A/B test (when available)

    These categories do NOT overlap - they measure different things:
    - #1 is actual spend
    - #2 is efficiency within the spend
    - #3 is counterfactual (what we avoided by not calling Doctor)
    - #4 is measured delta between control and treatment runs
    """

    run_id: str

    # Category 1: Actual spend (from llm_usage_events)
    total_tokens_spent: int
    total_prompt_tokens: int
    total_completion_tokens: int
    doctor_tokens_spent: int  # Subset of total_tokens_spent

    # Category 2: Artifact efficiency (from token_efficiency_metrics)
    artifact_tokens_avoided: int
    artifact_substitutions_count: int

    # Category 3: Doctor counterfactual estimate (from phase6_metrics)
    doctor_tokens_avoided_estimate: int
    doctor_calls_skipped_count: int
    estimate_coverage_n: Optional[int]
    estimate_source: Optional[str]

    # Category 4: A/B measured delta (when available)
    ab_delta_tokens_saved: Optional[int]
    ab_control_run_id: Optional[str]
    ab_treatment_run_id: Optional[str]

    # Metadata
    total_phases: int
    completed_phases: int

    def __init__(self, **data):
        for key, value in data.items():
            setattr(self, key, value)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "total_tokens_spent": self.total_tokens_spent,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "doctor_tokens_spent": self.doctor_tokens_spent,
            "artifact_tokens_avoided": self.artifact_tokens_avoided,
            "artifact_substitutions_count": self.artifact_substitutions_count,
            "doctor_tokens_avoided_estimate": self.doctor_tokens_avoided_estimate,
            "doctor_calls_skipped_count": self.doctor_calls_skipped_count,
            "estimate_coverage_n": self.estimate_coverage_n,
            "estimate_source": self.estimate_source,
            "ab_delta_tokens_saved": self.ab_delta_tokens_saved,
            "ab_control_run_id": self.ab_control_run_id,
            "ab_treatment_run_id": self.ab_treatment_run_id,
            "total_phases": self.total_phases,
            "completed_phases": self.completed_phases,
        }


@router.get("/runs/{run_id}/consolidated-metrics")
def get_consolidated_metrics(
    run_id: str,
    limit: int = 1000,
    offset: int = 0,
    db: Session = Depends(get_db)
) -> dict:
    """Get consolidated token metrics for a run (no double-counting).

    BUILD-146 P11 Observability: Returns all token metrics in clearly separated
    categories to prevent confusion and double-counting.

    BUILD-146 P12 Production Hardening: Added kill switch and pagination.

    Args:
        run_id: The run ID to fetch metrics for
        limit: Maximum number of records to return (max: 10000, default: 1000)
        offset: Number of records to skip (default: 0)
        db: Database session

    Returns:
        ConsolidatedTokenMetrics as dictionary

    Raises:
        HTTPException: If run not found or feature disabled
    """
    # BUILD-146 P12: Kill switch check (default: OFF)
    if os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1":
        raise HTTPException(
            status_code=503,
            detail="Consolidated metrics disabled. Set AUTOPACK_ENABLE_CONSOLIDATED_METRICS=1 to enable."
        )

    # Validate pagination parameters
    if limit > 10000:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 10000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset cannot be negative")

    # Verify run exists
    run_check = db.execute(
        text("SELECT id FROM runs WHERE id = :run_id"),
        {"run_id": run_id}
    ).fetchone()

    if not run_check:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Category 1: Actual spend from llm_usage_events
    actual_spend = db.execute(text("""
        SELECT
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
            COALESCE(SUM(completion_tokens), 0) as completion_tokens,
            COALESCE(SUM(CASE WHEN is_doctor_call = 1 THEN total_tokens ELSE 0 END), 0) as doctor_tokens
        FROM llm_usage_events
        WHERE run_id = :run_id
    """), {"run_id": run_id}).fetchone()

    total_tokens_spent = actual_spend[0] if actual_spend else 0
    total_prompt_tokens = actual_spend[1] if actual_spend else 0
    total_completion_tokens = actual_spend[2] if actual_spend else 0
    doctor_tokens_spent = actual_spend[3] if actual_spend else 0

    # Category 2: Artifact efficiency from token_efficiency_metrics
    artifact_efficiency = db.execute(text("""
        SELECT
            COALESCE(SUM(tokens_saved_artifacts), 0) as tokens_saved,
            COALESCE(SUM(artifact_substitutions), 0) as substitutions
        FROM token_efficiency_metrics
        WHERE run_id = :run_id
    """), {"run_id": run_id}).fetchone()

    artifact_tokens_avoided = artifact_efficiency[0] if artifact_efficiency else 0
    artifact_substitutions_count = artifact_efficiency[1] if artifact_efficiency else 0

    # Category 3: Doctor counterfactual from phase6_metrics
    doctor_counterfactual = db.execute(text("""
        SELECT
            COALESCE(SUM(doctor_tokens_avoided_estimate), 0) as total_estimate,
            COALESCE(SUM(CASE WHEN doctor_call_skipped = 1 THEN 1 ELSE 0 END), 0) as skipped_count,
            MAX(estimate_coverage_n) as max_coverage_n,
            MAX(estimate_source) as last_source
        FROM phase6_metrics
        WHERE run_id = :run_id
    """), {"run_id": run_id}).fetchone()

    doctor_tokens_avoided_estimate = doctor_counterfactual[0] if doctor_counterfactual else 0
    doctor_calls_skipped_count = doctor_counterfactual[1] if doctor_counterfactual else 0
    estimate_coverage_n = doctor_counterfactual[2] if doctor_counterfactual else None
    estimate_source = doctor_counterfactual[3] if doctor_counterfactual else None

    # Category 4: A/B delta (not implemented yet - would come from A/B test results)
    ab_delta_tokens_saved = None
    ab_control_run_id = None
    ab_treatment_run_id = None

    # Metadata: Phase counts
    phase_counts = db.execute(text("""
        SELECT
            COUNT(*) as total_phases,
            COALESCE(SUM(CASE WHEN state = 'COMPLETE' THEN 1 ELSE 0 END), 0) as completed_phases
        FROM phases
        WHERE run_id = :run_id
    """), {"run_id": run_id}).fetchone()

    total_phases = phase_counts[0] if phase_counts else 0
    completed_phases = phase_counts[1] if phase_counts else 0

    # Build response
    metrics = ConsolidatedTokenMetrics(
        run_id=run_id,
        total_tokens_spent=total_tokens_spent,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        doctor_tokens_spent=doctor_tokens_spent,
        artifact_tokens_avoided=artifact_tokens_avoided,
        artifact_substitutions_count=artifact_substitutions_count,
        doctor_tokens_avoided_estimate=doctor_tokens_avoided_estimate,
        doctor_calls_skipped_count=doctor_calls_skipped_count,
        estimate_coverage_n=estimate_coverage_n,
        estimate_source=estimate_source,
        ab_delta_tokens_saved=ab_delta_tokens_saved,
        ab_control_run_id=ab_control_run_id,
        ab_treatment_run_id=ab_treatment_run_id,
        total_phases=total_phases,
        completed_phases=completed_phases,
    )

    return metrics.to_dict()


@router.get("/runs/{run_id}/token-efficiency", response_model=TokenEfficiencyStats)
def get_token_efficiency_stats(run_id: str, db: Session = Depends(get_db)) -> TokenEfficiencyStats:
    """Get token efficiency statistics for a run (BUILD-145).

    Legacy endpoint - use /consolidated-metrics for new code.
    """
    from autopack.models import Run, Phase

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Aggregate token efficiency metrics
    efficiency_data = db.execute(text("""
        SELECT
            COUNT(*) as total_phases,
            COALESCE(SUM(artifact_substitutions), 0) as total_substitutions,
            COALESCE(SUM(tokens_saved_artifacts), 0) as total_tokens_saved,
            COALESCE(SUM(budget_used), 0) as total_budget_used,
            COALESCE(MAX(budget_cap), 0) as budget_cap,
            COALESCE(SUM(files_kept), 0) as total_files_kept,
            COALESCE(SUM(files_omitted), 0) as total_files_omitted,
            COALESCE(SUM(CASE WHEN budget_mode = 'semantic' THEN 1 ELSE 0 END), 0) as semantic_count,
            COALESCE(SUM(CASE WHEN budget_mode = 'lexical' THEN 1 ELSE 0 END), 0) as lexical_count
        FROM token_efficiency_metrics
        WHERE run_id = :run_id
    """), {"run_id": run_id}).fetchone()

    total_phases = efficiency_data[0] if efficiency_data else 0
    total_substitutions = efficiency_data[1] if efficiency_data else 0
    total_tokens_saved = efficiency_data[2] if efficiency_data else 0
    total_budget_used = efficiency_data[3] if efficiency_data else 0
    budget_cap = efficiency_data[4] if efficiency_data else 0
    total_files_kept = efficiency_data[5] if efficiency_data else 0
    total_files_omitted = efficiency_data[6] if efficiency_data else 0
    semantic_count = efficiency_data[7] if efficiency_data else 0
    lexical_count = efficiency_data[8] if efficiency_data else 0

    # Calculate averages
    avg_substitutions = total_substitutions / total_phases if total_phases > 0 else 0.0
    avg_tokens_saved = total_tokens_saved / total_phases if total_phases > 0 else 0.0
    budget_utilization = (total_budget_used / budget_cap * 100) if budget_cap > 0 else 0.0

    return TokenEfficiencyStats(
        run_id=run_id,
        total_phases=total_phases,
        total_artifact_substitutions=total_substitutions,
        total_tokens_saved_artifacts=total_tokens_saved,
        total_budget_used=total_budget_used,
        total_budget_cap=budget_cap,
        total_files_kept=total_files_kept,
        total_files_omitted=total_files_omitted,
        semantic_mode_count=semantic_count,
        lexical_mode_count=lexical_count,
        avg_artifact_substitutions_per_phase=avg_substitutions,
        avg_tokens_saved_per_phase=avg_tokens_saved,
        budget_utilization=budget_utilization,
    )


@router.get("/runs/{run_id}/phase6-stats", response_model=Phase6Stats)
def get_phase6_stats(run_id: str, db: Session = Depends(get_db)) -> Phase6Stats:
    """Get Phase 6 True Autonomy feature statistics for a run (BUILD-146).

    Legacy endpoint - use /consolidated-metrics for new code.
    """
    from autopack.models import Run

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Aggregate phase6_metrics
    phase6_data = db.execute(text("""
        SELECT
            COUNT(*) as total_phases,
            COALESCE(SUM(CASE WHEN failure_hardening_triggered = 1 THEN 1 ELSE 0 END), 0) as hardening_triggered,
            COALESCE(SUM(CASE WHEN doctor_call_skipped = 1 THEN 1 ELSE 0 END), 0) as doctor_skipped,
            COALESCE(SUM(doctor_tokens_avoided_estimate), 0) as total_doctor_avoided,
            COALESCE(SUM(CASE WHEN intention_context_injected = 1 THEN 1 ELSE 0 END), 0) as intention_injected,
            COALESCE(SUM(intention_context_chars), 0) as total_intention_chars,
            MAX(plan_normalization_used) as plan_norm_used
        FROM phase6_metrics
        WHERE run_id = :run_id
    """), {"run_id": run_id}).fetchone()

    total_phases = phase6_data[0] if phase6_data else 0
    hardening_triggered = phase6_data[1] if phase6_data else 0
    doctor_skipped = phase6_data[2] if phase6_data else 0
    total_doctor_avoided = phase6_data[3] if phase6_data else 0
    intention_injected = phase6_data[4] if phase6_data else 0
    total_intention_chars = phase6_data[5] if phase6_data else 0
    plan_norm_used = bool(phase6_data[6]) if phase6_data else False

    # Get failure pattern breakdown
    pattern_data = db.execute(text("""
        SELECT failure_pattern_detected, COUNT(*) as count
        FROM phase6_metrics
        WHERE run_id = :run_id AND failure_pattern_detected IS NOT NULL
        GROUP BY failure_pattern_detected
    """), {"run_id": run_id}).fetchall()

    failure_patterns = {row[0]: row[1] for row in pattern_data}

    # Get estimate coverage stats
    coverage_data = db.execute(text("""
        SELECT estimate_source, COUNT(*) as count, MAX(estimate_coverage_n) as max_n
        FROM phase6_metrics
        WHERE run_id = :run_id AND estimate_source IS NOT NULL
        GROUP BY estimate_source
    """), {"run_id": run_id}).fetchall()

    estimate_coverage_stats = {
        row[0]: {"count": row[1], "total_n": row[2]}
        for row in coverage_data
    }

    # Calculate average intention context chars
    avg_intention_chars = total_intention_chars / intention_injected if intention_injected > 0 else 0.0

    return Phase6Stats(
        run_id=run_id,
        total_phases=total_phases,
        failure_hardening_triggered_count=hardening_triggered,
        failure_patterns_detected=failure_patterns,
        doctor_calls_skipped_count=doctor_skipped,
        total_doctor_tokens_avoided_estimate=total_doctor_avoided,
        estimate_coverage_stats=estimate_coverage_stats,
        intention_context_injected_count=intention_injected,
        total_intention_context_chars=total_intention_chars,
        avg_intention_context_chars_per_phase=avg_intention_chars,
        plan_normalization_used=plan_norm_used,
    )


@router.get("/ab-results")
def get_ab_results(
    test_id: Optional[str] = None,
    valid_only: bool = True,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> dict:
    """Get A/B test results from database.

    BUILD-146 P12: Retrieves A/B test comparison results with strict validity filtering.

    Args:
        test_id: Optional filter by specific test ID
        valid_only: If True, only return valid comparisons (default: True)
        limit: Maximum number of results to return (default: 100, max: 1000)
        db: Database session

    Returns:
        Dictionary with list of A/B test results
    """
    from autopack.models import ABTestResult

    # Validate limit
    if limit > 1000:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 1000")

    # Build query
    query = db.query(ABTestResult)

    if test_id:
        query = query.filter(ABTestResult.test_id == test_id)

    if valid_only:
        query = query.filter(ABTestResult.is_valid == True)

    # Order by most recent first, apply limit
    results = query.order_by(ABTestResult.created_at.desc()).limit(limit).all()

    return {
        "count": len(results),
        "filters": {
            "test_id": test_id,
            "valid_only": valid_only,
        },
        "results": [
            {
                "id": r.id,
                "test_id": r.test_id,
                "control_run_id": r.control_run_id,
                "treatment_run_id": r.treatment_run_id,
                "is_valid": r.is_valid,
                "validity_errors": r.validity_errors,
                "token_delta": r.token_delta,
                "time_delta_seconds": r.time_delta_seconds,
                "success_rate_delta": r.success_rate_delta,
                "control_total_tokens": r.control_total_tokens,
                "control_phases_complete": r.control_phases_complete,
                "control_phases_failed": r.control_phases_failed,
                "control_total_phases": r.control_total_phases,
                "treatment_total_tokens": r.treatment_total_tokens,
                "treatment_phases_complete": r.treatment_phases_complete,
                "treatment_phases_failed": r.treatment_phases_failed,
                "treatment_total_phases": r.treatment_total_phases,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "created_by": r.created_by,
            }
            for r in results
        ]
    }
