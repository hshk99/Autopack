"""
Pick the next run_id to drain.

Default behavior: "P10-first" selection (BUILD-129 Phase 3)
- Prefer queued runs that are most likely to trigger P10 (truncation / >=95% utilization),
  using the same scoring logic as scripts/create_p10_first_drain_plan.py.
- Fall back to "highest queued count" when no queued phase scores > 0.

Output:
- Default: TSV "run_id<TAB>run_type"

Usage:
  python scripts/pick_next_run.py
  python scripts/pick_next_run.py --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal  # noqa: E402
from autopack.models import Phase, PhaseState  # noqa: E402
from autopack.token_estimator import TokenEstimator  # noqa: E402


RUN_TYPE_AUTOPACK_RE = re.compile(r"^(build\d+|build-|build_|autopack\b|autopack-|autopack_)", re.IGNORECASE)


def infer_run_type(run_id: str) -> str:
    # Mirrors the run-id heuristic used by the Cursor takeover prompt.
    if RUN_TYPE_AUTOPACK_RE.match(run_id or ""):
        return "autopack_maintenance"
    return "project_build"


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


SOT_BASENAMES = {
    "build_log.md",
    "build_history.md",
    "changelog.md",
    "release_notes.md",
    "history.md",
}


def _has_sot(deliverables: List[str]) -> bool:
    for d in deliverables:
        if not isinstance(d, str):
            continue
        base = d.replace("\\", "/").split("/")[-1].lower()
        if base in SOT_BASENAMES:
            return True
    return False


@dataclass(frozen=True)
class ScoredPhase:
    run_id: str
    score: int
    deliverable_count: int


def score_phase_for_p10(phase: Phase, estimator: TokenEstimator) -> ScoredPhase | None:
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
        estimated_category = category_hint

    dcount = len(deliverables)
    score = 0

    if dcount >= 12:
        score += 3
    elif 8 <= dcount <= 11:
        score += 2

    if estimated_category in ["IMPLEMENT_FEATURE", "integration"]:
        score += 2

    if complexity == "high":
        score += 2

    if estimated_category in ["doc_synthesis", "doc_sot_update"]:
        score += 2

    if _has_sot(deliverables):
        score += 2

    if phase.last_failure_reason and "patch" in str(phase.last_failure_reason).lower():
        score -= 2

    if score <= 0:
        return None

    return ScoredPhase(run_id=phase.run_id, score=score, deliverable_count=dcount)


def pick_next_run_id_p10_first(queued_phases: Iterable[Phase], estimator: TokenEstimator) -> str | None:
    scored: List[ScoredPhase] = []
    for p in queued_phases:
        sp = score_phase_for_p10(p, estimator)
        if sp:
            scored.append(sp)

    if not scored:
        return None

    by_run: Dict[str, List[ScoredPhase]] = {}
    for sp in scored:
        by_run.setdefault(sp.run_id, []).append(sp)

    run_rank: List[Tuple[int, int, str]] = []
    for run_id, items in by_run.items():
        items.sort(key=lambda x: (x.score, x.deliverable_count), reverse=True)
        run_score = sum(i.score for i in items[:10])
        top_deliverables = items[0].deliverable_count
        run_rank.append((run_score, top_deliverables, run_id))

    run_rank.sort(reverse=True)
    return run_rank[0][2]


def pick_next_run_id_highest_queued(session) -> str | None:
    # Equivalent to scripts/list_run_counts.py ranking (but implemented directly here).
    rows = (
        session.query(Phase.run_id)
        .filter(Phase.state == PhaseState.QUEUED)
        .all()
    )
    if not rows:
        return None

    counts: Dict[str, int] = {}
    for (run_id,) in rows:
        counts[run_id] = counts.get(run_id, 0) + 1

    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[0][0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Pick the next run_id to drain (P10-first with fallback).")
    ap.add_argument("--format", choices=["tsv", "json"], default="tsv")
    args = ap.parse_args()

    session = SessionLocal()
    try:
        queued = session.query(Phase).filter(Phase.state == PhaseState.QUEUED).all()
        estimator = TokenEstimator(workspace=Path.cwd())

        run_id = pick_next_run_id_p10_first(queued, estimator) or pick_next_run_id_highest_queued(session)
        if not run_id:
            # No queued work
            if args.format == "json":
                print(json.dumps({"run_id": None, "run_type": None}))
            else:
                print("\t".join(["", ""]))
            return 0

        run_type = infer_run_type(run_id)
        if args.format == "json":
            print(json.dumps({"run_id": run_id, "run_type": run_type}))
        else:
            print(f"{run_id}\t{run_type}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())


