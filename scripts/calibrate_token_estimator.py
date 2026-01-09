"""
T5: Token Estimator Calibration Job (Safe + Gated)

Analyzes successful telemetry data to propose coefficient updates for token_estimator.py.

Strategy:
1. Read llm_usage_events from database
2. Filter for success=True AND truncated=False (clean data only)
3. Group by category and complexity
4. Compute actual vs estimated token ratios
5. Propose coefficient adjustments (markdown + JSON patch)

Safety:
- Read-only database access
- No automatic edits to token_estimator.py
- Gated behind minimum sample size requirements
- Clear reporting of confidence levels

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
        python scripts/calibrate_token_estimator.py

    Optional flags:
        --min-samples N       Minimum samples required per category (default: 5)
        --confidence-threshold T  Minimum confidence to propose changes (default: 0.7)
        --output-dir PATH     Directory for output files (default: .)
        --allow-empty-db      Allow running on empty database (for testing)
"""

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.db_identity import print_db_identity, check_empty_db_warning, add_empty_db_arg


try:
    from autopack.models import TokenEstimationV2Event
except (ImportError, AttributeError):
    print("ERROR: TokenEstimationV2Event model not found in database schema")
    print("Telemetry collection may not be enabled or database needs migration")
    sys.exit(1)


@dataclass
class CalibrationSample:
    """Single telemetry sample for calibration."""
    phase_id: str
    run_id: str
    category: str
    complexity: str
    deliverable_count: int
    estimated_tokens: int
    actual_tokens: int
    selected_budget: int  # Estimator intent (BEFORE P4 enforcement)
    # BUILD-142 PARITY: Separate estimator intent from final ceiling
    actual_max_tokens: Optional[int]  # Final ceiling sent to API (AFTER P4 enforcement)
    success: bool
    truncated: bool
    timestamp: str


@dataclass
class CalibrationResult:
    """Calibration result for a category/complexity group."""
    category: str
    complexity: Optional[str]
    sample_count: int
    avg_actual: float
    avg_estimated: float
    avg_ratio: float  # actual / estimated
    median_ratio: float
    min_ratio: float
    max_ratio: float
    confidence: float  # 0.0-1.0 based on sample count and ratio variance
    proposed_multiplier: float  # Suggested adjustment to current coefficients
    samples: List[CalibrationSample]
    # Cost-aware metrics
    median_budget_waste: float  # selected_budget / actual_tokens
    p90_budget_waste: float
    avg_selected_budget: float


def collect_telemetry_samples(session, include_run_ids: Optional[List[str]] = None) -> List[CalibrationSample]:
    """
    Collect telemetry samples from database.

    Filters:
    - success = True (phase completed successfully)
    - truncated = False (no output truncation)
    - Has both estimated_tokens and actual_output_tokens
    - Optionally filter by run IDs

    Args:
        session: Database session
        include_run_ids: Optional list of run IDs to include (None = all runs)

    Returns:
        List of calibration samples
    """
    # Query TokenEstimationV2Events with required filters
    query = session.query(TokenEstimationV2Event).filter(
        TokenEstimationV2Event.success == True,
        TokenEstimationV2Event.truncated == False,
        TokenEstimationV2Event.predicted_output_tokens.isnot(None),
        TokenEstimationV2Event.actual_output_tokens.isnot(None)
    )

    # Apply run-id filter if specified
    if include_run_ids:
        query = query.filter(TokenEstimationV2Event.run_id.in_(include_run_ids))

    events = query.all()

    samples = []
    for event in events:
        # Skip if missing required fields
        if not event.phase_id or not event.run_id:
            continue

        # Extract metadata from event
        category = event.category or "unknown"
        complexity = event.complexity or "unknown"
        deliverable_count = event.deliverable_count or 0

        sample = CalibrationSample(
            phase_id=event.phase_id,
            run_id=event.run_id,
            category=category,
            complexity=complexity,
            deliverable_count=deliverable_count,
            estimated_tokens=event.predicted_output_tokens,
            actual_tokens=event.actual_output_tokens,
            selected_budget=event.selected_budget,
            # BUILD-142 PARITY: Extract actual_max_tokens (final ceiling) for accurate waste calculation
            actual_max_tokens=event.actual_max_tokens,
            success=event.success,
            truncated=event.truncated,
            timestamp=event.timestamp or datetime.now(timezone.utc).isoformat()
        )
        samples.append(sample)

    return samples


def group_samples_by_category_complexity(
    samples: List[CalibrationSample]
) -> Dict[Tuple[str, str], List[CalibrationSample]]:
    """
    Group samples by (category, complexity).

    Args:
        samples: List of calibration samples

    Returns:
        Dict mapping (category, complexity) -> samples
    """
    groups = defaultdict(list)
    for sample in samples:
        key = (sample.category, sample.complexity)
        groups[key].append(sample)
    return dict(groups)


def compute_calibration_result(
    category: str,
    complexity: str,
    samples: List[CalibrationSample],
    min_samples: int = 5
) -> Optional[CalibrationResult]:
    """
    Compute calibration result for a category/complexity group.

    Args:
        category: Phase category
        complexity: Phase complexity
        samples: Samples for this group
        min_samples: Minimum samples required for valid result

    Returns:
        CalibrationResult if sufficient samples, None otherwise
    """
    if len(samples) < min_samples:
        return None

    # Compute statistics
    actual_tokens = [s.actual_tokens for s in samples]
    estimated_tokens = [s.estimated_tokens for s in samples]
    ratios = [a / e if e > 0 else 0 for a, e in zip(actual_tokens, estimated_tokens)]

    avg_actual = sum(actual_tokens) / len(actual_tokens)
    avg_estimated = sum(estimated_tokens) / len(estimated_tokens)
    avg_ratio = sum(ratios) / len(ratios)

    sorted_ratios = sorted(ratios)
    median_ratio = sorted_ratios[len(sorted_ratios) // 2]
    min_ratio = min(ratios)
    max_ratio = max(ratios)

    # Compute confidence based on sample count and ratio variance
    # More samples → higher confidence
    # Lower variance → higher confidence
    # Max confidence at 12 samples (achievable target for well-studied groups)
    sample_confidence = min(1.0, len(samples) / 12)

    # Variance-based confidence: lower when ratios are widely spread
    # Use 1/(1+std) formula so confidence doesn't instantly collapse to 0
    ratio_variance = sum((r - avg_ratio) ** 2 for r in ratios) / len(ratios)
    ratio_std = ratio_variance ** 0.5
    variance_confidence = 1.0 / (1.0 + ratio_std)

    # Weight sample count more heavily (60/40) since we want min-samples gate to be meaningful
    confidence = 0.6 * sample_confidence + 0.4 * variance_confidence

    # Proposed multiplier: use median ratio as it's more robust to outliers
    # If median_ratio = 1.5, we're systematically underestimating by 50%
    # Proposed multiplier = median_ratio to correct the bias
    proposed_multiplier = median_ratio

    # Cost-aware metrics: budget waste analysis
    # BUILD-142 PARITY: Use actual_max_tokens (final ceiling) instead of selected_budget (estimator intent)
    # actual_max_tokens reflects what was actually sent to the API, giving accurate waste measurement
    # Fallback to selected_budget for backward compatibility with pre-BUILD-142 telemetry
    budget_waste_ratios = [
        (s.actual_max_tokens or s.selected_budget) / s.actual_tokens if s.actual_tokens > 0 else 0
        for s in samples
    ]
    sorted_waste = sorted(budget_waste_ratios)
    median_budget_waste = sorted_waste[len(sorted_waste) // 2]
    p90_index = int(len(sorted_waste) * 0.9)
    p90_budget_waste = sorted_waste[p90_index] if p90_index < len(sorted_waste) else sorted_waste[-1]
    avg_selected_budget = sum(s.selected_budget for s in samples) / len(samples)

    return CalibrationResult(
        category=category,
        complexity=complexity,
        sample_count=len(samples),
        avg_actual=avg_actual,
        avg_estimated=avg_estimated,
        avg_ratio=avg_ratio,
        median_ratio=median_ratio,
        min_ratio=min_ratio,
        max_ratio=max_ratio,
        confidence=confidence,
        proposed_multiplier=proposed_multiplier,
        samples=samples,
        median_budget_waste=median_budget_waste,
        p90_budget_waste=p90_budget_waste,
        avg_selected_budget=avg_selected_budget
    )


def generate_markdown_report(
    results: List[CalibrationResult],
    output_path: Path,
    confidence_threshold: float = 0.7
) -> None:
    """
    Generate markdown report with calibration results.

    Args:
        results: List of calibration results
        output_path: Output file path
        confidence_threshold: Minimum confidence for recommendations
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Token Estimator Calibration Report\n\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n")

        # Summary
        f.write("## Summary\n\n")
        total_samples = sum(r.sample_count for r in results)
        f.write(f"- Total samples analyzed: {total_samples}\n")
        f.write(f"- Total groups: {len(results)}\n")
        high_confidence = [r for r in results if r.confidence >= confidence_threshold]
        f.write(f"- High-confidence groups (≥{confidence_threshold:.0%}): {len(high_confidence)}\n\n")

        # Recommendations
        f.write("## Recommendations\n\n")
        if high_confidence:
            f.write("Groups with sufficient confidence for coefficient adjustments:\n\n")
            for result in sorted(high_confidence, key=lambda r: -r.confidence):
                f.write(f"### {result.category} / {result.complexity}\n\n")
                f.write(f"- **Samples**: {result.sample_count}\n")
                f.write(f"- **Confidence**: {result.confidence:.1%}\n")
                f.write(f"- **Current avg estimate**: {result.avg_estimated:.0f} tokens\n")
                f.write(f"- **Actual avg**: {result.avg_actual:.0f} tokens\n")
                f.write(f"- **Median ratio** (actual/estimated): {result.median_ratio:.2f}x\n")
                f.write(f"- **Proposed multiplier**: {result.proposed_multiplier:.2f}x\n")

                if result.median_ratio > 1.2:
                    f.write(f"- **Action**: Increase coefficients by {(result.proposed_multiplier - 1) * 100:.0f}%\n")
                elif result.median_ratio < 0.8:
                    f.write(f"- **Action**: Decrease coefficients by {(1 - result.proposed_multiplier) * 100:.0f}%\n")
                else:
                    f.write("- **Action**: No adjustment needed (within ±20% tolerance)\n")
                f.write("\n")
        else:
            f.write("No groups met the confidence threshold for recommendations.\n")
            f.write("Increase sample size or lower confidence threshold.\n\n")

        # Detailed Results
        f.write("## Detailed Results\n\n")
        f.write("All calibration groups (including low-confidence):\n\n")
        f.write("| Category | Complexity | Samples | Avg Actual | Avg Est | Median Ratio | Confidence | Proposed Mult |\n")
        f.write("|----------|------------|---------|------------|---------|--------------|------------|---------------|\n")
        for result in sorted(results, key=lambda r: (-r.sample_count, r.category, r.complexity or "")):
            f.write(
                f"| {result.category} | {result.complexity or 'N/A'} | {result.sample_count} | "
                f"{result.avg_actual:.0f} | {result.avg_estimated:.0f} | "
                f"{result.median_ratio:.2f}x | {result.confidence:.1%} | "
                f"{result.proposed_multiplier:.2f}x |\n"
            )

        f.write("\n")
        f.write("## Notes\n\n")
        f.write("- **Median ratio > 1.0**: Underestimating (need to increase coefficients)\n")
        f.write("- **Median ratio < 1.0**: Overestimating (need to decrease coefficients)\n")
        f.write("- **Confidence**: Based on sample count and ratio variance\n")
        f.write("- **Proposed multiplier**: Apply to current PHASE_OVERHEAD or TOKEN_WEIGHTS\n\n")


def generate_json_patch(
    results: List[CalibrationResult],
    output_path: Path,
    confidence_threshold: float = 0.7
) -> None:
    """
    Generate JSON patch with proposed coefficient updates.

    Args:
        results: List of calibration results
        output_path: Output file path
        confidence_threshold: Minimum confidence for recommendations
    """
    high_confidence = [r for r in results if r.confidence >= confidence_threshold]

    patch = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "confidence_threshold": confidence_threshold,
            "total_samples": sum(r.sample_count for r in results),
            "high_confidence_groups": len(high_confidence)
        },
        "proposed_changes": []
    }

    for result in high_confidence:
        # Propose PHASE_OVERHEAD adjustment
        # Current overhead unknown without reading token_estimator.py
        # So we provide the multiplier for manual application
        change = {
            "category": result.category,
            "complexity": result.complexity,
            "sample_count": result.sample_count,
            "confidence": round(result.confidence, 3),
            "median_ratio": round(result.median_ratio, 3),
            "proposed_multiplier": round(result.proposed_multiplier, 3),
            "action": "multiply PHASE_OVERHEAD[(category, complexity)] by proposed_multiplier",
            "reasoning": f"Actual tokens are {result.median_ratio:.2f}x estimated (median)"
        }
        patch["proposed_changes"].append(change)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(patch, f, indent=2)


def main():
    """Main calibration job."""
    parser = argparse.ArgumentParser(
        description="Token estimator calibration job (T5 - safe + gated)"
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
        help="Minimum samples required per category/complexity group (default: 5)"
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Minimum confidence to propose changes (default: 0.7)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for output files (default: current directory)"
    )
    parser.add_argument(
        "--include-run-id",
        action="append",
        dest="include_run_ids",
        help="Only include samples from specified run IDs (repeatable). Example: --include-run-id telemetry-collection-v5 --include-run-id telemetry-collection-v6"
    )
    add_empty_db_arg(parser)

    args = parser.parse_args()

    # T2: Print DB identity and check for empty database
    session = SessionLocal()
    try:
        print_db_identity(session)
        check_empty_db_warning(
            session,
            script_name="calibrate_token_estimator",
            allow_empty=args.allow_empty_db
        )
    finally:
        session.close()

    print("\n" + "=" * 70)
    print("TOKEN ESTIMATOR CALIBRATION JOB (T5)")
    print("=" * 70)
    print(f"Min samples per group: {args.min_samples}")
    print(f"Confidence threshold: {args.confidence_threshold:.0%}")
    print(f"Output directory: {args.output_dir}")
    if args.include_run_ids:
        print(f"Run-ID filter: {', '.join(args.include_run_ids)}")
    else:
        print("Run-ID filter: None (all runs)")
    print()

    # Collect telemetry samples
    session = SessionLocal()
    try:
        print("Collecting telemetry samples...")
        samples = collect_telemetry_samples(session, include_run_ids=args.include_run_ids)
        print(f"  Found {len(samples)} samples (success=True, truncated=False)")

        # BUILD-142: Check actual_max_tokens coverage
        if samples:
            populated_count = sum(1 for s in samples if s.actual_max_tokens is not None)
            coverage_pct = (populated_count / len(samples) * 100) if len(samples) > 0 else 0
            print(f"\nTelemetry coverage: actual_max_tokens populated in {populated_count}/{len(samples)} samples ({coverage_pct:.1f}%)")
            if coverage_pct < 80.0:
                print("⚠️  WARNING: Low actual_max_tokens coverage (<80%)")
                print("   Waste numbers may be underestimated (falling back to selected_budget)")
                print("   Consider running BUILD-142 migration/backfill:")
                print("     python scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py")
                print()

        if not samples:
            print("\n[STOP] No telemetry samples found")
            print("  Possible reasons:")
            print("    1. No successful phase executions with TELEMETRY_DB_ENABLED=1")
            print("    2. All successful phases were truncated")
            print("    3. Database missing llm_usage_events table")
            print("\n  To collect telemetry:")
            print("    1. Create telemetry run: python scripts/create_telemetry_collection_run.py")
            print("    2. Drain phases: python scripts/drain_one_phase.py --run-id <run> --phase-id <phase>")
            print("       (with TELEMETRY_DB_ENABLED=1 environment variable)")
            sys.exit(1)

        # Group samples
        print("\nGrouping by category/complexity...")
        groups = group_samples_by_category_complexity(samples)
        print(f"  Found {len(groups)} unique groups")

        # Compute calibration results
        print("\nComputing calibration results...")
        results = []
        below_threshold_groups = []
        for (category, complexity), group_samples in groups.items():
            result = compute_calibration_result(
                category=category,
                complexity=complexity,
                samples=group_samples,
                min_samples=args.min_samples
            )
            if result:
                results.append(result)
                print(f"  [{category}/{complexity}] {result.sample_count} samples, "
                      f"median ratio: {result.median_ratio:.2f}x, "
                      f"confidence: {result.confidence:.1%}")
            else:
                below_threshold_groups.append((category, complexity, len(group_samples)))
                print(f"  [{category}/{complexity}] {len(group_samples)} samples (below min threshold)")

        if not results:
            print("\n[STOP] No groups met minimum sample size")
            print(f"  Minimum required: {args.min_samples} samples per group")
            print(f"  Largest group: {max(len(s) for s in groups.values())} samples")
            print("\n  Collect more telemetry data and try again.")
            sys.exit(1)

        # Generate outputs
        print("\nGenerating outputs...")
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        markdown_path = output_dir / f"token_estimator_calibration_{timestamp}.md"
        json_path = output_dir / f"token_estimator_calibration_{timestamp}.json"

        generate_markdown_report(results, markdown_path, args.confidence_threshold)
        generate_json_patch(results, json_path, args.confidence_threshold)

        print(f"  Markdown report: {markdown_path}")
        print(f"  JSON patch: {json_path}")

        # Summary
        print("\n" + "=" * 70)
        print("CALIBRATION SUMMARY")
        print("=" * 70)
        samples_in_results = sum(r.sample_count for r in results)
        high_confidence = [r for r in results if r.confidence >= args.confidence_threshold]

        print(f"Total clean samples collected: {len(samples)}")
        print(f"Total groups found: {len(groups)}")
        print(f"Groups meeting min-samples threshold: {len(results)}")
        print(f"Samples included in results: {samples_in_results}")
        print(f"High-confidence groups (≥{args.confidence_threshold:.0%}): {len(high_confidence)}")

        if below_threshold_groups:
            print("\nBelow-threshold groups (need more samples for V7):")
            for cat, comp, count in sorted(below_threshold_groups, key=lambda x: (x[0], x[1])):
                needed = args.min_samples - count
                print(f"  [{cat}/{comp}] {count} samples (need {needed} more to reach {args.min_samples})")

        # Cost-aware analysis
        print("\n" + "=" * 70)
        print("COST-AWARE ANALYSIS (Budget Waste)")
        print("=" * 70)
        print("Group                      Median Waste  P90 Waste  Avg Budget  Avg Actual")
        print("-" * 70)
        for result in sorted(results, key=lambda r: (r.category, r.complexity or '')):
            print(f"{result.category}/{result.complexity or 'all':15s}   "
                  f"{result.median_budget_waste:6.2f}x      "
                  f"{result.p90_budget_waste:6.2f}x    "
                  f"{result.avg_selected_budget:7.0f}     "
                  f"{result.avg_actual:7.0f}")
        print("=" * 70)
        print("Note: Waste = actual_max_tokens / actual_tokens (BUILD-142+)")
        print("      Fallback to selected_budget for pre-BUILD-142 telemetry")
        print("      Median waste >2x suggests over-budgeting")
        print()

        if high_confidence:
            print("Recommended adjustments (high-confidence groups):")
            for result in sorted(high_confidence, key=lambda r: -r.confidence):
                action = "increase" if result.median_ratio > 1.0 else "decrease"
                pct = abs((result.proposed_multiplier - 1) * 100)
                print(f"  [{result.category}/{result.complexity}] "
                      f"{action} coefficients by {pct:.0f}% "
                      f"(confidence: {result.confidence:.1%})")

            print("\n⚠️  IMPORTANT: Review outputs before applying changes!")
            print(f"  1. Read markdown report: {markdown_path}")
            print(f"  2. Review JSON patch: {json_path}")
            print("  3. Manually update src/autopack/token_estimator.py if changes are warranted")
        else:
            print("\nNo high-confidence recommendations.")
            print(f"  All groups below {args.confidence_threshold:.0%} confidence threshold")
            print("  Collect more data or lower threshold to see recommendations")

        print("=" * 70)
        print()

    finally:
        session.close()


if __name__ == "__main__":
    main()
