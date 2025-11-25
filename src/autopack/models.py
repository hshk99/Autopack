"""Database models for runs, tiers, and phases (Chunk A implementation)"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class RunState(str, Enum):
    """Run lifecycle states per §3 of v7 playbook"""

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
    state = Column(SQLEnum(RunState), nullable=False, default=RunState.RUN_CREATED)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="tiers")
    phases = relationship("Phase", back_populates="tier", cascade="all, delete-orphan")


class Phase(Base):
    """Individual phase of work within a tier"""

    __tablename__ = "phases"

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

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="phases")
    tier = relationship("Tier", back_populates="phases")
