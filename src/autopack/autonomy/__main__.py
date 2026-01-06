"""Autopilot CLI entry point.

Usage:
    python -m autopack.autonomy --run-id RUN_ID --project-id PROJECT_ID [--enable] [--write]

Examples:
    # Report only (dry-run, disabled by default):
    python -m autopack.autonomy --run-id test-run-001 --project-id autopack

    # Enable autopilot and execute auto-approved actions:
    python -m autopack.autonomy --run-id test-run-001 --project-id autopack --enable --write
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .autopilot import AutopilotController
from ..file_layout import RunFileLayout
from ..intention_anchor.v2 import IntentionAnchorV2

logger = logging.getLogger(__name__)


def main() -> int:
    """CLI entry point for autopilot controller.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        description="Autopilot controller - autonomous execution with safe gates",
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
        "--enable",
        action="store_true",
        help="REQUIRED: Explicitly enable autopilot execution (default: OFF)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write autopilot session to run-local artifact (default: report only)",
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
                f"[Autopilot] ERROR: Intention anchor not found: {anchor_path}",
                file=sys.stderr,
            )
            print(
                "[Autopilot] Create an anchor first or specify --anchor-path",
                file=sys.stderr,
            )
            return 1

        logger.info(f"Loading intention anchor from: {anchor_path}")
        anchor = IntentionAnchorV2.load_from_file(anchor_path)

        # Check if autopilot is enabled
        if not args.enable:
            print(
                "[Autopilot] WARNING: Autopilot is DISABLED by default.",
                file=sys.stderr,
            )
            print(
                "[Autopilot] This is a dry-run. No actions will be executed.",
                file=sys.stderr,
            )
            print(
                "[Autopilot] Use --enable to explicitly enable autonomous execution.",
                file=sys.stderr,
            )
            print("", file=sys.stderr)

        # Create controller
        controller = AutopilotController(
            workspace_root=workspace_root,
            project_id=args.project_id,
            run_id=args.run_id,
            enabled=args.enable,
        )

        # Run session
        logger.info("Starting autopilot session...")
        session = controller.run_session(anchor)

        # Print summary to stderr
        print(
            f"[Autopilot] Session {session.session_id}: {session.status}",
            file=sys.stderr,
        )

        if session.execution_summary:
            summary = session.execution_summary
            print(
                f"[Autopilot] Executed {summary.executed_actions}/{summary.total_actions} actions "
                f"({summary.successful_actions} successful, {summary.failed_actions} failed)",
                file=sys.stderr,
            )

        if session.approval_requests:
            print(
                f"[Autopilot] {len(session.approval_requests)} action(s) require approval",
                file=sys.stderr,
            )

        if args.write:
            # Write to run-local artifact
            session_path = controller.save_session()
            print(f"[Autopilot] Wrote session: {session_path}", file=sys.stderr)

        # Print JSON to stdout
        print(json.dumps(session.to_json_dict(), indent=2, ensure_ascii=False))

        return 0

    except RuntimeError as e:
        # Expected errors (e.g., autopilot disabled)
        print(f"[Autopilot] ERROR: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        logger.exception("Autopilot failed")
        print(f"[Autopilot] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
