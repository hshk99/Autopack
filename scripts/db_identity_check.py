"""
Database Identity Check

Standalone script to print DB identity and statistics without performing any operations.
Safe to run on any database - read-only.

Usage:
    # Check legacy backlog DB
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" python scripts/db_identity_check.py

    # Check telemetry seed DB
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" python scripts/db_identity_check.py
"""

import os
import sys
from pathlib import Path

# Add src to path before imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.db_identity import print_db_identity
from autopack.models import Phase, PhaseState, TokenEstimationV2Event, TokenBudgetEscalationEvent


def print_detailed_stats(session):
    """Print detailed database statistics."""

    # Phase stats
    phase_count = session.query(Phase).count()
    failed = session.query(Phase).filter(Phase.state == PhaseState.FAILED).count()
    queued = session.query(Phase).filter(Phase.state == PhaseState.QUEUED).count()
    complete = session.query(Phase).filter(Phase.state == PhaseState.COMPLETE).count()
    executing = session.query(Phase).filter(Phase.state == PhaseState.EXECUTING).count()

    print("Phase State Breakdown:")
    print(f"  COMPLETE: {complete}")
    print(f"  FAILED: {failed}")
    print(f"  QUEUED: {queued}")
    print(f"  EXECUTING: {executing}")
    print(f"  TOTAL: {phase_count}")
    print()

    # Telemetry stats
    try:
        v2_events = session.query(TokenEstimationV2Event).count()
        v2_success = session.query(TokenEstimationV2Event).filter(
            TokenEstimationV2Event.success == True
        ).count()
        v2_truncated = session.query(TokenEstimationV2Event).filter(
            TokenEstimationV2Event.truncated == True
        ).count()

        escalation_events = session.query(TokenBudgetEscalationEvent).count()

        print("Telemetry Statistics:")
        print("  TokenEstimationV2Event:")
        print(f"    Total: {v2_events}")
        print(f"    Success: {v2_success} ({v2_success / v2_events * 100:.1f}%)" if v2_events > 0 else "    Success: 0 (0.0%)")
        print(f"    Truncated: {v2_truncated} ({v2_truncated / v2_events * 100:.1f}%)" if v2_events > 0 else "    Truncated: 0 (0.0%)")
        print(f"  TokenBudgetEscalationEvent: {escalation_events}")
        print()

        # Breakdown by category and complexity
        if v2_events > 0:
            print("Breakdown by Category (success=True only):")
            from sqlalchemy import func
            category_stats = session.query(
                TokenEstimationV2Event.category,
                func.count(TokenEstimationV2Event.id)
            ).filter(
                TokenEstimationV2Event.success == True
            ).group_by(
                TokenEstimationV2Event.category
            ).all()

            for category, count in category_stats:
                print(f"  {category}: {count}")
            print()

            print("Breakdown by Complexity (success=True only):")
            complexity_stats = session.query(
                TokenEstimationV2Event.complexity,
                func.count(TokenEstimationV2Event.id)
            ).filter(
                TokenEstimationV2Event.success == True
            ).group_by(
                TokenEstimationV2Event.complexity
            ).all()

            for complexity, count in complexity_stats:
                print(f"  {complexity}: {count}")
            print()

    except Exception as e:
        print(f"Telemetry Statistics: Error querying telemetry tables ({e})")
        print()


def main():
    """Main entry point."""

    # Check DATABASE_URL is set
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL environment variable not set")
        print()
        print("Examples:")
        print("  DATABASE_URL='sqlite:///autopack_legacy.db' python scripts/db_identity_check.py")
        print("  DATABASE_URL='sqlite:///autopack_telemetry_seed.db' python scripts/db_identity_check.py")
        return 1

    session = SessionLocal()
    try:
        print_db_identity(session)
        print_detailed_stats(session)

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_trace()
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
