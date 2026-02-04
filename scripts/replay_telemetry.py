"""
Replay TokenEstimationV2 telemetry against the current TokenEstimator.

Preferred mode (BUILD-129 Phase 3+):
- Pull events directly from DB (real deliverables, real categories/complexities).

Legacy mode:
- Parse telemetry samples from build132_telemetry_samples.txt (synthetic deliverables).
"""

import re
import json
import sys
from pathlib import Path
from autopack.token_estimator import TokenEstimator
from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event


def parse_telemetry_line(line: str) -> dict:
    """Parse a telemetry log line into structured data."""
    match = re.search(
        r"predicted_output=(\d+) actual_output=(\d+) smape=([\d.]+)% "
        r"selected_budget=(\d+) category=(\w+) complexity=(\w+) deliverables=(\d+)",
        line,
    )
    if not match:
        return None

    return {
        "old_predicted": int(match.group(1)),
        "actual": int(match.group(2)),
        "old_smape": float(match.group(3)),
        "budget": int(match.group(4)),
        "category": match.group(5),
        "complexity": match.group(6),
        "deliverable_count": int(match.group(7)),
    }


def calculate_smape(predicted: int, actual: int) -> float:
    """Calculate SMAPE between predicted and actual."""
    if predicted == 0 and actual == 0:
        return 0.0
    return abs(predicted - actual) / ((abs(predicted) + abs(actual)) / 2) * 100


def load_samples_from_db(limit: int | None = None) -> list[dict]:
    """Load samples from DB with real deliverables."""
    session = SessionLocal()
    try:
        q = session.query(TokenEstimationV2Event).order_by(TokenEstimationV2Event.timestamp.desc())
        if limit:
            q = q.limit(limit)
        events = q.all()
        samples: list[dict] = []
        for e in events:
            try:
                deliverables = json.loads(e.deliverables_json) if e.deliverables_json else []
            except Exception:
                deliverables = []
            samples.append(
                {
                    "source": "db",
                    "run_id": e.run_id,
                    "phase_id": e.phase_id,
                    "category": e.category,
                    "complexity": e.complexity,
                    "deliverables": deliverables,
                    "deliverable_count": e.deliverable_count,
                    "old_predicted": e.predicted_output_tokens,
                    "actual": e.actual_output_tokens,
                    "budget": e.selected_budget,
                    "success": e.success,
                    "truncated": e.truncated,
                }
            )
        return samples
    finally:
        session.close()


def main():
    # Prefer DB-backed replay (real deliverables)
    samples = load_samples_from_db()
    if samples:
        print(f"Loaded {len(samples)} telemetry samples from DB\n")
    else:
        # Legacy fallback: parse file-based samples
        telemetry_file = Path("build132_telemetry_samples.txt")
        if not telemetry_file.exists():
            print("Error: No DB samples found and build132_telemetry_samples.txt is missing")
            return
        with open(telemetry_file) as f:
            for line in f:
                if "[TokenEstimationV2]" in line:
                    parsed = parse_telemetry_line(line)
                    if parsed:
                        parsed["source"] = "log"
                        samples.append(parsed)
        print(f"Loaded {len(samples)} telemetry samples from log file\n")

    # Replay with new estimator
    estimator = TokenEstimator()

    print("=" * 100)
    print(
        f"{'#':<3} {'Category':<14} {'Comp':<6} {'Del':<4} {'Old Pred':<9} {'New Pred':<9} {'Actual':<8} {'Old SMAPE':<10} {'New SMAPE':<10} {'Improve':<8}"
    )
    print("=" * 100)

    total_old_smape = 0
    total_new_smape = 0

    for i, sample in enumerate(samples, 1):
        deliverables = sample.get("deliverables")
        if not deliverables:
            deliverables = [f"src/file{j}.py" for j in range(sample.get("deliverable_count", 0))]
            if i == 1:
                print(
                    "WARNING: Using synthetic deliverables (no deliverables available)",
                    file=sys.stderr,
                )

        # Get new prediction
        estimate = estimator.estimate(
            deliverables=deliverables, category=sample["category"], complexity=sample["complexity"]
        )

        new_predicted = estimate.estimated_tokens
        new_smape = calculate_smape(new_predicted, sample["actual"])

        old_smape = sample.get("old_smape")
        if old_smape is None:
            old_smape = calculate_smape(sample["old_predicted"], sample["actual"])
        improvement = old_smape - new_smape

        total_old_smape += old_smape
        total_new_smape += new_smape

        # Symbol for improvement
        improve_symbol = "+" if improvement > 0 else "-"

        print(
            f"{i:<3} {sample['category']:<14} {sample['complexity']:<6} {sample['deliverable_count']:<4} "
            f"{sample['old_predicted']:<9} {new_predicted:<9} {sample['actual']:<8} "
            f"{old_smape:<10.1f} {new_smape:<10.1f} {improve_symbol} {improvement:>6.1f}%"
        )

    print("=" * 100)

    avg_old_smape = total_old_smape / max(1, len(samples))
    avg_new_smape = total_new_smape / max(1, len(samples))
    avg_improvement = avg_old_smape - avg_new_smape

    print(
        f"\n{'AVERAGES:':<29} {'':<9} {'':<9} {'':<8} {avg_old_smape:<10.1f} {avg_new_smape:<10.1f} {'':>2} {avg_improvement:>6.1f}%"
    )

    # Underestimation analysis
    old_underestimations = sum(1 for s in samples if s["old_predicted"] < s["actual"])
    new_underestimations = 0
    for s in samples:
        dels = s.get("deliverables") or [
            f"src/file{j}.py" for j in range(s.get("deliverable_count", 0))
        ]
        if estimator.estimate(dels, s["category"], s["complexity"]).estimated_tokens < s["actual"]:
            new_underestimations += 1

    print("\nUnderestimation rate:")
    print(
        f"  Old: {old_underestimations}/{len(samples)} ({old_underestimations / len(samples) * 100:.1f}%)"
    )
    print(
        f"  New: {new_underestimations}/{len(samples)} ({new_underestimations / len(samples) * 100:.1f}%)"
    )

    # Waste analysis (overestimation)
    print("\nMedian waste ratio (predicted/actual):")
    old_waste_ratios = [s["old_predicted"] / s["actual"] for s in samples if s["actual"] > 0]
    new_waste_ratios = []
    for s in samples:
        if s["actual"] > 0:
            dels = s.get("deliverables") or [
                f"src/file{j}.py" for j in range(s.get("deliverable_count", 0))
            ]
            new_pred = estimator.estimate(dels, s["category"], s["complexity"]).estimated_tokens
            new_waste_ratios.append(new_pred / s["actual"])

    old_waste_ratios.sort()
    new_waste_ratios.sort()
    old_median = old_waste_ratios[len(old_waste_ratios) // 2]
    new_median = new_waste_ratios[len(new_waste_ratios) // 2]

    print(f"  Old median: {old_median:.2f}x")
    print(f"  New median: {new_median:.2f}x")
    print("  (1.0 = perfect, <1.0 = underestimate, >1.0 = overestimate)")


if __name__ == "__main__":
    main()
