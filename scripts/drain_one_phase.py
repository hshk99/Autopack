"""
Drain a single specific phase by run_id and phase_id.

Used by batch_drain_controller.py for targeted phase draining.

Usage:
  python scripts/drain_one_phase.py --run-id <RUN_ID> --phase-id <PHASE_ID>
"""

from __future__ import annotations

import argparse
import os
import sys
import socket
from pathlib import Path

# Default DATABASE_URL to local SQLite
if not os.environ.get("DATABASE_URL"):
    _default_db_path = Path("autopack.db")
    if _default_db_path.exists():
        os.environ["DATABASE_URL"] = "sqlite:///autopack.db"

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
from autopack.autonomous_executor import AutonomousExecutor


def _pick_free_local_port() -> int:
    """Pick a free TCP port on localhost."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main() -> int:
    p = argparse.ArgumentParser(description="Drain a single phase")
    p.add_argument("--run-id", required=True, help="Run ID")
    p.add_argument("--phase-id", required=True, help="Phase ID")
    p.add_argument(
        "--run-type",
        choices=["project_build", "autopack_maintenance", "autopack_upgrade", "self_repair"],
        default=os.environ.get("AUTOPACK_RUN_TYPE", "project_build"),
    )
    p.add_argument("--no-dual-auditor", action="store_true")

    args = p.parse_args()

    # Enable Qdrant autostart
    os.environ.setdefault("AUTOPACK_QDRANT_AUTOSTART", "1")

    # Check phase exists and is in a drainable state
    db = SessionLocal()
    try:
        phase = db.query(Phase).filter(
            Phase.run_id == args.run_id,
            Phase.phase_id == args.phase_id
        ).first()

        if not phase:
            print(f"Error: Phase not found: {args.run_id} / {args.phase_id}", file=sys.stderr)
            return 1

        if phase.state not in (PhaseState.QUEUED, PhaseState.FAILED):
            print(f"Warning: Phase state is {phase.state.value}, not QUEUED or FAILED")
            # Continue anyway - executor might still be able to retry it

    finally:
        db.close()

    # Use free port to avoid conflicts
    port = _pick_free_local_port()
    os.environ["AUTOPACK_API_URL"] = f"http://localhost:{port}"

    print(f"[drain_one_phase] Draining: {args.run_id} / {args.phase_id}")
    print(f"[drain_one_phase] Using API port: {port}")
    print()

    # Create executor and drain single phase
    executor = AutonomousExecutor(
        workspace=str(Path.cwd()),
        run_type=args.run_type,
        api_url=f"http://localhost:{port}",
        enable_dual_auditor=not args.no_dual_auditor,
    )

    try:
        # Execute a single iteration targeting this specific phase
        # The executor will pick up QUEUED/FAILED phases from the run
        executor.execute_run(
            run_id=args.run_id,
            max_iterations=1,  # Only one phase
            stop_on_first_failure=False,
        )

        # Check final state
        db = SessionLocal()
        try:
            phase = db.query(Phase).filter(
                Phase.run_id == args.run_id,
                Phase.phase_id == args.phase_id
            ).first()

            if phase:
                final_state = phase.state.value
                print(f"\n[drain_one_phase] Final state: {final_state}")

                if final_state == PhaseState.COMPLETE.value:
                    return 0
                else:
                    print(f"[drain_one_phase] Phase did not complete successfully")
                    if phase.last_failure_reason:
                        print(f"[drain_one_phase] Failure reason: {phase.last_failure_reason[:200]}")
                    return 1
            else:
                print("[drain_one_phase] Warning: Phase not found after execution", file=sys.stderr)
                return 1

        finally:
            db.close()

    except KeyboardInterrupt:
        print("\n[drain_one_phase] Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n[drain_one_phase] Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
