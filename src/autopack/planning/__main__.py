"""Plan proposer CLI entry point.

Usage:
    python -m autopack.planning --run-id RUN_ID --project-id PROJECT_ID [--write]

Examples:
    # Report only (prints to stdout):
    python -m autopack.planning --run-id test-run-001 --project-id autopack

    # Write to run-local artifact:
    python -m autopack.planning --run-id test-run-001 --project-id autopack --write
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from ..file_layout import RunFileLayout
from ..gaps.models import GapReportV1
from ..intention_anchor.v2 import IntentionAnchorV2
from .plan_proposer import propose_plan

logger = logging.getLogger(__name__)


def main() -> int:
    """CLI entry point for plan proposer.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        description="Propose plan from anchor and gap report",
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
        help="Write plan proposal to run-local artifact (default: report only)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root directory (default: current directory)",
    )
    parser.add_argument(
        "--anchor-path",
        type=Path,
        help="Path to intention anchor v2 JSON (optional, auto-detects if not provided)",
    )
    parser.add_argument(
        "--gap-report-path",
        type=Path,
        help="Path to gap report v1 JSON (optional, auto-detects if not provided)",
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
        workspace_root = args.workspace.resolve()
        layout = RunFileLayout(run_id=args.run_id, project_id=args.project_id)

        # Load intention anchor v2
        if args.anchor_path:
            anchor_path = args.anchor_path
        else:
            # Auto-detect from run directory
            anchor_path = layout.base_dir / "intention_v2.json"

        if not anchor_path.exists():
            print(
                f"[Plan Proposer] ERROR: Intention anchor not found: {anchor_path}",
                file=sys.stderr,
            )
            print(
                "[Plan Proposer] Create an anchor first or specify --anchor-path",
                file=sys.stderr,
            )
            return 1

        logger.info(f"Loading intention anchor from: {anchor_path}")
        anchor = IntentionAnchorV2.load_from_file(anchor_path)

        # Load gap report v1
        if args.gap_report_path:
            gap_report_path = args.gap_report_path
        else:
            # Auto-detect from run directory
            gap_report_path = layout.base_dir / "gaps" / "gap_report_v1.json"

        if not gap_report_path.exists():
            print(
                f"[Plan Proposer] ERROR: Gap report not found: {gap_report_path}",
                file=sys.stderr,
            )
            print(
                "[Plan Proposer] Run gap scanner first or specify --gap-report-path",
                file=sys.stderr,
            )
            return 1

        logger.info(f"Loading gap report from: {gap_report_path}")
        gap_report = GapReportV1.load_from_file(gap_report_path)

        # Propose plan
        logger.info("Proposing plan...")
        proposal = propose_plan(
            anchor=anchor,
            gap_report=gap_report,
            workspace_root=workspace_root,
        )

        # Validate proposal
        proposal.validate_against_schema()

        # Print summary to stderr
        print(
            f"[Plan Proposer] Generated {proposal.summary.total_actions} actions "
            f"({proposal.summary.auto_approved_actions} auto-approved, "
            f"{proposal.summary.requires_approval_actions} require approval, "
            f"{proposal.summary.blocked_actions} blocked)",
            file=sys.stderr,
        )

        if args.write:
            # Write to run-local artifact
            layout.ensure_directories()

            # Create planning directory
            planning_dir = layout.base_dir / "planning"
            planning_dir.mkdir(exist_ok=True)

            plan_proposal_path = planning_dir / "plan_proposal_v1.json"
            proposal.save_to_file(plan_proposal_path)

            print(
                f"[Plan Proposer] Wrote plan proposal: {plan_proposal_path}",
                file=sys.stderr,
            )

        # Print JSON to stdout
        print(json.dumps(proposal.to_json_dict(), indent=2, ensure_ascii=False))

        return 0

    except Exception as e:
        logger.exception("Plan proposer failed")
        print(f"[Plan Proposer] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
