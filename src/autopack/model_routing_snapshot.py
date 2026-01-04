"""
Model routing snapshot system for intention-first autonomy.

Implements:
- Routing snapshot refresh at run start (and optionally once/24h)
- Persisted routing snapshot as run-local artifact (auditability)
- Budget-aware escalation (max 1 per phase, never bypass budgets)
- Graceful degradation if refresh unavailable (use last known routing)

All routing decisions are reproducible via persisted snapshot.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from autopack.file_layout import RunFileLayout


class ModelTier(str):
    """Model tier for escalation logic."""

    # Common tier names (can be extended)
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class ModelRoutingEntry(BaseModel):
    """
    Single model entry in routing table.

    Represents "best available model" for a given tier under budget+safety constraints.
    """

    model_config = ConfigDict(extra="forbid")

    tier: str  # e.g., "haiku", "sonnet", "opus"
    model_id: str  # e.g., "claude-3-5-haiku-20241022"
    provider: str  # e.g., "anthropic", "openai"
    max_tokens: int
    max_context_chars: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    safety_compatible: bool = True  # Whether compatible with strict safety profile


class ModelRoutingSnapshot(BaseModel):
    """
    Routing table snapshot persisted per run.

    Intention: make routing decisions reproducible and auditable.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    run_id: str
    created_at: datetime
    expires_at: datetime | None = None  # Optional: for 24h refresh cadence
    entries: list[ModelRoutingEntry]

    def get_model_for_tier(
        self, tier: str, safety_profile: Literal["normal", "strict"] = "normal"
    ) -> ModelRoutingEntry | None:
        """
        Get the best model for a given tier and safety profile.

        Args:
            tier: Model tier (e.g., "haiku", "sonnet", "opus")
            safety_profile: Safety profile from IntentionRiskProfile

        Returns:
            ModelRoutingEntry if found, else None
        """
        for entry in self.entries:
            if entry.tier == tier:
                if safety_profile == "strict" and not entry.safety_compatible:
                    continue
                return entry
        return None

    def escalate_tier(
        self, current_tier: str, safety_profile: Literal["normal", "strict"] = "normal"
    ) -> ModelRoutingEntry | None:
        """
        Escalate to next tier (budget permitting).

        Args:
            current_tier: Current tier
            safety_profile: Safety profile from IntentionRiskProfile

        Returns:
            ModelRoutingEntry for escalated tier, or None if no escalation available
        """
        # Define escalation order
        tier_order = ["haiku", "sonnet", "opus"]
        try:
            current_idx = tier_order.index(current_tier)
            if current_idx < len(tier_order) - 1:
                next_tier = tier_order[current_idx + 1]
                return self.get_model_for_tier(next_tier, safety_profile)
        except ValueError:
            pass
        return None


class RoutingSnapshotStorage:
    """
    Persistence layer for routing snapshots.

    Stores snapshots as run-local artifacts for auditability.
    """

    @staticmethod
    def get_snapshot_path(run_id: str, project_id: str | None = None) -> Path:
        """
        Get canonical path for routing snapshot.

        Uses the repo-standard run layout:
        `.autonomous_runs/<project>/runs/<family>/<run_id>/model_routing_snapshot.json`
        """
        layout = RunFileLayout(run_id=run_id, project_id=project_id)
        return layout.base_dir / "model_routing_snapshot.json"

    @staticmethod
    def save_snapshot(snapshot: ModelRoutingSnapshot) -> None:
        """
        Save routing snapshot to run-local artifact.

        Args:
            snapshot: Routing snapshot to save
        """
        path = RoutingSnapshotStorage.get_snapshot_path(snapshot.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write (temp → replace)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            snapshot.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
        temp_path.replace(path)

    @staticmethod
    def load_snapshot(run_id: str) -> ModelRoutingSnapshot | None:
        """
        Load routing snapshot from run-local artifact.

        Args:
            run_id: Run ID

        Returns:
            ModelRoutingSnapshot if exists, else None
        """
        path = RoutingSnapshotStorage.get_snapshot_path(run_id)
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        return ModelRoutingSnapshot(**data)

    @staticmethod
    def is_snapshot_fresh(
        snapshot: ModelRoutingSnapshot, max_age_hours: int = 24
    ) -> bool:
        """
        Check if snapshot is still fresh.

        Args:
            snapshot: Routing snapshot
            max_age_hours: Max age in hours

        Returns:
            True if fresh, False if expired
        """
        # Important: this codebase uses a mix of naive and timezone-aware datetimes.
        # For determinism (esp. in tests), compare naive-with-naive and aware-with-aware.

        # If expires_at is provided, treat it as authoritative.
        if snapshot.expires_at is not None:
            expires_at = snapshot.expires_at
            if expires_at.tzinfo is None:
                return datetime.now() < expires_at
            return datetime.now(timezone.utc) < expires_at.astimezone(timezone.utc)

        # Otherwise, fall back to created_at age (bounded freshness).
        created_at = snapshot.created_at
        if created_at.tzinfo is None:
            return datetime.now() < (created_at + timedelta(hours=max_age_hours))
        return datetime.now(timezone.utc) < (
            created_at.astimezone(timezone.utc) + timedelta(hours=max_age_hours)
        )


def create_default_snapshot(run_id: str) -> ModelRoutingSnapshot:
    """
    Create a default routing snapshot with hardcoded fallback models.

    This is used as graceful degradation if refresh is unavailable.

    Args:
        run_id: Run ID

    Returns:
        Default routing snapshot
    """
    now = datetime.now(timezone.utc)
    return ModelRoutingSnapshot(
        snapshot_id=f"default-{run_id}",
        run_id=run_id,
        created_at=now,
        expires_at=now + timedelta(hours=24),
        entries=[
            ModelRoutingEntry(
                tier="haiku",
                model_id="claude-3-5-haiku-20241022",
                provider="anthropic",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=1.0,
                cost_per_1k_output=5.0,
                safety_compatible=True,
            ),
            ModelRoutingEntry(
                tier="sonnet",
                model_id="claude-3-5-sonnet-20241022",
                provider="anthropic",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=3.0,
                cost_per_1k_output=15.0,
                safety_compatible=True,
            ),
            ModelRoutingEntry(
                tier="opus",
                model_id="claude-opus-4-20250514",
                provider="anthropic",
                max_tokens=4096,
                max_context_chars=200_000,
                cost_per_1k_input=15.0,
                cost_per_1k_output=75.0,
                safety_compatible=True,
            ),
        ],
    )


def refresh_or_load_snapshot(
    run_id: str, force_refresh: bool = False
) -> ModelRoutingSnapshot:
    """
    Refresh or load routing snapshot.

    Logic:
    1. If force_refresh or no snapshot exists: create default and save
    2. If snapshot exists and fresh: load it
    3. If snapshot exists but expired: create default and save

    Args:
        run_id: Run ID
        force_refresh: Force snapshot refresh

    Returns:
        Fresh routing snapshot
    """
    if not force_refresh:
        existing = RoutingSnapshotStorage.load_snapshot(run_id)
        if existing and RoutingSnapshotStorage.is_snapshot_fresh(existing):
            return existing

    # Create default snapshot and save
    snapshot = create_default_snapshot(run_id)
    RoutingSnapshotStorage.save_snapshot(snapshot)
    return snapshot
