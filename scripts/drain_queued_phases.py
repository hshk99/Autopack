"""
Drain queued phases for a given run_id in safe batches.

Why:
- Large backlogs (e.g., 160 queued phases) are best processed in batches to avoid long-running
  single processes and to make failures/resume behavior predictable.

Behavior:
- Runs the executor in repeated batches (--max-iterations N).
- Optionally stops on first failure for the first batch to catch systemic misconfig early.
- Prints progress and exits cleanly when no more QUEUED phases remain.

Usage (Windows PowerShell):
  python scripts/drain_queued_phases.py --run-id <RUN_ID> --batch-size 25

Optional:
  python scripts/drain_queued_phases.py --run-id <RUN_ID> --batch-size 5 --stop-on-first-failure
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import socket
from pathlib import Path

# Ensure src/ is importable when running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal  # noqa: E402
from autopack.models import Phase, PhaseState  # noqa: E402
from autopack.autonomous_executor import AutonomousExecutor  # noqa: E402


def _count_phases(db, run_id: str) -> tuple[int, int, int]:
    queued = db.query(Phase).filter(Phase.run_id == run_id, Phase.state == PhaseState.QUEUED).count()
    complete = db.query(Phase).filter(Phase.run_id == run_id, Phase.state == PhaseState.COMPLETE).count()
    failed = db.query(Phase).filter(Phase.run_id == run_id, Phase.state == PhaseState.FAILED).count()
    return queued, complete, failed


def _pick_free_local_port() -> int:
    """Pick a free TCP port on localhost.

    We use this to avoid accidentally connecting to an already-running Autopack API
    that may be pointing at a different DATABASE_URL than the drain script.
    """
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
    p = argparse.ArgumentParser(description="Drain queued phases for an Autopack run in batches")
    p.add_argument("--run-id", required=True)
    p.add_argument("--batch-size", type=int, default=25)
    p.add_argument("--poll-seconds", type=int, default=2)
    p.add_argument("--stop-on-first-failure", action="store_true")
    p.add_argument("--max-batches", type=int, default=None, help="Optional cap for number of batches")
    p.add_argument(
        "--run-type",
        choices=["project_build", "autopack_maintenance", "autopack_upgrade", "self_repair"],
        default=os.environ.get("AUTOPACK_RUN_TYPE", "project_build"),
        help=(
            "Run type passed to the AutonomousExecutor. "
            "Use autopack_maintenance for draining Autopack-internal phases that modify src/autopack/."
        ),
    )
    p.add_argument(
        "--no-dual-auditor",
        action="store_true",
        help="Disable dual auditor mode to reduce LLM calls during draining/triage.",
    )

    args = p.parse_args()

    # Autopack is supposed to be autonomous; enable Qdrant autostart by default if operator didn't set it.
    os.environ.setdefault("AUTOPACK_QDRANT_AUTOSTART", "1")

    # IMPORTANT: The executor selects phases via the Supervisor API (BUILD-115), but this script
    # counts queued phases via the local DB. If we accidentally connect to an already-running API
    # pointed at a different DATABASE_URL, the executor may see "no executable phases" even when
    # the local DB shows queued work. To prevent that, default to a fresh, free localhost port
    # unless the operator explicitly set AUTOPACK_API_URL.
    if not os.environ.get("AUTOPACK_API_URL"):
        port = _pick_free_local_port()
        os.environ["AUTOPACK_API_URL"] = f"http://localhost:{port}"
        print(f"[drain] AUTOPACK_API_URL not set; using ephemeral API URL: {os.environ['AUTOPACK_API_URL']}")

    db = SessionLocal()
    try:
        batch = 0
        while True:
            batch += 1
            queued, complete, failed = _count_phases(db, args.run_id)
            print(f"[drain] run_id={args.run_id} queued={queued} complete={complete} failed={failed}")
            if queued == 0:
                print("[drain] No queued phases remain. Done.")
                return 0

            if args.max_batches is not None and batch > args.max_batches:
                print(f"[drain] Reached max-batches={args.max_batches}. Exiting.")
                return 0

            # Run one batch
            print(f"[drain] Starting batch {batch} (max-iterations={args.batch_size})...")
            executor = AutonomousExecutor(
                run_id=args.run_id,
                workspace=Path("."),
                api_url=os.environ.get("AUTOPACK_API_URL", "http://localhost:8000"),
                run_type=args.run_type,
                use_dual_auditor=not args.no_dual_auditor,
            )
            executor.run_autonomous_loop(
                poll_interval=10,
                max_iterations=args.batch_size,
                stop_on_first_failure=args.stop_on_first_failure,
            )

            # Give DB a moment to reflect state updates
            time.sleep(max(0, args.poll_seconds))

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())


