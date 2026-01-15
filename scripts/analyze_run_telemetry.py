"""
ROAD-B: Automated Telemetry Analysis and Prioritization

Aggregates phase outcome telemetry into ranked issue lists for automated discovery.
Generates: top cost sinks, failure modes, retry causes, flaky patterns.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional


class TelemetryAnalyzer:
    """Analyze telemetry events and generate ranked issue lists."""

    def __init__(self, db_path: str = "autopack.db"):
        """Initialize analyzer with database path.

        Args:
            db_path: SQLite database path containing telemetry events
        """
        self.db_path = db_path
        self.conn = None

    def connect(self):
        """Connect to database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # Access rows as dicts

    def disconnect(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def analyze_failures(self, window_days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
        """Analyze top failure modes.

        Args:
            window_days: Look back N days
            limit: Top N failures to return

        Returns:
            List of failure patterns with frequency
        """
        if not self.conn:
            raise RuntimeError("Database not connected. Use context manager or call connect().")

        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(days=window_days)

        # Try to query if table exists; otherwise return empty
        try:
            cursor.execute(
                """
                SELECT
                    phase_id,
                    outcome,
                    stop_reason,
                    COUNT(*) as frequency
                FROM phase_outcome_events
                WHERE timestamp >= ? AND outcome = 'FAILED'
                GROUP BY phase_id, stop_reason
                ORDER BY frequency DESC
                LIMIT ?
            """,
                (cutoff.isoformat(), limit),
            )

            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return []

    def analyze_cost_sinks(self, window_days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
        """Analyze top token cost sinks.

        Args:
            window_days: Look back N days
            limit: Top N sinks to return

        Returns:
            List of phases by token usage
        """
        if not self.conn:
            raise RuntimeError("Database not connected. Use context manager or call connect().")

        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(days=window_days)

        # Try to query if table exists; otherwise return empty
        try:
            cursor.execute(
                """
                SELECT
                    phase_id,
                    SUM(tokens_used) as total_tokens,
                    COUNT(*) as run_count
                FROM phases
                WHERE created_at >= ?
                GROUP BY phase_id
                ORDER BY total_tokens DESC
                LIMIT ?
            """,
                (cutoff.isoformat(), limit),
            )

            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return []

    def analyze_retry_patterns(self, window_days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
        """Analyze top retry causes.

        Args:
            window_days: Look back N days
            limit: Top N patterns to return

        Returns:
            List of retry patterns with frequency
        """
        if not self.conn:
            raise RuntimeError("Database not connected. Use context manager or call connect().")

        cursor = self.conn.cursor()
        cutoff = datetime.now() - timedelta(days=window_days)

        # Try to query; otherwise return empty
        try:
            cursor.execute(
                """
                SELECT
                    phase_id,
                    stop_reason,
                    COUNT(*) as retry_count
                FROM phase_outcome_events
                WHERE timestamp >= ? AND outcome IN ('FAILED', 'STUCK')
                GROUP BY phase_id, stop_reason
                HAVING retry_count > 1
                ORDER BY retry_count DESC
                LIMIT ?
            """,
                (cutoff.isoformat(), limit),
            )

            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []

    def generate_analysis_report(
        self,
        window_days: int = 7,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Generate comprehensive analysis report.

        Args:
            window_days: Analysis window in days
            limit: Top N items per category

        Returns:
            Structured analysis report
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "window_days": window_days,
            "top_failures": self.analyze_failures(window_days, limit),
            "top_cost_sinks": self.analyze_cost_sinks(window_days, limit),
            "top_retry_patterns": self.analyze_retry_patterns(window_days, limit),
        }


def write_analysis_report(
    report: Dict[str, Any],
    output_path: Path,
) -> None:
    """Write analysis report to file.

    Args:
        report: Analysis report from generate_analysis_report
        output_path: Output file path (will create parent directories)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write human-readable markdown
    with open(output_path, "w") as f:
        f.write("# Telemetry Analysis Report\n\n")
        f.write(f"**Generated**: {report['timestamp']}\n")
        f.write(f"**Analysis Window**: Last {report['window_days']} days\n\n")

        # Top failures
        f.write("## Top Failure Modes\n\n")
        if report["top_failures"]:
            for failure in report["top_failures"]:
                f.write(
                    f"- **{failure['phase_id']}**: {failure['stop_reason']} "
                    f"({failure['frequency']} times)\n"
                )
        else:
            f.write("No failures recorded in this period.\n")

        # Top cost sinks
        f.write("\n## Top Cost Sinks (Token Usage)\n\n")
        if report["top_cost_sinks"]:
            for sink in report["top_cost_sinks"]:
                f.write(
                    f"- **{sink['phase_id']}**: {sink['total_tokens']:,} tokens "
                    f"({sink['run_count']} runs)\n"
                )
        else:
            f.write("No cost data available.\n")

        # Retry patterns
        f.write("\n## Top Retry Patterns\n\n")
        if report["top_retry_patterns"]:
            for pattern in report["top_retry_patterns"]:
                f.write(
                    f"- **{pattern['phase_id']}**: {pattern['stop_reason']} "
                    f"({pattern['retry_count']} retries)\n"
                )
        else:
            f.write("No retry patterns detected.\n")

    # Also write machine-readable JSON
    json_path = output_path.with_suffix(".json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"✅ Analysis report written to {output_path}")
    print(f"✅ Machine-readable JSON written to {json_path}")


def main():
    """Run telemetry analysis as standalone script."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze Autopack telemetry events")
    parser.add_argument(
        "--db",
        default="autopack.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=7,
        help="Analysis window in days (default: 7)",
    )
    parser.add_argument(
        "--output",
        default=".autonomous_runs/telemetry_analysis/report.md",
        help="Output report path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Top N items per category (default: 10)",
    )

    args = parser.parse_args()

    # Run analysis
    with TelemetryAnalyzer(args.db) as analyzer:
        report = analyzer.generate_analysis_report(
            window_days=args.window,
            limit=args.limit,
        )

    # Write output
    output_path = Path(args.output)
    write_analysis_report(report, output_path)

    print("\n📊 Analysis Summary:")
    print(f"   Failures: {len(report['top_failures'])}")
    print(f"   Cost sinks: {len(report['top_cost_sinks'])}")
    print(f"   Retry patterns: {len(report['top_retry_patterns'])}")


if __name__ == "__main__":
    main()
