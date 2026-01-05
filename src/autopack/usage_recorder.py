"""LLM usage tracking for token consumption monitoring"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import Column, DateTime, Integer, String, Boolean, JSON
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base


class LlmUsageEvent(Base):
    """Record of LLM token usage for a single API call"""

    __tablename__ = "llm_usage_events"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False, index=True)  # openai, anthropic, google_gemini, glm
    model = Column(String, nullable=False, index=True)  # gpt-4o, claude-3-5-sonnet, etc.
    run_id = Column(String, nullable=True, index=True)  # null for global aux runs
    phase_id = Column(String, nullable=True)
    role = Column(String, nullable=False)  # builder, auditor, agent:planner, doctor, etc.
    # BUILD-144 P0.4: Always record total_tokens (non-null); splits are optional
    total_tokens = Column(Integer, nullable=False, default=0)  # Always populated
    # BUILD-144: nullable=True to support total-only recording when exact splits unavailable
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Doctor-specific fields
    is_doctor_call = Column(Boolean, nullable=False, default=False, index=True)
    doctor_model = Column(String, nullable=True)  # cheap or strong
    doctor_action = Column(String, nullable=True)  # retry_with_fix, replan, skip_phase, etc.


class DoctorUsageStats(Base):
    """Aggregated Doctor usage statistics per run"""

    __tablename__ = "doctor_usage_stats"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=False, unique=True, index=True)

    # Call counts
    doctor_calls_total = Column(Integer, nullable=False, default=0)
    doctor_cheap_calls = Column(Integer, nullable=False, default=0)
    doctor_strong_calls = Column(Integer, nullable=False, default=0)
    doctor_escalations = Column(Integer, nullable=False, default=0)  # cheap -> strong upgrades

    # Action distribution (JSON dict: {action_type: count})
    doctor_actions = Column(JSON, nullable=False, default=dict)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TokenEfficiencyMetrics(Base):
    """Token efficiency metrics per phase (BUILD-145)"""

    __tablename__ = "token_efficiency_metrics"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    # Artifact substitution metrics
    artifact_substitutions = Column(Integer, nullable=False, default=0)
    tokens_saved_artifacts = Column(Integer, nullable=False, default=0)

    # Context budget metrics
    budget_mode = Column(String, nullable=False)  # "semantic" or "lexical"
    budget_used = Column(Integer, nullable=False, default=0)
    budget_cap = Column(Integer, nullable=False, default=0)
    files_kept = Column(Integer, nullable=False, default=0)
    files_omitted = Column(Integer, nullable=False, default=0)

    # Phase outcome (BUILD-145 P1 hardening: terminal state tracking)
    # Nullable for backward compatibility; stores COMPLETE, FAILED, BLOCKED, etc.
    phase_outcome = Column(String, nullable=True, index=True)

    # BUILD-145 deployment hardening: Embedding cache observability
    # Nullable for backward compatibility
    embedding_cache_hits = Column(Integer, nullable=True, default=0)
    embedding_cache_misses = Column(Integer, nullable=True, default=0)
    embedding_calls_made = Column(Integer, nullable=True, default=0)
    embedding_cap_value = Column(Integer, nullable=True, default=0)
    embedding_fallback_reason = Column(String, nullable=True)  # "cap_exceeded", "disabled", None

    # BUILD-145 deployment hardening: Budgeting context observability
    # Nullable for backward compatibility
    deliverables_count = Column(Integer, nullable=True, default=0)
    context_files_total = Column(Integer, nullable=True, default=0)  # Total files before budgeting

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )


class Phase6Metrics(Base):
    """Phase 6 True Autonomy feature effectiveness metrics (BUILD-146)"""

    __tablename__ = "phase6_metrics"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    # Failure hardening metrics
    failure_hardening_triggered = Column(Boolean, nullable=False, default=False)
    failure_pattern_detected = Column(String, nullable=True)  # pattern_id if detected
    failure_hardening_mitigated = Column(Boolean, nullable=False, default=False)
    doctor_call_skipped = Column(Boolean, nullable=False, default=False)

    # BUILD-146 P3: Counterfactual estimate of tokens avoided by skipping Doctor
    # This is NOT actual tokens saved (use A/B deltas for that), but expected baseline cost
    doctor_tokens_avoided_estimate = Column(Integer, nullable=False, default=0)
    estimate_coverage_n = Column(Integer, nullable=True)  # Sample size for baseline
    estimate_source = Column(String, nullable=True)  # "run_local", "global", "fallback"

    # Intention context metrics
    intention_context_injected = Column(Boolean, nullable=False, default=False)
    intention_context_chars = Column(Integer, nullable=False, default=0)
    intention_context_source = Column(String, nullable=True)  # "memory", "fallback", None

    # Plan normalization metrics (for runs using plan normalizer)
    plan_normalization_used = Column(Boolean, nullable=False, default=False)
    plan_normalization_confidence = Column(Integer, nullable=True)  # 1-10 scale
    plan_normalization_warnings = Column(Integer, nullable=False, default=0)
    plan_deliverables_count = Column(Integer, nullable=True)
    plan_scope_size_bytes = Column(Integer, nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )


@dataclass
class UsageEventData:
    """Dataclass for passing usage event data

    BUILD-144 P0.4: total_tokens is always required (non-null).
    prompt_tokens and completion_tokens are Optional to support
    total-only recording when exact splits are unavailable from provider.
    """

    provider: str
    model: str
    run_id: Optional[str]
    phase_id: Optional[str]
    role: str
    total_tokens: int  # Always required
    prompt_tokens: Optional[int]  # Optional: NULL when split unavailable
    completion_tokens: Optional[int]  # Optional: NULL when split unavailable

    # Doctor-specific fields
    is_doctor_call: bool = False
    doctor_model: Optional[str] = None  # "cheap" or "strong"
    doctor_action: Optional[str] = None  # action type recommended


def record_usage(db: Session, event: UsageEventData) -> LlmUsageEvent:
    """
    Record a single LLM usage event.

    Args:
        db: Database session
        event: Usage event data

    Returns:
        Created LlmUsageEvent record
    """
    usage_record = LlmUsageEvent(
        provider=event.provider,
        model=event.model,
        run_id=event.run_id,
        phase_id=event.phase_id,
        role=event.role,
        total_tokens=event.total_tokens,
        prompt_tokens=event.prompt_tokens,
        completion_tokens=event.completion_tokens,
        created_at=datetime.now(timezone.utc),
        is_doctor_call=event.is_doctor_call,
        doctor_model=event.doctor_model,
        doctor_action=event.doctor_action,
    )

    db.add(usage_record)
    db.commit()
    db.refresh(usage_record)

    # Update aggregated Doctor stats if this is a Doctor call
    if event.is_doctor_call and event.run_id:
        update_doctor_stats(db, event)

    return usage_record


def update_doctor_stats(db: Session, event: UsageEventData) -> None:
    """
    Update aggregated Doctor usage statistics for a run.

    Args:
        db: Database session
        event: Usage event data (must be a Doctor call with run_id)
    """
    if not event.run_id or not event.is_doctor_call:
        return

    # Get or create stats record
    stats = db.query(DoctorUsageStats).filter(DoctorUsageStats.run_id == event.run_id).first()

    if not stats:
        stats = DoctorUsageStats(
            run_id=event.run_id,
            doctor_calls_total=0,
            doctor_cheap_calls=0,
            doctor_strong_calls=0,
            doctor_escalations=0,
            doctor_actions={},
        )
        db.add(stats)

    # Update counts
    stats.doctor_calls_total += 1

    if event.doctor_model == "cheap":
        stats.doctor_cheap_calls += 1
    elif event.doctor_model == "strong":
        stats.doctor_strong_calls += 1
        # Check if this was an escalation (previous call was cheap)
        prev_call = (
            db.query(LlmUsageEvent)
            .filter(
                LlmUsageEvent.run_id == event.run_id,
                LlmUsageEvent.phase_id == event.phase_id,
                LlmUsageEvent.is_doctor_call,
                LlmUsageEvent.doctor_model == "cheap",
            )
            .order_by(LlmUsageEvent.created_at.desc())
            .first()
        )

        if prev_call:
            stats.doctor_escalations += 1

    # Update action distribution
    if event.doctor_action:
        if stats.doctor_actions is None:
            stats.doctor_actions = {}
        stats.doctor_actions[event.doctor_action] = (
            stats.doctor_actions.get(event.doctor_action, 0) + 1
        )

    stats.updated_at = datetime.now(timezone.utc)
    db.commit()


def get_doctor_stats(db: Session, run_id: str) -> Optional[Dict]:
    """
    Get Doctor usage statistics for a run.

    Args:
        db: Database session
        run_id: Run identifier

    Returns:
        Dictionary with Doctor stats or None if no stats exist
    """
    stats = db.query(DoctorUsageStats).filter(DoctorUsageStats.run_id == run_id).first()

    if not stats:
        return None

    return {
        "run_id": stats.run_id,
        "doctor_calls_total": stats.doctor_calls_total,
        "doctor_cheap_calls": stats.doctor_cheap_calls,
        "doctor_strong_calls": stats.doctor_strong_calls,
        "doctor_escalations": stats.doctor_escalations,
        "doctor_actions": stats.doctor_actions or {},
        "cheap_vs_strong_ratio": (
            stats.doctor_cheap_calls / stats.doctor_calls_total
            if stats.doctor_calls_total > 0
            else 0
        ),
        "escalation_frequency": (
            stats.doctor_escalations / stats.doctor_calls_total
            if stats.doctor_calls_total > 0
            else 0
        ),
    }


def record_token_efficiency_metrics(
    db: Session,
    run_id: str,
    phase_id: str,
    artifact_substitutions: int,
    tokens_saved_artifacts: int,
    budget_mode: str,
    budget_used: int,
    budget_cap: int,
    files_kept: int,
    files_omitted: int,
    phase_outcome: Optional[str] = None,
    # BUILD-145 deployment hardening: embedding cache observability (all optional)
    embedding_cache_hits: Optional[int] = None,
    embedding_cache_misses: Optional[int] = None,
    embedding_calls_made: Optional[int] = None,
    embedding_cap_value: Optional[int] = None,
    embedding_fallback_reason: Optional[str] = None,
    # BUILD-145 deployment hardening: budgeting context observability (all optional)
    deliverables_count: Optional[int] = None,
    context_files_total: Optional[int] = None,
) -> TokenEfficiencyMetrics:
    """Record token efficiency metrics for a phase.

    BUILD-146 P17.1: Idempotency guard ensures exactly one metrics record per
    (run_id, phase_id, outcome) even across retries/replans/crashes.

    BUILD-146 P17.x: Race-safe under concurrency via DB-level unique index enforcement.
    If a concurrent writer beats us to inserting the same terminal outcome, we catch
    IntegrityError, rollback, and return the existing record.

    Args:
        db: Database session
        run_id: Run identifier
        phase_id: Phase identifier
        artifact_substitutions: Number of files substituted with artifacts
        tokens_saved_artifacts: Estimated tokens saved via artifacts
        budget_mode: Context budget mode ("semantic" or "lexical")
        budget_used: Estimated tokens used in context
        budget_cap: Token budget cap
        files_kept: Number of files kept in context
        files_omitted: Number of files omitted from context
        phase_outcome: Optional terminal phase outcome (COMPLETE, FAILED, BLOCKED, etc.)
        embedding_cache_hits: Optional cache hit count
        embedding_cache_misses: Optional cache miss count
        embedding_calls_made: Optional total embedding API calls made
        embedding_cap_value: Optional embedding cap value used
        embedding_fallback_reason: Optional reason for lexical fallback
        deliverables_count: Optional number of deliverables in phase
        context_files_total: Optional total files before budgeting

    Returns:
        Created or existing TokenEfficiencyMetrics record
    """
    # BUILD-146 P17.1: Fast-path idempotency check (avoids insert attempt when already exists)
    # If phase_outcome is specified, check for existing record with that outcome
    if phase_outcome:
        existing = (
            db.query(TokenEfficiencyMetrics)
            .filter(
                TokenEfficiencyMetrics.run_id == run_id,
                TokenEfficiencyMetrics.phase_id == phase_id,
                TokenEfficiencyMetrics.phase_outcome == phase_outcome,
            )
            .first()
        )

        if existing:
            # Already recorded for this outcome - return existing record without duplication
            return existing

    # BUILD-146 P17.x: Create new record
    metrics = TokenEfficiencyMetrics(
        run_id=run_id,
        phase_id=phase_id,
        artifact_substitutions=artifact_substitutions,
        tokens_saved_artifacts=tokens_saved_artifacts,
        budget_mode=budget_mode,
        budget_used=budget_used,
        budget_cap=budget_cap,
        files_kept=files_kept,
        files_omitted=files_omitted,
        phase_outcome=phase_outcome,
        embedding_cache_hits=embedding_cache_hits,
        embedding_cache_misses=embedding_cache_misses,
        embedding_calls_made=embedding_calls_made,
        embedding_cap_value=embedding_cap_value,
        embedding_fallback_reason=embedding_fallback_reason,
        deliverables_count=deliverables_count,
        context_files_total=context_files_total,
        created_at=datetime.now(timezone.utc),
    )

    db.add(metrics)

    try:
        # BUILD-146 P17.x: Attempt commit
        db.commit()
        db.refresh(metrics)
        return metrics
    except IntegrityError:
        # BUILD-146 P17.x: Race condition - another writer inserted same terminal outcome
        # This happens when DB unique index (run_id, phase_id, phase_outcome) is violated
        # Rollback failed transaction, then re-query for existing record
        db.rollback()

        # Re-query for existing record (must exist if IntegrityError was raised)
        if phase_outcome:
            existing = (
                db.query(TokenEfficiencyMetrics)
                .filter(
                    TokenEfficiencyMetrics.run_id == run_id,
                    TokenEfficiencyMetrics.phase_id == phase_id,
                    TokenEfficiencyMetrics.phase_outcome == phase_outcome,
                )
                .first()
            )

            if existing:
                # Found existing record created by concurrent writer
                return existing

        # If we get here, something unexpected happened (shouldn't be possible)
        # Re-raise to make the error visible
        raise


def get_token_efficiency_stats(db: Session, run_id: str) -> Dict:
    """Get aggregated token efficiency statistics for a run.

    Args:
        db: Database session
        run_id: Run identifier

    Returns:
        Dictionary with aggregated token efficiency stats
    """
    metrics = db.query(TokenEfficiencyMetrics).filter(TokenEfficiencyMetrics.run_id == run_id).all()

    if not metrics:
        return {
            "run_id": run_id,
            "total_phases": 0,
            "total_artifact_substitutions": 0,
            "total_tokens_saved_artifacts": 0,
            "total_budget_used": 0,
            "total_budget_cap": 0,
            "total_files_kept": 0,
            "total_files_omitted": 0,
            "semantic_mode_count": 0,
            "lexical_mode_count": 0,
            "avg_artifact_substitutions_per_phase": 0.0,
            "avg_tokens_saved_per_phase": 0.0,
            "budget_utilization": 0.0,
        }

    total_artifact_substitutions = sum(m.artifact_substitutions for m in metrics)
    total_tokens_saved_artifacts = sum(m.tokens_saved_artifacts for m in metrics)
    total_budget_used = sum(m.budget_used for m in metrics)
    total_budget_cap = sum(m.budget_cap for m in metrics)
    total_files_kept = sum(m.files_kept for m in metrics)
    total_files_omitted = sum(m.files_omitted for m in metrics)
    semantic_mode_count = sum(1 for m in metrics if m.budget_mode == "semantic")
    lexical_mode_count = sum(1 for m in metrics if m.budget_mode == "lexical")

    # BUILD-145 deployment hardening: Add phase outcome breakdown
    outcome_counts = {}
    for m in metrics:
        outcome = m.phase_outcome or "UNKNOWN"
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    return {
        "run_id": run_id,
        "total_phases": len(metrics),
        "total_artifact_substitutions": total_artifact_substitutions,
        "total_tokens_saved_artifacts": total_tokens_saved_artifacts,
        "total_budget_used": total_budget_used,
        "total_budget_cap": total_budget_cap,
        "total_files_kept": total_files_kept,
        "total_files_omitted": total_files_omitted,
        "semantic_mode_count": semantic_mode_count,
        "lexical_mode_count": lexical_mode_count,
        "avg_artifact_substitutions_per_phase": (
            total_artifact_substitutions / len(metrics) if metrics else 0.0
        ),
        "avg_tokens_saved_per_phase": (
            total_tokens_saved_artifacts / len(metrics) if metrics else 0.0
        ),
        "budget_utilization": (
            total_budget_used / total_budget_cap if total_budget_cap > 0 else 0.0
        ),
        "phase_outcome_counts": outcome_counts,  # {"COMPLETE": 10, "FAILED": 2, "UNKNOWN": 1}
    }


def estimate_doctor_tokens_avoided(
    db: Session,
    run_id: str,
    doctor_model: Optional[str] = None,
) -> tuple[int, int, str]:
    """
    Estimate tokens that would be consumed by a Doctor call using median baseline.

    BUILD-146 P3: Conservative counterfactual estimation for Doctor skip ROI.
    - NOT actual tokens saved (use A/B deltas for that)
    - Uses median of historical Doctor calls to avoid overcount
    - Prioritizes run-local baseline, falls back to global baseline

    Args:
        db: Database session
        run_id: Current run ID (for run-local baseline)
        doctor_model: Optional Doctor model type ("cheap", "strong")

    Returns:
        Tuple of (estimate, sample_size, source):
        - estimate: Median tokens per Doctor call (conservative)
        - sample_size: Number of samples in baseline
        - source: "run_local", "global", or "fallback"
    """

    # Try run-local baseline first (same run, same doctor_model if specified)
    query = db.query(LlmUsageEvent.total_tokens).filter(
        LlmUsageEvent.run_id == run_id,
        LlmUsageEvent.is_doctor_call,
    )
    if doctor_model:
        query = query.filter(LlmUsageEvent.doctor_model == doctor_model)

    run_local_samples = query.all()

    if len(run_local_samples) >= 3:  # Require at least 3 samples for median
        tokens = sorted([s[0] for s in run_local_samples])
        median_idx = len(tokens) // 2
        median_tokens = tokens[median_idx]
        return (median_tokens, len(tokens), "run_local")

    # Fallback to global baseline (last 100 Doctor calls, any run)
    query = db.query(LlmUsageEvent.total_tokens).filter(
        LlmUsageEvent.is_doctor_call,
    )
    if doctor_model:
        query = query.filter(LlmUsageEvent.doctor_model == doctor_model)

    global_samples = query.order_by(LlmUsageEvent.created_at.desc()).limit(100).all()

    if len(global_samples) >= 3:
        tokens = sorted([s[0] for s in global_samples])
        median_idx = len(tokens) // 2
        median_tokens = tokens[median_idx]
        return (median_tokens, len(tokens), "global")

    # Last resort: conservative fallback estimate
    # Use 10k for cheap Doctor, 15k for strong, 12k if unknown
    fallback_estimate = {
        "cheap": 10000,
        "strong": 15000,
    }.get(doctor_model or "", 12000)
    return (fallback_estimate, 0, "fallback")


def record_phase6_metrics(
    db: Session,
    run_id: str,
    phase_id: str,
    failure_hardening_triggered: bool = False,
    failure_pattern_detected: Optional[str] = None,
    failure_hardening_mitigated: bool = False,
    doctor_call_skipped: bool = False,
    doctor_tokens_avoided_estimate: int = 0,
    estimate_coverage_n: Optional[int] = None,
    estimate_source: Optional[str] = None,
    intention_context_injected: bool = False,
    intention_context_chars: int = 0,
    intention_context_source: Optional[str] = None,
    plan_normalization_used: bool = False,
    plan_normalization_confidence: Optional[int] = None,
    plan_normalization_warnings: int = 0,
    plan_deliverables_count: Optional[int] = None,
    plan_scope_size_bytes: Optional[int] = None,
) -> Phase6Metrics:
    """
    Record Phase 6 True Autonomy feature effectiveness metrics.

    Args:
        db: Database session
        run_id: Run ID
        phase_id: Phase ID
        failure_hardening_triggered: Whether failure hardening was triggered
        failure_pattern_detected: Pattern ID if detected (e.g., "python_missing_dep")
        failure_hardening_mitigated: Whether failure was mitigated without Doctor
        doctor_call_skipped: Whether Doctor call was skipped due to mitigation
        doctor_tokens_avoided_estimate: Counterfactual estimate of Doctor tokens avoided (median baseline)
        estimate_coverage_n: Sample size used for baseline estimate
        estimate_source: Source of baseline ("run_local", "global", "fallback")
        intention_context_injected: Whether intention context was injected
        intention_context_chars: Number of characters of intention context
        intention_context_source: Source of intention context ("memory", "fallback")
        plan_normalization_used: Whether plan normalizer was used
        plan_normalization_confidence: Confidence score (1-10)
        plan_normalization_warnings: Number of normalization warnings
        plan_deliverables_count: Number of deliverables in normalized plan
        plan_scope_size_bytes: Size of normalized plan scope in bytes

    Returns:
        Created Phase6Metrics record
    """
    metrics = Phase6Metrics(
        run_id=run_id,
        phase_id=phase_id,
        failure_hardening_triggered=failure_hardening_triggered,
        failure_pattern_detected=failure_pattern_detected,
        failure_hardening_mitigated=failure_hardening_mitigated,
        doctor_call_skipped=doctor_call_skipped,
        doctor_tokens_avoided_estimate=doctor_tokens_avoided_estimate,
        estimate_coverage_n=estimate_coverage_n,
        estimate_source=estimate_source,
        intention_context_injected=intention_context_injected,
        intention_context_chars=intention_context_chars,
        intention_context_source=intention_context_source,
        plan_normalization_used=plan_normalization_used,
        plan_normalization_confidence=plan_normalization_confidence,
        plan_normalization_warnings=plan_normalization_warnings,
        plan_deliverables_count=plan_deliverables_count,
        plan_scope_size_bytes=plan_scope_size_bytes,
    )

    db.add(metrics)
    db.commit()
    db.refresh(metrics)

    return metrics


def get_phase6_metrics_summary(db: Session, run_id: str, limit: int = 1000) -> Dict:
    """
    Get aggregated Phase 6 metrics for a run.

    Args:
        db: Database session
        run_id: Run ID
        limit: Maximum number of phase metrics to aggregate (default 1000, prevents slow queries)

    Returns:
        Dictionary with aggregated Phase 6 metrics
    """
    # BUILD-146 Ops hardening: Add limit to prevent slow queries on huge runs
    metrics = db.query(Phase6Metrics).filter(Phase6Metrics.run_id == run_id).limit(limit).all()

    if not metrics:
        return {
            "total_phases": 0,
            "failure_hardening_triggered_count": 0,
            "failure_patterns_detected": {},
            "doctor_calls_skipped_count": 0,
            "total_doctor_tokens_avoided_estimate": 0,
            "estimate_coverage_stats": {},
            "intention_context_injected_count": 0,
            "total_intention_context_chars": 0,
            "plan_normalization_used": False,
        }

    # Aggregate metrics
    failure_hardening_triggered_count = sum(1 for m in metrics if m.failure_hardening_triggered)
    doctor_calls_skipped_count = sum(1 for m in metrics if m.doctor_call_skipped)
    total_doctor_tokens_avoided_estimate = sum(m.doctor_tokens_avoided_estimate for m in metrics)
    intention_context_injected_count = sum(1 for m in metrics if m.intention_context_injected)
    total_intention_context_chars = sum(m.intention_context_chars for m in metrics)

    # BUILD-146 P3: Collect estimate coverage stats
    estimate_coverage_stats = {}
    for m in metrics:
        if m.estimate_source:
            source = m.estimate_source
            if source not in estimate_coverage_stats:
                estimate_coverage_stats[source] = {"count": 0, "total_n": 0}
            estimate_coverage_stats[source]["count"] += 1
            if m.estimate_coverage_n:
                estimate_coverage_stats[source]["total_n"] += m.estimate_coverage_n

    # Count failure patterns
    failure_patterns_detected = {}
    for m in metrics:
        if m.failure_pattern_detected:
            failure_patterns_detected[m.failure_pattern_detected] = (
                failure_patterns_detected.get(m.failure_pattern_detected, 0) + 1
            )

    # Check if plan normalization was used (run-level, not phase-level)
    plan_normalization_used = any(m.plan_normalization_used for m in metrics)

    return {
        "total_phases": len(metrics),
        "failure_hardening_triggered_count": failure_hardening_triggered_count,
        "failure_patterns_detected": failure_patterns_detected,
        "doctor_calls_skipped_count": doctor_calls_skipped_count,
        "total_doctor_tokens_avoided_estimate": total_doctor_tokens_avoided_estimate,
        "estimate_coverage_stats": estimate_coverage_stats,  # {"run_local": {"count": 5, "total_n": 25}, ...}
        "intention_context_injected_count": intention_context_injected_count,
        "total_intention_context_chars": total_intention_context_chars,
        "avg_intention_context_chars_per_phase": (
            total_intention_context_chars / intention_context_injected_count
            if intention_context_injected_count > 0
            else 0.0
        ),
        "plan_normalization_used": plan_normalization_used,
    }
