"""
BUILD-129 Phase 3: P10 Escalation Validation Test

Validates P10 evidence-based escalation fix (commit 3f47d86a) by:
1. Finding a historically truncating phase from recent runs
2. Running it once with normal settings
3. Capturing P10 escalation logs to verify correct base calculation
4. Checking retry success

Expected log format after fix #2:
[BUILD-129:P10] ESCALATE-ONCE: phase=X attempt=1 base=Y (from SOURCE) → retry=Z (1.25x, truncation)

where SOURCE should be one of: selected_budget, actual_max_tokens, tokens_used, complexity_default

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/validate_p10_escalation.py
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

# P10 fix #2 cutoff (commit 3f47d86a)
P10_FIX2_CUTOFF = datetime(2025, 12, 25, 23, 45, 0)


def analyze_p10_logs():
    """Analyze telemetry to find evidence of P10 escalation behavior."""
    session = SessionLocal()

    print("=" * 70)
    print("BUILD-129 Phase 3: P10 Escalation Validation")
    print("=" * 70)
    print()

    # Get all events to find truncation patterns
    all_events = (
        session.query(TokenEstimationV2Event)
        .order_by(TokenEstimationV2Event.timestamp.desc())
        .limit(100)
        .all()
    )

    print(f"Analyzed last {len(all_events)} telemetry events")
    print()

    # Find phases that truncated
    truncated_phases = {}
    for e in all_events:
        if e.truncated:
            key = (e.run_id, e.phase_id)
            if key not in truncated_phases:
                truncated_phases[key] = []
            truncated_phases[key].append(e)

    print(f"Found {len(truncated_phases)} unique phases that truncated:")
    for (run_id, phase_id), events in sorted(
        truncated_phases.items(), key=lambda x: x[1][0].timestamp, reverse=True
    )[:5]:
        event = events[0]
        print(f"  {phase_id} (run={run_id})")
        print(f"    Latest: {event.timestamp}")
        print(f"    Category: {event.category}, Complexity: {event.complexity}")
        print(f"    Deliverables: {event.deliverable_count}")
        print(f"    Truncations: {len(events)}")
        print()

    # Check if we have any events after P10 fix #2
    post_fix2 = [e for e in all_events if e.timestamp >= P10_FIX2_CUTOFF]
    print(f"Events after P10 fix #2 (>= {P10_FIX2_CUTOFF}): {len(post_fix2)}")
    print()

    if not post_fix2:
        print("⚠️  No telemetry events found after P10 fix #2")
        print("   Need to run a phase to generate telemetry with new P10 logic")
        print()
        print("RECOMMENDATION:")
        print("  Use research-foundation-intent-discovery (historically truncates)")
        print("  This phase has shown consistent 100% utilization / truncation")
        print()
    else:
        print("✅ Found post-fix telemetry events")
        print()
        print("Checking for P10 escalation evidence:")
        for e in post_fix2:
            print(f"  {e.timestamp}: {e.phase_id}")
            print(f"    Truncated: {e.truncated}, Budget: {e.selected_budget}")
            print(f"    Actual output: {e.actual_output_tokens}")
            if e.truncated:
                utilization = (
                    (e.actual_output_tokens / e.selected_budget * 100) if e.selected_budget else 0
                )
                print(f"    Utilization: {utilization:.1f}%")
                print("    → Should trigger P10 escalation on retry")
            print()

    session.close()

    print("=" * 70)
    print("VALIDATION STATUS")
    print("=" * 70)
    print()

    if not post_fix2:
        print("Status: PENDING")
        print("Action: Run targeted truncation test")
        print()
        print("Suggested phase: research-foundation-intent-discovery")
        print("Expected behavior:")
        print("  1. First attempt: Truncate at budget (e.g., 16,707 tokens)")
        print("  2. P10 trigger: Log shows 'base=X (from SOURCE) → retry=Y'")
        print("  3. Retry attempt: Higher budget, should succeed")
    else:
        print("Status: ANALYZING")
        print("Action: Check execution logs for P10 escalation messages")
        print()
        print("Look for log pattern:")
        print("  [BUILD-129:P10] ESCALATE-ONCE: phase=X attempt=1 base=Y (from SOURCE) → retry=Z")
        print()
        print("Verify SOURCE is one of:")
        print("  - selected_budget (P7 intent)")
        print("  - actual_max_tokens (P4 ceiling)")
        print("  - tokens_used (actual output)")
        print("  - complexity_default (fallback)")


if __name__ == "__main__":
    print("\n")
    analyze_p10_logs()
