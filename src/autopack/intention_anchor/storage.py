"""
Intention Anchor storage helpers (load/save/update/version bump).

Intention behind it: canonical path resolver + atomic writes + versioning.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import IntentionAnchor

logger = logging.getLogger(__name__)


def get_canonical_path(run_id: str, base_dir: str | Path = ".") -> Path:
    """
    Returns the canonical path for an Intention Anchor.

    Canonical location: `.autonomous_runs/<run_id>/intention_anchor.json`

    Args:
        run_id: The run identifier.
        base_dir: The base directory (defaults to current directory).

    Returns:
        Absolute path to the intention anchor file.
    """
    base = Path(base_dir).resolve()
    return base / ".autonomous_runs" / run_id / "intention_anchor.json"


def create_anchor(
    run_id: str,
    project_id: str,
    north_star: str,
    *,
    anchor_id: str | None = None,
    **kwargs: Any,
) -> IntentionAnchor:
    """
    Creates a new IntentionAnchor with version=1.

    Intention behind it: explicit factory for new anchors (no implicit defaults).

    Args:
        run_id: The run identifier.
        project_id: The project identifier.
        north_star: The one-paragraph goal statement.
        anchor_id: Optional anchor ID (generates one if not provided).
        **kwargs: Additional fields to pass to IntentionAnchor.

    Returns:
        A new IntentionAnchor instance with version=1.
    """
    now = datetime.now(timezone.utc)
    if anchor_id is None:
        anchor_id = f"IA-{uuid.uuid4().hex[:12]}"

    return IntentionAnchor(
        anchor_id=anchor_id,
        run_id=run_id,
        project_id=project_id,
        created_at=now,
        updated_at=now,
        version=1,
        north_star=north_star,
        **kwargs,
    )


def save_anchor(
    anchor: IntentionAnchor,
    base_dir: str | Path = ".",
    *,
    generate_artifacts: bool = True,
) -> Path:
    """
    Saves an IntentionAnchor to its canonical path (atomic write).

    Intention behind it: atomic writes (temp → replace) to be Windows-safe.
    Also generates run-local SOT-ready artifacts (anchor_summary.md + event log).

    Args:
        anchor: The IntentionAnchor to save.
        base_dir: The base directory (defaults to current directory).
        generate_artifacts: If True, generate SOT-ready artifacts (default: True).

    Returns:
        The path where the anchor was saved.
    """
    canonical_path = get_canonical_path(anchor.run_id, base_dir=base_dir)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file first, then replace (atomic)
    temp_path = canonical_path.with_suffix(".tmp")
    temp_path.write_text(anchor.model_dump_json(indent=2, exclude_none=False), encoding="utf-8")
    temp_path.replace(canonical_path)

    # Generate run-local SOT-ready artifacts
    if generate_artifacts:
        try:
            from .artifacts import (log_anchor_event, save_anchor_summary,
                                    save_anchor_summary_snapshot)

            # Save human-readable summary (current state)
            save_anchor_summary(anchor, base_dir=base_dir)

            # Save versioned snapshot (append-only audit trail)
            save_anchor_summary_snapshot(anchor, base_dir=base_dir)

            # Log creation/update event
            event_type = "anchor_created" if anchor.version == 1 else "anchor_updated"
            log_anchor_event(
                run_id=anchor.run_id,
                event_type=event_type,
                anchor_id=anchor.anchor_id,
                version=anchor.version,
                message=f"Anchor saved (version {anchor.version})",
                base_dir=base_dir,
            )
        except Exception as e:
            logger.warning(f"[{anchor.run_id}] Failed to generate SOT artifacts: {e}")

    return canonical_path


def load_anchor(run_id: str, base_dir: str | Path = ".") -> IntentionAnchor:
    """
    Loads an IntentionAnchor from its canonical path.

    Intention behind it: fail loudly if the anchor doesn't exist or is malformed.

    Args:
        run_id: The run identifier.
        base_dir: The base directory (defaults to current directory).

    Returns:
        The loaded IntentionAnchor.

    Raises:
        FileNotFoundError: If the anchor file doesn't exist.
        ValueError: If the anchor JSON is malformed or fails validation.
    """
    canonical_path = get_canonical_path(run_id, base_dir=base_dir)
    if not canonical_path.exists():
        raise FileNotFoundError(f"Intention anchor not found at canonical path: {canonical_path}")

    data = json.loads(canonical_path.read_text(encoding="utf-8"))
    return IntentionAnchor.model_validate(data)


def update_anchor(
    anchor: IntentionAnchor, *, save: bool = False, base_dir: str | Path = "."
) -> IntentionAnchor:
    """
    Creates an updated copy of the anchor with incremented version and updated timestamp.

    Intention behind it: explicit version bump + timestamp update for intent changes.

    Args:
        anchor: The original anchor.
        save: If True, save the updated anchor to disk.
        base_dir: The base directory (used if save=True).

    Returns:
        A new IntentionAnchor instance with version+1 and updated_at set to now.
    """
    updated = anchor.model_copy(deep=True)
    updated.version += 1
    updated.updated_at = datetime.now(timezone.utc)

    if save:
        save_anchor(updated, base_dir=base_dir)

    return updated
