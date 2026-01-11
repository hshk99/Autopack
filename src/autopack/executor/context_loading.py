"""Context loading policy for AutonomousExecutor.

Goal (PR2):
- Keep the *policy* (scope precedence + pattern targeting selection) in a small,
  testable module to reduce merge conflicts in `autonomous_executor.py`.

Non-goal (PR2):
- Move the full heuristic loader implementation out of the executor yet.

Design:
- Expects an executor object with:
  - _load_scoped_context
  - _load_targeted_context_for_templates
  - _load_targeted_context_for_frontend
  - _load_targeted_context_for_docker
  - _load_repository_context_heuristic (fallback)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_repository_context(executor: Any, phase: dict) -> dict:
    phase_id = phase.get("phase_id", "")
    phase_name = (phase.get("name", "") or "").lower()
    phase_desc = (phase.get("description", "") or "").lower()
    task_category = phase.get("task_category", "")

    scope_config = phase.get("scope")
    if scope_config and scope_config.get("paths"):
        logger.info(f"[{phase_id}] Using scope-aware context (overrides targeted context)")
        return executor._load_scoped_context(phase, scope_config)

    if "template" in phase_name and ("country" in phase_desc or "template" in phase_id):
        logger.info(f"[{phase_id}] Using targeted context for country template phase")
        return executor._load_targeted_context_for_templates(phase)

    if task_category == "frontend" or "frontend" in phase_name:
        logger.info(f"[{phase_id}] Using targeted context for frontend phase")
        return executor._load_targeted_context_for_frontend(phase)

    if "docker" in phase_name or task_category == "deployment":
        logger.info(f"[{phase_id}] Using targeted context for docker/deployment phase")
        return executor._load_targeted_context_for_docker(phase)

    return executor._load_repository_context_heuristic(phase)
