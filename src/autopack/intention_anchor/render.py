"""
Intention Anchor prompt renderer (deterministic, budget-bounded).

Intention behind it: keep the anchor always-present in prompts without bloat.
"""

from __future__ import annotations

from .models import IntentionAnchor


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
