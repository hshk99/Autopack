#!/usr/bin/env python
"""Tidy script: Consolidate telemetry insights into SOT ledgers."""
import argparse
import sys
from pathlib import Path

# Add src to path for imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from autopack.tidy.telemetry_consolidator import TelemetryConsolidator


def main():
    """Main entry point for telemetry consolidation script."""
    parser = argparse.ArgumentParser(description="Consolidate telemetry insights into SOT files")
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=3,
        help="Minimum occurrences for a pattern to be included",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.8,
        help="Minimum confidence score for patterns (0.0-1.0)",
    )
    parser.add_argument(
        "--sot-root",
        type=Path,
        default=Path("docs"),
        help="Root directory for SOT files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing",
    )

    args = parser.parse_args()

    consolidator = TelemetryConsolidator(sot_root=args.sot_root)

    print("Consolidating telemetry insights to SOT...")

    if args.dry_run:
        print("[DRY RUN] Would consolidate learned rules")
        print(f"[DRY RUN] Min occurrences: {args.min_occurrences}")
        print(f"[DRY RUN] Min confidence: {args.min_confidence}")
        print(f"[DRY RUN] SOT root: {args.sot_root}")
        return 0

    try:
        # Consolidate learned rules
        rules = consolidator.consolidate_learned_rules(
            min_occurrences=args.min_occurrences,
            min_confidence=args.min_confidence,
        )
        print(f"  - Extracted {len(rules)} high-signal patterns to LEARNED_RULES.json")

        # TODO: Future enhancements
        # - Append significant insights to DEBUG_LOG.md
        # - Consolidate BUILD_HISTORY from phase summaries
        # - Extract architecture decision patterns

        print("Done!")
        return 0
    except Exception as e:
        print(f"Error during consolidation: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
