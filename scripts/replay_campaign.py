"""Replay Campaign Script - BUILD-146 P12

Re-runs previously failed runs/phases with Phase 6 features enabled,
capturing metrics and patterns for analysis.

Purpose:
- Clone failed runs with new IDs
- Enable Phase 6 features for replay
- Execute using run_parallel.py --executor api for async execution
- Generate comparison reports between original and replay
- Integrate with pattern expansion for post-replay analysis

Usage:
    # Replay specific run
    python scripts/replay_campaign.py --run-id failed-run-123

    # Replay all failed runs from date range
    python scripts/replay_campaign.py \\
        --from-date 2025-12-01 \\
        --to-date 2025-12-31 \\
        --state FAILED

    # Dry run (don't execute)
    python scripts/replay_campaign.py --state FAILED --dry-run

    # Replay with custom Phase 6 settings
    python scripts/replay_campaign.py \\
        --run-id failed-run-123 \\
        --enable-phase6-metrics \\
        --enable-consolidated-metrics
"""

import os
import sys
import json
import argparse
import asyncio
import subprocess
from datetime import datetime
from typing import List, Optional
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState


def get_database_url() -> str:
    """Get DATABASE_URL from environment with helpful error."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "="*80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print("\nSet DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\"", file=sys.stderr)
        print("  python scripts/replay_campaign.py --run-id failed-run\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"sqlite:///autopack.db\"", file=sys.stderr)
        print("  python scripts/replay_campaign.py --run-id failed-run\n", file=sys.stderr)
        sys.exit(1)
    return db_url


async def find_failed_runs(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    state: str = "FAILED"
) -> List[str]:
    """Find failed runs in date range.

    Args:
        from_date: Start date (ISO format YYYY-MM-DD)
        to_date: End date (ISO format YYYY-MM-DD)
        state: Run state filter (default: FAILED)

    Returns:
        List of run IDs
    """
    with SessionLocal() as session:
        query = session.query(Run)

        # Filter by state
        if state == "FAILED":
            query = query.filter(Run.state == RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW)
        else:
            # Allow filtering by any state
            query = query.filter(Run.state == state)

        # Filter by date range
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
            query = query.filter(Run.created_at >= from_dt)

        if to_date:
            to_dt = datetime.fromisoformat(to_date)
            query = query.filter(Run.created_at <= to_dt)

        runs = query.all()
        return [r.id for r in runs]


def clone_run(original_run_id: str, session) -> str:
    """Clone a run with new ID.

    Args:
        original_run_id: Original run ID to clone
        session: Database session

    Returns:
        New run ID for the cloned run
    """
    # Get original run
    original_run = session.query(Run).filter(Run.id == original_run_id).first()
    if not original_run:
        raise ValueError(f"Run not found: {original_run_id}")

    # Create new run ID
    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    new_run_id = f"{original_run_id}-replay-{timestamp}"

    # Clone run
    new_run = Run(
        id=new_run_id,
        state=RunState.RUN_CREATED,
        safety_profile=original_run.safety_profile,
        run_scope=original_run.run_scope,
        token_cap=original_run.token_cap,
        max_phases=original_run.max_phases,
        max_duration_minutes=original_run.max_duration_minutes,
        git_commit_sha=original_run.git_commit_sha,
        model_mapping_hash=original_run.model_mapping_hash,
    )
    session.add(new_run)
    session.flush()

    # Clone tiers
    original_tiers = session.query(Tier).filter(Tier.run_id == original_run_id).all()
    for orig_tier in original_tiers:
        new_tier = Tier(
            tier_id=orig_tier.tier_id,
            run_id=new_run_id,
            tier_number=orig_tier.tier_number,
            description=orig_tier.description,
        )
        session.add(new_tier)

    session.flush()

    # Clone phases
    original_phases = session.query(Phase).filter(Phase.run_id == original_run_id).all()
    for orig_phase in original_phases:
        new_phase = Phase(
            phase_id=orig_phase.phase_id,
            run_id=new_run_id,
            tier_id=orig_phase.tier_id,
            state=PhaseState.QUEUED,  # Reset to QUEUED for replay
            description=orig_phase.description,
            scope=orig_phase.scope,
        )
        session.add(new_phase)

    session.commit()

    print(f"✓ Cloned run: {original_run_id} → {new_run_id}")
    return new_run_id


async def execute_run(
    run_id: str,
    executor_mode: str = "api",
    enable_phase6_metrics: bool = True,
    enable_consolidated_metrics: bool = True
) -> bool:
    """Execute a run with Phase 6 features enabled.

    Args:
        run_id: Run ID to execute
        executor_mode: "api" or "local" (prefer "api" for async execution)
        enable_phase6_metrics: Enable Phase 6 P3 telemetry
        enable_consolidated_metrics: Enable consolidated metrics dashboard

    Returns:
        True if execution started successfully, False otherwise
    """
    # Set environment variables for Phase 6 features
    env = os.environ.copy()

    if enable_phase6_metrics:
        env["AUTOPACK_ENABLE_PHASE6_METRICS"] = "1"

    if enable_consolidated_metrics:
        env["AUTOPACK_ENABLE_CONSOLIDATED_METRICS"] = "1"

    # Construct command
    if executor_mode == "api":
        # Use run_parallel.py with --executor api for async execution
        cmd = [
            sys.executable,
            "scripts/run_parallel.py",
            "--executor", "api",
            "--run-id", run_id
        ]
    else:
        # Use autonomous_executor.py for local execution
        cmd = [
            sys.executable,
            "-m", "autopack.autonomous_executor",
            "--run-id", run_id
        ]

    print(f"  Executing: {' '.join(cmd)}")

    try:
        # Start subprocess in background
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        print(f"  ✓ Started execution (PID: {process.pid})")
        return True

    except Exception as e:
        print(f"  ❌ Failed to start execution: {e}")
        return False


def generate_comparison_report(original_run_id: str, replay_run_id: str):
    """Generate comparison report between original and replay.

    Args:
        original_run_id: Original run ID
        replay_run_id: Replay run ID

    Saves report to archive/replay_results/
    """
    with SessionLocal() as session:
        original = session.query(Run).filter(Run.id == original_run_id).first()
        replay = session.query(Run).filter(Run.id == replay_run_id).first()

        if not original or not replay:
            print(f"  ⚠ Cannot generate report: runs not found")
            return

        # Get phase counts
        original_phases = session.query(Phase).filter(Phase.run_id == original_run_id).all()
        replay_phases = session.query(Phase).filter(Phase.run_id == replay_run_id).all()

        original_complete = sum(1 for p in original_phases if p.state == PhaseState.COMPLETE)
        original_failed = sum(1 for p in original_phases if p.state == PhaseState.FAILED)

        replay_complete = sum(1 for p in replay_phases if p.state == PhaseState.COMPLETE)
        replay_failed = sum(1 for p in replay_phases if p.state == PhaseState.FAILED)

        report = {
            "original_run_id": original_run_id,
            "replay_run_id": replay_run_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "original": {
                "state": original.state.value,
                "tokens_used": original.tokens_used,
                "total_phases": len(original_phases),
                "phases_complete": original_complete,
                "phases_failed": original_failed,
            },
            "replay": {
                "state": replay.state.value,
                "tokens_used": replay.tokens_used,
                "total_phases": len(replay_phases),
                "phases_complete": replay_complete,
                "phases_failed": replay_failed,
            },
            "deltas": {
                "token_delta": replay.tokens_used - original.tokens_used if replay.tokens_used else None,
                "phase_complete_delta": replay_complete - original_complete,
                "phase_failed_delta": replay_failed - original_failed,
            }
        }

        # Save to archive
        output_dir = Path("archive/replay_results")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{replay_run_id}_comparison.json"
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"  ✓ Comparison report saved: {output_path}")


async def replay_run(
    run_id: str,
    executor_mode: str = "api",
    enable_phase6_metrics: bool = True,
    enable_consolidated_metrics: bool = True,
    dry_run: bool = False
) -> Optional[str]:
    """Replay a single run with Phase 6 features enabled.

    Args:
        run_id: Original run ID to replay
        executor_mode: "api" or "local" (prefer "api" for async execution)
        enable_phase6_metrics: Enable Phase 6 P3 telemetry
        enable_consolidated_metrics: Enable consolidated metrics
        dry_run: If True, don't actually execute

    Returns:
        New run ID if successful, None otherwise
    """
    print(f"\n[REPLAY] {run_id}")

    with SessionLocal() as session:
        # Clone run with new ID
        try:
            new_run_id = clone_run(run_id, session)
        except Exception as e:
            print(f"  ❌ Failed to clone run: {e}")
            return None

        if dry_run:
            print(f"  🔍 DRY RUN - Would execute: {new_run_id}")
            return new_run_id

        # Execute run
        success = await execute_run(
            new_run_id,
            executor_mode=executor_mode,
            enable_phase6_metrics=enable_phase6_metrics,
            enable_consolidated_metrics=enable_consolidated_metrics
        )

        if success:
            # Generate comparison report (will be incomplete until run finishes)
            generate_comparison_report(run_id, new_run_id)
            return new_run_id
        else:
            return None


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Replay failed runs with Phase 6 features enabled"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Specific run to replay"
    )
    parser.add_argument(
        "--from-date",
        type=str,
        help="Start date (ISO format YYYY-MM-DD)"
    )
    parser.add_argument(
        "--to-date",
        type=str,
        help="End date (ISO format YYYY-MM-DD)"
    )
    parser.add_argument(
        "--state",
        type=str,
        default="FAILED",
        help="Run state filter (default: FAILED)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't execute, just show what would be replayed"
    )
    parser.add_argument(
        "--executor",
        type=str,
        default="api",
        choices=["api", "local"],
        help="Executor mode (default: api for async execution)"
    )
    parser.add_argument(
        "--enable-phase6-metrics",
        action="store_true",
        default=True,
        help="Enable Phase 6 P3 telemetry (default: True)"
    )
    parser.add_argument(
        "--enable-consolidated-metrics",
        action="store_true",
        default=True,
        help="Enable consolidated metrics dashboard (default: True)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of runs to execute in parallel (default: 5)"
    )

    args = parser.parse_args()

    print("BUILD-146 P12: Replay Campaign")
    print("="*80)
    print()

    # Get database connection
    db_url = get_database_url()
    print(f"Database: {db_url}")
    print()

    # Collect runs to replay
    if args.run_id:
        run_ids = [args.run_id]
        print(f"Replaying specific run: {args.run_id}")
    else:
        run_ids = await find_failed_runs(args.from_date, args.to_date, args.state)
        print(f"Found {len(run_ids)} runs to replay")
        if args.from_date:
            print(f"  From date: {args.from_date}")
        if args.to_date:
            print(f"  To date: {args.to_date}")
        print(f"  State filter: {args.state}")

    print()

    if not run_ids:
        print("No runs found to replay")
        return

    if args.dry_run:
        print("🔍 DRY RUN - Would replay:")
        for run_id in run_ids:
            print(f"  - {run_id}")
        print()
        print(f"Total: {len(run_ids)} runs")
        return

    # Replay in parallel (batches)
    print(f"Replaying {len(run_ids)} runs in batches of {args.batch_size}...")
    print()

    replayed_runs = []

    for i in range(0, len(run_ids), args.batch_size):
        batch = run_ids[i:i+args.batch_size]
        print(f"Batch {i // args.batch_size + 1}: {len(batch)} runs")

        tasks = [
            replay_run(
                run_id,
                executor_mode=args.executor,
                enable_phase6_metrics=args.enable_phase6_metrics,
                enable_consolidated_metrics=args.enable_consolidated_metrics,
                dry_run=args.dry_run
            )
            for run_id in batch
        ]

        batch_results = await asyncio.gather(*tasks)
        replayed_runs.extend([r for r in batch_results if r is not None])

        # Small delay between batches
        if i + args.batch_size < len(run_ids):
            print()
            print("Waiting 5 seconds before next batch...")
            await asyncio.sleep(5)

    print()
    print("="*80)
    print(f"REPLAY CAMPAIGN COMPLETE")
    print("="*80)
    print(f"Replayed: {len(replayed_runs)} / {len(run_ids)} runs")
    print()

    if replayed_runs:
        print("Replayed run IDs:")
        for run_id in replayed_runs:
            print(f"  - {run_id}")
        print()
        print("Next steps:")
        print("1. Monitor run execution via dashboard or API")
        print("2. Review comparison reports in: archive/replay_results/")
        print("3. Run pattern expansion on replayed runs:")
        print(f"   python scripts/pattern_expansion.py --run-id {replayed_runs[0]} --generate-code")


if __name__ == "__main__":
    asyncio.run(main())
