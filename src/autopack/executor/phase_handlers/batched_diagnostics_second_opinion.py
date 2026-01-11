"""Phase handler for diagnostics-second-opinion-triage batched execution.

Specialized in-phase batching for followup-3 `diagnostics-second-opinion-triage` (code -> tests -> docs).
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple


def execute(
    executor: Any,
    *,
    phase: dict,
    attempt_index: int,
    allowed_paths: Optional[List[str]],
) -> Tuple[bool, str]:
    """Execute diagnostics-second-opinion-triage phase with batched deliverables.

    Args:
        executor: AutonomousExecutor instance.
        phase: Phase specification dictionary.
        attempt_index: Current 0-based attempt number.
        allowed_paths: List of allowed file paths for scope enforcement, or None.

    Returns:
        Tuple of (success, status) where status is "COMPLETE", "FAILED", etc.
    """
    # Import inside function to avoid circular imports
    from autopack.deliverables_validator import extract_deliverables_from_scope

    scope_base = phase.get("scope") or {}
    all_paths = [
        p for p in extract_deliverables_from_scope(scope_base) if isinstance(p, str) and p.strip()
    ]

    # Batch 1: code
    batch_code = sorted([p for p in all_paths if p.startswith("src/autopack/diagnostics/")])
    # Batch 2: tests
    batch_tests = sorted([p for p in all_paths if p.startswith("tests/autopack/diagnostics/")])
    # Batch 3: docs
    batch_docs = sorted([p for p in all_paths if p.startswith("docs/autopack/")])

    batches = [b for b in [batch_code, batch_tests, batch_docs] if b]
    if not batches:
        batches = [sorted(set(all_paths))]

    return executor._execute_batched_deliverables_phase(
        phase=phase,
        attempt_index=attempt_index,
        allowed_paths=allowed_paths,
        batches=batches,
        batching_label="diagnostics_second_opinion",
        manifest_allowed_roots=(
            "src/autopack/diagnostics/",
            "tests/autopack/diagnostics/",
            "docs/autopack/",
        ),
        apply_allowed_roots=(
            "src/autopack/diagnostics/",
            "tests/autopack/diagnostics/",
            "docs/autopack/",
        ),
    )
