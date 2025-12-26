"""Database models for runs, tiers, and phases (Chunk A implementation)"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Float,
)
from sqlalchemy.orm import relationship, synonym

from .database import Base


class RunState(str, Enum):
    """Run lifecycle states per §3 of v7 playbook"""

    QUEUED = "QUEUED"  # Legacy state for backwards compatibility
    PLAN_BOOTSTRAP = "PLAN_BOOTSTRAP"
    RUN_CREATED = "RUN_CREATED"
    PHASE_QUEUEING = "PHASE_QUEUEING"
    PHASE_EXECUTION = "PHASE_EXECUTION"
    GATE = "GATE"
    CI_RUNNING = "CI_RUNNING"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"
    DONE_SUCCESS = "DONE_SUCCESS"
    DONE_FAILED_BUDGET_EXHAUSTED = "DONE_FAILED_BUDGET_EXHAUSTED"
    DONE_FAILED_POLICY_VIOLATION = "DONE_FAILED_POLICY_VIOLATION"
    DONE_FAILED_REQUIRES_HUMAN_REVIEW = "DONE_FAILED_REQUIRES_HUMAN_REVIEW"
    DONE_FAILED_ENVIRONMENT = "DONE_FAILED_ENVIRONMENT"


class PhaseState(str, Enum):
    """Phase execution states"""

    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    GATE = "GATE"
    CI_RUNNING = "CI_RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TierState(str, Enum):
    """Tier completion states"""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class Run(Base):
    """Autonomous build run model"""

    __tablename__ = "runs"

    id = Column(String, primary_key=True, index=True)
    # Backwards compatibility: some legacy API code still references Run.run_id.
    # Provide a synonym so both "id" and "run_id" point to the same column.
    run_id = synonym("id")
    state = Column(SQLEnum(RunState), nullable=False, default=RunState.RUN_CREATED)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Configuration
    safety_profile = Column(String, nullable=False, default="normal")  # normal or safety_critical
    run_scope = Column(String, nullable=False, default="multi_tier")  # multi_tier or single_tier

    # Budgets and caps (per §9.1 of v7 playbook)
    token_cap = Column(Integer, nullable=False, default=5_000_000)
    max_phases = Column(Integer, nullable=False, default=25)
    max_duration_minutes = Column(Integer, nullable=False, default=120)
    max_minor_issues_total = Column(Integer, nullable=True)  # computed as phases_in_run * 3

    # Current usage
    tokens_used = Column(Integer, nullable=False, default=0)
    ci_runs_used = Column(Integer, nullable=False, default=0)
    minor_issues_count = Column(Integer, nullable=False, default=0)
    major_issues_count = Column(Integer, nullable=False, default=0)

    # Status flags
    promotion_eligible_to_main = Column(String, nullable=False, default="false")  # true/false
    debt_status = Column(String, nullable=True)  # e.g. "clean", "has_minor_issues", "excess_minor_issues"
    failure_reason = Column(Text, nullable=True)

    # Goal anchor for drift detection (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
    goal_anchor = Column(Text, nullable=True)  # Short text describing the run's goal

    # Relationships
    tiers = relationship("Tier", back_populates="run", cascade="all, delete-orphan")
    phases = relationship("Phase", back_populates="run", cascade="all, delete-orphan")


class Tier(Base):
    """Tier grouping of phases"""

    __tablename__ = "tiers"

    id = Column(Integer, primary_key=True, index=True)
    tier_id = Column(String, nullable=False, index=True)  # e.g. "T1", "T2", "Auth & Security"
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)

    # Ordering
    tier_index = Column(Integer, nullable=False)

    # Metadata
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    state = Column(SQLEnum(TierState), nullable=False, default=TierState.PENDING)

    # Budgets (per §9.2 of v7 playbook)
    token_cap = Column(Integer, nullable=True)
    ci_run_cap = Column(Integer, nullable=True)
    max_minor_issues_tolerated = Column(Integer, nullable=True)
    max_major_issues_tolerated = Column(Integer, nullable=False, default=0)

    # Current usage
    tokens_used = Column(Integer, nullable=False, default=0)
    ci_runs_used = Column(Integer, nullable=False, default=0)
    minor_issues_count = Column(Integer, nullable=False, default=0)
    major_issues_count = Column(Integer, nullable=False, default=0)

    # Cleanliness status (per §10.3 of v7 playbook)
    cleanliness = Column(String, nullable=False, default="clean")  # "clean" or "not_clean"

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="tiers")
    phases = relationship("Phase", back_populates="tier", cascade="all, delete-orphan")


class Phase(Base):
    """Individual phase of work within a tier"""

    __tablename__ = "phases"
    __table_args__ = (
        # NOTE: `phase_id` is NOT globally unique across runs in existing data.
        # Many subsystems (including TokenEstimationV2 DB telemetry) need a stable phase identifier.
        # Enforce uniqueness at the (run_id, phase_id) level.
        UniqueConstraint("run_id", "phase_id", name="uq_phases_run_id_phase_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    phase_id = Column(String, nullable=False, index=True)  # e.g. "F2.3", "auth-001"
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    tier_id = Column(Integer, ForeignKey("tiers.id"), nullable=False)

    # Ordering
    phase_index = Column(Integer, nullable=False)

    # Metadata
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    state = Column(SQLEnum(PhaseState), nullable=False, default=PhaseState.QUEUED)

    # Classification (per §4.1 of v7 playbook)
    task_category = Column(String, nullable=True)  # e.g. schema_change, cross_cutting_refactor
    complexity = Column(String, nullable=True)  # low, medium, high
    builder_mode = Column(String, nullable=True)  # e.g. tweak_light, scaffolding_heavy

    # Scope configuration (file paths and read-only context)
    scope = Column(JSON, nullable=True)  # {"paths": [...], "read_only_context": [...]}

    # Budgets (per §9.3 of v7 playbook)
    max_builder_attempts = Column(Integer, nullable=True)
    max_auditor_attempts = Column(Integer, nullable=True)
    incident_token_cap = Column(Integer, nullable=True)

    # Current usage
    builder_attempts = Column(Integer, nullable=False, default=0)
    auditor_attempts = Column(Integer, nullable=False, default=0)
    tokens_used = Column(Integer, nullable=False, default=0)

    # Issue tracking
    minor_issues_count = Column(Integer, nullable=False, default=0)
    major_issues_count = Column(Integer, nullable=False, default=0)
    issue_state = Column(String, nullable=False, default="no_issues")  # no_issues, has_minor_issues, has_major_issues

    # Quality gate (Phase 2)
    quality_level = Column(String, nullable=True)  # "ok" | "needs_review" | "blocked"
    quality_blocked = Column(Boolean, nullable=False, default=False)

    # BUILD-050 Phase 2: Decoupled attempt counters for non-destructive replanning
    retry_attempt = Column(Integer, nullable=False, default=0)  # Monotonic retry counter (for hints accumulation and model escalation)
    revision_epoch = Column(Integer, nullable=False, default=0)  # Replan counter (increments when Doctor revises approach)
    escalation_level = Column(Integer, nullable=False, default=0)  # Model escalation level (0=base, 1=escalated, etc.)

    # Attempt tracking metadata
    last_attempt_timestamp = Column(DateTime, nullable=True)  # When last attempt occurred
    last_failure_reason = Column(String, nullable=True)  # Most recent failure status

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="phases")
    tier = relationship("Tier", back_populates="phases")


# ---------------------------------------------------------------------------
# Planning + decision logging (Phase 2 memory/context)
# ---------------------------------------------------------------------------


class PlanningArtifact(Base):
    """Versioned planning artifacts (templates, prompts, compiled analyses)."""

    __tablename__ = "planning_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    project_id = Column(String, nullable=True, index=True)
    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    hash = Column(String, nullable=False)
    author = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active")  # active|superseded|archived
    replaced_by = Column(Integer, nullable=True)
    vector_id = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("path", "version", name="uq_planning_artifacts_path_version"),
    )


class PlanChange(Base):
    """Tracked plan/template revisions with rationale."""

    __tablename__ = "plan_changes"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=True, index=True)
    phase_id = Column(String, nullable=True, index=True)
    project_id = Column(String, nullable=True, index=True)
    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    author = Column(String, nullable=True)
    summary = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    replaces_version = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="active")  # active|superseded|archived
    replaced_by = Column(Integer, nullable=True)
    vector_id = Column(String, nullable=True)


class DecisionLog(Base):
    """Decision log entries for doctor/replan triggers."""

    __tablename__ = "decision_log"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=True, index=True)
    phase_id = Column(String, nullable=True, index=True)
    project_id = Column(String, nullable=True, index=True)
    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    trigger = Column(String, nullable=True)
    alternatives = Column(Text, nullable=True)
    choice = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    vector_id = Column(String, nullable=True)


class ApprovalRequest(Base):
    """Approval requests for BUILD-113 risky or ambiguous decisions."""

    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)
    context = Column(String, nullable=False)  # "build113_risky_decision", "build113_ambiguous_decision", "troubleshoot"
    decision_info = Column(JSON, nullable=True)  # Decision metadata
    deletion_info = Column(JSON, nullable=True)  # Deletion details if applicable

    # Timestamps
    requested_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    responded_at = Column(DateTime, nullable=True)
    timeout_at = Column(DateTime, nullable=True)  # When request expires

    # Status and response
    status = Column(String, nullable=False, default="pending")  # pending, approved, rejected, timeout, error
    response_method = Column(String, nullable=True)  # "telegram", "dashboard", "auto", "timeout"
    approval_reason = Column(Text, nullable=True)
    rejected_reason = Column(Text, nullable=True)

    # Telegram integration
    telegram_message_id = Column(String, nullable=True)
    telegram_sent = Column(Boolean, nullable=False, default=False)
    telegram_error = Column(Text, nullable=True)


class GovernanceRequest(Base):
    """Governance requests for BUILD-127 Phase 2 protected path modifications."""

    __tablename__ = "governance_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, nullable=False, index=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    # Request details
    requested_paths = Column(Text, nullable=False)  # JSON array of paths
    justification = Column(Text, nullable=True)
    risk_level = Column(String, nullable=True)  # "low", "medium", "high", "critical"

    # Approval status
    auto_approved = Column(Boolean, nullable=False, default=False)
    approved = Column(Boolean, nullable=True, index=True)  # None = pending, True/False = decided
    approved_by = Column(String, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )


class TokenEstimationV2Event(Base):
    """TokenEstimationV2 telemetry events for BUILD-129 overhead model validation"""

    __tablename__ = "token_estimation_v2_events"
    __table_args__ = (
        # Link telemetry to the specific phase instance within a run.
        # IMPORTANT: `phases.phase_id` is not globally unique; use composite key.
        ForeignKeyConstraint(
            ["run_id", "phase_id"],
            ["phases.run_id", "phases.phase_id"],
            ondelete="CASCADE",
            name="fk_token_est_v2_run_phase",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, name="event_id")
    run_id = Column(String, ForeignKey("runs.id"), nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    # Timestamp
    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Estimation inputs
    category = Column(String, nullable=False, index=True)
    complexity = Column(String, nullable=False, index=True)
    deliverable_count = Column(Integer, nullable=False, index=True)
    deliverables_json = Column(Text, nullable=False)  # JSON array of deliverable paths

    # Token predictions vs actuals
    predicted_output_tokens = Column(Integer, nullable=False)
    actual_output_tokens = Column(Integer, nullable=False)
    selected_budget = Column(Integer, nullable=False)

    # Outcome
    success = Column(Boolean, nullable=False, index=True)
    truncated = Column(Boolean, nullable=False, default=False, index=True)
    stop_reason = Column(String, nullable=True)
    model = Column(String, nullable=False)

    # Calculated metrics
    smape_percent = Column(Float, nullable=True)  # 200 * |pred - actual| / (|pred| + |actual|)
    waste_ratio = Column(Float, nullable=True)    # pred / actual
    underestimated = Column(Boolean, nullable=True, index=True)  # actual > pred

    # BUILD-129 Phase 3: Truncation awareness and feature tracking
    # When truncated=True, actual_output_tokens is a LOWER BOUND, not exact measurement
    is_truncated_output = Column(Boolean, nullable=False, default=False, index=True)

    # Documentation synthesis features (for DOC_SYNTHESIS tasks)
    api_reference_required = Column(Boolean, nullable=True)  # API docs needed
    examples_required = Column(Boolean, nullable=True)       # Code examples needed
    research_required = Column(Boolean, nullable=True)       # Investigation needed
    usage_guide_required = Column(Boolean, nullable=True)    # Usage docs needed
    context_quality = Column(String, nullable=True)          # "none", "some", "strong"

    # BUILD-129 Phase 3 P3: SOT (Source of Truth) file tracking
    # SOT files (BUILD_LOG.md, BUILD_HISTORY.md, etc.) require different estimation
    is_sot_file = Column(Boolean, nullable=True, default=False)  # Is this an SOT file update?
    sot_file_name = Column(String, nullable=True)                # SOT file basename (e.g., "build_log.md")
    sot_entry_count_hint = Column(Integer, nullable=True)        # Number of entries to write (proxy)

    # Timestamp
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )


class TokenBudgetEscalationEvent(Base):
    """
    Token budget escalation telemetry (BUILD-129 Phase 3 P10).

    Why a separate table:
    - TokenEstimationV2Event is recorded inside the builder call (anthropic_clients.py).
    - P10 decisions are made later in autonomous_executor.py after seeing truncation/utilization.
    - This table records the escalation decision at the moment it is made (base/source/retry).
    """

    __tablename__ = "token_budget_escalation_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "phase_id"],
            ["phases.run_id", "phases.phase_id"],
            ondelete="CASCADE",
            name="fk_token_budget_escalation_run_phase",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, name="event_id")
    run_id = Column(String, ForeignKey("runs.id"), nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    attempt_index = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)  # "truncation" or "utilization"
    was_truncated = Column(Boolean, nullable=False, default=False)
    output_utilization = Column(Float, nullable=True)  # percent

    escalation_factor = Column(Float, nullable=False)
    base_value = Column(Integer, nullable=False)
    base_source = Column(String, nullable=False)
    retry_max_tokens = Column(Integer, nullable=False)

    # Candidate values (for debugging / post-hoc validation)
    selected_budget = Column(Integer, nullable=True)
    actual_max_tokens = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
