"""LLM usage tracking for token consumption monitoring"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, JSON
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
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    
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

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

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
    stats = db.query(DoctorUsageStats).filter(
        DoctorUsageStats.run_id == event.run_id
    ).first()
    
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
        prev_call = db.query(LlmUsageEvent).filter(
            LlmUsageEvent.run_id == event.run_id,
            LlmUsageEvent.phase_id == event.phase_id,
            LlmUsageEvent.is_doctor_call == True,
            LlmUsageEvent.doctor_model == "cheap",
        ).order_by(LlmUsageEvent.created_at.desc()).first()
        
        if prev_call:
            stats.doctor_escalations += 1
    
    # Update action distribution
    if event.doctor_action:
        if stats.doctor_actions is None:
            stats.doctor_actions = {}
        stats.doctor_actions[event.doctor_action] = stats.doctor_actions.get(event.doctor_action, 0) + 1
    
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
    stats = db.query(DoctorUsageStats).filter(
        DoctorUsageStats.run_id == run_id
    ).first()
    
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
            if stats.doctor_calls_total > 0 else 0
        ),
        "escalation_frequency": (
            stats.doctor_escalations / stats.doctor_calls_total
            if stats.doctor_calls_total > 0 else 0
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
) -> TokenEfficiencyMetrics:
    """Record token efficiency metrics for a phase.

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

    Returns:
        Created TokenEfficiencyMetrics record
    """
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
        created_at=datetime.now(timezone.utc),
    )

    db.add(metrics)
    db.commit()
    db.refresh(metrics)

    return metrics


def get_token_efficiency_stats(db: Session, run_id: str) -> Dict:
    """Get aggregated token efficiency statistics for a run.
    
    Args:
        db: Database session
        run_id: Run identifier
    
    Returns:
        Dictionary with aggregated token efficiency stats
    """
    metrics = db.query(TokenEfficiencyMetrics).filter(
        TokenEfficiencyMetrics.run_id == run_id
    ).all()
    
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
    }
