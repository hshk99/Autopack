"""
Monitor real-time telemetry collection from running phases.
"""

import re
from pathlib import Path


def parse_telemetry_from_logs(log_dir: Path):
    """Extract [TokenEstimationV2] telemetry from run logs."""
    telemetry_samples = []

    if not log_dir.exists():
        return telemetry_samples

    # Search all log files
    for log_file in log_dir.rglob("*.log"):
        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            for line in content.split("\n"):
                if "[TokenEstimationV2]" in line:
                    telemetry_samples.append(line)
        except Exception as e:
            pass

    return telemetry_samples


def main():
    # Check both Lovable P1 and P2 runs
    runs = [
        ("lovable-p1-core-precision", ".autonomous_runs/autopack/runs/lovable-p1-core-precision"),
        ("lovable-p2-quality-ux", ".autonomous_runs/autopack/runs/lovable-p2-quality-ux"),
    ]

    total_samples = 0
    print("BUILD-129 Phase 3: Telemetry Collection Monitor")
    print("=" * 80)

    for run_id, run_path in runs:
        log_dir = Path(run_path)
        samples = parse_telemetry_from_logs(log_dir)

        print(f"\n{run_id}:")
        print(f"  Log directory: {log_dir}")
        print(f"  Samples collected: {len(samples)}")

        if samples:
            print("  Latest samples:")
            for sample in samples[-3:]:  # Show last 3
                # Extract key metrics
                match = re.search(
                    r"predicted_output=(\d+) actual_output=(\d+) smape=([\d.]+)%", sample
                )
                if match:
                    pred, actual, smape = match.groups()
                    print(f"    - Predicted: {pred}, Actual: {actual}, SMAPE: {smape}%")

        total_samples += len(samples)

    print("\n" + "=" * 80)
    print(f"Total telemetry samples collected: {total_samples}")
    print("Target: 9 samples (4 from P1, 5 from P2)")
    print(f"Progress: {total_samples}/9 ({total_samples/9*100:.1f}%)")


if __name__ == "__main__":
    main()
