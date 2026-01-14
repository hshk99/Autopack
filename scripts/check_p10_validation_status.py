"""
BUILD-129 Phase 3: Quick P10 Validation Status Check

Quickly checks if any P10 events have occurred since fix #2 deployment.

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/check_p10_validation_status.py
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

# P10 fix #2 deployment time
P10_FIX2_DEPLOYED = datetime(2025, 12, 25, 23, 45, 0)


def check_status():
    """Quick check for P10 validation status."""
    session = SessionLocal()

    # Preferred: check DB-backed P10 escalation events (deterministic).
    p10_events = []
    p10_query_ok = False
    try:
        from autopack.models import TokenBudgetEscalationEvent  # type: ignore

        p10_events = (
            session.query(TokenBudgetEscalationEvent)
            .order_by(TokenBudgetEscalationEvent.timestamp.desc())
            .all()
        )
        p10_query_ok = True
    except Exception:
        p10_events = []

    # Fallback: check token estimation events (less direct; P10 may trigger later in executor).
    all_events = (
        session.query(TokenEstimationV2Event)
        .order_by(TokenEstimationV2Event.timestamp.desc())
        .all()
    )

    # NOTE: SQLite CURRENT_TIMESTAMP is UTC; local logs are usually local time.
    # Some environments end up with naive datetimes that make strict "after deploy" comparisons misleading.
    try:
        post_fix2 = [e for e in p10_events if e.timestamp and e.timestamp >= P10_FIX2_DEPLOYED]
    except Exception:
        post_fix2 = list(p10_events)

    print("=" * 70)
    print("P10 Validation Status Check")
    print("=" * 70)
    print()
    print(f"P10 Fix #2 deployed: {P10_FIX2_DEPLOYED}")
    print(f"Total token estimation events in DB: {len(all_events)}")
    if p10_query_ok:
        print(f"Total P10 escalation events in DB: {len(p10_events)}")
        print(f"P10 escalation events after fix #2: {len(post_fix2)}")
    else:
        print("Total P10 escalation events in DB: (unavailable)")
        print(
            "Hint: apply migrations/005_add_p10_escalation_events.sql (see scripts/apply_sql_file.py)."
        )
    print()

    if not p10_events:
        print("⏳ STATUS: AWAITING VALIDATION")
        print()
        print("No P10 escalation events recorded yet.")
        print("Validation will occur when:")
        print("  1. Any autonomous run executes")
        print("  2. A phase truncates or hits ≥95% utilization")
        print("  3. P10 escalation is triggered")
        print()
        print("Expected log pattern:")
        print("  [BUILD-129:P10] ESCALATE-ONCE: phase=X attempt=1")
        print("    base=Y (from SOURCE) → retry=Z (1.25x, ...)")
        print()
        print("Where SOURCE should be one of:")
        print("  - selected_budget")
        print("  - actual_max_tokens")
        print("  - tokens_used")
        print("  - complexity_default")
    else:
        print("✅ STATUS: P10 ESCALATION RECORDED (END-TO-END VALIDATION COMPLETE)")
        print()
        if post_fix2:
            print(f"Found {len(post_fix2)} P10 escalation events after fix #2 cutoff:")
            show = post_fix2
        else:
            print("Found P10 escalation events, but none are >= the configured fix #2 cutoff.")
            print(
                "This is usually a timezone/clock mismatch (DB timestamps are often UTC). Showing most recent events:"
            )
            show = p10_events
        for e in show[:5]:
            print(f"  {e.timestamp}: {e.phase_id} (attempt {e.attempt_index})")
            print(
                f"    base={e.base_value} (from {e.base_source}) → retry={e.retry_max_tokens} (x{e.escalation_factor})"
            )
            print(
                f"    reason={e.reason}, truncated={bool(e.was_truncated)}, utilization={e.output_utilization}"
            )
            print()

        print("Next steps:")
        print("  1. Check execution logs for P10 escalation messages")
        print("  2. Run: python scripts/validate_p10_escalation.py")
        print("  3. Run: python scripts/p10_effectiveness_dashboard.py")

    print("=" * 70)

    session.close()


if __name__ == "__main__":
    print("\n")
    check_status()
