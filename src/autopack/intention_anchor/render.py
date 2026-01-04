"""
Intention Anchor prompt renderer (deterministic, budget-bounded).

Intention behind it: keep the anchor always-present in prompts without bloat.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import IntentionAnchor
from .storage import load_anchor


def render_for_prompt(
    anchor: IntentionAnchor, *, max_bullets: int = 7
) -> str:
    """
    Renders an IntentionAnchor as a deterministic prompt section.

    Intention behind it: compact, stable output that can be included in every
    builder/auditor/doctor prompt without causing token bloat.

    Args:
        anchor: The IntentionAnchor to render.
        max_bullets: Maximum number of bullets to include per section (default: 7).

    Returns:
        A formatted string suitable for inclusion in prompts.

    Determinism guarantees:
        - Stable ordering (no randomness)
        - No timestamps in output
        - Capped bullet counts
    """
    lines = [
        "## Intention Anchor (canonical)",
        f"North star: {anchor.north_star.strip()}",
    ]

    # Success criteria (capped)
    if anchor.success_criteria:
        bullets = anchor.success_criteria[:max_bullets]
        lines.append("Success criteria:")
        lines.extend([f"- {b.strip()}" for b in bullets])

    # Constraints: must (capped)
    if anchor.constraints.must:
        bullets = anchor.constraints.must[:max_bullets]
        lines.append("Must:")
        lines.extend([f"- {b.strip()}" for b in bullets])

    # Constraints: must_not (capped)
    if anchor.constraints.must_not:
        bullets = anchor.constraints.must_not[:max_bullets]
        lines.append("Must not:")
        lines.extend([f"- {b.strip()}" for b in bullets])

    # Preferences (capped, optional - only if present and space allows)
    if anchor.constraints.preferences:
        bullets = anchor.constraints.preferences[:max_bullets]
        lines.append("Preferences:")
        lines.extend([f"- {b.strip()}" for b in bullets])

    return "\n".join(lines).strip() + "\n"


def render_compact(anchor: IntentionAnchor) -> str:
    """
    Renders a very compact single-line summary of the anchor.

    Intention behind it: for logging, telemetry, or ultra-compact contexts.

    Args:
        anchor: The IntentionAnchor to render.

    Returns:
        A single-line summary.
    """
    return f"[{anchor.anchor_id} v{anchor.version}] {anchor.north_star[:80]}"


def render_for_builder(
    anchor: IntentionAnchor,
    phase_id: str,
    *,
    max_bullets: int = 5,
) -> str:
    """
    Render anchor for Builder agent prompts.

    Intention behind it: Builder needs clear intent context to prevent goal drift
    during code generation.

    Args:
        anchor: The IntentionAnchor to render.
        phase_id: Current phase identifier for context.
        max_bullets: Maximum bullets per section (default: 5 for Builder).

    Returns:
        Formatted string for Builder prompt injection.
    """
    base = render_for_prompt(anchor, max_bullets=max_bullets)
    header = f"# Project Intent (Phase: {phase_id})\n\n"
    return header + base


def render_for_auditor(
    anchor: IntentionAnchor,
    *,
    max_bullets: int = 5,
) -> str:
    """
    Render anchor for Auditor agent prompts.

    Intention behind it: Auditor needs intent context to validate that changes
    align with project goals.

    Args:
        anchor: The IntentionAnchor to render.
        max_bullets: Maximum bullets per section (default: 5 for Auditor).

    Returns:
        Formatted string for Auditor prompt injection.
    """
    base = render_for_prompt(anchor, max_bullets=max_bullets)
    header = "# Project Intent (for validation)\n\n"
    return header + base


def render_for_doctor(
    anchor: IntentionAnchor,
    *,
    max_bullets: int = 3,
) -> str:
    """
    Render anchor for Doctor agent prompts.

    Intention behind it: Doctor needs compact intent reminder to guide error
    recovery without overwhelming the prompt.

    Args:
        anchor: The IntentionAnchor to render.
        max_bullets: Maximum bullets per section (default: 3 for Doctor).

    Returns:
        Formatted string for Doctor prompt injection.
    """
    base = render_for_prompt(anchor, max_bullets=max_bullets)
    header = "# Project Intent (original goal)\n\n"
    return header + base


def load_and_render_for_builder(
    run_id: str,
    phase_id: str,
    *,
    base_dir: str | Path = ".",
) -> Optional[str]:
    """
    Load anchor from disk and render for Builder.

    Intention behind it: Convenience helper for prompt injection - returns None
    if anchor doesn't exist (graceful degradation).

    Args:
        run_id: Run identifier.
        phase_id: Current phase identifier.
        base_dir: Base directory for anchor storage (default: ".").

    Returns:
        Rendered prompt section or None if anchor doesn't exist.
    """
    try:
        anchor = load_anchor(run_id, base_dir=base_dir)
        return render_for_builder(anchor, phase_id=phase_id)
    except FileNotFoundError:
        return None


def load_and_render_for_auditor(
    run_id: str,
    *,
    base_dir: str | Path = ".",
) -> Optional[str]:
    """
    Load anchor from disk and render for Auditor.

    Intention behind it: Convenience helper for prompt injection - returns None
    if anchor doesn't exist (graceful degradation).

    Args:
        run_id: Run identifier.
        base_dir: Base directory for anchor storage (default: ".").

    Returns:
        Rendered prompt section or None if anchor doesn't exist.
    """
    try:
        anchor = load_anchor(run_id, base_dir=base_dir)
        return render_for_auditor(anchor)
    except FileNotFoundError:
        return None


def load_and_render_for_doctor(
    run_id: str,
    *,
    base_dir: str | Path = ".",
) -> Optional[str]:
    """
    Load anchor from disk and render for Doctor.

    Intention behind it: Convenience helper for prompt injection - returns None
    if anchor doesn't exist (graceful degradation).

    Args:
        run_id: Run identifier.
        base_dir: Base directory for anchor storage (default: ".").

    Returns:
        Rendered prompt section or None if anchor doesn't exist.
    """
    try:
        anchor = load_anchor(run_id, base_dir=base_dir)
        return render_for_doctor(anchor)
    except FileNotFoundError:
        return None
