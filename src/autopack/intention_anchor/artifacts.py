"""
Run-local SOT-ready artifacts for Intention Anchors.

Intention behind it: Generate append-only artifacts within .autonomous_runs/<run_id>/
that can be consolidated into SOT ledgers by tidy, without requiring autonomous runs
to write directly to BUILD_HISTORY/DEBUG_LOG during execution.

Design principles:
- Append-only: events are logged, never edited
- Human-readable: summaries are markdown, events are NDJSON for easy parsing
- Self-contained: all references (anchor_id, version, phase_id) are explicit
- Tidy-ready: format is designed for mechanical consolidation into SOT ledgers
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from .models import IntentionAnchor

logger = logging.getLogger(__name__)

# Event types for anchor_events.ndjson
AnchorEventType = Literal[
    "anchor_created",
    "anchor_updated",
    "prompt_injected_builder",
    "prompt_injected_auditor",
    "prompt_injected_doctor",
    "validation_warning",
    "validation_error",
]


def get_anchor_summary_path(run_id: str, base_dir: str | Path = ".") -> Path:
    """
    Get canonical path for anchor_summary.md.

    Args:
        run_id: Run identifier.
        base_dir: Base directory (default: ".").

    Returns:
        Path to anchor_summary.md file.
    """
    return Path(base_dir) / ".autonomous_runs" / run_id / "anchor_summary.md"


def get_anchor_events_path(run_id: str, base_dir: str | Path = ".") -> Path:
    """
    Get canonical path for anchor_events.ndjson.

    Args:
        run_id: Run identifier.
        base_dir: Base directory (default: ".").

    Returns:
        Path to anchor_events.ndjson file.
    """
    return Path(base_dir) / ".autonomous_runs" / run_id / "anchor_events.ndjson"


def get_anchor_summary_version_path(run_id: str, version: int, base_dir: str | Path = ".") -> Path:
    """
    Get canonical path for versioned anchor summary snapshot.

    Intention behind it: Support append-only versioned snapshots to preserve
    historical anchor states for audit trail.

    Args:
        run_id: Run identifier.
        version: Anchor version number.
        base_dir: Base directory (default: ".").

    Returns:
        Path to anchor_summary_v{version:04d}.md file.
    """
    return (
        Path(base_dir)
        / ".autonomous_runs"
        / run_id
        / "anchor_summaries"
        / f"anchor_summary_v{version:04d}.md"
    )


def generate_anchor_summary(anchor: IntentionAnchor) -> str:
    """
    Generate human-readable markdown summary of anchor.

    Intention behind it: Create a self-contained summary that references anchor_id +
    version and can be mechanically consolidated into BUILD_HISTORY by tidy.

    Args:
        anchor: IntentionAnchor to summarize.

    Returns:
        Markdown-formatted summary string.
    """
    lines = [
        "# Intention Anchor Summary",
        "",
        f"**Anchor ID**: `{anchor.anchor_id}`",
        f"**Run ID**: `{anchor.run_id}`",
        f"**Project ID**: `{anchor.project_id}`",
        f"**Version**: {anchor.version}",
        f"**Created**: {anchor.created_at.isoformat()}",
        f"**Updated**: {anchor.updated_at.isoformat()}",
        "",
        "## North Star",
        "",
        anchor.north_star,
        "",
    ]

    if anchor.success_criteria:
        lines.append("## Success Criteria")
        lines.append("")
        for i, criterion in enumerate(anchor.success_criteria):
            lines.append(f"{i}. {criterion}")
        lines.append("")

    if anchor.constraints.must or anchor.constraints.must_not or anchor.constraints.preferences:
        lines.append("## Constraints")
        lines.append("")

        if anchor.constraints.must:
            lines.append("**Must:**")
            for i, constraint in enumerate(anchor.constraints.must):
                lines.append(f"- [{i}] {constraint}")
            lines.append("")

        if anchor.constraints.must_not:
            lines.append("**Must Not:**")
            for i, constraint in enumerate(anchor.constraints.must_not):
                lines.append(f"- [{i}] {constraint}")
            lines.append("")

        if anchor.constraints.preferences:
            lines.append("**Preferences:**")
            for i, pref in enumerate(anchor.constraints.preferences):
                lines.append(f"- [{i}] {pref}")
            lines.append("")

    if anchor.scope.allowed_paths or anchor.scope.out_of_scope:
        lines.append("## Scope")
        lines.append("")

        if anchor.scope.allowed_paths:
            lines.append("**Allowed Paths:**")
            for path in anchor.scope.allowed_paths:
                lines.append(f"- `{path}`")
            lines.append("")

        if anchor.scope.out_of_scope:
            lines.append("**Out of Scope:**")
            for path in anchor.scope.out_of_scope:
                lines.append(f"- `{path}`")
            lines.append("")

    if anchor.budgets.max_context_chars != 100_000 or anchor.budgets.max_sot_chars != 4_000:
        lines.append("## Budgets")
        lines.append("")
        lines.append(f"- Max context chars: {anchor.budgets.max_context_chars:,}")
        lines.append(f"- Max SOT chars: {anchor.budgets.max_sot_chars:,}")
        lines.append("")

    if anchor.risk_profile.safety_profile != "normal" or anchor.risk_profile.protected_paths:
        lines.append("## Risk Profile")
        lines.append("")
        lines.append(f"- Safety profile: `{anchor.risk_profile.safety_profile}`")
        if anchor.risk_profile.protected_paths:
            lines.append("- Protected paths:")
            for path in anchor.risk_profile.protected_paths:
                lines.append(f"  - `{path}`")
        lines.append("")

    return "\n".join(lines)


def save_anchor_summary(anchor: IntentionAnchor, base_dir: str | Path = ".") -> Path:
    """
    Save anchor summary to anchor_summary.md.

    Intention behind it: Create a durable, human-readable summary that references
    anchor_id + version for later consolidation into BUILD_HISTORY.

    Args:
        anchor: IntentionAnchor to save.
        base_dir: Base directory (default: ".").

    Returns:
        Path to written file.
    """
    summary_path = get_anchor_summary_path(anchor.run_id, base_dir)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    summary_content = generate_anchor_summary(anchor)

    # Always overwrite (not append) - summary reflects current anchor state
    summary_path.write_text(summary_content, encoding="utf-8")

    logger.info(
        f"[{anchor.run_id}] Saved anchor summary to {summary_path} "
        f"(anchor_id={anchor.anchor_id}, version={anchor.version})"
    )

    return summary_path


def save_anchor_summary_snapshot(anchor: IntentionAnchor, base_dir: str | Path = ".") -> Path:
    """
    Save versioned anchor summary snapshot.

    Intention behind it: Create append-only versioned snapshots to preserve
    historical anchor states for audit trail. Each version gets its own file.

    Args:
        anchor: IntentionAnchor to save.
        base_dir: Base directory (default: ".").

    Returns:
        Path to written snapshot file.
    """
    snapshot_path = get_anchor_summary_version_path(anchor.run_id, anchor.version, base_dir)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    summary_content = generate_anchor_summary(anchor)

    # Append-only: write snapshot only if it doesn't exist
    if not snapshot_path.exists():
        snapshot_path.write_text(summary_content, encoding="utf-8")
        logger.info(
            f"[{anchor.run_id}] Saved versioned snapshot to {snapshot_path} "
            f"(anchor_id={anchor.anchor_id}, version={anchor.version})"
        )
    else:
        logger.debug(
            f"[{anchor.run_id}] Snapshot v{anchor.version} already exists at {snapshot_path}, skipping"
        )

    return snapshot_path


def log_anchor_event(
    run_id: str,
    event_type: AnchorEventType,
    *,
    anchor_id: Optional[str] = None,
    version: Optional[int] = None,
    phase_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    chars_injected: Optional[int] = None,
    message: Optional[str] = None,
    metadata: Optional[dict] = None,
    base_dir: str | Path = ".",
) -> None:
    """
    Append event to anchor_events.ndjson.

    Intention behind it: Create an append-only audit trail of anchor usage that can
    be analyzed or consolidated by tidy.

    Args:
        run_id: Run identifier.
        event_type: Type of event (see AnchorEventType).
        anchor_id: Optional anchor ID.
        version: Optional anchor version.
        phase_id: Optional phase ID (for prompt injection events).
        agent_type: Optional agent type (builder/auditor/doctor).
        chars_injected: Optional character count (for prompt injection events).
        message: Optional human-readable message.
        metadata: Optional additional metadata.
        base_dir: Base directory (default: ".").
    """
    events_path = get_anchor_events_path(run_id, base_dir)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "run_id": run_id,
    }

    if anchor_id:
        event["anchor_id"] = anchor_id
    if version is not None:
        event["version"] = version
    if phase_id:
        event["phase_id"] = phase_id
    if agent_type:
        event["agent_type"] = agent_type
    if chars_injected is not None:
        event["chars_injected"] = chars_injected
    if message:
        event["message"] = message
    if metadata:
        event["metadata"] = metadata

    # Append-only: always append, never overwrite
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    logger.debug(f"[{run_id}] Logged anchor event: {event_type}")


def read_anchor_events(
    run_id: str,
    base_dir: str | Path = ".",
    event_type_filter: Optional[AnchorEventType] = None,
) -> list[dict]:
    """
    Read anchor events from anchor_events.ndjson.

    Args:
        run_id: Run identifier.
        base_dir: Base directory (default: ".").
        event_type_filter: Optional filter by event type.

    Returns:
        List of event dictionaries.
    """
    events_path = get_anchor_events_path(run_id, base_dir)

    if not events_path.exists():
        return []

    events = []
    with events_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event_type_filter is None or event.get("event_type") == event_type_filter:
                    events.append(event)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse event line: {e}")
                continue

    return events


def generate_anchor_diff_summary(old_anchor: IntentionAnchor, new_anchor: IntentionAnchor) -> str:
    """
    Generate human-readable diff summary between two anchor versions.

    Intention behind it: Track what changed between versions for audit trail.

    Args:
        old_anchor: Previous version of anchor.
        new_anchor: New version of anchor.

    Returns:
        Human-readable diff summary.
    """
    changes = []

    # Version check
    if new_anchor.version != old_anchor.version + 1:
        changes.append(
            f"⚠️ Version jump: {old_anchor.version} → {new_anchor.version} (expected {old_anchor.version + 1})"
        )

    # North star change
    if new_anchor.north_star != old_anchor.north_star:
        changes.append(
            f"**North star changed:**\n  - Old: {old_anchor.north_star}\n  - New: {new_anchor.north_star}"
        )

    # Success criteria changes
    old_sc = set(old_anchor.success_criteria)
    new_sc = set(new_anchor.success_criteria)
    added_sc = new_sc - old_sc
    removed_sc = old_sc - new_sc

    if added_sc:
        changes.append(f"**Success criteria added:** {list(added_sc)}")
    if removed_sc:
        changes.append(f"**Success criteria removed:** {list(removed_sc)}")

    # Constraint changes
    old_must = set(old_anchor.constraints.must)
    new_must = set(new_anchor.constraints.must)
    added_must = new_must - old_must
    removed_must = old_must - new_must

    if added_must:
        changes.append(f"**Must constraints added:** {list(added_must)}")
    if removed_must:
        changes.append(f"**Must constraints removed:** {list(removed_must)}")

    # Scope changes
    if new_anchor.scope != old_anchor.scope:
        changes.append("**Scope changed** (see anchor_summary.md for details)")

    # Budget changes
    if new_anchor.budgets != old_anchor.budgets:
        changes.append(
            f"**Budgets changed:** "
            f"context {old_anchor.budgets.max_context_chars} → {new_anchor.budgets.max_context_chars}, "
            f"sot {old_anchor.budgets.max_sot_chars} → {new_anchor.budgets.max_sot_chars}"
        )

    # Risk profile changes
    if new_anchor.risk_profile != old_anchor.risk_profile:
        changes.append(
            f"**Risk profile changed:** {old_anchor.risk_profile.safety_profile} → {new_anchor.risk_profile.safety_profile}"
        )

    if not changes:
        return "No changes detected (metadata-only update?)"

    return "\n".join(changes)
