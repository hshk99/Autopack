"""
Telemetry-aware wrappers for intention anchor rendering.

Intention behind it: Track anchor usage in Phase6Metrics without adding database
dependencies to the core render module.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .render import (
    load_and_render_for_auditor,
    load_and_render_for_builder,
    load_and_render_for_doctor,
)

logger = logging.getLogger(__name__)


def load_and_render_for_builder_with_telemetry(
    run_id: str,
    phase_id: str,
    *,
    base_dir: str | Path = ".",
    db: Optional[Session] = None,
) -> Optional[str]:
    """
    Load anchor and render for Builder, emitting telemetry.

    Intention behind it: Track anchor usage in Phase6Metrics when Builder prompts
    include intention context.

    Args:
        run_id: Run identifier.
        phase_id: Current phase identifier.
        base_dir: Base directory for anchor storage (default: ".").
        db: Optional database session for telemetry recording.

    Returns:
        Rendered prompt section or None if anchor doesn't exist.
    """
    rendered = load_and_render_for_builder(
        run_id=run_id,
        phase_id=phase_id,
        base_dir=base_dir,
    )

    if rendered and db:
        try:
            from autopack.usage_recorder import record_phase6_metrics

            record_phase6_metrics(
                db=db,
                run_id=run_id,
                phase_id=phase_id,
                intention_context_injected=True,
                intention_context_chars=len(rendered),
                intention_context_source="anchor",
            )
        except Exception as e:
            logger.warning(
                f"[{phase_id}] Failed to record intention anchor telemetry: {e}"
            )

    return rendered


def load_and_render_for_auditor_with_telemetry(
    run_id: str,
    phase_id: str,  # Auditor needs phase_id for telemetry even though renderer doesn't
    *,
    base_dir: str | Path = ".",
    db: Optional[Session] = None,
) -> Optional[str]:
    """
    Load anchor and render for Auditor, emitting telemetry.

    Intention behind it: Track anchor usage in Phase6Metrics when Auditor prompts
    include intention context.

    Args:
        run_id: Run identifier.
        phase_id: Current phase identifier (for telemetry).
        base_dir: Base directory for anchor storage (default: ".").
        db: Optional database session for telemetry recording.

    Returns:
        Rendered prompt section or None if anchor doesn't exist.
    """
    rendered = load_and_render_for_auditor(
        run_id=run_id,
        base_dir=base_dir,
    )

    if rendered and db:
        try:
            from autopack.usage_recorder import record_phase6_metrics

            record_phase6_metrics(
                db=db,
                run_id=run_id,
                phase_id=phase_id,
                intention_context_injected=True,
                intention_context_chars=len(rendered),
                intention_context_source="anchor",
            )
        except Exception as e:
            logger.warning(
                f"[{phase_id}] Failed to record intention anchor telemetry: {e}"
            )

    return rendered


def load_and_render_for_doctor_with_telemetry(
    run_id: str,
    phase_id: str,
    *,
    base_dir: str | Path = ".",
    db: Optional[Session] = None,
) -> Optional[str]:
    """
    Load anchor and render for Doctor, emitting telemetry.

    Intention behind it: Track anchor usage in Phase6Metrics when Doctor prompts
    include intention context.

    Args:
        run_id: Run identifier.
        phase_id: Current phase identifier.
        base_dir: Base directory for anchor storage (default: ".").
        db: Optional database session for telemetry recording.

    Returns:
        Rendered prompt section or None if anchor doesn't exist.
    """
    rendered = load_and_render_for_doctor(
        run_id=run_id,
        base_dir=base_dir,
    )

    if rendered and db:
        try:
            from autopack.usage_recorder import record_phase6_metrics

            record_phase6_metrics(
                db=db,
                run_id=run_id,
                phase_id=phase_id,
                intention_context_injected=True,
                intention_context_chars=len(rendered),
                intention_context_source="anchor",
            )
        except Exception as e:
            logger.warning(
                f"[{phase_id}] Failed to record intention anchor telemetry: {e}"
            )

    return rendered
