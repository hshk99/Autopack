"""
BUILD-129 Phase 3: P10-first Drain Plan

Goal:
- Find queued phases most likely to trigger P10 (truncation / >=95% utilization).
- Output a ranked plan that is practical to execute with scripts/drain_queued_phases.py (run_id-level).

Why:
Targeted replay is non-deterministic; P10 should be validated during representative draining.
This script makes that token-efficient by prioritizing high-probability phases/runs first.

Usage:
  TELEMETRY_DB_ENABLED=1 PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
    python scripts/create_p10_first_drain_plan.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
from autopack.token_estimator import TokenEstimator


SOT_BASENAMES = {
    "build_log.md",
    "build_history.md",
    "changelog.md",
    "release_notes.md",
    "history.md",
}


def _flatten_deliverables(scope: Any) -> List[str]:
    if not isinstance(scope, dict):
        return []

    deliverables = scope.get("deliverables")
    if deliverables is None and isinstance(scope.get("scope"), dict):
        deliverables = scope["scope"].get("deliverables")

    return TokenEstimator.normalize_deliverables(deliverables)


def _guess_complexity(phase: Phase) -> str:
    if phase.complexity:
        return str(phase.complexity)
    if isinstance(phase.scope, dict) and phase.scope.get("complexity"):
        return str(phase.scope.get("complexity"))
    return "medium"


def _guess_category_hint(phase: Phase) -> str:
    if phase.task_category:
        return str(phase.task_category)
    if isinstance(phase.scope, dict) and phase.scope.get("category"):
        return str(phase.scope.get("category"))
    return "implementation"


def _has_sot(deliverables: List[str]) -> bool:
    for d in deliverables:
        if not isinstance(d, str):
            continue
        base = d.replace("\\", "/").split("/")[-1].lower()
        if base in SOT_BASENAMES:
            return True
    return False


@dataclass
class ScoredPhase:
    run_id: str
    phase_id: str
    complexity: str
    deliverable_count: int
    estimated_category: str
    builder_mode: str | None
    score: int
    reasons: List[str]


def score_phase(phase: Phase, estimator: TokenEstimator) -> ScoredPhase | None:
    if phase.state != PhaseState.QUEUED:
        return None

    scope = phase.scope if isinstance(phase.scope, dict) else {}
    deliverables = _flatten_deliverables(scope)
    if not deliverables:
        return None

    complexity = _guess_complexity(phase)
    category_hint = _guess_category_hint(phase)
    scope_paths = scope.get("paths", []) if isinstance(scope.get("paths", []), list) else []
    task_description = (phase.description or "") + " " + (phase.name or "")

    try:
        estimate = estimator.estimate(
            deliverables=deliverables,
            category=category_hint,
            complexity=complexity,
            scope_paths=scope_paths,
            task_description=task_description,
        )
        estimated_category = estimate.category
    except Exception:
        # If estimator fails for any reason, fall back to hint.
        estimated_category = category_hint

    dcount = len(deliverables)
    score = 0
    reasons: List[str] = []

    # Deliverable count: big predictor of long outputs
    if dcount >= 12:
        score += 3
        reasons.append("deliverables>=12 (+3)")
    elif 8 <= dcount <= 11:
        score += 2
        reasons.append("deliverables 8-11 (+2)")

    # Risky categories: feature/integration tend to be verbose and iterative
    if estimated_category in ["IMPLEMENT_FEATURE", "integration"]:
        score += 2
        reasons.append(f"category={estimated_category} (+2)")

    # High complexity: often longer output
    if complexity == "high":
        score += 2
        reasons.append("complexity=high (+2)")

    # Docs synthesis / SOT updates: high variance and can be long
    if estimated_category in ["doc_synthesis", "doc_sot_update"]:
        score += 2
        reasons.append(f"category={estimated_category} (+2)")

    # Additional signal: SOT deliverable even if category didn't flip
    if _has_sot(deliverables):
        score += 2
        reasons.append("has_sot_file (+2)")

    # Builder hints
    builder_mode = phase.builder_mode
    if isinstance(scope.get("builder_mode"), str) and not builder_mode:
        builder_mode = scope.get("builder_mode")
    if isinstance(scope.get("change_size"), str):
        # "large_refactor" frequently implies bigger outputs
        if scope.get("change_size") in ["large", "large_refactor"]:
            score += 1
            reasons.append("change_size=large (+1)")

    # Penalize phases that were already failing repeatedly (optional; keeps drain efficient)
    if phase.last_failure_reason and "patch" in str(phase.last_failure_reason).lower():
        score -= 2
        reasons.append("last_failure_reason~patch (-2)")

    return ScoredPhase(
        run_id=phase.run_id,
        phase_id=phase.phase_id,
        complexity=complexity,
        deliverable_count=dcount,
        estimated_category=estimated_category,
        builder_mode=builder_mode,
        score=score,
        reasons=reasons,
    )


def main() -> None:
    session = SessionLocal()
    estimator = TokenEstimator(workspace=Path.cwd())
    try:
        queued = session.query(Phase).filter(Phase.state == PhaseState.QUEUED).all()
        scored: List[ScoredPhase] = []
        for p in queued:
            sp = score_phase(p, estimator)
            if sp and sp.score > 0:
                scored.append(sp)

        scored.sort(key=lambda x: (x.score, x.deliverable_count), reverse=True)

        print("=" * 80)
        print("BUILD-129 Phase 3: P10-first Drain Plan (Ranked)")
        print("=" * 80)
        print(f"Queued phases scanned: {len(queued)}")
        print(f"High-probability phases (score>0): {len(scored)}")
        print()

        # Show top phases
        top_n = 30
        print(f"Top {min(top_n, len(scored))} phases by P10 trigger probability:")
        for sp in scored[:top_n]:
            print(
                f"- score={sp.score:2d} run_id={sp.run_id} phase_id={sp.phase_id} "
                f"cat={sp.estimated_category} cx={sp.complexity} deliverables={sp.deliverable_count}"
            )
            if sp.reasons:
                print(f"  reasons: {', '.join(sp.reasons)}")

        # Aggregate by run_id so we can execute with drain_queued_phases.py
        by_run: Dict[str, List[ScoredPhase]] = {}
        for sp in scored:
            by_run.setdefault(sp.run_id, []).append(sp)

        run_rank: List[Tuple[int, str, int]] = []
        for run_id, items in by_run.items():
            run_score = sum(i.score for i in items[:10])  # cap influence
            run_rank.append((run_score, run_id, len(items)))
        run_rank.sort(reverse=True)

        print("\n" + "=" * 80)
        print("Recommended run_ids to drain first (ranked):")
        print("=" * 80)
        for run_score, run_id, count in run_rank[:10]:
            print(f"- run_id={run_id} run_score={run_score} high_prob_phases={count}")

        print("\n" + "=" * 80)
        print("Suggested execution commands (top 4 runs):")
        print("=" * 80)
        for run_score, run_id, count in run_rank[:4]:
            # Conservative batch sizing: keep batches small to avoid long hangs
            batch_size = 3
            max_batches = 4
            print(f"# P10-first drain: {run_id} (run_score={run_score}, high_prob_phases={count})")
            print(
                'TELEMETRY_DB_ENABLED=1 PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \\'
            )
            print("  timeout 600 python scripts/drain_queued_phases.py \\")
            print(f"  --run-id {run_id} \\")
            print(f"  --batch-size {batch_size} \\")
            print(f"  --max-batches {max_batches}")
            print()

        print("Note: Once the first P10 trigger happens, validate it via:")
        # ASCII-only to avoid Windows console/encoding issues.
        print("  - log line: [BUILD-129:P10] ESCALATE-ONCE: base=... (from ...) -> retry=...")
        print("  - DB: token_budget_escalation_events (new) once migrations are applied.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
