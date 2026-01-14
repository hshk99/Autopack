"""
BUILD-129 Phase 3: Truncation Triage Report

Analyzes truncated events to identify which segments are driving the 52.6% truncation rate.
For each truncated event, computes lower-bound underestimate factor:
    lb_factor = actual_lower_bound / predicted

Stratifies by:
- estimated_category
- complexity
- deliverable_count_bucket (1, 2-5, 6-10, 11-20, 20+)
- doc subtypes (doc_synthesis, doc_sot_update)

Goal: Identify the top 2-3 segments where lb_factor is worst to guide coefficient tuning.

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/truncation_triage_report.py
"""

import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import statistics

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event


def get_deliverable_bucket(count: int) -> str:
    """Bucket deliverable count into ranges."""
    if count == 1:
        return "1"
    elif 2 <= count <= 5:
        return "2-5"
    elif 6 <= count <= 10:
        return "6-10"
    elif 11 <= count <= 20:
        return "11-20"
    else:
        return "20+"


def analyze_truncation_segments():
    """Analyze truncated events by segment to identify worst offenders."""
    session = SessionLocal()

    print("=" * 70)
    print("BUILD-129 Phase 3: Truncation Triage Report")
    print("=" * 70)
    print()

    # Get all truncated events
    truncated = (
        session.query(TokenEstimationV2Event).filter(TokenEstimationV2Event.truncated == True).all()
    )

    print(f"Total Truncated Events: {len(truncated)}")
    print()

    if not truncated:
        print("No truncated events found.")
        session.close()
        return

    # Calculate lb_factor for each truncated event
    segments = defaultdict(list)

    for e in truncated:
        # Lower-bound underestimate factor
        lb_factor = e.actual_output_tokens / max(e.predicted_output_tokens, 1)

        # Segment keys
        category = e.category or "unknown"
        complexity = e.complexity or "unknown"
        deliv_bucket = get_deliverable_bucket(e.deliverable_count)

        # Store by multiple segment dimensions
        segments[f"category={category}"].append(lb_factor)
        segments[f"complexity={complexity}"].append(lb_factor)
        segments[f"deliverables={deliv_bucket}"].append(lb_factor)
        segments[f"cat={category},complexity={complexity}"].append(lb_factor)
        segments[f"cat={category},deliv={deliv_bucket}"].append(lb_factor)
        segments[f"complexity={complexity},deliv={deliv_bucket}"].append(lb_factor)

    # Rank segments by worst lb_factor (highest mean = worst underestimation)
    segment_stats = []
    for segment, factors in segments.items():
        if len(factors) >= 2:  # At least 2 samples
            segment_stats.append(
                {
                    "segment": segment,
                    "count": len(factors),
                    "lb_factor_mean": statistics.mean(factors),
                    "lb_factor_median": statistics.median(factors),
                    "lb_factor_max": max(factors),
                }
            )

    # Sort by worst mean lb_factor
    segment_stats.sort(key=lambda x: x["lb_factor_mean"], reverse=True)

    print("=" * 70)
    print("Top Segments by Underestimation (Worst lb_factor)")
    print("=" * 70)
    print()
    print(f"{'Segment':<50} {'Count':<6} {'Mean':<8} {'Median':<8} {'Max':<8}")
    print("-" * 70)

    for i, stat in enumerate(segment_stats[:15], 1):
        print(
            f"{stat['segment']:<50} {stat['count']:<6} {stat['lb_factor_mean']:<8.2f} "
            f"{stat['lb_factor_median']:<8.2f} {stat['lb_factor_max']:<8.2f}"
        )

    print()
    print("=" * 70)
    print("Interpretation:")
    print("=" * 70)
    print()
    print("  lb_factor = actual_lower_bound / predicted")
    print("  Higher lb_factor = worse underestimation")
    print()
    print("  Target segments for coefficient tuning:")
    print("  - Focus on top 2-3 segments with:")
    print("    * lb_factor_mean >= 1.5 (50%+ underestimation)")
    print("    * count >= 3 (enough samples)")
    print()

    # Detailed breakdown of top 3 segments
    print("=" * 70)
    print("Detailed Analysis: Top 3 Segments")
    print("=" * 70)
    print()

    for i, stat in enumerate(segment_stats[:3], 1):
        print(f"{i}. {stat['segment']}")
        print(f"   Samples: {stat['count']}")
        print(f"   Mean lb_factor: {stat['lb_factor_mean']:.2f}")
        print(f"   Median lb_factor: {stat['lb_factor_median']:.2f}")
        print(f"   Max lb_factor: {stat['lb_factor_max']:.2f}")
        print()
        print("   Tuning recommendation:")
        print(
            f"   - Increase base estimate for this segment by {(stat['lb_factor_mean'] - 1) * 100:.0f}%"
        )
        print(f"   - OR increase buffer margin to {stat['lb_factor_mean']:.2f}x")
        print()

    session.close()


def analyze_non_truncated_outliers():
    """Analyze non-truncated events with high SMAPE to identify misclassifications."""
    session = SessionLocal()

    print("=" * 70)
    print("Non-Truncated SMAPE Outliers")
    print("=" * 70)
    print()

    # Get non-truncated events
    non_truncated = (
        session.query(TokenEstimationV2Event)
        .filter(TokenEstimationV2Event.truncated == False)
        .all()
    )

    if not non_truncated:
        print("No non-truncated events found.")
        session.close()
        return

    # Calculate SMAPE for each
    outliers = []
    for e in non_truncated:
        pred = e.predicted_output_tokens
        actual = e.actual_output_tokens
        smape = abs(pred - actual) * 200 / (abs(pred) + abs(actual)) if (pred + actual) > 0 else 0

        if smape > 100:  # Outliers with SMAPE > 100%
            outliers.append(
                {
                    "phase_id": e.phase_id,
                    "category": e.category,
                    "complexity": e.complexity,
                    "deliverable_count": e.deliverable_count,
                    "predicted": pred,
                    "actual": actual,
                    "smape": smape,
                }
            )

    outliers.sort(key=lambda x: x["smape"], reverse=True)

    print(f"Found {len(outliers)} non-truncated events with SMAPE > 100%")
    print()

    if outliers:
        print(f"{'Phase':<40} {'Cat':<20} {'Deliv':<6} {'Pred':<8} {'Actual':<8} {'SMAPE':<8}")
        print("-" * 100)
        for o in outliers[:5]:
            print(
                f"{o['phase_id'][:38]:<40} {o['category'][:18]:<20} "
                f"{o['deliverable_count']:<6} {o['predicted']:<8} "
                f"{o['actual']:<8} {o['smape']:<8.1f}%"
            )
        print()
        print("Recommended action: Inspect top 2 outliers for missing heuristics")
        print()

    session.close()


if __name__ == "__main__":
    print("\n")

    analyze_truncation_segments()
    analyze_non_truncated_outliers()

    print("=" * 70)
    print("✓ Truncation triage complete")
    print("=" * 70)
    print()
