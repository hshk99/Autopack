"""IMP-DOCTOR-002: Add Doctor outcome tracking table

Creates the doctor_outcome_events table for tracking Doctor effectiveness.

This migration adds telemetry for measuring:
- Doctor recommendation success rates
- Phase outcomes after Doctor intervention
- Doctor action effectiveness by category
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import inspect, text
from autopack.database import engine, SessionLocal
from autopack.models import Base, DoctorOutcomeEvent


def table_exists(table_name: str) -> bool:
    """Check if table exists in database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate_add_doctor_outcome_table(dry_run: bool = False):
    """Add doctor_outcome_events table if it doesn't exist."""

    if table_exists("doctor_outcome_events"):
        print("✓ doctor_outcome_events table already exists, skipping migration")
        return

    if dry_run:
        print("[DRY RUN] Would create doctor_outcome_events table")
        print("\nTable schema:")
        print("  - id (primary key)")
        print("  - run_id, phase_id (foreign key to phases)")
        print("  - timestamp")
        print("  - error_category, builder_attempts")
        print("  - doctor_action, doctor_rationale, doctor_confidence")
        print("  - builder_hint_provided")
        print("  - recommendation_followed")
        print("  - phase_succeeded_after_doctor (nullable)")
        print("  - attempts_after_doctor (nullable)")
        print("  - final_phase_outcome (nullable)")
        print("  - doctor_tokens_used, model_used")
        print("\nIndexes:")
        print("  - ix_doctor_outcome_run_id")
        print("  - ix_doctor_outcome_phase_id")
        print("  - ix_doctor_outcome_action")
        print("  - ix_doctor_outcome_timestamp")
        print("  - ix_doctor_outcome_success")
        return

    print("Creating doctor_outcome_events table...")

    # Create table using SQLAlchemy model
    DoctorOutcomeEvent.__table__.create(engine, checkfirst=True)

    print("✓ Successfully created doctor_outcome_events table")

    # Verify table structure
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "SELECT COUNT(*) as count FROM information_schema.columns "
                "WHERE table_name = 'doctor_outcome_events'"
            )
        )
        column_count = result.fetchone()[0]
        print(f"✓ Table has {column_count} columns")

        # Check indexes
        result = db.execute(
            text(
                "SELECT COUNT(*) as count FROM pg_indexes "
                "WHERE tablename = 'doctor_outcome_events'"
            )
        )
        index_count = result.fetchone()[0]
        print(f"✓ Table has {index_count} indexes")

    except Exception as e:
        # Likely SQLite, skip index check
        print(f"✓ Table created (index verification skipped: {e})")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="IMP-DOCTOR-002: Add Doctor outcome tracking table"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("IMP-DOCTOR-002: Doctor Outcome Tracking Migration")
    print("=" * 60)
    print()

    try:
        migrate_add_doctor_outcome_table(dry_run=args.dry_run)
        print()
        print("✓ Migration completed successfully")

        if not args.dry_run:
            print()
            print("Next steps:")
            print("1. Ensure TELEMETRY_DB_ENABLED=true to enable tracking")
            print("2. Doctor outcomes will be recorded automatically on next run")
            print("3. Query success rates with:")
            print("   SELECT doctor_action, ")
            print("          COUNT(*) as total,")
            print(
                "          SUM(CASE WHEN phase_succeeded_after_doctor THEN 1 ELSE 0 END) as successes"
            )
            print("   FROM doctor_outcome_events")
            print("   WHERE phase_succeeded_after_doctor IS NOT NULL")
            print("   GROUP BY doctor_action")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
