"""
BUILD-129 Phase 3 P7+P9 Validation Analysis

Analyzes telemetry collected AFTER P7+P9 implementation to validate truncation reduction.

Metrics:
- Truncation rate (target: <25-30%)
- Waste ratio P90 using actual_max_tokens from P8
- SMAPE on non-truncated events
- Category-specific truncation rates

Go/No-Go Rule:
- If truncation >25-30%: Pause and tune buffers/estimator
- If truncation <25-30%: Resume stratified draining

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/analyze_p7p9_validation.py
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

# P7+P9 implementation cutoff (events before this are pre-P7+P9)
P7P9_CUTOFF = datetime(2025, 12, 25, 0, 15, 0)  # 2025-12-25 00:15:00


def analyze_p7p9_validation():
    """Analyze P7+P9 validation telemetry."""
    session = SessionLocal()

    print("=" * 70)
    print("BUILD-129 Phase 3 P7+P9: Validation Analysis")
    print("=" * 70)
    print()

    # Get all events
    all_events = session.query(TokenEstimationV2Event).all()

    # Separate pre-P7+P9 and post-P7+P9
    pre_p7p9 = [e for e in all_events if e.timestamp < P7P9_CUTOFF]
    post_p7p9 = [e for e in all_events if e.timestamp >= P7P9_CUTOFF]

    print(f"Total events: {len(all_events)}")
    print(f"  Pre-P7+P9 (before {P7P9_CUTOFF}): {len(pre_p7p9)}")
    print(f"  Post-P7+P9 (after {P7P9_CUTOFF}): {len(post_p7p9)}")
    print()

    if not post_p7p9:
        print("⚠️  No P7+P9 validation events found!")
        print(f"   All events are from before {P7P9_CUTOFF}")
        print()
        print("Action: Run validation batch with TELEMETRY_DB_ENABLED=1")
        session.close()
        return

    # Analyze P7+P9 events
    print("=" * 70)
    print("P7+P9 Validation Results")
    print("=" * 70)
    print()

    # Truncation rate
    truncated = [e for e in post_p7p9 if e.truncated]
    non_truncated = [e for e in post_p7p9 if not e.truncated]

    truncation_rate = len(truncated) / len(post_p7p9) * 100

    print(f"Truncation Rate: {truncation_rate:.1f}% ({len(truncated)}/{len(post_p7p9)})")
    print("  Target: <25-30%")
    print(
        f"  Baseline (pre-P7+P9): {len([e for e in pre_p7p9 if e.truncated]) / max(len(pre_p7p9), 1) * 100:.1f}%"
    )
    print()

    if truncation_rate > 30:
        print("  ❌ ABOVE TARGET - Need to tune buffers/estimator")
    elif truncation_rate > 25:
        print("  ⚠️  MARGINAL - Consider tuning")
    else:
        print("  ✅ BELOW TARGET - Good performance")
    print()

    # Waste ratio P90 (using actual_max_tokens from P8)
    waste_ratios = []
    for e in non_truncated:
        if e.selected_budget and e.actual_output_tokens:
            waste_ratio = e.selected_budget / e.actual_output_tokens
            waste_ratios.append(waste_ratio)

    if waste_ratios:
        if len(waste_ratios) >= 2:
            waste_p90 = (
                statistics.quantiles(waste_ratios, n=10)[8]
                if len(waste_ratios) >= 10
                else max(waste_ratios)
            )
            print(f"Waste Ratio P90: {waste_p90:.2f}x")
        print("  Ideal: 1.0-1.5x")
        print(f"  Mean: {statistics.mean(waste_ratios):.2f}x")
        if len(waste_ratios) >= 2:
            print(f"  Median: {statistics.median(waste_ratios):.2f}x")
        print(f"  Max: {max(waste_ratios):.2f}x")
        print()

    # SMAPE on non-truncated events
    if non_truncated:
        smapes = []
        for e in non_truncated:
            pred = e.predicted_output_tokens
            actual = e.actual_output_tokens
            if pred + actual > 0:
                smape = abs(pred - actual) * 200 / (abs(pred) + abs(actual))
                smapes.append(smape)

        print(
            f"SMAPE (Non-Truncated): {statistics.mean(smapes):.1f}% mean, {statistics.median(smapes):.1f}% median"
        )
        print("  Target: <50%")
        print(f"  Samples: {len(non_truncated)}")
        print()

    # Category-specific truncation
    from collections import Counter

    categories = Counter()
    truncated_by_cat = Counter()

    for e in post_p7p9:
        if e.category:
            categories[e.category] += 1
            if e.truncated:
                truncated_by_cat[e.category] += 1

    print("Truncation by Category:")
    for cat in sorted(categories.keys()):
        trunc = truncated_by_cat[cat]
        total_cat = categories[cat]
        rate = trunc / max(total_cat, 1) * 100
        print(f"  {cat}: {trunc}/{total_cat} ({rate:.1f}%)")
    print()

    # Detailed event breakdown
    print("=" * 70)
    print("Detailed Event Breakdown (Post-P7+P9)")
    print("=" * 70)
    print()

    for e in sorted(post_p7p9, key=lambda x: x.timestamp):
        trunc_marker = "🔴 TRUNCATED" if e.truncated else "✅ OK"
        utilization = e.actual_output_tokens / max(e.selected_budget, 1) * 100
        smape = (
            abs(e.predicted_output_tokens - e.actual_output_tokens)
            * 200
            / (abs(e.predicted_output_tokens) + abs(e.actual_output_tokens))
            if (e.predicted_output_tokens + e.actual_output_tokens) > 0
            else 0
        )

        print(f"{trunc_marker} {e.phase_id}")
        print(f"  Category: {e.category}, Complexity: {e.complexity}")
        print(
            f"  Predicted: {e.predicted_output_tokens}, Budget: {e.selected_budget}, Actual: {e.actual_output_tokens}"
        )
        print(f"  Utilization: {utilization:.1f}%, SMAPE: {smape:.1f}%")
        print()

    # Go/No-Go Decision
    print("=" * 70)
    print("GO/NO-GO DECISION")
    print("=" * 70)
    print()

    print(f"Sample size: {len(post_p7p9)} events")
    print(f"Truncation rate: {truncation_rate:.1f}%")
    print()

    if len(post_p7p9) < 10:
        print("❌ INSUFFICIENT DATA")
        print(f"   Need at least 10 events for Go/No-Go decision (have {len(post_p7p9)})")
        print()
        print("   Action: Run more validation batches")
        decision = "WAIT"
    elif truncation_rate > 30:
        print("🛑 NO-GO: Truncation rate >30%")
        print()
        print("   Action: Pause and tune buffers/estimator")
        print("   Recommendations:")
        print("   1. Increase buffer margins for high-truncation categories")
        print("   2. Implement escalate-once logic (Task 2)")
        print("   3. Use truncated events as constraints (Task 5)")
        decision = "PAUSE_AND_TUNE"
    elif truncation_rate > 25:
        print("⚠️  MARGINAL: Truncation rate 25-30%")
        print()
        print("   Action: Consider tuning or proceed with caution")
        print("   Recommendation: Implement escalate-once logic (Task 2)")
        decision = "MARGINAL"
    else:
        print("✅ GO: Truncation rate <25%")
        print()
        print("   Action: Resume stratified draining")
        print("   Target: Collect ≥50 success events for coefficient tuning")
        decision = "GO"

    print()
    print("=" * 70)

    session.close()

    return decision


if __name__ == "__main__":
    print("\n")

    decision = analyze_p7p9_validation()

    if decision == "GO":
        print("\n✅ P7+P9 validation PASSED - Ready for stratified draining")
        sys.exit(0)
    elif decision == "MARGINAL":
        print("\n⚠️  P7+P9 validation MARGINAL - Proceed with caution")
        sys.exit(0)
    elif decision == "PAUSE_AND_TUNE":
        print("\n🛑 P7+P9 validation FAILED - Pause and tune")
        sys.exit(1)
    else:  # WAIT
        print("\n❌ Insufficient data - Collect more samples")
        sys.exit(1)
