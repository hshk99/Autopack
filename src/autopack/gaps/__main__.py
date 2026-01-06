"""Gap scanner CLI entry point.

Usage:
    python -m autopack.gaps --run-id RUN_ID --project-id PROJECT_ID [--write]

Examples:
    # Report only (prints to stdout):
    python -m autopack.gaps --run-id test-run-001 --project-id autopack

    # Write to run-local artifact:
    python -m autopack.gaps --run-id test-run-001 --project-id autopack --write
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .scanner import scan_workspace
from ..file_layout import RunFileLayout

logger = logging.getLogger(__name__)


def main() -> int:
    """CLI entry point for gap scanner.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        description="Scan workspace for gaps (deterministic)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier",
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="Project identifier",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write gap report to run-local artifact (default: report only)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root directory (default: current directory)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Scan workspace
        workspace_root = args.workspace.resolve()
        logger.info(f"Scanning workspace: {workspace_root}")

        report = scan_workspace(
            workspace_root=workspace_root,
            project_id=args.project_id,
            run_id=args.run_id,
        )

        # Validate report
        report.validate_against_schema()

        # Print summary to stderr (so stdout is clean JSON)
        print(
            f"[Gap Scanner] Found {report.summary.total_gaps} gaps "
            f"({report.summary.autopilot_blockers} blockers)",
            file=sys.stderr,
        )

        if args.write:
            # Write to run-local artifact
            layout = RunFileLayout(run_id=args.run_id, project_id=args.project_id)
            layout.ensure_directories()

            # Create gaps directory
            gaps_dir = layout.base_dir / "gaps"
            gaps_dir.mkdir(exist_ok=True)

            gap_report_path = gaps_dir / "gap_report_v1.json"
            report.save_to_file(gap_report_path)

            print(
                f"[Gap Scanner] Wrote gap report: {gap_report_path}",
                file=sys.stderr,
            )

        # Print JSON to stdout
        print(json.dumps(report.to_json_dict(), indent=2, ensure_ascii=False))

        return 0

    except Exception as e:
        logger.exception("Gap scanner failed")
        print(f"[Gap Scanner] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
