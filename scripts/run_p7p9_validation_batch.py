"""
BUILD-129 Phase 3 P7+P9 Validation Batch

Runs 10-15 phases with intentional coverage to validate truncation reduction:
- 3-5 documentation phases (DOC_SYNTHESIS + SOT)
- 3-5 implement_feature phases
- 2-3 testing phases

After validation, recompute:
- Truncation rate (target: <25-30%)
- Waste ratio P90 using actual_max_tokens
- SMAPE on non-truncated events

Go/No-Go rule: If truncation >25-30%, pause and tune before full backlog drain.

Usage:
    TELEMETRY_DB_ENABLED=1 PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/run_p7p9_validation_batch.py
"""

import sys
from pathlib import Path
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase


def select_validation_phases():
    """Select 10-15 phases with intentional coverage."""
    session = SessionLocal()

    print("=" * 70)
    print("BUILD-129 Phase 3 P7+P9: Validation Batch Selection")
    print("=" * 70)
    print()

    # Get all QUEUED phases
    queued_phases = session.query(Phase).filter(Phase.state == "QUEUED").all()

    print(f"Total QUEUED phases: {len(queued_phases)}")
    print()

    # Categorize phases
    targets = {
        "documentation": [],  # DOC_SYNTHESIS + SOT
        "implement_feature": [],
        "testing": [],
        "other": [],
    }

    for phase in queued_phases:
        scope = phase.scope if isinstance(phase.scope, dict) else {}
        category = scope.get("category", "unknown")
        complexity = scope.get("complexity", "medium")
        deliverables = scope.get("deliverables", [])

        # Normalize deliverables
        if isinstance(deliverables, dict):
            flat_delivs = []
            for v in deliverables.values():
                if isinstance(v, list):
                    flat_delivs.extend(v)
                else:
                    flat_delivs.append(v)
            deliverables = flat_delivs
        elif not isinstance(deliverables, list):
            deliverables = []

        dcount = len(deliverables)

        phase_info = {
            "run_id": phase.run_id,
            "phase_id": phase.phase_id,
            "category": category,
            "complexity": complexity,
            "deliverable_count": dcount,
            "deliverables": deliverables[:5],  # First 5 for preview
        }

        # Classify phase
        if category in ["documentation", "docs"]:
            targets["documentation"].append(phase_info)
        elif category in ["testing", "test"]:
            targets["testing"].append(phase_info)
        elif category in ["IMPLEMENT_FEATURE", "implementation", "feature"]:
            targets["implement_feature"].append(phase_info)
        else:
            targets["other"].append(phase_info)

    # Print distribution
    print("Available phases by category:")
    for cat, phases in targets.items():
        if phases:
            print(f"  {cat}: {len(phases)} phases")
    print()

    # Select validation batch (target: 10-15 phases)
    validation_batch = []

    # Priority 1: 3-5 documentation phases (DOC_SYNTHESIS + SOT)
    doc_phases = targets["documentation"][:5]
    validation_batch.extend(doc_phases)
    print(f"Selected {len(doc_phases)} documentation phases")

    # Priority 2: 3-5 implement_feature phases
    impl_phases = targets["implement_feature"][:5]
    validation_batch.extend(impl_phases)
    print(f"Selected {len(impl_phases)} implement_feature phases")

    # Priority 3: 2-3 testing phases
    test_phases = targets["testing"][:3]
    validation_batch.extend(test_phases)
    print(f"Selected {len(test_phases)} testing phases")

    print()
    print("=" * 70)
    print(f"Validation Batch: {len(validation_batch)} phases")
    print("=" * 70)
    print()

    # Print batch details
    for i, p in enumerate(validation_batch, 1):
        print(f"{i}. {p['run_id']} / {p['phase_id']}")
        print(
            f"   Category: {p['category']}, Complexity: {p['complexity']}, Deliverables: {p['deliverable_count']}"
        )

    print()
    print("=" * 70)
    print("Execution Commands:")
    print("=" * 70)
    print()

    # Group by run_id
    by_run = defaultdict(list)
    for p in validation_batch:
        by_run[p["run_id"]].append(p["phase_id"])

    for run_id, phase_ids in by_run.items():
        print(f"# {run_id} ({len(phase_ids)} phases)")
        print(
            'TELEMETRY_DB_ENABLED=1 PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \\'
        )
        print("  timeout 600 python scripts/drain_queued_phases.py \\")
        print(f"  --run-id {run_id} \\")
        print(f"  --batch-size {len(phase_ids)} \\")
        print("  --max-batches 1")
        print()

    session.close()

    return validation_batch


if __name__ == "__main__":
    print("\n")

    validation_batch = select_validation_phases()

    print("=" * 70)
    print("Next Steps:")
    print("=" * 70)
    print()
    print("1. Run the execution commands above to process validation batch")
    print("2. After completion, run:")
    print(
        '   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/analyze_token_telemetry_v3.py'
    )
    print()
    print("3. Check metrics:")
    print("   - Truncation rate (target: <25-30%)")
    print("   - Waste ratio P90 using actual_max_tokens")
    print("   - SMAPE on non-truncated events")
    print()
    print("4. Go/No-Go decision:")
    print("   - If truncation <25-30%: Resume stratified draining")
    print("   - If truncation >25-30%: Pause and tune buffers/estimator")
    print()
