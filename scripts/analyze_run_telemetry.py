"""CLI script for analyzing run telemetry and generating ranked issues.

Usage:
    # Analyze last 7 days (default)
    python scripts/analyze_run_telemetry.py

    # Analyze last 30 days
    python scripts/analyze_run_telemetry.py --window-days 30

    # Custom output path
    python scripts/analyze_run_telemetry.py --output archive/telemetry/analysis.md

    # Specific database
    DATABASE_URL="postgresql://..." python scripts/analyze_run_telemetry.py
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.telemetry.analyzer import TelemetryAnalyzer


def get_database_url() -> str:
    """Get DATABASE_URL from environment with helpful error."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "=" * 80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("\nSet DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print(
            '  $env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"',
            file=sys.stderr,
        )
        print("  python scripts/analyze_run_telemetry.py\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
        print("  python scripts/analyze_run_telemetry.py\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze run telemetry and generate ranked issues")
    parser.add_argument(
        "--window-days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="archive/telemetry/ranked_issues.md",
        help="Output path for ranked issues report (default: archive/telemetry/ranked_issues.md)",
    )

    args = parser.parse_args()

    print("ROAD-B: Telemetry Analysis")
    print("=" * 80)
    print()

    # Get database connection
    db_url = get_database_url()
    print(f"Database: {db_url}")
    print(f"Analysis window: {args.window_days} days")
    print()

    # Run analysis
    with SessionLocal() as session:
        analyzer = TelemetryAnalyzer(session)

        print("Analyzing telemetry data...")
        issues = analyzer.aggregate_telemetry(window_days=args.window_days)

        # Print summary
        print()
        print("Analysis Summary:")
        print(f"  - Cost Sinks: {len(issues['top_cost_sinks'])}")
        print(f"  - Failure Modes: {len(issues['top_failure_modes'])}")
        print(f"  - Retry Causes: {len(issues['top_retry_causes'])}")
        print(f"  - Phase Type Stats: {len(issues['phase_type_stats'])}")
        print()

        # Write report
        output_path = Path(args.output)
        analyzer.write_ranked_issues(issues, output_path)

        print(f"✓ Ranked issues report written to: {output_path}")
        print()
        print("Next steps:")
        print("1. Review ranked issues in the report")
        print("2. Use top failure modes to update healing patterns (ROAD-J)")
        print("3. Use phase type stats for model optimization (ROAD-L)")


if __name__ == "__main__":
    main()
