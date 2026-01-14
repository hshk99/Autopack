"""
Monitor BUILD-112/113/114 stability during BUILD-129 execution.

Tracks key metrics:
- BUILD-112: Deep retrieval trigger counts
- BUILD-113: Goal-aware decision counts
- BUILD-114: Structured edit fallback counts

Run after each BUILD-129 phase to detect regressions.
"""

import sys
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def find_recent_execution_logs(since_date: str = None) -> List[Path]:
    """Find execution logs since specified date."""
    autonomous_runs = Path(".autonomous_runs")

    if not autonomous_runs.exists():
        print("❌ .autonomous_runs directory not found")
        return []

    # Parse since_date or default to last 7 days
    if since_date:
        cutoff = datetime.fromisoformat(since_date)
    else:
        cutoff = datetime.now() - timedelta(days=7)

    logs = []
    for log_file in autonomous_runs.rglob("execution.log"):
        # Check modification time
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        if mtime >= cutoff:
            logs.append(log_file)

    return sorted(logs, key=lambda p: p.stat().st_mtime, reverse=True)


def count_pattern_in_log(log_file: Path, pattern: str) -> int:
    """Count occurrences of pattern in log file."""
    try:
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        return len(re.findall(pattern, content, re.IGNORECASE))
    except Exception as e:
        print(f"⚠️  Error reading {log_file}: {e}")
        return 0


def analyze_build112_stability(logs: List[Path]) -> Dict:
    """
    Analyze BUILD-112 (Deep Retrieval) stability.

    Patterns:
    - Deep retrieval triggers: "[DeepRetrieval] Starting bounded retrieval"
    - SOT file retrievals: "Retrieved .* SOT files"
    - Memory retrievals: "Retrieved .* memory entries"
    """
    metrics = {
        "deep_retrieval_triggers": 0,
        "sot_file_retrievals": 0,
        "memory_retrievals": 0,
        "logs_with_deep_retrieval": 0,
    }

    for log in logs:
        triggers = count_pattern_in_log(log, r"\[DeepRetrieval\] Starting bounded retrieval")
        sot = count_pattern_in_log(log, r"Retrieved .* SOT files")
        memory = count_pattern_in_log(log, r"Retrieved .* memory entries")

        metrics["deep_retrieval_triggers"] += triggers
        metrics["sot_file_retrievals"] += sot
        metrics["memory_retrievals"] += memory

        if triggers > 0:
            metrics["logs_with_deep_retrieval"] += 1

    return metrics


def analyze_build113_stability(logs: List[Path]) -> Dict:
    """
    Analyze BUILD-113 (Goal-Aware Decision Making) stability.

    Patterns:
    - Decision triggers: "[GoalAwareDecisionMaker] Decision:"
    - Proactive mode: "Proactive mode enabled"
    - Risk assessments: "Risk assessment:"
    """
    metrics = {
        "goal_aware_decisions": 0,
        "proactive_mode_triggers": 0,
        "risk_assessments": 0,
        "logs_with_decisions": 0,
    }

    for log in logs:
        decisions = count_pattern_in_log(log, r"\[GoalAwareDecisionMaker\] Decision:")
        proactive = count_pattern_in_log(log, r"Proactive mode enabled")
        risk = count_pattern_in_log(log, r"Risk assessment:")

        metrics["goal_aware_decisions"] += decisions
        metrics["proactive_mode_triggers"] += proactive
        metrics["risk_assessments"] += risk

        if decisions > 0:
            metrics["logs_with_decisions"] += 1

    return metrics


def analyze_build114_stability(logs: List[Path]) -> Dict:
    """
    Analyze BUILD-114 (Structured Edit Support) stability.

    Patterns:
    - Structured edit fallbacks: "Falling back to structured_edit"
    - JSON repair attempts: "Attempting JSON repair"
    - Format conversions: "Converting to structured edit"
    """
    metrics = {
        "structured_edit_fallbacks": 0,
        "json_repair_attempts": 0,
        "format_conversions": 0,
        "logs_with_fallbacks": 0,
    }

    for log in logs:
        fallbacks = count_pattern_in_log(log, r"Falling back to structured_edit")
        repairs = count_pattern_in_log(log, r"Attempting JSON repair")
        conversions = count_pattern_in_log(log, r"Converting to structured edit")

        metrics["structured_edit_fallbacks"] += fallbacks
        metrics["json_repair_attempts"] += repairs
        metrics["format_conversions"] += conversions

        if fallbacks > 0:
            metrics["logs_with_fallbacks"] += 1

    return metrics


def check_stability(
    current_metrics: Dict, baseline_metrics: Dict, threshold: float = 0.10
) -> Tuple[bool, List[str]]:
    """
    Check if current metrics are within acceptable range of baseline.

    Args:
        current_metrics: Current metric values
        baseline_metrics: Expected baseline values
        threshold: Acceptable drop percentage (default 10%)

    Returns:
        (is_stable, warnings)
    """
    is_stable = True
    warnings = []

    for key, baseline_value in baseline_metrics.items():
        if baseline_value == 0:
            continue  # Skip zero baselines

        current_value = current_metrics.get(key, 0)
        drop_percentage = (baseline_value - current_value) / baseline_value

        if drop_percentage > threshold:
            is_stable = False
            warnings.append(
                f"  ⚠️  {key}: {current_value} (baseline: {baseline_value}, "
                f"drop: {drop_percentage * 100:.1f}%)"
            )
        elif drop_percentage > threshold / 2:
            # Warning but not failure
            warnings.append(
                f"  ⚡ {key}: {current_value} (baseline: {baseline_value}, "
                f"drop: {drop_percentage * 100:.1f}%) - close to threshold"
            )

    return is_stable, warnings


def main():
    """Main monitoring function."""
    print("BUILD-112/113/114 Stability Monitor")
    print("=" * 80)
    print()

    # Find recent logs
    logs = find_recent_execution_logs()
    print(f"Analyzing {len(logs)} execution logs from last 7 days")
    print()

    if not logs:
        print("⚠️  No recent execution logs found")
        return

    # Analyze each build
    print("BUILD-112: Deep Retrieval Stability")
    print("-" * 40)
    build112_metrics = analyze_build112_stability(logs)
    for key, value in build112_metrics.items():
        print(f"  {key}: {value}")
    print()

    print("BUILD-113: Goal-Aware Decision Making Stability")
    print("-" * 40)
    build113_metrics = analyze_build113_stability(logs)
    for key, value in build113_metrics.items():
        print(f"  {key}: {value}")
    print()

    print("BUILD-114: Structured Edit Support Stability")
    print("-" * 40)
    build114_metrics = analyze_build114_stability(logs)
    for key, value in build114_metrics.items():
        print(f"  {key}: {value}")
    print()

    # Check against baselines (from BUILD-129_SELF_IMPROVEMENT_PLAN.md)
    print("Stability Check Against Baselines")
    print("=" * 80)
    print()

    # Baselines from recent builds (conservative estimates)
    build112_baseline = {
        "deep_retrieval_triggers": 10,  # ~15 per week, but conservative
        "logs_with_deep_retrieval": 3,
    }

    build113_baseline = {
        "goal_aware_decisions": 5,  # ~8 per week, but conservative
        "logs_with_decisions": 2,
    }

    build114_baseline = {
        "structured_edit_fallbacks": 8,  # ~12 per week, but conservative
        "logs_with_fallbacks": 3,
    }

    # Check BUILD-112 stability
    print("BUILD-112 Status:")
    stable_112, warnings_112 = check_stability(build112_metrics, build112_baseline)
    if stable_112 and not warnings_112:
        print("  ✅ STABLE - No regressions detected")
    elif stable_112:
        print("  ⚡ STABLE (with warnings):")
        for w in warnings_112:
            print(w)
    else:
        print("  ❌ REGRESSION DETECTED:")
        for w in warnings_112:
            print(w)
    print()

    # Check BUILD-113 stability
    print("BUILD-113 Status:")
    stable_113, warnings_113 = check_stability(build113_metrics, build113_baseline)
    if stable_113 and not warnings_113:
        print("  ✅ STABLE - No regressions detected")
    elif stable_113:
        print("  ⚡ STABLE (with warnings):")
        for w in warnings_113:
            print(w)
    else:
        print("  ❌ REGRESSION DETECTED:")
        for w in warnings_113:
            print(w)
    print()

    # Check BUILD-114 stability
    print("BUILD-114 Status:")
    stable_114, warnings_114 = check_stability(build114_metrics, build114_baseline)
    if stable_114 and not warnings_114:
        print("  ✅ STABLE - No regressions detected")
    elif stable_114:
        print("  ⚡ STABLE (with warnings):")
        for w in warnings_114:
            print(w)
    else:
        print("  ❌ REGRESSION DETECTED:")
        for w in warnings_114:
            print(w)
    print()

    # Overall status
    print("=" * 80)
    all_stable = stable_112 and stable_113 and stable_114

    if all_stable:
        print("✅ OVERALL STATUS: ALL SYSTEMS STABLE")
        print()
        print("Safe to proceed with next BUILD-129 phase")
        return 0
    else:
        print("❌ OVERALL STATUS: REGRESSIONS DETECTED")
        print()
        print("⚠️  PAUSE BUILD-129 execution and investigate regressions")
        return 1


if __name__ == "__main__":
    sys.exit(main())
