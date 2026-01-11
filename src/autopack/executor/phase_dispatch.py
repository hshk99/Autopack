"""Phase dispatch helpers for AutonomousExecutor.

Goal:
- Reduce merge conflicts and cognitive load in `autonomous_executor.py` by moving
  the special-case phase-id ladder into a small registry.

Design (PR1):
- Keep it extremely small and non-invasive.
- The registry returns *method names* that already exist on AutonomousExecutor.
  This avoids moving large handler bodies in the first refactor PR.

Follow-ups:
- Migrate method-name mapping to real handler objects under `executor/phase_handlers/`.
"""

from __future__ import annotations

from typing import Optional

SPECIAL_PHASE_METHODS: dict[str, str] = {
    "research-tracer-bullet": "_execute_research_tracer_bullet_batched",
    "research-gatherers-web-compilation": "_execute_research_gatherers_web_compilation_batched",
    "diagnostics-handoff-bundle": "_execute_diagnostics_handoff_bundle_batched",
    "diagnostics-cursor-prompt": "_execute_diagnostics_cursor_prompt_batched",
    "diagnostics-second-opinion-triage": "_execute_diagnostics_second_opinion_batched",
    "diagnostics-deep-retrieval": "_execute_diagnostics_deep_retrieval_batched",
    "diagnostics-iteration-loop": "_execute_diagnostics_iteration_loop_batched",
}


def resolve_special_phase_method(phase_id: Optional[str]) -> Optional[str]:
    """Return AutonomousExecutor method name for special phase_id, else None."""
    if not phase_id:
        return None
    return SPECIAL_PHASE_METHODS.get(phase_id)
