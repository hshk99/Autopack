"""Detect and remediate stale QUEUED phases.

A phase is considered "stale" if:
1. It has been in QUEUED state for longer than a threshold (default: 30 minutes)
2. There is no active executor process working on it
3. The phase hasn't been updated recently

Remediation options:
- --mark-failed: Automatically mark stale phases as FAILED
- --report-only: Just report stale phases without taking action (default)
- --max-age-minutes: Threshold for considering a phase stale (default: 30)

Usage:
    # Report stale queued phases
    PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack.db" python scripts/detect_stale_queued.py

    # Mark stale phases as FAILED after 60 minutes
    PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack.db" python scripts/detect_stale_queued.py \\
        --mark-failed --max-age-minutes 60
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Tuple

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState


def detect_stale_queued_phases(
    session,
    max_age_minutes: int = 30
) -> List[Tuple[Phase, int]]:
    """Detect phases that have been QUEUED for too long.

    Args:
        session: Database session
        max_age_minutes: Maximum age in minutes before considering a phase stale

    Returns:
        List of (phase, age_in_minutes) tuples for stale phases
    """
    queued_phases = session.query(Phase).filter(Phase.state == PhaseState.QUEUED).all()

    if not queued_phases:
        return []

    now = datetime.now(timezone.utc)
    threshold = timedelta(minutes=max_age_minutes)
    stale_phases = []

    for phase in queued_phases:
        # Use updated_at if available, otherwise created_at
        last_modified = phase.updated_at or phase.created_at

        if last_modified is None:
            # If no timestamp, assume it's fresh (defensive)
            continue

        # Ensure timezone-aware comparison
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)

        age = now - last_modified

        if age > threshold:
            age_minutes = int(age.total_seconds() / 60)
            stale_phases.append((phase, age_minutes))

    return stale_phases


def mark_phase_as_failed(
    session,
    phase: Phase,
    reason: str
):
    """Mark a stale QUEUED phase as FAILED.

    Args:
        session: Database session
        phase: Phase to mark as failed
        reason: Reason for marking as failed
    """
    phase.state = PhaseState.FAILED

    # Update failure reason to indicate stale detection
    if phase.last_failure_reason:
        phase.last_failure_reason = f"[STALE-QUEUED] {reason}; Original: {phase.last_failure_reason}"
    else:
        phase.last_failure_reason = f"[STALE-QUEUED] {reason}"

    phase.updated_at = datetime.now(timezone.utc)
    session.commit()


def format_stale_report(
    stale_phases: List[Tuple[Phase, int]]
) -> str:
    """Format a report of stale queued phases.

    Args:
        stale_phases: List of (phase, age_in_minutes) tuples

    Returns:
        Formatted report string
    """
    if not stale_phases:
        return "No stale QUEUED phases detected."

    lines = [
        f"{'='*70}",
        f"STALE QUEUED PHASES DETECTED: {len(stale_phases)}",
        f"{'='*70}",
        ""
    ]

    # Group by run_id
    by_run = {}
    for phase, age_minutes in stale_phases:
        if phase.run_id not in by_run:
            by_run[phase.run_id] = []
        by_run[phase.run_id].append((phase, age_minutes))

    for run_id, phases in sorted(by_run.items()):
        lines.append(f"\nRun: {run_id}")
        lines.append(f"  Stale phases: {len(phases)}")

        for phase, age_minutes in sorted(phases, key=lambda x: x[1], reverse=True):
            hours = age_minutes // 60
            mins = age_minutes % 60

            age_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            lines.append(f"    - {phase.phase_id:40s} (queued for {age_str})")

    lines.extend([
        "",
        f"{'='*70}",
        "RECOMMENDATIONS",
        f"{'='*70}",
        "",
        "1. Check if there are any stuck executor processes:",
        "   - Look for hung API servers or drain_one_phase processes",
        "   - Check .autonomous_runs/ for active session directories",
        "",
        "2. Mark stale phases as FAILED to unblock the queue:",
        "   python scripts/detect_stale_queued.py --mark-failed",
        "",
        "3. Or drain them individually to attempt completion:",
        "   python scripts/drain_queued_phases.py --run-id <run_id>",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect and remediate stale QUEUED phases"
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=30,
        help="Maximum age in minutes before considering a phase stale (default: 30)"
    )
    parser.add_argument(
        "--mark-failed",
        action="store_true",
        help="Automatically mark stale phases as FAILED (default: report only)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        default=True,
        help="Only report stale phases without taking action (default)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.max_age_minutes < 1:
        print("Error: --max-age-minutes must be at least 1")
        return 1

    session = SessionLocal()

    try:
        print(f"[stale-detect] Scanning for QUEUED phases older than {args.max_age_minutes} minutes...")
        print()

        stale_phases = detect_stale_queued_phases(session, args.max_age_minutes)

        # Generate report
        report = format_stale_report(stale_phases)
        print(report)

        # Take action if requested
        if args.mark_failed and stale_phases:
            print()
            print(f"{'='*70}")
            print(f"MARKING {len(stale_phases)} STALE PHASES AS FAILED")
            print(f"{'='*70}")
            print()

            for phase, age_minutes in stale_phases:
                reason = f"Phase queued for {age_minutes} minutes with no progress"
                print(f"  Marking {phase.run_id}/{phase.phase_id} as FAILED...")
                mark_phase_as_failed(session, phase, reason)

            print()
            print(f"[stale-detect] Successfully marked {len(stale_phases)} phases as FAILED")
            print()
            print("These phases can now be re-attempted via batch drain controller:")
            print("  python scripts/batch_drain_controller.py --batch-size 10")

        return 0 if not stale_phases else 2  # Exit code 2 indicates stale phases found

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
