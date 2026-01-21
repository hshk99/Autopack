"""initial schema migration

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-01-19 00:00:00.000000

This migration captures the current database schema including:
- Runs, Tiers, Phases tables for autonomous execution
- Planning artifacts and plan changes
- User authentication models (users, api_keys)
- LLM usage tracking
- Doctor usage stats and token efficiency metrics

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema to initial state."""

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    # Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(op.f("ix_api_keys_id"), "api_keys", ["id"], unique=False)
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=False)

    # Create runs table
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("state", sa.Enum(name="runstate"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safety_profile", sa.String(), nullable=False, server_default="normal"),
        sa.Column("run_scope", sa.String(), nullable=False, server_default="multi_tier"),
        sa.Column("token_cap", sa.Integer(), nullable=False, server_default="5000000"),
        sa.Column("max_phases", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("max_duration_minutes", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("max_minor_issues_total", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ci_runs_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minor_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("major_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "promotion_eligible_to_main",
            sa.String(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("debt_status", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("goal_anchor", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_id"), "runs", ["id"], unique=True)
    op.create_index(op.f("ix_runs_state_created"), "runs", ["state", "created_at"], unique=False)

    # Create tiers table
    op.create_table(
        "tiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tier_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("tier_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.Enum(name="tierstate"), nullable=False),
        sa.Column("token_cap", sa.Integer(), nullable=True),
        sa.Column("ci_run_cap", sa.Integer(), nullable=True),
        sa.Column("max_minor_issues_tolerated", sa.Integer(), nullable=True),
        sa.Column("max_major_issues_tolerated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ci_runs_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minor_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("major_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cleanliness", sa.String(), nullable=False, server_default="clean"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_tiers_run_id_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tiers_id"), "tiers", ["id"], unique=False)
    op.create_index(op.f("ix_tiers_tier_id"), "tiers", ["tier_id"], unique=False)

    # Create phases table
    op.create_table(
        "phases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phase_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("tier_id", sa.Integer(), nullable=False),
        sa.Column("phase_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.Enum(name="phasestate"), nullable=False),
        sa.Column("task_category", sa.String(), nullable=True),
        sa.Column("complexity", sa.String(), nullable=True),
        sa.Column("builder_mode", sa.String(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("max_builder_attempts", sa.Integer(), nullable=True),
        sa.Column("max_auditor_attempts", sa.Integer(), nullable=True),
        sa.Column("incident_token_cap", sa.Integer(), nullable=True),
        sa.Column("builder_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auditor_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minor_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("major_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issue_state", sa.String(), nullable=False, server_default="no_issues"),
        sa.Column("quality_level", sa.String(), nullable=True),
        sa.Column("quality_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("retry_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_phases_run_id_runs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tier_id"], ["tiers.id"], name="fk_phases_tier_id_tiers"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "phase_id", name="uq_phases_run_id_phase_id"),
    )
    op.create_index(op.f("ix_phases_id"), "phases", ["id"], unique=False)
    op.create_index(op.f("ix_phases_phase_id"), "phases", ["phase_id"], unique=False)
    op.create_index(op.f("ix_phases_run_id"), "phases", ["run_id"], unique=False)
    op.create_index(op.f("ix_phases_run_state"), "phases", ["run_id", "state"], unique=False)
    op.create_index(
        op.f("ix_phases_state_started"), "phases", ["state", "started_at"], unique=False
    )

    # Create planning_artifacts table
    op.create_table(
        "planning_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("replaced_by", sa.Integer(), nullable=True),
        sa.Column("vector_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path", "version", name="uq_planning_artifacts_path_version"),
    )
    op.create_index(op.f("ix_planning_artifacts_id"), "planning_artifacts", ["id"], unique=False)
    op.create_index(
        op.f("ix_planning_artifacts_path"), "planning_artifacts", ["path"], unique=False
    )
    op.create_index(
        op.f("ix_planning_artifacts_project_id"), "planning_artifacts", ["project_id"], unique=False
    )

    # Create plan_changes table
    op.create_table(
        "plan_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("phase_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_type", sa.String(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_changes_id"), "plan_changes", ["id"], unique=False)
    op.create_index(op.f("ix_plan_changes_run_id"), "plan_changes", ["run_id"], unique=False)
    op.create_index(op.f("ix_plan_changes_phase_id"), "plan_changes", ["phase_id"], unique=False)
    op.create_index(
        op.f("ix_plan_changes_project_id"), "plan_changes", ["project_id"], unique=False
    )

    # Create llm_usage_events table
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("phase_id", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=False),
        sa.Column("tokens_output", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.DECIMAL(precision=10, scale=6), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_usage_events_id"), "llm_usage_events", ["id"], unique=False)
    op.create_index(
        op.f("ix_llm_usage_events_run_id"), "llm_usage_events", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_llm_usage_events_timestamp"), "llm_usage_events", ["timestamp"], unique=False
    )

    # Create doctor_usage_stats table
    op.create_table(
        "doctor_usage_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("phase_id", sa.String(), nullable=True),
        sa.Column("doctor_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_diagnoses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_diagnoses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_diagnosis_time_ms", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_doctor_usage_stats_id"), "doctor_usage_stats", ["id"], unique=False)
    op.create_index(
        op.f("ix_doctor_usage_stats_run_id"), "doctor_usage_stats", ["run_id"], unique=False
    )

    # Create token_efficiency_metrics table
    op.create_table(
        "token_efficiency_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("phase_id", sa.String(), nullable=True),
        sa.Column("tokens_budgeted", sa.Integer(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("tokens_saved", sa.Integer(), nullable=False),
        sa.Column("efficiency_pct", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_token_efficiency_metrics_id"), "token_efficiency_metrics", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_token_efficiency_metrics_run_id"),
        "token_efficiency_metrics",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade database schema (drop all tables)."""
    op.drop_table("token_efficiency_metrics")
    op.drop_table("doctor_usage_stats")
    op.drop_table("llm_usage_events")
    op.drop_table("plan_changes")
    op.drop_table("planning_artifacts")
    op.drop_table("phases")
    op.drop_table("tiers")
    op.drop_table("runs")
    op.drop_table("api_keys")
    op.drop_table("users")
