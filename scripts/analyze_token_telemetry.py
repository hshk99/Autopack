"""
Token Estimation Telemetry Analysis Script

Analyzes [TokenEstimation] logs to:
1. Calculate average error rate
2. Identify patterns in over/under-estimation
3. Generate recommendations for coefficient tuning
4. Track improvement over time

Usage:
    python scripts/analyze_token_telemetry.py [--log-dir DIR] [--output REPORT.md]
"""

import re
import sys
import argparse
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict


class TokenEstimationRecord:
    """Single token estimation record from logs."""

    def __init__(self, timestamp: str, predicted: int, actual: int, error_pct: float,
                 source_file: str = "", line_number: int = 0):
        self.timestamp = timestamp
        self.predicted = predicted
        self.actual = actual
        self.error_pct = error_pct
        self.source_file = source_file
        self.line_number = line_number
        self.meta: Dict = {}

    @property
    def absolute_error(self) -> int:
        return abs(self.actual - self.predicted)

    @property
    def is_over_estimated(self) -> bool:
        return self.predicted > self.actual

    @property
    def is_under_estimated(self) -> bool:
        return self.predicted < self.actual


class TelemetryAnalyzer:
    """Analyzes token estimation telemetry data."""

    # Pattern: [TokenEstimation] Predicted: 500 output tokens, Actual: 114 output tokens, Error: 77.2%
    TELEMETRY_PATTERN = re.compile(
        r'\[TokenEstimation\]\s+Predicted:\s+(\d+)\s+output tokens,\s+'
        r'Actual:\s+(\d+)\s+output tokens,\s+Error:\s+([\d.]+)%'
    )

    # Pattern:
    # [TokenEstimationV2] predicted_output=448 actual_output=128 smape=111.8% selected_budget=8192 category=implementation ...
    TELEMETRY_V2_PATTERN = re.compile(
        r'\[TokenEstimationV2\]\s+'
        r'predicted_output=(\d+)\s+'
        r'actual_output=(\d+)\s+'
        r'smape=([\d.]+)%\s+'
        r'selected_budget=([^\s]+)\s+'
        r'category=([^\s]+)\s+'
        r'complexity=([^\s]+)\s+'
        r'deliverables=(\d+)\s+'
        r'success=([^\s]+)\s+'
        r'stop_reason=([^\s]+)\s+'
        r'truncated=([^\s]+)\s+'
        r'model=([^\s]+)'
    )

    # Timestamp pattern (various formats)
    TIMESTAMP_PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})'
    )

    def __init__(self):
        self.records: List[TokenEstimationRecord] = []

    def parse_log_file(self, log_path: Path) -> int:
        """Parse a single log file for telemetry records.

        Args:
            log_path: Path to log file

        Returns:
            Number of records found
        """
        count = 0
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    v2 = self.TELEMETRY_V2_PATTERN.search(line)
                    if v2:
                        predicted = int(v2.group(1))
                        actual = int(v2.group(2))
                        smape_pct = float(v2.group(3))

                        # Extract timestamp if present
                        timestamp = ""
                        ts_match = self.TIMESTAMP_PATTERN.search(line)
                        if ts_match:
                            timestamp = ts_match.group(1)

                        record = TokenEstimationRecord(
                            timestamp=timestamp,
                            predicted=predicted,
                            actual=actual,
                            error_pct=smape_pct,  # Store as error_pct for reporting compatibility
                            source_file=str(log_path),
                            line_number=line_num
                        )
                        # Attach lightweight metadata for richer reporting
                        record.meta = {
                            "format": "v2",
                            "selected_budget": v2.group(4),
                            "category": v2.group(5),
                            "complexity": v2.group(6),
                            "deliverables": int(v2.group(7)),
                            "success": v2.group(8),
                            "stop_reason": v2.group(9),
                            "truncated": v2.group(10),
                            "model": v2.group(11),
                        }
                        self.records.append(record)
                        count += 1
                        continue

                    match = self.TELEMETRY_PATTERN.search(line)
                    if match:
                        predicted = int(match.group(1))
                        actual = int(match.group(2))
                        error_pct = float(match.group(3))

                        # Extract timestamp if present
                        timestamp = ""
                        ts_match = self.TIMESTAMP_PATTERN.search(line)
                        if ts_match:
                            timestamp = ts_match.group(1)

                        record = TokenEstimationRecord(
                            timestamp=timestamp,
                            predicted=predicted,
                            actual=actual,
                            error_pct=error_pct,
                            source_file=str(log_path),
                            line_number=line_num
                        )
                        record.meta = {"format": "v1"}
                        self.records.append(record)
                        count += 1
        except Exception as e:
            print(f"Warning: Failed to parse {log_path}: {e}", file=sys.stderr)

        return count

    def scan_directory(self, directory: Path, pattern: str = "*.log") -> int:
        """Scan directory recursively for log files.

        Args:
            directory: Directory to scan
            pattern: Glob pattern for log files

        Returns:
            Total number of records found
        """
        total = 0
        for log_file in directory.rglob(pattern):
            count = self.parse_log_file(log_file)
            if count > 0:
                print(f"Found {count} records in {log_file}")
            total += count
        return total

    def calculate_statistics(self) -> Dict:
        """Calculate statistics from collected records.

        Returns:
            Dictionary with statistics
        """
        if not self.records:
            return {
                "total_records": 0,
                "error": "No telemetry records found"
            }

        errors = [r.error_pct for r in self.records]
        predicted = [r.predicted for r in self.records]
        actual = [r.actual for r in self.records]
        absolute_errors = [r.absolute_error for r in self.records]

        over_estimated = [r for r in self.records if r.is_over_estimated]
        under_estimated = [r for r in self.records if r.is_under_estimated]

        # Truncation- and risk-oriented metrics (best-effort; only for V2 records)
        v2_records = [r for r in self.records if getattr(r, "meta", {}).get("format") == "v2"]
        truncated = [r for r in v2_records if str(r.meta.get("truncated")).lower() == "true"]
        succeeded = [r for r in v2_records if str(r.meta.get("success")).lower() == "true"]
        # Underestimation flag: actual > predicted
        under_risk = [r for r in self.records if r.actual > r.predicted]

        stats = {
            "total_records": len(self.records),
            "formats": {
                "v2_records": len(v2_records),
                "v1_records": len(self.records) - len(v2_records),
            },
            "error_rate": {
                "mean": sum(errors) / len(errors),
                "median": sorted(errors)[len(errors) // 2],
                "min": min(errors),
                "max": max(errors),
                "std_dev": self._std_dev(errors),
            },
            "directional": {
                "under_estimated_count": len(under_estimated),
                "over_estimated_count": len(over_estimated),
                "under_estimated_pct": len(under_estimated) / len(self.records) * 100,
                "over_estimated_pct": len(over_estimated) / len(self.records) * 100,
                "under_risk_pct": len(under_risk) / len(self.records) * 100,
            },
            "predicted_tokens": {
                "mean": sum(predicted) / len(predicted),
                "median": sorted(predicted)[len(predicted) // 2],
                "min": min(predicted),
                "max": max(predicted),
            },
            "actual_tokens": {
                "mean": sum(actual) / len(actual),
                "median": sorted(actual)[len(actual) // 2],
                "min": min(actual),
                "max": max(actual),
            },
            "absolute_error": {
                "mean": sum(absolute_errors) / len(absolute_errors),
                "median": sorted(absolute_errors)[len(absolute_errors) // 2],
            },
            "v2": {
                "truncated_count": len(truncated),
                "truncated_pct": (len(truncated) / len(v2_records) * 100) if v2_records else 0.0,
                "success_count": len(succeeded),
                "success_pct": (len(succeeded) / len(v2_records) * 100) if v2_records else 0.0,
            },
        }

        return stats

    def _std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def generate_report(self, stats: Dict, output_path: Optional[Path] = None) -> str:
        """Generate analysis report.

        Args:
            stats: Statistics dictionary
            output_path: Optional path to write report

        Returns:
            Report text
        """
        if "error" in stats:
            return f"# Token Estimation Analysis\n\n{stats['error']}\n"

        # Check if meets target (legacy: mean % error)
        mean_error = stats["error_rate"]["mean"]
        target_met = "✅ YES" if mean_error < 30.0 else "❌ NO"

        report = f"""# Token Estimation Telemetry Analysis
Generated: {datetime.now().isoformat()}

## Summary

**Total Records Analyzed:** {stats['total_records']}
**Formats:** v2={stats.get('formats', {}).get('v2_records', 0)} v1={stats.get('formats', {}).get('v1_records', 0)}
**Mean Error Rate:** {mean_error:.1f}%
**Target (<30% error):** {target_met}
**Under-estimation rate:** {stats.get('directional', {}).get('under_estimated_pct', 0.0):.1f}% (risk for truncation)
**Over-estimation rate:** {stats.get('directional', {}).get('over_estimated_pct', 0.0):.1f}%
**V2 truncation rate:** {stats.get('v2', {}).get('truncated_pct', 0.0):.1f}% (only where V2 telemetry present)
**V2 success rate:** {stats.get('v2', {}).get('success_pct', 0.0):.1f}% (only where V2 telemetry present)

## Error Rate Statistics

- **Mean:** {stats['error_rate']['mean']:.1f}%
- **Median:** {stats['error_rate']['median']:.1f}%
- **Min:** {stats['error_rate']['min']:.1f}%
- **Max:** {stats['error_rate']['max']:.1f}%
- **Std Dev:** {stats['error_rate']['std_dev']:.1f}%

## Token Predictions

### Predicted Tokens
- **Mean:** {stats['predicted_tokens']['mean']:.0f}
- **Median:** {stats['predicted_tokens']['median']:.0f}
- **Range:** {stats['predicted_tokens']['min']:.0f} - {stats['predicted_tokens']['max']:.0f}

### Actual Tokens
- **Mean:** {stats['actual_tokens']['mean']:.0f}
- **Median:** {stats['actual_tokens']['median']:.0f}
- **Range:** {stats['actual_tokens']['min']:.0f} - {stats['actual_tokens']['max']:.0f}

### Absolute Error
- **Mean:** {stats['absolute_error']['mean']:.0f} tokens
- **Median:** {stats['absolute_error']['median']:.0f} tokens

## Estimation Direction (Risk)

- **Over-estimated:** {stats['directional']['over_estimated_count']} records ({stats['directional']['over_estimated_pct']:.1f}%)
- **Under-estimated:** {stats['directional']['under_estimated_count']} records ({stats['directional']['under_estimated_pct']:.1f}%)

## Recommendations

"""

        # Add recommendations based on analysis
        if mean_error >= 50.0:
            report += """### 🔴 Critical: High Error Rate (≥50%)

1. **Immediate Action Required:**
   - Review TokenEstimator coefficients in `src/autopack/token_estimator.py`
   - Check if deliverable type categorization is accurate
   - Verify base estimates for different file types

2. **Investigation Areas:**
   - Are actual file sizes much different from estimated averages?
   - Are there specific deliverable categories with consistently high errors?
   - Is the context size calculation accurate?

"""
        elif mean_error >= 30.0:
            report += """### 🟡 Warning: Above Target (30-50%)

1. **Tuning Recommended:**
   - Fine-tune coefficients for common deliverable types
   - Consider adding more granular categorization
   - Collect more data to identify patterns

2. **Monitor:**
   - Track error rates over next 20-30 runs
   - Identify which phases have highest errors

"""
        else:
            report += """### 🟢 Good: Within Target (<30%)

1. **Maintain:**
   - Current TokenEstimator configuration is working well
   - Continue monitoring for regressions
   - Consider optimizing high-error outliers

"""

        # Bias-specific recommendations
        over_pct = stats['directional']['over_estimated_pct']
        under_pct = stats['directional']['under_estimated_pct']

        if over_pct > 70:
            report += """
### Bias: Consistent Over-Estimation

The estimator is over-predicting by a large margin. Consider:
- Reducing base estimates for common file types
- Lowering safety buffers
- Reviewing context size multipliers

"""
        elif under_pct > 70:
            report += """
### Bias: Consistent Under-Estimation

The estimator is under-predicting. Consider:
- Increasing base estimates
- Adding safety buffers
- Reviewing actual vs estimated file sizes

"""
        else:
            report += """
### Bias: Well-Balanced

Over/under-estimation is relatively balanced, which is good.

"""

        report += """## Next Steps

1. **Prioritize V2 telemetry:** Ensure logs include `[TokenEstimationV2]` so we measure the real TokenEstimator.
2. **Collect representative runs:** Prefer successful phases; failure-mode outputs skew token counts downwards.
3. **Tune for truncation risk:** Track under-estimation rate + truncation rate alongside error.
4. **Stratify:** Break down by category/deliverable count once you have enough V2 records.

## Data Sources

"""

        # List source files
        source_files = defaultdict(int)
        for record in self.records:
            source_files[record.source_file] += 1

        for source, count in sorted(source_files.items(), key=lambda x: x[1], reverse=True):
            report += f"- `{source}`: {count} records\n"

        # Write report if output path specified
        if output_path:
            output_path.write_text(report, encoding='utf-8')
            print(f"\nReport written to: {output_path}")

        return report

    def get_worst_predictions(self, n: int = 10) -> List[TokenEstimationRecord]:
        """Get the N worst predictions by error percentage.

        Args:
            n: Number of worst predictions to return

        Returns:
            List of worst prediction records
        """
        return sorted(self.records, key=lambda r: r.error_pct, reverse=True)[:n]


def main():
    parser = argparse.ArgumentParser(
        description="Analyze token estimation telemetry from logs"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(".autonomous_runs"),
        help="Directory to scan for log files (default: .autonomous_runs)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for report (default: stdout only)"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.log",
        help="Log file pattern (default: *.log)"
    )
    parser.add_argument(
        "--worst",
        type=int,
        default=0,
        help="Show N worst predictions (default: 0, don't show)"
    )

    args = parser.parse_args()

    print(f"Scanning {args.log_dir} for {args.pattern} files...")

    analyzer = TelemetryAnalyzer()
    total_records = analyzer.scan_directory(args.log_dir, args.pattern)

    print(f"\nTotal records found: {total_records}")

    if total_records == 0:
        print("\n⚠️  No [TokenEstimation] telemetry found in logs.")
        print("This is expected if:")
        print("  1. No runs have completed since telemetry was added")
        print("  2. Runs used plans without _estimated_output_tokens")
        print("\nTo generate telemetry data, run a new autonomous execution.")
        return 1

    stats = analyzer.calculate_statistics()
    report = analyzer.generate_report(stats, args.output)

    # Print to stdout if no output file
    if not args.output:
        print("\n" + report)

    # Show worst predictions if requested
    if args.worst > 0:
        worst = analyzer.get_worst_predictions(args.worst)
        print(f"\n## Top {len(worst)} Worst Predictions\n")
        for i, record in enumerate(worst, 1):
            print(f"{i}. Error: {record.error_pct:.1f}% | "
                  f"Predicted: {record.predicted} | Actual: {record.actual} | "
                  f"Source: {Path(record.source_file).name}:{record.line_number}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
