"""
Add execution_checkpoints table for Storage Optimizer (BUILD-152).

This migration creates the execution_checkpoints table for tracking:
- SHA256-based idempotency (prevent re-deleting same files)
- Execution audit trail (timestamps, errors, lock types)
- Retry tracking (retry attempts and lock classification)

Compatible with both SQLite and PostgreSQL.

Usage:
    # SQLite (local development)
    PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/add_execution_checkpoints.py

    # PostgreSQL (production)
    PYTHONUTF8=1 DATABASE_URL="postgresql://..." python scripts/migrations/add_execution_checkpoints.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from sqlalchemy import text
from autopack.database import SessionLocal, engine


def check_database_type():
    """Check if we're using SQLite or PostgreSQL."""
    db_url = os.getenv("DATABASE_URL", "sqlite:///autopack.db")
    if "postgresql" in db_url:
        print("✓ PostgreSQL detected")
        return "postgresql"
    elif "sqlite" in db_url:
        print("✓ SQLite detected")
        return "sqlite"
    else:
        print(f"✗ Unknown database type: {db_url}")
        return "unknown"


def table_exists(session, table_name):
    """Check if a table exists in the database."""
    db_type = check_database_type()

    if db_type == "postgresql":
        result = session.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table)"),
            {"table": table_name},
        ).scalar()
    else:  # SQLite
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :table"),
            {"table": table_name},
        ).scalar()

    return bool(result)


def create_execution_checkpoints_table(session, db_type):
    """Create execution_checkpoints table."""

    if db_type == "postgresql":
        # PostgreSQL version with TIMESTAMPTZ and SERIAL
        session.execute(
            text(
                """
            CREATE TABLE execution_checkpoints (
                id SERIAL PRIMARY KEY,
                run_id TEXT NOT NULL,
                candidate_id INTEGER,

                -- Action details
                action TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes BIGINT,
                sha256 TEXT,

                -- Execution result
                status TEXT NOT NULL,
                error TEXT,

                -- Lock handling (BUILD-152)
                lock_type TEXT,
                retry_count INTEGER DEFAULT 0,

                -- Timing
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """
            )
        )

        # Create indexes
        session.execute(
            text("CREATE INDEX idx_execution_checkpoints_run_id ON execution_checkpoints(run_id)")
        )
        session.execute(
            text(
                "CREATE INDEX idx_execution_checkpoints_candidate_id ON execution_checkpoints(candidate_id)"
            )
        )
        session.execute(
            text("CREATE INDEX idx_execution_checkpoints_sha256 ON execution_checkpoints(sha256)")
        )
        session.execute(
            text(
                "CREATE INDEX idx_execution_checkpoints_timestamp ON execution_checkpoints(timestamp DESC)"
            )
        )
        session.execute(
            text("CREATE INDEX idx_execution_checkpoints_status ON execution_checkpoints(status)")
        )

    else:  # SQLite
        # SQLite version with INTEGER PRIMARY KEY AUTOINCREMENT
        session.execute(
            text(
                """
            CREATE TABLE execution_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                candidate_id INTEGER,

                -- Action details
                action TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes BIGINT,
                sha256 TEXT,

                -- Execution result
                status TEXT NOT NULL,
                error TEXT,

                -- Lock handling (BUILD-152)
                lock_type TEXT,
                retry_count INTEGER DEFAULT 0,

                -- Timing
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
            )
        )

        # Create indexes
        session.execute(
            text("CREATE INDEX idx_execution_checkpoints_run_id ON execution_checkpoints(run_id)")
        )
        session.execute(
            text(
                "CREATE INDEX idx_execution_checkpoints_candidate_id ON execution_checkpoints(candidate_id)"
            )
        )
        session.execute(
            text("CREATE INDEX idx_execution_checkpoints_sha256 ON execution_checkpoints(sha256)")
        )
        session.execute(
            text(
                "CREATE INDEX idx_execution_checkpoints_timestamp ON execution_checkpoints(timestamp DESC)"
            )
        )
        session.execute(
            text("CREATE INDEX idx_execution_checkpoints_status ON execution_checkpoints(status)")
        )

    session.commit()
    print("  ✓ Created execution_checkpoints table")
    print("  ✓ Created 5 indexes (run_id, candidate_id, sha256, timestamp, status)")


def main():
    print("=" * 80)
    print("BUILD-152: Add execution_checkpoints table")
    print("=" * 80)
    print()

    db_type = check_database_type()

    if db_type == "unknown":
        print("\n✗ Cannot determine database type")
        return 1

    session = SessionLocal()

    try:
        # Check if table already exists
        if table_exists(session, "execution_checkpoints"):
            print("\n✓ execution_checkpoints table already exists (migration already applied)")
            return 0

        print("\nCreating execution_checkpoints table...")
        create_execution_checkpoints_table(session, db_type)

        print("\n" + "=" * 80)
        print("✅ Migration complete!")
        print("=" * 80)
        print("\nNext steps:")
        print("  1. Checkpoint logger will now use PostgreSQL for execution tracking")
        print("  2. Idempotency: Deleted files won't be re-suggested in future scans")
        print("  3. Audit trail: Query execution_checkpoints for debugging")
        print("\nExample query:")
        print(
            "  SELECT * FROM execution_checkpoints WHERE status = 'failed' ORDER BY timestamp DESC LIMIT 10;"
        )

        return 0

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        session.rollback()
        import traceback

        traceback.print_exc()
        return 1

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
