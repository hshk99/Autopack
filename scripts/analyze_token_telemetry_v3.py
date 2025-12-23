"""
Token Estimation Telemetry Analysis Script - V3 Enhanced

Implements recommendations from parallel cursor second opinion:
1. Success-only filtering for tuning decisions
2. 2-tier metrics: Risk first (truncation/underestimation), cost second (waste)
3. Stratification by category/complexity/deliverable count
4. SMAPE as diagnostic only, not decision metric

Usage:
    # All samples
    python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs

    # Success-only (for tuning decisions)
    python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs --success-only

    # Stratified analysis
    python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs --stratify
"""

import re
import sys
import argparse
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict
import statistics


class TokenEstimationRecord:
    """Single token estimation record from logs."""

    def __init__(self, timestamp: str, predicted: int, actual: int, error_pct: float,
                 source_file: str = "", line_number: int = 0):
        self.timestamp = timestamp
        self.predicted = predicted
        self.actual = actual
        self.error_pct = error_pct  # SMAPE for V2, asymmetric % for V1
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

    @property
    def is_successful(self) -> bool:
        """Check if this was a successful phase (V2 only)."""
        if self.meta.get("format") != "v2":
            return False  # Can't determine for V1
        return str(self.meta.get("success", "")).lower() == "true"

    @property
    def was_truncated(self) -> bool:
        """Check if output was truncated (V2 only)."""
        if self.meta.get("format") != "v2":
            return False
        return str(self.meta.get("truncated", "")).lower() == "true"

    @property
    def waste_ratio(self) -> float:
        """Calculate waste ratio: predicted / actual (>1 = overestimation)."""
        if self.actual == 0:
            return float('inf')
        return self.predicted / self.actual


class TelemetryAnalyzerV3:
    """Enhanced analyzer with success filtering and 2-tier metrics."""

    # V2 Pattern
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

    # V1 Pattern (legacy)
    TELEMETRY_PATTERN = re.compile(
        r'\[TokenEstimation\]\s+Predicted:\s+(\d+)\s+output tokens,\s+'
        r'Actual:\s+(\d+)\s+output tokens,\s+Error:\s+([\d.]+)%'
    )

    TIMESTAMP_PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})'
    )

    def __init__(self):
        self.records: List[TokenEstimationRecord] = []

    def parse_log_file(self, log_path: Path) -> int:
        """Parse a single log file for telemetry records."""
        count = 0
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    # Try V2 first
                    v2 = self.TELEMETRY_V2_PATTERN.search(line)
                    if v2:
                        predicted = int(v2.group(1))
                        actual = int(v2.group(2))
                        smape_pct = float(v2.group(3))

                        timestamp = ""
                        ts_match = self.TIMESTAMP_PATTERN.search(line)
                        if ts_match:
                            timestamp = ts_match.group(1)

                        record = TokenEstimationRecord(
                            timestamp=timestamp,
                            predicted=predicted,
                            actual=actual,
                            error_pct=smape_pct,
                            source_file=str(log_path),
                            line_number=line_num
                        )
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

                    # Fall back to V1
                    match = self.TELEMETRY_PATTERN.search(line)
                    if match:
                        predicted = int(match.group(1))
                        actual = int(match.group(2))
                        error_pct = float(match.group(3))

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
        """Scan directory recursively for log files."""
        total = 0
        for log_file in directory.rglob(pattern):
            count = self.parse_log_file(log_file)
            if count > 0:
                print(f"Found {count} records in {log_file}")
            total += count
        return total

    def calculate_tier1_metrics(self, records: List[TokenEstimationRecord]) -> Dict:
        """Tier 1: Risk Metrics (truncation prevention)."""
        if not records:
            return {"error": "No records"}

        # Underestimation: actual > predicted (risk of truncation)
        underestimated = [r for r in records if r.actual > r.predicted]
        underestimation_rate = len(underestimated) / len(records) * 100

        # Truncation (V2 only)
        v2_records = [r for r in records if r.meta.get("format") == "v2"]
        truncated = [r for r in v2_records if r.was_truncated]
        truncation_rate = (len(truncated) / len(v2_records) * 100) if v2_records else 0.0

        # Success rate (V2 only)
        succeeded = [r for r in v2_records if r.is_successful]
        success_rate = (len(succeeded) / len(v2_records) * 100) if v2_records else 0.0

        return {
            "underestimation_rate_pct": underestimation_rate,
            "underestimation_count": len(underestimated),
            "truncation_rate_pct": truncation_rate,
            "truncation_count": len(truncated),
            "success_rate_pct": success_rate,
            "success_count": len(succeeded),
            "total_samples": len(records),
            "v2_samples": len(v2_records),
        }

    def calculate_tier2_metrics(self, records: List[TokenEstimationRecord]) -> Dict:
        """Tier 2: Cost Metrics (budget waste)."""
        if not records:
            return {"error": "No records"}

        waste_ratios = [r.waste_ratio for r in records if r.waste_ratio != float('inf')]

        if not waste_ratios:
            return {"error": "No valid waste ratios"}

        return {
            "waste_ratio_median": statistics.median(waste_ratios),
            "waste_ratio_p90": statistics.quantiles(waste_ratios, n=10)[8] if len(waste_ratios) >= 10 else max(waste_ratios),
            "waste_ratio_mean": statistics.mean(waste_ratios),
        }

    def calculate_diagnostic_metrics(self, records: List[TokenEstimationRecord]) -> Dict:
        """Diagnostic metrics (SMAPE, basic stats)."""
        if not records:
            return {"error": "No records"}

        errors = [r.error_pct for r in records]
        predicted = [r.predicted for r in records]
        actual = [r.actual for r in records]

        return {
            "smape_mean": statistics.mean(errors),
            "smape_median": statistics.median(errors),
            "smape_min": min(errors),
            "smape_max": max(errors),
            "predicted_mean": statistics.mean(predicted),
            "predicted_median": statistics.median(predicted),
            "actual_mean": statistics.mean(actual),
            "actual_median": statistics.median(actual),
        }

    def generate_report(self, success_only: bool = False, stratify: bool = False,
                       output_path: Optional[Path] = None) -> str:
        """Generate comprehensive analysis report."""
        if not self.records:
            return "# Token Estimation Analysis\n\nNo telemetry records found.\n"

        # Filter to success-only if requested
        analysis_records = self.records
        if success_only:
            analysis_records = [r for r in self.records if r.is_successful]
            if not analysis_records:
                return "# Token Estimation Analysis\n\nNo successful records found for analysis.\n"

        tier1 = self.calculate_tier1_metrics(analysis_records)
        tier2 = self.calculate_tier2_metrics(analysis_records)
        diagnostic = self.calculate_diagnostic_metrics(analysis_records)

        # Determine if tuning is needed
        needs_tuning = (
            tier1.get("underestimation_rate_pct", 0) > 5.0 or
            tier1.get("truncation_rate_pct", 0) > 2.0
        )

        tuning_status = "❌ TUNING NEEDED" if needs_tuning else "✅ WITHIN TARGETS"

        report = f"""# Token Estimation Telemetry Analysis V3
Generated: {datetime.now().isoformat()}

## Analysis Configuration
- **Filter**: {"SUCCESS ONLY (for tuning decisions)" if success_only else "ALL SAMPLES (includes failures)"}
- **Total Records**: {len(self.records)}
- **Analysis Records**: {len(analysis_records)}
- **V2 Records**: {tier1.get('v2_samples', 0)}

---

## 🎯 TIER 1: RISK METRICS (Primary Tuning Gates)

### Truncation Prevention
- **Underestimation Rate**: {tier1.get('underestimation_rate_pct', 0):.1f}% ({tier1.get('underestimation_count', 0)} samples)
  - **Target**: ≤ 5%
  - **Status**: {"❌ ABOVE TARGET" if tier1.get('underestimation_rate_pct', 0) > 5.0 else "✅ WITHIN TARGET"}

- **Truncation Rate** (V2 only): {tier1.get('truncation_rate_pct', 0):.1f}% ({tier1.get('truncation_count', 0)} samples)
  - **Target**: ≤ 2%
  - **Status**: {"❌ ABOVE TARGET" if tier1.get('truncation_rate_pct', 0) > 2.0 else "✅ WITHIN TARGET"}

### Quality
- **Success Rate** (V2 only): {tier1.get('success_rate_pct', 0):.1f}% ({tier1.get('success_count', 0)} samples)

---

## 💰 TIER 2: COST METRICS (Secondary Optimization)

### Budget Waste (predicted/actual ratio)
- **Median**: {tier2.get('waste_ratio_median', 0):.2f}x
- **P90**: {tier2.get('waste_ratio_p90', 0):.2f}x
- **Mean**: {tier2.get('waste_ratio_mean', 0):.2f}x

**Interpretation**:
- 1.0x = perfect prediction
- >1.0x = overestimation (budget waste)
- <1.0x = underestimation (truncation risk)

---

## 📊 DIAGNOSTIC METRICS (SMAPE - for reference only)

### SMAPE (Symmetric Mean Absolute Percentage Error)
- **Mean**: {diagnostic.get('smape_mean', 0):.1f}%
- **Median**: {diagnostic.get('smape_median', 0):.1f}%
- **Range**: {diagnostic.get('smape_min', 0):.1f}% - {diagnostic.get('smape_max', 0):.1f}%

### Token Distribution
- **Predicted**: mean={diagnostic.get('predicted_mean', 0):.0f}, median={diagnostic.get('predicted_median', 0):.0f}
- **Actual**: mean={diagnostic.get('actual_mean', 0):.0f}, median={diagnostic.get('actual_median', 0):.0f}

---

## 🚦 TUNING DECISION: {tuning_status}

"""

        if needs_tuning:
            report += """### ⚠️ Action Required

Based on Tier 1 metrics, coefficient tuning is recommended:

"""
            if tier1.get("underestimation_rate_pct", 0) > 5.0:
                report += f"- **Underestimation rate {tier1.get('underestimation_rate_pct', 0):.1f}% > 5% target**\n"
                report += "  - Increase base estimates for affected categories\n"
                report += "  - Consider higher quantile targets (p90 instead of p50)\n\n"

            if tier1.get("truncation_rate_pct", 0) > 2.0:
                report += f"- **Truncation rate {tier1.get('truncation_rate_pct', 0):.1f}% > 2% target**\n"
                report += "  - Increase safety margins\n"
                report += "  - Review selected_budget calculation\n\n"
        else:
            report += """### ✅ No Tuning Needed

Tier 1 metrics are within targets. Monitor for drift, but coefficient changes are not required.

Consider cost optimization (Tier 2) if waste ratio P90 > 3x, but this is secondary to truncation prevention.

"""

        # Stratification section
        if stratify:
            report += self._generate_stratified_analysis(analysis_records)

        # Recommendations
        report += """
---

## 📋 Next Steps

"""
        if success_only:
            report += """1. ✅ **Using success-only filter** - This analysis is tuning-ready
2. Review stratified breakdown by category/complexity if available
3. If tuning needed, adjust coefficients and re-validate on held-out data
4. Monitor Tier 1 metrics for 20 production runs post-tuning
"""
        else:
            report += """1. ⚠️ **Re-run with --success-only flag** for tuning decisions
2. Current analysis includes failure-mode samples (not representative)
3. Only use Tier 1 metrics from successful phases for tuning
4. Keep this "all samples" view for monitoring overall behavior
"""

        report += f"""
---

## Data Sources

Total files analyzed: {len(set(r.source_file for r in self.records))}

"""

        # List source files
        source_files = defaultdict(int)
        for record in self.records:
            source_files[record.source_file] += 1

        for source, count in sorted(source_files.items(), key=lambda x: x[1], reverse=True):
            report += f"- `{source}`: {count} records\n"

        if output_path:
            output_path.write_text(report, encoding='utf-8')
            print(f"\nReport written to: {output_path}")

        return report

    def _generate_stratified_analysis(self, records: List[TokenEstimationRecord]) -> str:
        """Generate stratified breakdown by category/complexity."""
        v2_records = [r for r in records if r.meta.get("format") == "v2"]

        if not v2_records:
            return "\n## Stratified Analysis\n\nNo V2 records available for stratification.\n"

        report = "\n## 📊 Stratified Analysis\n\n"

        # By category
        by_category = defaultdict(list)
        for r in v2_records:
            by_category[r.meta.get("category", "unknown")].append(r)

        report += "### By Category\n\n"
        for category, cat_records in sorted(by_category.items()):
            tier1 = self.calculate_tier1_metrics(cat_records)
            report += f"**{category}** ({len(cat_records)} samples):\n"
            report += f"- Underestimation: {tier1.get('underestimation_rate_pct', 0):.1f}%\n"
            report += f"- Truncation: {tier1.get('truncation_rate_pct', 0):.1f}%\n"
            report += f"- Success: {tier1.get('success_rate_pct', 0):.1f}%\n\n"

        # By complexity
        by_complexity = defaultdict(list)
        for r in v2_records:
            by_complexity[r.meta.get("complexity", "unknown")].append(r)

        report += "### By Complexity\n\n"
        for complexity, comp_records in sorted(by_complexity.items()):
            tier1 = self.calculate_tier1_metrics(comp_records)
            report += f"**{complexity}** ({len(comp_records)} samples):\n"
            report += f"- Underestimation: {tier1.get('underestimation_rate_pct', 0):.1f}%\n"
            report += f"- Truncation: {tier1.get('truncation_rate_pct', 0):.1f}%\n"
            report += f"- Success: {tier1.get('success_rate_pct', 0):.1f}%\n\n"

        return report


def main():
    parser = argparse.ArgumentParser(
        description="Analyze token estimation telemetry (V3 Enhanced)"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(".autonomous_runs"),
        help="Directory to scan for log files"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.log",
        help="Log file pattern (default: *.log)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for report"
    )
    parser.add_argument(
        "--success-only",
        action="store_true",
        help="Filter to successful phases only (for tuning decisions)"
    )
    parser.add_argument(
        "--stratify",
        action="store_true",
        help="Include stratified analysis by category/complexity"
    )

    args = parser.parse_args()

    print(f"Scanning {args.log_dir} for {args.pattern} files...")
    if args.success_only:
        print("Filter: SUCCESS ONLY (for tuning decisions)")

    analyzer = TelemetryAnalyzerV3()
    total_records = analyzer.scan_directory(args.log_dir, args.pattern)

    print(f"\nTotal records found: {total_records}")

    if total_records == 0:
        print("\n⚠️  No telemetry found.")
        return 1

    report = analyzer.generate_report(
        success_only=args.success_only,
        stratify=args.stratify,
        output_path=args.output
    )

    if not args.output:
        print("\n" + report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
