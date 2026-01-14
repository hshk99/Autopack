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

# Require DATABASE_URL to be explicitly set (P0: prevent silent fallback to autopack.db)
if not os.environ.get("DATABASE_URL"):
    print("[ERROR] DATABASE_URL must be set", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage:", file=sys.stderr)
    print(
        "  DATABASE_URL='sqlite:///autopack_telemetry_seed.db' TELEMETRY_DB_ENABLED=1 \\",
        file=sys.stderr,
    )
    print(
        "    python scripts/drain_one_phase.py --run-id <RUN_ID> --phase-id <PHASE_ID>",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
from autopack.autonomous_executor import AutonomousExecutor
from autopack.db_identity import print_db_identity, add_empty_db_arg


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
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Proceed even if there are other QUEUED phases in the run (non-exclusive execution). "
            "Without --force, this script refuses to run if it cannot guarantee the target phase "
            "is the next QUEUED phase."
        ),
    )
    add_empty_db_arg(p)

    args = p.parse_args()

    # Enable Qdrant autostart
    os.environ.setdefault("AUTOPACK_QDRANT_AUTOSTART", "1")

    # Print DB identity (no empty check - drain_one_phase is a targeted operation)
    db = SessionLocal()
    try:
        print_db_identity(db)
        phase = (
            db.query(Phase)
            .filter(Phase.run_id == args.run_id, Phase.phase_id == args.phase_id)
            .first()
        )

        if not phase:
            print(f"Error: Phase not found: {args.run_id} / {args.phase_id}", file=sys.stderr)
            return 1

        initial_state = phase.state.value if phase.state else "UNKNOWN"

        if phase.state == PhaseState.FAILED:
            print(
                f"[drain_one_phase] Re-queueing FAILED phase -> QUEUED: {args.run_id} / {args.phase_id}"
            )
            phase.state = PhaseState.QUEUED
            # Keep last_failure_reason for context; the executor will update it on re-failure.
            db.commit()
            db.refresh(phase)

        if phase.state != PhaseState.QUEUED:
            print(
                f"[drain_one_phase] Refusing to drain: phase state is {phase.state.value}, not QUEUED.",
                file=sys.stderr,
            )
            return 2

        queued_in_run = (
            db.query(Phase)
            .filter(Phase.run_id == args.run_id, Phase.state == PhaseState.QUEUED)
            .count()
        )
        if queued_in_run != 1 and not args.force:
            print(
                f"[drain_one_phase] Refusing to drain non-exclusively: run has {queued_in_run} QUEUED phases. "
                f"Use --force if you accept that the executor may run a different phase first.",
                file=sys.stderr,
            )
            return 2

    finally:
        db.close()

    # Use free port to avoid conflicts
    if not os.environ.get("AUTOPACK_API_URL"):
        port = _pick_free_local_port()
        os.environ["AUTOPACK_API_URL"] = f"http://localhost:{port}"
    else:
        port = int(os.environ["AUTOPACK_API_URL"].rsplit(":", 1)[-1])

    # B2: Print DB/API identity for observability
    db_url = os.environ.get("DATABASE_URL", "sqlite:///autopack.db (default)")
    api_url = os.environ.get("AUTOPACK_API_URL", f"http://localhost:{port}")
    print("[drain_one_phase] ===== ENVIRONMENT IDENTITY =====")
    print(f"[drain_one_phase] DATABASE_URL: {db_url}")
    print(f"[drain_one_phase] AUTOPACK_API_URL: {api_url}")
    print("[drain_one_phase] ================================")
    print(f"[drain_one_phase] Draining: {args.run_id} / {args.phase_id}")
    print()

    # Create executor and drain single phase
    executor = AutonomousExecutor(
        run_id=args.run_id,
        workspace=Path.cwd(),
        run_type=args.run_type,
        api_url=os.environ.get("AUTOPACK_API_URL", f"http://localhost:{port}"),
        use_dual_auditor=not args.no_dual_auditor,
    )

    try:
        # Execute a single iteration; with exclusivity guard above, this should drain the target phase.
        executor.run_autonomous_loop(
            poll_interval=10,
            max_iterations=1,
            stop_on_first_failure=False,
        )

        # Check final state
        db = SessionLocal()
        try:
            phase = (
                db.query(Phase)
                .filter(Phase.run_id == args.run_id, Phase.phase_id == args.phase_id)
                .first()
            )

            if phase:
                final_state = phase.state.value
                print(f"\n[drain_one_phase] Final state: {final_state}")

                if final_state == PhaseState.COMPLETE.value:
                    return 0
                else:
                    print("[drain_one_phase] Phase did not complete successfully")
                    if phase.last_failure_reason:
                        print(
                            f"[drain_one_phase] Failure reason: {phase.last_failure_reason[:200]}"
                        )
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
