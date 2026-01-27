"""Database models for runs, tiers, and phases (Chunk A implementation)"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DECIMAL, JSON, BigInteger, Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    debt_status = Column(
        String, nullable=True
    )  # e.g. "clean", "has_minor_issues", "excess_minor_issues"
    failure_reason = Column(Text, nullable=True)

    # Goal anchor for drift detection (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
    goal_anchor = Column(Text, nullable=True)  # Short text describing the run's goal

    # Composite indexes for high-traffic queries
    __table_args__ = (Index("ix_runs_state_created", "state", "created_at"),)

    # Relationships
    tiers = relationship("Tier", back_populates="run", cascade="all, delete-orphan")
    phases = relationship("Phase", back_populates="run", cascade="all, delete-orphan")


class Tier(Base):
    """Tier grouping of phases"""

    __tablename__ = "tiers"

    id = Column(Integer, primary_key=True, index=True)
    tier_id = Column(String, nullable=False, index=True)  # e.g. "T1", "T2", "Auth & Security"
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)

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
        # Composite indexes for high-traffic queries
        Index("ix_phases_run_state", "run_id", "state"),
        Index("ix_phases_state_started", "state", "started_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    phase_id = Column(String, nullable=False, index=True)  # e.g. "F2.3", "auth-001"
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tier_id = Column(Integer, ForeignKey("tiers.id"), nullable=False)

    # Ordering
    phase_index = Column(Integer, nullable=False)

    # Metadata
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    state = Column(SQLEnum(PhaseState), nullable=False, default=PhaseState.QUEUED, index=True)

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
    issue_state = Column(
        String, nullable=False, default="no_issues"
    )  # no_issues, has_minor_issues, has_major_issues

    # Quality gate (Phase 2)
    quality_level = Column(String, nullable=True)  # "ok" | "needs_review" | "blocked"
    quality_blocked = Column(Boolean, nullable=False, default=False)

    # BUILD-050 Phase 2: Decoupled attempt counters for non-destructive replanning
    retry_attempt = Column(
        Integer, nullable=False, default=0
    )  # Monotonic retry counter (for hints accumulation and model escalation)
    revision_epoch = Column(
        Integer, nullable=False, default=0
    )  # Replan counter (increments when Doctor revises approach)
    escalation_level = Column(
        Integer, nullable=False, default=0
    )  # Model escalation level (0=base, 1=escalated, etc.)

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
    context = Column(
        String, nullable=False
    )  # "build113_risky_decision", "build113_ambiguous_decision", "troubleshoot"
    decision_info = Column(JSON, nullable=True)  # Decision metadata
    deletion_info = Column(JSON, nullable=True)  # Deletion details if applicable

    # Timestamps
    requested_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    responded_at = Column(DateTime, nullable=True)
    timeout_at = Column(DateTime, nullable=True)  # When request expires

    # Status and response
    status = Column(
        String, nullable=False, default="pending"
    )  # pending, approved, rejected, timeout, error
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
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
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
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
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
        # Composite indexes for high-traffic telemetry queries
        Index("ix_telemetry_run_category", "run_id", "category"),
        Index("ix_telemetry_category_timestamp", "category", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True, name="event_id")
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    # Timestamp
    timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
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
    # BUILD-142 PARITY: Separate estimator intent from final ceiling
    actual_max_tokens = Column(Integer, nullable=True)  # Final ceiling after P4 enforcement

    # Outcome
    success = Column(Boolean, nullable=False, index=True)
    truncated = Column(Boolean, nullable=False, default=False, index=True)
    stop_reason = Column(String, nullable=True)
    model = Column(String, nullable=False)

    # Calculated metrics
    smape_percent = Column(Float, nullable=True)  # 200 * |pred - actual| / (|pred| + |actual|)
    waste_ratio = Column(Float, nullable=True)  # pred / actual
    underestimated = Column(Boolean, nullable=True, index=True)  # actual > pred

    # BUILD-129 Phase 3: Truncation awareness and feature tracking
    # When truncated=True, actual_output_tokens is a LOWER BOUND, not exact measurement
    is_truncated_output = Column(Boolean, nullable=False, default=False, index=True)

    # Documentation synthesis features (for DOC_SYNTHESIS tasks)
    api_reference_required = Column(Boolean, nullable=True)  # API docs needed
    examples_required = Column(Boolean, nullable=True)  # Code examples needed
    research_required = Column(Boolean, nullable=True)  # Investigation needed
    usage_guide_required = Column(Boolean, nullable=True)  # Usage docs needed
    context_quality = Column(String, nullable=True)  # "none", "some", "strong"

    # BUILD-129 Phase 3 P3: SOT (Source of Truth) file tracking
    # SOT files (BUILD_LOG.md, BUILD_HISTORY.md, etc.) require different estimation
    is_sot_file = Column(Boolean, nullable=True, default=False)  # Is this an SOT file update?
    sot_file_name = Column(String, nullable=True)  # SOT file basename (e.g., "build_log.md")
    sot_entry_count_hint = Column(Integer, nullable=True)  # Number of entries to write (proxy)

    # Timestamp
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )


class PhaseOutcomeEvent(Base):
    """Track per-phase outcomes with stop reasons for ROAD-A telemetry foundation.

    Enables automated analysis (ROAD-B), anomaly detection (ROAD-G), and model optimization (ROAD-L).
    """

    __tablename__ = "phase_outcome_events"
    __table_args__ = (
        Index("ix_phase_outcome_run_id", "run_id"),
        Index("ix_phase_outcome_phase_id", "phase_id"),
        Index("ix_phase_outcome_outcome", "phase_outcome"),
        Index("ix_phase_outcome_timestamp", "timestamp"),
        Index("ix_phase_outcome_phase_type", "phase_type"),
    )

    id = Column(Integer, primary_key=True)
    run_id = Column(String, nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)
    phase_type = Column(String, nullable=True)  # For ROAD-L model optimization
    phase_outcome = Column(
        SQLEnum("SUCCESS", "FAILED", "TIMEOUT", "STUCK", name="phase_outcome"), nullable=False
    )
    stop_reason = Column(String, nullable=True)  # e.g., "max_tokens", "retry_limit", "user_abort"
    stuck_decision_rationale = Column(String, nullable=True)
    tokens_used = Column(Integer, nullable=True)  # For cost tracking
    duration_seconds = Column(Float, nullable=True)  # For anomaly detection
    model_used = Column(String, nullable=True)  # For ROAD-L optimization
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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
        # Composite indexes for escalation event queries
        Index("ix_escalation_run_timestamp", "run_id", "timestamp"),
        Index("ix_escalation_reason_timestamp", "reason", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True, name="event_id")
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
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


class SOTRetrievalEvent(Base):
    """
    SOT (Source of Truth) retrieval telemetry - BUILD-155.

    Tracks per-phase SOT retrieval metrics to prevent silent prompt bloat
    and enable budget optimization. Records both gating decisions and
    actual retrieval/formatting outcomes.

    Why a separate table:
    - SOT retrieval happens in autonomous_executor.py during context assembly
    - Need to track both budget gating decisions AND actual char usage
    - Enables post-hoc analysis of SOT impact on token costs
    """

    __tablename__ = "sot_retrieval_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "phase_id"],
            ["phases.run_id", "phases.phase_id"],
            ondelete="CASCADE",
            name="fk_sot_retrieval_run_phase",
        ),
        # Composite indexes for SOT retrieval queries
        Index("ix_sot_run_include", "run_id", "include_sot"),
        Index("ix_sot_include_timestamp", "include_sot", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True, name="event_id")
    run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Budget gating (input decision)
    include_sot = Column(Boolean, nullable=False, index=True)  # Was SOT retrieval attempted?
    max_context_chars = Column(Integer, nullable=False)  # Budget allocated for total context
    sot_budget_chars = Column(Integer, nullable=False)  # Budget allocated specifically for SOT

    # Retrieval outcome (raw results before formatting)
    sot_chunks_retrieved = Column(Integer, nullable=False, default=0)  # Number of chunks returned
    sot_chars_raw = Column(Integer, nullable=False, default=0)  # Total chars in raw SOT chunks

    # Formatting outcome (after format_retrieved_context cap enforcement)
    total_context_chars = Column(Integer, nullable=False)  # Final formatted context length
    sot_chars_formatted = Column(
        Integer, nullable=True
    )  # SOT contribution after formatting (NULL if not included)

    # Utilization metrics
    budget_utilization_pct = Column(
        Float, nullable=False
    )  # total_context_chars / max_context_chars * 100
    sot_truncated = Column(
        Boolean, nullable=False, default=False
    )  # Was SOT section truncated during formatting?

    # Context composition (JSON list of section names included)
    sections_included = Column(JSON, nullable=True)  # e.g., ["code", "summaries", "errors", "sot"]

    # Retrieval configuration
    retrieval_enabled = Column(Boolean, nullable=False)  # AUTOPACK_SOT_RETRIEVAL_ENABLED setting
    top_k = Column(Integer, nullable=True)  # Number of chunks requested (from settings)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class DoctorOutcomeEvent(Base):
    """
    Doctor diagnostic outcome telemetry - IMP-DOCTOR-002.

    Tracks Doctor invocations and outcomes to measure effectiveness:
    - Was Doctor's recommendation followed?
    - Did the phase succeed after Doctor intervention?
    - What actions did Doctor recommend?

    Enables success rate tracking and Doctor effectiveness analysis.
    """

    __tablename__ = "doctor_outcome_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "phase_id"],
            ["phases.run_id", "phases.phase_id"],
            ondelete="CASCADE",
            name="fk_doctor_outcome_run_phase",
        ),
        # Composite indexes for Doctor outcome queries
        Index("ix_doctor_outcome_run_id", "run_id"),
        Index("ix_doctor_outcome_phase_id", "phase_id"),
        Index("ix_doctor_outcome_action", "doctor_action"),
        Index("ix_doctor_outcome_timestamp", "timestamp"),
        Index("ix_doctor_outcome_success", "phase_succeeded_after_doctor"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=False, index=True)
    phase_id = Column(String, nullable=False, index=True)

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Doctor invocation context
    error_category = Column(String, nullable=False)  # e.g., "auditor_reject", "ci_failure"
    builder_attempts = Column(Integer, nullable=False)  # Attempts before Doctor called

    # Doctor recommendation
    doctor_action = Column(
        String, nullable=False, index=True
    )  # e.g., "retry_with_hint", "replan", "skip"
    doctor_rationale = Column(String, nullable=True)  # Doctor's reasoning
    doctor_confidence = Column(Float, nullable=True)  # Doctor's confidence (0-1)
    builder_hint_provided = Column(
        Boolean, nullable=False, default=False
    )  # Did Doctor provide hint?

    # Follow-through tracking
    recommendation_followed = Column(
        Boolean, nullable=False, default=True, index=True
    )  # Was Doctor's action taken?

    # Outcome tracking (NULL if phase still in progress)
    phase_succeeded_after_doctor = Column(
        Boolean, nullable=True, index=True
    )  # Did phase eventually succeed?
    attempts_after_doctor = Column(Integer, nullable=True)  # Additional attempts after Doctor
    final_phase_outcome = Column(
        String, nullable=True
    )  # Final status: "COMPLETE", "FAILED", "SKIPPED", etc.

    # Cost tracking
    doctor_tokens_used = Column(Integer, nullable=True)  # Tokens used by Doctor call
    model_used = Column(String, nullable=True)  # Model used for Doctor (haiku/sonnet/opus)


class ABTestResult(Base):
    """A/B test comparison results - BUILD-146 P12.

    Stores pair comparisons between control and treatment runs
    with strict validity checks enforced.
    """

    __tablename__ = "ab_test_results"

    id = Column(Integer, primary_key=True)
    test_id = Column(String, nullable=False, index=True)  # e.g., "telemetry-v5-vs-v6"

    # Run pair
    control_run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    treatment_run_id = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)

    # Validity checks (MUST match for valid comparison)
    control_commit_sha = Column(String, nullable=False)
    treatment_commit_sha = Column(String, nullable=False)
    control_model_hash = Column(String, nullable=False)
    treatment_model_hash = Column(String, nullable=False)

    # Validity status
    is_valid = Column(Boolean, nullable=False, default=True, index=True)
    validity_errors = Column(JSON)  # List of validation failures

    # Metrics deltas (treatment - control)
    token_delta = Column(Integer)  # Positive = treatment used more tokens
    time_delta_seconds = Column(Float)  # Positive = treatment took longer
    success_rate_delta = Column(
        Float
    )  # Positive = treatment had better success rate (percentage points)

    # Aggregated results from control run
    control_total_tokens = Column(Integer)
    control_phases_complete = Column(Integer)
    control_phases_failed = Column(Integer)
    control_total_phases = Column(Integer)

    # Aggregated results from treatment run
    treatment_total_tokens = Column(Integer)
    treatment_phases_complete = Column(Integer)
    treatment_phases_failed = Column(Integer)
    treatment_total_phases = Column(Integer)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String)  # Script or user that generated result

    # Note: Index constraints are defined in migration script for clarity


# ==============================================================================
# Storage Optimizer Models (BUILD-149 Phase 2)
# ==============================================================================


class StorageScan(Base):
    """
    Storage scan metadata persisted to database.

    Tracks scan history, allowing trend analysis and comparison over time.
    """

    __tablename__ = "storage_scans"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    scan_type = Column(String(20), nullable=False)  # 'drive' or 'directory'
    scan_target = Column(String(500), nullable=False)  # 'C:' or 'c:/dev/Autopack'
    max_depth = Column(Integer, nullable=True)
    max_items = Column(Integer, nullable=True)
    policy_version = Column(String(50), nullable=True)

    # Scan results
    total_items_scanned = Column(Integer, nullable=False, default=0)
    total_size_bytes = Column(BigInteger, nullable=False, default=0)
    cleanup_candidates_count = Column(Integer, nullable=False, default=0)
    potential_savings_bytes = Column(BigInteger, nullable=False, default=0)

    # Performance
    scan_duration_seconds = Column(Integer, nullable=True)

    # Metadata
    created_by = Column(String(100), nullable=True)  # 'cli', 'api', 'scheduled'
    notes = Column(Text, nullable=True)


class CleanupCandidateDB(Base):
    """
    Cleanup candidate persisted to database.

    Tracks files/folders eligible for cleanup, approval status, and execution state.
    """

    __tablename__ = "cleanup_candidates"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(
        Integer, ForeignKey("storage_scans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # File info
    path = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    age_days = Column(Integer, nullable=True)
    last_modified = Column(DateTime, nullable=True)

    # Classification
    category = Column(String(50), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    requires_approval = Column(Boolean, nullable=False)

    # Approval state
    approval_status = Column(String(20), nullable=False, default="pending", index=True)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Execution state
    execution_status = Column(
        String(20), nullable=True
    )  # 'executing', 'completed', 'failed', 'skipped'
    executed_at = Column(DateTime, nullable=True)
    execution_error = Column(Text, nullable=True)

    # Compression (if applicable)
    compressed = Column(Boolean, nullable=False, default=False)
    compressed_path = Column(Text, nullable=True)
    compression_ratio = Column(DECIMAL(5, 2), nullable=True)
    compression_duration_seconds = Column(Integer, nullable=True)


class ApprovalDecision(Base):
    """
    User approval decision for batch cleanup.

    Records who approved what, when, and via which method.
    """

    __tablename__ = "approval_decisions"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(
        Integer, ForeignKey("storage_scans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Approval metadata
    approved_by = Column(String(100), nullable=False)
    approved_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    approval_method = Column(
        String(50), nullable=True
    )  # 'cli_interactive', 'api', 'telegram', 'automated'

    # Batch approval
    total_candidates = Column(Integer, nullable=False)
    total_size_bytes = Column(BigInteger, nullable=False)

    # Decision
    decision = Column(String(20), nullable=False)  # 'approve', 'reject', 'defer'
    notes = Column(Text, nullable=True)


class ExecutionCheckpoint(Base):
    """
    Storage Optimizer execution checkpoint (BUILD-152).

    This table is used for auditability + idempotency support and is written by
    `CheckpointLogger` when PostgreSQL is configured. A JSONL fallback exists for
    local/offline operation.
    """

    __tablename__ = "execution_checkpoints"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Execution identity
    run_id = Column(String(128), nullable=False, index=True)
    candidate_id = Column(Integer, nullable=True, index=True)

    # Action + target
    action = Column(String(20), nullable=False)  # 'delete' | 'compress' | 'skip'
    path = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(128), nullable=True, index=True)

    # Outcome
    status = Column(String(20), nullable=False, index=True)  # 'completed' | 'failed' | 'skipped'
    error = Column(Text, nullable=True)
    lock_type = Column(String(50), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)


class LearnedRule(Base):
    """
    Learned policy rules from approval patterns (BUILD-151 Phase 4).

    Tracks patterns detected from user approval/rejection history,
    suggests new policy rules to reduce manual approval burden.
    """

    __tablename__ = "learned_rules"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Pattern
    pattern_type = Column(
        String(50), nullable=False
    )  # 'path_pattern', 'file_type', 'age_threshold', 'size_threshold'
    pattern_value = Column(Text, nullable=False)

    # Classification
    suggested_category = Column(String(50), nullable=False)
    confidence_score = Column(DECIMAL(5, 2), nullable=False)

    # Evidence
    based_on_approvals = Column(Integer, nullable=False, default=0)
    based_on_rejections = Column(Integer, nullable=False, default=0)
    sample_paths = Column(Text, nullable=True)  # JSON array for SQLite, TEXT[] for PostgreSQL

    # Lifecycle
    status = Column(
        String(20), nullable=False, default="pending", index=True
    )  # 'pending', 'approved', 'rejected', 'applied'
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    applied_to_policy_version = Column(String(50), nullable=True)

    # Notes
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)


class PolicyPromotion(Base):
    """
    Policy promotion records for validated improvements (IMP-ARCH-006).

    Tracks automated promotion of A-B tested improvements to production configuration
    with rollback protection and monitoring.
    """

    __tablename__ = "policy_promotions"

    id = Column(Integer, primary_key=True, index=True)
    promotion_id = Column(String(128), nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Source
    ab_test_result_id = Column(
        Integer, ForeignKey("ab_test_results.id"), nullable=False, index=True
    )
    improvement_task_id = Column(String(128), nullable=False, index=True)

    # Configuration changes
    config_changes = Column(JSON, nullable=False)  # {"key": {"old": val1, "new": val2}}
    promoted_version = Column(String(128), nullable=False)
    previous_version = Column(String(128), nullable=False)

    # Promotion lifecycle
    promoted_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    monitoring_until = Column(DateTime, nullable=True)  # 24hr monitoring window

    # Rollback
    rollback_triggered = Column(Boolean, nullable=False, default=False, index=True)
    rollback_reason = Column(Text, nullable=True)
    rollback_at = Column(DateTime, nullable=True)

    # Post-promotion metrics
    post_promotion_metrics = Column(JSON, nullable=True)  # Tracked during monitoring period
    degradation_detected = Column(Boolean, nullable=False, default=False)

    # Status
    status = Column(
        String(20), nullable=False, default="active", index=True
    )  # 'active', 'stable', 'rolled_back'

    # Relationship
    ab_test_result = relationship("ABTestResult", backref="promotions")


class GapDetection(Base):
    """Records gap detection events for telemetry and analysis."""

    __tablename__ = "gap_detections"
    __table_args__ = (
        Index("ix_gap_detection_run_id", "run_id"),
        Index("ix_gap_detection_gap_type", "gap_type"),
        Index("ix_gap_detection_risk", "risk_classification"),
        Index("ix_gap_detection_timestamp", "detected_at"),
        Index("ix_gap_detection_blocks", "blocks_autopilot"),
    )

    id = Column(Integer, primary_key=True, index=True, name="event_id")
    gap_id = Column(String(12), nullable=False, index=True)
    gap_type = Column(String(50), nullable=False, index=True)
    detected_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    file_path = Column(String(500), nullable=True)
    risk_classification = Column(String(20), nullable=False, default="medium", index=True)
    blocks_autopilot = Column(Boolean, nullable=False, default=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class GapRemediation(Base):
    """Records gap remediation attempts and outcomes."""

    __tablename__ = "gap_remediations"
    __table_args__ = (
        Index("ix_gap_remediation_run_id", "run_id"),
        Index("ix_gap_remediation_gap_type", "gap_type"),
        Index("ix_gap_remediation_success", "success"),
        Index("ix_gap_remediation_timestamp", "detected_at"),
    )

    id = Column(Integer, primary_key=True, index=True, name="event_id")
    gap_id = Column(String(12), nullable=False, index=True)
    gap_type = Column(String(50), nullable=False, index=True)
    detected_at = Column(DateTime, nullable=False)
    remediated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    success = Column(Boolean, nullable=False, index=True)
    method = Column(String(20), nullable=False)  # "auto", "manual", "ignored"
    run_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ==============================================================================
# Self-Improvement Loop Models (IMP-ARCH-011)
# ==============================================================================


class TaskGenerationEvent(Base):
    """Task generation telemetry event (IMP-LOOP-004).

    Tracks success/failure metrics for task generation operations to enable
    monitoring and quality improvement of the self-improvement loop.

    Captured metrics:
    - Success/failure status of generation runs
    - Number of insights processed and patterns detected
    - Tasks generated count
    - Generation duration for performance monitoring
    - Error details for failure analysis
    """

    __tablename__ = "task_generation_events"
    __table_args__ = (
        Index("ix_task_gen_run_id", "run_id"),
        Index("ix_task_gen_success", "success"),
        Index("ix_task_gen_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(50), nullable=True, index=True)  # Run that triggered generation

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Generation outcome
    success = Column(Boolean, nullable=False, index=True)
    error_message = Column(Text, nullable=True)  # Error details if failed
    error_type = Column(String(100), nullable=True)  # Exception type if failed

    # Metrics
    insights_processed = Column(Integer, nullable=False, default=0)
    patterns_detected = Column(Integer, nullable=False, default=0)
    tasks_generated = Column(Integer, nullable=False, default=0)
    tasks_persisted = Column(Integer, nullable=False, default=0)
    generation_time_ms = Column(Float, nullable=True)  # Duration in milliseconds

    # Source tracking
    telemetry_source = Column(
        String(50), nullable=True
    )  # "direct" (telemetry_insights param) or "memory" (MemoryService)
    min_confidence = Column(Float, nullable=True)  # Confidence threshold used
    max_tasks = Column(Integer, nullable=True)  # Max tasks limit used

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class GeneratedTaskModel(Base):
    """Database model for persisting generated improvement tasks (IMP-ARCH-011).

    Part of the self-improvement feedback loop:
    1. Telemetry is collected during runs
    2. ROAD-C generates improvement tasks from telemetry insights
    3. Tasks are persisted here for retrieval in subsequent runs
    4. Executor loads pending tasks and incorporates them into planning

    This enables continuity across runs - generated tasks survive restarts
    and can be prioritized, tracked, and executed autonomously.
    """

    __tablename__ = "generated_tasks"
    __table_args__ = (
        Index("ix_generated_tasks_status", "status"),
        Index("ix_generated_tasks_priority", "priority"),
        Index("ix_generated_tasks_run_id", "run_id"),
        Index("ix_generated_tasks_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # Indexes defined in __table_args__ to avoid duplicates
    priority = Column(String(20), nullable=False, default="medium")  # critical, high, medium, low
    source_insights = Column(JSON, nullable=True)  # List of insight IDs that led to this task
    suggested_files = Column(JSON, nullable=True)  # List of file paths to modify
    estimated_effort = Column(String(10), nullable=True)  # S, M, L, XL
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, in_progress, completed, skipped, failed
    run_id = Column(String(50), nullable=True)  # Run that generated this task
    completed_at = Column(DateTime, nullable=True)
    executed_in_run_id = Column(String(50), nullable=True)  # Run that executed this task
    updated_at = Column(DateTime, nullable=True)  # Last status update time (IMP-REL-003)
    failure_reason = Column(Text, nullable=True)  # Reason for failure (IMP-REL-003)
    # IMP-LOOP-005: Retry tracking columns
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    failure_runs = Column(
        JSON, nullable=True, default=list
    )  # List of run IDs that failed this task

    def __repr__(self) -> str:
        title_preview = self.title[:30] if self.title else ""
        return f"<GeneratedTask(task_id={self.task_id}, title={title_preview}..., status={self.status})>"


class AnomalyAlertEvent(Base):
    """Anomaly alert telemetry event (IMP-TEL-004).

    Persists anomaly alerts generated by TelemetryAnomalyDetector during phase execution.
    Enables analysis of anomaly patterns and alert effectiveness for ROAD-G monitoring.

    Alert types:
    - TOKEN_SPIKE: Token usage exceeds 2x rolling baseline
    - DURATION_SPIKE: Phase duration exceeds p95 threshold
    - FAILURE_RATE: Failure rate exceeds configured threshold
    """

    __tablename__ = "anomaly_alert_events"
    __table_args__ = (
        Index("ix_anomaly_alert_run_id", "run_id"),
        Index("ix_anomaly_alert_phase_id", "phase_id"),
        Index("ix_anomaly_alert_severity", "severity"),
        Index("ix_anomaly_alert_metric", "metric"),
        Index("ix_anomaly_alert_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(128), nullable=False, unique=True, index=True)
    run_id = Column(String, nullable=True, index=True)
    phase_id = Column(String, nullable=True, index=True)

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Alert details
    severity = Column(String(20), nullable=False, index=True)  # info, warning, critical
    metric = Column(String(50), nullable=False, index=True)  # tokens, duration, failure_rate
    current_value = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    baseline = Column(Float, nullable=True)
    recommendation = Column(Text, nullable=True)

    # Resolution tracking
    resolved = Column(Boolean, nullable=False, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_action = Column(String(100), nullable=True)  # auto_healed, escalated, ignored

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class TaskCompletionEvent(Base):
    """Task completion telemetry event (IMP-LOOP-012).

    Records task execution outcomes to enable measurement of task effectiveness
    and target achievement. Feeds back into the self-improvement loop to track
    whether generated improvement tasks actually achieved their intended goals.

    Captured metrics:
    - Task success/failure status
    - Target metric vs actual metric achieved
    - Whether the improvement target was met
    - Execution duration and run context
    """

    __tablename__ = "task_completion_events"
    __table_args__ = (
        Index("ix_task_completion_task_id", "task_id"),
        Index("ix_task_completion_success", "success"),
        Index("ix_task_completion_target_achieved", "target_achieved"),
        Index("ix_task_completion_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(50), nullable=False, index=True)  # Links to GeneratedTaskModel
    run_id = Column(String(50), nullable=True, index=True)  # Run that executed the task

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Execution outcome
    success = Column(Boolean, nullable=False, index=True)
    failure_reason = Column(Text, nullable=True)  # Reason if failed

    # Target vs actual metrics
    target_metric = Column(Float, nullable=True)  # Expected improvement target
    actual_metric = Column(Float, nullable=True)  # Actual measured result
    target_achieved = Column(Boolean, nullable=True, index=True)  # Did we hit the target?
    improvement_percentage = Column(Float, nullable=True)  # Percentage improvement achieved

    # Task context
    task_type = Column(String(50), nullable=True)  # cost_sink, failure_mode, retry_cause
    task_priority = Column(String(20), nullable=True)  # critical, high, medium, low

    # Execution details
    execution_duration_ms = Column(Float, nullable=True)  # How long the task took
    retry_count = Column(Integer, nullable=False, default=0)  # Retries needed

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<TaskCompletionEvent(task_id={self.task_id}, "
            f"success={self.success}, target_achieved={self.target_achieved})>"
        )


class RiskGatingEvent(Base):
    """Risk gating telemetry event (IMP-LOOP-018).

    Tracks regression risk gating decisions during task generation to monitor
    the effectiveness of the risk gating system and track regression rate trends.
    """

    __tablename__ = "risk_gating_events"
    __table_args__ = (
        Index("ix_risk_gating_timestamp", "timestamp"),
        Index("ix_risk_gating_blocked_count", "blocked_count"),
    )

    id = Column(Integer, primary_key=True, index=True)

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Pattern counts by risk level
    total_patterns = Column(Integer, nullable=False, default=0)
    blocked_count = Column(Integer, nullable=False, default=0)
    low_risk_count = Column(Integer, nullable=False, default=0)
    medium_risk_count = Column(Integer, nullable=False, default=0)
    high_risk_count = Column(Integer, nullable=False, default=0)
    critical_risk_count = Column(Integer, nullable=False, default=0)

    # Historical regression rate tracking
    avg_historical_regression_rate = Column(Float, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class InsightPathEvent(Base):
    """Insight path selection telemetry event (IMP-LOOP-013).

    Tracks which insight source was used during task generation for
    observability and debugging. Enables analysis of:
    1. Which insight paths are most commonly used
    2. Performance characteristics of each path
    3. Debugging insight retrieval issues

    Part of the unified InsightConsumer interface implementation.
    """

    __tablename__ = "insight_path_events"
    __table_args__ = (
        Index("ix_insight_path_source", "source"),
        Index("ix_insight_path_timestamp", "timestamp"),
        Index("ix_insight_path_run_id", "run_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(50), nullable=True, index=True)  # Run that triggered retrieval

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Path selection
    source = Column(String(20), nullable=False, index=True)  # "direct", "analyzer", "memory"

    # Metrics
    insights_count = Column(Integer, nullable=False, default=0)
    retrieval_time_ms = Column(Float, nullable=True)  # Time to retrieve insights

    # Additional context (source-specific details)
    extra_data = Column(JSON, nullable=True)  # Source-specific context (renamed from metadata)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<InsightPathEvent(source={self.source}, "
            f"count={self.insights_count}, time={self.retrieval_time_ms}ms)>"
        )


class CausalAnalysisRecord(Base):
    """Causal analysis record for tracking change-outcome relationships (IMP-FBK-005).

    Persists causal analysis results from CausalAnalyzer to enable:
    1. Historical risk assessment for task prioritization
    2. Learning from past change impacts
    3. Avoiding tasks that historically caused failures

    Part of the ROAD-H causal analysis integration with task generation.
    """

    __tablename__ = "causal_analysis_records"
    __table_args__ = (
        Index("ix_causal_analysis_pattern_type", "pattern_type"),
        Index("ix_causal_analysis_effect_direction", "effect_direction"),
        Index("ix_causal_analysis_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(128), unique=True, nullable=False, index=True)

    # Change information
    change_id = Column(String(128), nullable=True, index=True)
    change_type = Column(String(50), nullable=True)  # code, config, policy, model
    pattern_type = Column(String(50), nullable=False)  # cost_sink, failure_mode, retry_cause

    # Causal analysis results
    effect_direction = Column(String(20), nullable=False)  # positive, negative, neutral
    causal_strength = Column(String(20), nullable=True)  # strong, moderate, weak, none, confounded
    confidence = Column(Float, nullable=True)  # 0.0-1.0
    effect_size = Column(Float, nullable=True)

    # Statistical details
    p_value = Column(Float, nullable=True)
    sample_size = Column(Integer, nullable=True)
    baseline_mean = Column(Float, nullable=True)
    post_change_mean = Column(Float, nullable=True)
    percent_change = Column(Float, nullable=True)

    # Metadata
    affected_components = Column(JSON, nullable=True)  # List of affected component names
    confounding_factors = Column(JSON, nullable=True)  # List of confounding factor descriptions
    explanation = Column(Text, nullable=True)

    # Run context
    run_id = Column(String(50), nullable=True, index=True)

    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CausalAnalysisRecord(analysis_id={self.analysis_id}, "
            f"pattern_type={self.pattern_type}, effect={self.effect_direction})>"
        )
