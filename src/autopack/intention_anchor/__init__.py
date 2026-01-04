"""
Intention Anchor module - canonical, versioned intent representation for runs.

Public API exports:
    - IntentionAnchor: main schema
    - IntentionConstraints, IntentionScope, IntentionBudgets, IntentionRiskProfile: sub-schemas
    - create_anchor, save_anchor, load_anchor, update_anchor: storage helpers
    - render_for_prompt, render_compact: prompt renderers
    - get_canonical_path: path resolver
"""

from .models import (
    IntentionAnchor,
    IntentionBudgets,
    IntentionConstraints,
    IntentionRiskProfile,
    IntentionScope,
)
from .render import render_compact, render_for_prompt
from .storage import (
    create_anchor,
    get_canonical_path,
    load_anchor,
    save_anchor,
    update_anchor,
)

__all__ = [
    # Models
    "IntentionAnchor",
    "IntentionConstraints",
    "IntentionScope",
    "IntentionBudgets",
    "IntentionRiskProfile",
    # Storage
    "create_anchor",
    "save_anchor",
    "load_anchor",
    "update_anchor",
    "get_canonical_path",
    # Rendering
    "render_for_prompt",
    "render_compact",
]
