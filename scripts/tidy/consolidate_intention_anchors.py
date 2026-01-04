"""
Tidy hook: Consolidate Intention Anchor artifacts into SOT ledgers.

Intention behind it: Provide a human-triggered (or scheduled) consolidation of
run-local anchor artifacts into BUILD_HISTORY/DEBUG_LOG, without requiring
autonomous runs to write directly to SOT ledgers during execution.

This is a PLACEHOLDER implementation for Milestone 3. Full implementation
requires autonomous runs to complete and generate meaningful completion summaries.

Design principles:
- Run-local artifacts are append-only and never modified during consolidation
- Consolidation is idempotent (safe to run multiple times)
- SOT ledgers remain manually curated (this script assists, doesn't replace)
- Dry-run mode by default (requires explicit --apply flag)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from autopack.intention_anchor import (
    generate_anchor_summary,
    get_anchor_events_path,
    get_anchor_summary_path,
    load_anchor,
    read_anchor_events,
)

logger = logging.getLogger(__name__)


def find_runs_with_anchors(base_dir: Path = Path(".")) -> list[str]:
    """
    Find all run IDs that have intention anchors.

    Args:
        base_dir: Base directory to search (default: ".").

    Returns:
        List of run IDs with intention anchors.
    """
    runs_dir = base_dir / ".autonomous_runs"
    if not runs_dir.exists():
        return []

    run_ids = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue

        anchor_path = run_dir / "intention_anchor.json"
        if anchor_path.exists():
            run_ids.append(run_dir.name)

    return sorted(run_ids)


def analyze_anchor_artifacts(run_id: str, base_dir: Path = Path(".")) -> dict:
    """
    Analyze anchor artifacts for a run.

    Args:
        run_id: Run identifier.
        base_dir: Base directory (default: ".").

    Returns:
        Dictionary with analysis results.
    """
    analysis = {
        "run_id": run_id,
        "has_anchor": False,
        "has_summary": False,
        "has_events": False,
        "anchor_version": None,
        "anchor_id": None,
        "event_count": 0,
        "prompt_injections": 0,
        "last_updated": None,
    }

    # Check for anchor
    try:
        anchor = load_anchor(run_id, base_dir=base_dir)
        analysis["has_anchor"] = True
        analysis["anchor_version"] = anchor.version
        analysis["anchor_id"] = anchor.anchor_id
        analysis["last_updated"] = anchor.updated_at.isoformat()
    except FileNotFoundError:
        pass

    # Check for summary
    summary_path = get_anchor_summary_path(run_id, base_dir=base_dir)
    analysis["has_summary"] = summary_path.exists()

    # Check for events
    events_path = get_anchor_events_path(run_id, base_dir=base_dir)
    if events_path.exists():
        analysis["has_events"] = True
        events = read_anchor_events(run_id, base_dir=base_dir)
        analysis["event_count"] = len(events)
        analysis["prompt_injections"] = len([
            e for e in events
            if e.get("event_type", "").startswith("prompt_injected_")
        ])

    return analysis


def generate_consolidation_report(
    run_ids: list[str],
    base_dir: Path = Path("."),
) -> str:
    """
    Generate human-readable consolidation report.

    Intention behind it: Show what would be consolidated without actually doing it
    (dry-run mode).

    Args:
        run_ids: List of run IDs to analyze.
        base_dir: Base directory (default: ".").

    Returns:
        Markdown-formatted report.
    """
    lines = [
        "# Intention Anchor Consolidation Report",
        "",
        f"**Total runs analyzed**: {len(run_ids)}",
        "",
    ]

    for run_id in run_ids:
        analysis = analyze_anchor_artifacts(run_id, base_dir=base_dir)

        lines.append(f"## Run: {run_id}")
        lines.append("")
        lines.append(f"- Anchor ID: `{analysis['anchor_id']}`")
        lines.append(f"- Version: {analysis['anchor_version']}")
        lines.append(f"- Last updated: {analysis['last_updated']}")
        lines.append(f"- Summary exists: {analysis['has_summary']}")
        lines.append(f"- Events logged: {analysis['event_count']}")
        lines.append(f"- Prompt injections: {analysis['prompt_injections']}")
        lines.append("")

        # PLACEHOLDER: Where consolidation logic would go
        lines.append("**Consolidation actions (PLACEHOLDER):**")
        lines.append("- [ ] Review anchor_summary.md manually")
        lines.append("- [ ] Assess if run completed successfully")
        lines.append("- [ ] Add entry to BUILD_HISTORY referencing anchor_id + version")
        lines.append("- [ ] Optionally add DEBUG_LOG entry if interesting failure modes")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("**Note**: This is a PLACEHOLDER implementation for Milestone 3.")
    lines.append("Full consolidation requires:")
    lines.append("1. Autonomous runs to complete end-to-end")
    lines.append("2. Runs to generate completion summaries")
    lines.append("3. Tidy rules to mechanically identify 'interesting' runs")
    lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point for consolidation hook."""
    parser = argparse.ArgumentParser(
        description="Consolidate Intention Anchor artifacts into SOT ledgers (PLACEHOLDER)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform consolidation (default: dry-run only)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Consolidate specific run ID (default: all runs)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Write report to file (default: stdout)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting Intention Anchor consolidation analysis...")

    # Find runs with anchors
    if args.run_id:
        run_ids = [args.run_id]
    else:
        run_ids = find_runs_with_anchors()

    logger.info(f"Found {len(run_ids)} run(s) with intention anchors")

    if not run_ids:
        logger.warning("No runs with intention anchors found")
        return

    # Generate report
    report = generate_consolidation_report(run_ids)

    # Output report
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report, encoding="utf-8")
        logger.info(f"Report written to: {output_path}")
    else:
        print(report)

    # Apply consolidation (PLACEHOLDER)
    if args.apply:
        logger.warning(
            "⚠️  --apply flag detected, but consolidation is NOT yet implemented"
        )
        logger.warning(
            "This is a PLACEHOLDER for Milestone 3. Manual review of anchor_summary.md required."
        )
        logger.info(
            "To consolidate: manually review .autonomous_runs/<run_id>/anchor_summary.md "
            "and add relevant entries to BUILD_HISTORY/DEBUG_LOG referencing anchor_id + version"
        )


if __name__ == "__main__":
    main()
