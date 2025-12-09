# autopack/memory/goal_drift.py
"""
Goal drift detection for pre-apply gating.

Per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md:
- Store a short goal anchor per run (in SQLite)
- Before apply, run a small LLM check comparing current change intent vs anchor
- Block or replan on drift (configurable: advisory or blocking mode)
"""

import logging
from typing import Optional, Tuple
import yaml
from pathlib import Path

from .embeddings import sync_embed_text

logger = logging.getLogger(__name__)


def _load_goal_drift_config() -> dict:
    """Load goal drift configuration from config/memory.yaml."""
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "memory.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                return config.get("goal_drift", {})
        except Exception as e:
            logger.warning(f"Failed to load goal drift config: {e}")
    return {}


def cosine_similarity(vec_a: list, vec_b: list) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def check_goal_drift(
    goal_anchor: str,
    change_intent: str,
    threshold: Optional[float] = None,
) -> Tuple[bool, float, str]:
    """
    Check if the change intent drifts from the goal anchor.

    Uses embedding similarity to detect semantic drift.

    Args:
        goal_anchor: Original goal text (from run)
        change_intent: Current change description (from phase/patch)
        threshold: Similarity threshold (default from config)

    Returns:
        Tuple of (is_aligned, similarity_score, message)
        - is_aligned: True if similarity >= threshold
        - similarity_score: Cosine similarity [0, 1]
        - message: Human-readable explanation
    """
    config = _load_goal_drift_config()

    if not config.get("enabled", True):
        return True, 1.0, "Goal drift check disabled"

    if not goal_anchor or not goal_anchor.strip():
        return True, 1.0, "No goal anchor set"

    if not change_intent or not change_intent.strip():
        return True, 1.0, "No change intent provided"

    threshold = threshold or config.get("threshold", 0.7)

    try:
        # Embed both texts
        anchor_vec = sync_embed_text(goal_anchor)
        intent_vec = sync_embed_text(change_intent)

        # Compute similarity
        similarity = cosine_similarity(anchor_vec, intent_vec)

        is_aligned = similarity >= threshold
        if is_aligned:
            message = f"Change aligns with goal (similarity={similarity:.2f} >= {threshold})"
        else:
            message = f"Potential goal drift detected (similarity={similarity:.2f} < {threshold})"
            logger.warning(f"[GoalDrift] {message}")
            logger.warning(f"[GoalDrift] Goal: {goal_anchor[:100]}...")
            logger.warning(f"[GoalDrift] Intent: {change_intent[:100]}...")

        return is_aligned, similarity, message

    except Exception as e:
        logger.warning(f"[GoalDrift] Check failed: {e}")
        return True, 1.0, f"Goal drift check failed: {e}"


def should_block_on_drift(
    goal_anchor: str,
    change_intent: str,
) -> Tuple[bool, str]:
    """
    Determine if a change should be blocked due to goal drift.

    Args:
        goal_anchor: Original goal text
        change_intent: Current change description

    Returns:
        Tuple of (should_block, reason)
    """
    config = _load_goal_drift_config()
    mode = config.get("mode", "advisory")

    is_aligned, similarity, message = check_goal_drift(goal_anchor, change_intent)

    if is_aligned:
        return False, message

    if mode == "blocking":
        return True, f"BLOCKED: {message}"
    else:
        # Advisory mode - log but don't block
        logger.info(f"[GoalDrift:Advisory] {message}")
        return False, f"ADVISORY: {message}"


def extract_goal_from_description(description: str) -> str:
    """
    Extract a short goal anchor from a run/phase description.

    Takes the first sentence or first 200 chars, whichever is shorter.

    Args:
        description: Full description text

    Returns:
        Short goal anchor string
    """
    if not description:
        return ""

    # Clean whitespace
    description = description.strip()

    # Try to get first sentence
    for delimiter in [". ", ".\n", "! ", "? "]:
        if delimiter in description:
            first_sentence = description.split(delimiter)[0] + delimiter[0]
            if len(first_sentence) <= 200:
                return first_sentence.strip()

    # Fall back to first 200 chars
    if len(description) > 200:
        return description[:200].rsplit(" ", 1)[0] + "..."

    return description
