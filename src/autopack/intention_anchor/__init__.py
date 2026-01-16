"""
Intention Anchor module - canonical, versioned intent representation for runs.

Also known as: Intentions Framework v2 (from BUILD-178)
See: docs/BUILD_HISTORY.md "Phase 6" Naming Clarification section
     docs/PHASE_NAMING.md for full clarification

This module provides the intention anchoring system for guiding autonomous execution.
Previously documented as "Phase 6 Intentions" in BUILD-178.

NOT to be confused with "Execution Hardening" from BUILD-146 (src/autopack/executor/)
which covers failure recovery, plan normalization, and retry budget management.

Public API exports (v1 - existing):
    - IntentionAnchor: main schema
    - IntentionConstraints, IntentionScope, IntentionBudgets, IntentionRiskProfile: sub-schemas
    - create_anchor, save_anchor, load_anchor, update_anchor: storage helpers
    - render_for_prompt, render_compact: prompt renderers
    - render_for_builder, render_for_auditor, render_for_doctor: agent-specific renderers
    - load_and_render_for_builder, load_and_render_for_auditor, load_and_render_for_doctor: prompt injection helpers
    - load_and_render_for_builder_with_telemetry, load_and_render_for_auditor_with_telemetry, load_and_render_for_doctor_with_telemetry: telemetry-aware helpers
    - get_canonical_path: path resolver
    - generate_anchor_summary, save_anchor_summary, log_anchor_event, read_anchor_events: SOT artifact helpers

Public API exports (v2 - universal pivot intentions):
    - IntentionAnchorV2: v2 schema (universal pivot intentions)
    - create_from_inputs: create v2 anchor from inputs
    - validate_pivot_completeness: validate v2 anchor completeness
"""

from .artifacts import (
    generate_anchor_diff_summary,
    generate_anchor_summary,
    get_anchor_events_path,
    get_anchor_summary_path,
    log_anchor_event,
    read_anchor_events,
    save_anchor_summary,
)
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
from .telemetry import (
    load_and_render_for_auditor_with_telemetry,
    load_and_render_for_builder_with_telemetry,
    load_and_render_for_doctor_with_telemetry,
)
from .v2 import (
    IntentionAnchorV2,
    create_from_inputs,
    validate_pivot_completeness,
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
    # Telemetry-aware prompt injection helpers
    "load_and_render_for_builder_with_telemetry",
    "load_and_render_for_auditor_with_telemetry",
    "load_and_render_for_doctor_with_telemetry",
    # SOT artifact helpers
    "generate_anchor_summary",
    "save_anchor_summary",
    "log_anchor_event",
    "read_anchor_events",
    "get_anchor_summary_path",
    "get_anchor_events_path",
    "generate_anchor_diff_summary",
    # V2 Models and helpers
    "IntentionAnchorV2",
    "create_from_inputs",
    "validate_pivot_completeness",
]
