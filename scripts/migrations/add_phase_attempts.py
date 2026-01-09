"""
BUILD-041: Database Migration - Add Attempt Tracking to Phases Table

Adds four columns to support database-backed state persistence:
- attempts_used: Current attempt count
- max_attempts: Maximum attempts allowed
- last_attempt_timestamp: When last attempt occurred
- last_failure_reason: Most recent failure status

This enables the executor to track phase retry state in the database
instead of instance attributes, fixing the infinite failure loop bug.

Usage:
    python scripts/migrations/add_phase_attempts.py upgrade
    python scripts/migrations/add_phase_attempts.py downgrade
"""

import os
import sys

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Get DATABASE_URL from environment"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return db_url


def check_column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade(engine: Engine) -> None:
    """Add attempt tracking columns to phases table"""
    print("=" * 60)
    print("BUILD-041 Migration: Add Phase Attempt Tracking Columns")
    print("=" * 60)

    with engine.begin() as conn:
        # Check if columns already exist
        if check_column_exists(engine, "phases", "attempts_used"):
            print("✓ Column 'attempts_used' already exists, skipping migration")
            return

        print("\n[1/5] Adding column: attempts_used (Integer, default=0)")
        conn.execute(text("""
            ALTER TABLE phases
            ADD COLUMN attempts_used INTEGER NOT NULL DEFAULT 0
        """))
        print("      ✓ Column 'attempts_used' added")

        print("\n[2/5] Adding column: max_attempts (Integer, default=5)")
        conn.execute(text("""
            ALTER TABLE phases
            ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5
        """))
        print("      ✓ Column 'max_attempts' added")

        print("\n[3/5] Adding column: last_attempt_timestamp (DateTime, nullable)")
        conn.execute(text("""
            ALTER TABLE phases
            ADD COLUMN last_attempt_timestamp TIMESTAMP WITH TIME ZONE
        """))
        print("      ✓ Column 'last_attempt_timestamp' added")

        print("\n[4/5] Adding column: last_failure_reason (String, nullable)")
        conn.execute(text("""
            ALTER TABLE phases
            ADD COLUMN last_failure_reason VARCHAR
        """))
        print("      ✓ Column 'last_failure_reason' added")

        print("\n[5/5] Creating index: idx_phase_executable")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_phase_executable
            ON phases (run_id, state, attempts_used)
        """))
        print("      ✓ Index 'idx_phase_executable' created")

        # Verify existing phases have correct defaults
        result = conn.execute(text("SELECT COUNT(*) FROM phases"))
        phase_count = result.scalar()

        print("\n✓ Migration complete!")
        print(f"  - {phase_count} existing phases have been updated with defaults:")
        print("    - attempts_used = 0")
        print("    - max_attempts = 5")
        print("    - last_attempt_timestamp = NULL")
        print("    - last_failure_reason = NULL")

    print("\n" + "=" * 60)
    print("BUILD-041 Migration: SUCCESS")
    print("=" * 60)


def downgrade(engine: Engine) -> None:
    """Remove attempt tracking columns from phases table"""
    print("=" * 60)
    print("BUILD-041 Rollback: Remove Phase Attempt Tracking Columns")
    print("=" * 60)

    with engine.begin() as conn:
        # Check if columns exist before trying to drop
        if not check_column_exists(engine, "phases", "attempts_used"):
            print("✓ Columns already removed, nothing to rollback")
            return

        print("\n[1/5] Dropping index: idx_phase_executable")
        conn.execute(text("DROP INDEX IF EXISTS idx_phase_executable"))
        print("      ✓ Index 'idx_phase_executable' dropped")

        print("\n[2/5] Dropping column: last_failure_reason")
        conn.execute(text("ALTER TABLE phases DROP COLUMN IF EXISTS last_failure_reason"))
        print("      ✓ Column 'last_failure_reason' dropped")

        print("\n[3/5] Dropping column: last_attempt_timestamp")
        conn.execute(text("ALTER TABLE phases DROP COLUMN IF EXISTS last_attempt_timestamp"))
        print("      ✓ Column 'last_attempt_timestamp' dropped")

        print("\n[4/5] Dropping column: max_attempts")
        conn.execute(text("ALTER TABLE phases DROP COLUMN IF EXISTS max_attempts"))
        print("      ✓ Column 'max_attempts' dropped")

        print("\n[5/5] Dropping column: attempts_used")
        conn.execute(text("ALTER TABLE phases DROP COLUMN IF EXISTS attempts_used"))
        print("      ✓ Column 'attempts_used' dropped")

    print("\n" + "=" * 60)
    print("BUILD-041 Rollback: SUCCESS")
    print("=" * 60)


def main():
    """Main entry point for migration script"""
    if len(sys.argv) < 2:
        print("Usage: python add_phase_attempts.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command not in ["upgrade", "downgrade"]:
        print(f"Error: Invalid command '{command}'")
        print("Usage: python add_phase_attempts.py [upgrade|downgrade]")
        sys.exit(1)

    try:
        db_url = get_database_url()
        print(f"\nConnecting to database: {db_url.split('@')[1] if '@' in db_url else 'local'}")

        engine = create_engine(db_url)

        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()

        print("✓ Database connection successful\n")

        if command == "upgrade":
            upgrade(engine)
        else:
            downgrade(engine)

        print("\n✓ Migration script completed successfully")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
