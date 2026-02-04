"""
BUILD-129 Phase 3 P10: Effectiveness Dashboard

Tracks P10 escalate-once effectiveness during stratified draining.

Metrics (rolling every 10 events):
- first_attempt_truncation_rate: Truncation on initial attempt
- p10_trigger_rate: How often P10 escalates
- p10_retry_success_rate: Did escalation fix truncation?
- clean_smape_median: Accuracy on non-truncated (valid events)
- waste_ratio_p90: Budget efficiency using actual_max_tokens

Stop Criteria:
- first_attempt_truncation >40%
- p10_retry_success <80%

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/p10_effectiveness_dashboard.py
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics
from collections import Counter, defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

# P7+P9+P10 implementation cutoff (events before this are pre-P10)
P7P9_CUTOFF = datetime(2025, 12, 25, 0, 15, 0)  # 2025-12-25 00:15:00


def analyze_p10_effectiveness():
    """Analyze P10 escalate-once effectiveness."""
    session = SessionLocal()

    print("=" * 70)
    print("BUILD-129 Phase 3 P10: Effectiveness Dashboard")
    print("=" * 70)
    print()

    # Get all events post-P7+P9+P10
    all_events = session.query(TokenEstimationV2Event).all()
    post_p10 = sorted(
        [e for e in all_events if e.timestamp >= P7P9_CUTOFF], key=lambda x: x.timestamp
    )

    print(f"Total events (post-P10): {len(post_p10)}")
    print(f"Cutoff timestamp: {P7P9_CUTOFF}")
    print()

    if not post_p10:
        print("⚠️  No P10 events found!")
        session.close()
        return

    # Compute rolling stats (every 10 events)
    print("=" * 70)
    print("Rolling Statistics (every 10 events)")
    print("=" * 70)
    print()

    for i in range(10, len(post_p10) + 1, 10):
        window = post_p10[:i]
        print(f"After {i} events:")
        print()

        # First-attempt truncation rate
        first_attempt_truncated = [e for e in window if e.truncated and e.retry_attempt == 1]
        first_attempt_total = [e for e in window if e.retry_attempt == 1]
        first_attempt_trunc_rate = (
            len(first_attempt_truncated) / max(len(first_attempt_total), 1) * 100
        )

        print(
            f"  First-Attempt Truncation: {first_attempt_trunc_rate:.1f}% "
            f"({len(first_attempt_truncated)}/{len(first_attempt_total)})"
        )

        # P10 trigger rate (output_utilization ≥95% or truncated on first attempt)
        p10_triggered = [
            e
            for e in window
            if e.retry_attempt == 1 and (e.truncated or (e.output_utilization or 0) >= 95.0)
        ]
        p10_trigger_rate = len(p10_triggered) / max(len(first_attempt_total), 1) * 100

        print(
            f"  P10 Trigger Rate: {p10_trigger_rate:.1f}% "
            f"({len(p10_triggered)}/{len(first_attempt_total)})"
        )

        # P10 retry success rate (how many retries succeeded after P10 escalation)
        # We need to track retry_attempt=2 events and see if they succeeded
        retry_events = [e for e in window if e.retry_attempt == 2]
        retry_success = [e for e in retry_events if not e.truncated]
        p10_retry_success_rate = (
            len(retry_success) / max(len(retry_events), 1) * 100 if retry_events else 0
        )

        print(
            f"  P10 Retry Success: {p10_retry_success_rate:.1f}% "
            f"({len(retry_success)}/{len(retry_events)}) "
            f"{'⚠️ LOW (<80%)' if p10_retry_success_rate < 80 and retry_events else ''}"
        )

        # Clean SMAPE median (non-truncated, valid events only)
        non_truncated_valid = [
            e
            for e in window
            if not e.truncated and e.actual_output_tokens >= 50  # Validity guard
        ]

        if non_truncated_valid:
            smapes = []
            for e in non_truncated_valid:
                pred = e.predicted_output_tokens
                actual = e.actual_output_tokens
                if pred + actual > 0:
                    smape = abs(pred - actual) * 200 / (abs(pred) + abs(actual))
                    smapes.append(smape)

            if smapes:
                clean_smape_median = statistics.median(smapes)
                print(
                    f"  Clean SMAPE Median: {clean_smape_median:.1f}% "
                    f"(n={len(non_truncated_valid)})"
                )

        # Waste ratio P90 (using actual_max_tokens from P8)
        waste_ratios = []
        for e in non_truncated_valid:
            if e.selected_budget and e.actual_output_tokens:
                waste_ratio = e.selected_budget / e.actual_output_tokens
                waste_ratios.append(waste_ratio)

        if waste_ratios and len(waste_ratios) >= 2:
            waste_p90 = (
                statistics.quantiles(waste_ratios, n=10)[8]
                if len(waste_ratios) >= 10
                else max(waste_ratios)
            )
            print(f"  Waste Ratio P90: {waste_p90:.2f}x (target: 1.0-1.5x)")

        # Overall success rate
        success_events = [e for e in window if e.success]
        success_rate = len(success_events) / len(window) * 100
        print(f"  Success Rate: {success_rate:.1f}% ({len(success_events)}/{len(window)})")

        print()

        # Stop criteria check
        if first_attempt_trunc_rate > 40:
            print("  🛑 STOP CRITERION: First-attempt truncation >40%")
            print("     Action: Pause and tune P7 buffers")
            print()
        if retry_events and p10_retry_success_rate < 80:
            print("  🛑 STOP CRITERION: P10 retry success <80%")
            print("     Action: Increase P10 escalation factor from 1.25x → 1.5x")
            print()

    # Detailed breakdown by category and deliverable count
    print("=" * 70)
    print("P10 Effectiveness by Segment")
    print("=" * 70)
    print()

    # Group by category
    by_category = defaultdict(lambda: {"total": 0, "truncated": 0, "p10_triggered": 0})
    for e in post_p10:
        if e.retry_attempt == 1:  # First attempts only
            cat = e.category or "(null)"
            by_category[cat]["total"] += 1
            if e.truncated:
                by_category[cat]["truncated"] += 1
            if e.truncated or (e.output_utilization or 0) >= 95.0:
                by_category[cat]["p10_triggered"] += 1

    print("By Category (first attempts):")
    for cat in sorted(by_category.keys()):
        stats = by_category[cat]
        trunc_rate = stats["truncated"] / max(stats["total"], 1) * 100
        trigger_rate = stats["p10_triggered"] / max(stats["total"], 1) * 100
        print(
            f"  {cat}: {stats['truncated']}/{stats['total']} truncated ({trunc_rate:.1f}%), "
            f"{stats['p10_triggered']} P10 triggers ({trigger_rate:.1f}%)"
        )
    print()

    # Group by deliverable count bucket
    by_deliv = defaultdict(lambda: {"total": 0, "truncated": 0, "p10_triggered": 0})
    for e in post_p10:
        if e.retry_attempt == 1:  # First attempts only
            dcount = e.deliverable_count or 0
            # Bucket: 0-3, 4-7, 8-15, 16+
            if dcount == 0:
                bucket = "0"
            elif dcount <= 3:
                bucket = "1-3"
            elif dcount <= 7:
                bucket = "4-7"
            elif dcount <= 15:
                bucket = "8-15"
            else:
                bucket = "16+"

            by_deliv[bucket]["total"] += 1
            if e.truncated:
                by_deliv[bucket]["truncated"] += 1
            if e.truncated or (e.output_utilization or 0) >= 95.0:
                by_deliv[bucket]["p10_triggered"] += 1

    print("By Deliverable Count (first attempts):")
    for bucket in ["0", "1-3", "4-7", "8-15", "16+"]:
        if bucket in by_deliv:
            stats = by_deliv[bucket]
            trunc_rate = stats["truncated"] / max(stats["total"], 1) * 100
            trigger_rate = stats["p10_triggered"] / max(stats["total"], 1) * 100
            print(
                f"  {bucket} deliverables: {stats['truncated']}/{stats['total']} truncated "
                f"({trunc_rate:.1f}%), {stats['p10_triggered']} P10 triggers ({trigger_rate:.1f}%)"
            )
    print()

    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print()

    first_attempt_events = [e for e in post_p10 if e.retry_attempt == 1]
    first_attempt_truncated = [e for e in first_attempt_events if e.truncated]
    overall_trunc_rate = len(first_attempt_truncated) / max(len(first_attempt_events), 1) * 100

    retry_events = [e for e in post_p10 if e.retry_attempt == 2]
    retry_success = [e for e in retry_events if not e.truncated]
    overall_retry_success = (
        len(retry_success) / max(len(retry_events), 1) * 100 if retry_events else 0
    )

    print(f"Overall first-attempt truncation: {overall_trunc_rate:.1f}%")
    print(
        f"Overall P10 retry success: {overall_retry_success:.1f}% ({len(retry_success)}/{len(retry_events)})"
    )
    print()

    if overall_trunc_rate <= 30:
        print("✅ First-attempt truncation within target (≤30%)")
    elif overall_trunc_rate <= 40:
        print("⚠️  First-attempt truncation marginal (30-40%)")
    else:
        print("❌ First-attempt truncation above threshold (>40%)")

    if retry_events:
        if overall_retry_success >= 80:
            print("✅ P10 retry success within target (≥80%)")
        else:
            print("❌ P10 retry success below threshold (<80%)")
            print("   Recommendation: Increase P10 escalation factor from 1.25x → 1.5x")

    print()
    print("=" * 70)

    session.close()


if __name__ == "__main__":
    print("\n")
    analyze_p10_effectiveness()
