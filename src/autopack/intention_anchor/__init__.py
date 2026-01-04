"""
Intention Anchor module - canonical, versioned intent representation for runs.

Public API exports:
    - IntentionAnchor: main schema
    - IntentionConstraints, IntentionScope, IntentionBudgets, IntentionRiskProfile: sub-schemas
    - create_anchor, save_anchor, load_anchor, update_anchor: storage helpers
    - render_for_prompt, render_compact: prompt renderers
    - render_for_builder, render_for_auditor, render_for_doctor: agent-specific renderers
    - load_and_render_for_builder, load_and_render_for_auditor, load_and_render_for_doctor: prompt injection helpers
    - get_canonical_path: path resolver
"""

from .models import (
    IntentionAnchor,
    IntentionBudgets,
    IntentionConstraints,
    IntentionRiskProfile,
    IntentionScope,
)
from .render import (
    load_and_render_for_auditor,
    load_and_render_for_builder,
    load_and_render_for_doctor,
    render_compact,
    render_for_auditor,
    render_for_builder,
    render_for_doctor,
    render_for_prompt,
)
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
    # Rendering (general)
    "render_for_prompt",
    "render_compact",
    # Rendering (agent-specific)
    "render_for_builder",
    "render_for_auditor",
    "render_for_doctor",
    # Prompt injection helpers
    "load_and_render_for_builder",
    "load_and_render_for_auditor",
    "load_and_render_for_doctor",
]
