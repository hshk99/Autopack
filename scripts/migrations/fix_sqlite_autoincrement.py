"""
Fix SQLite auto-increment for storage optimizer tables.

The tables were created with PostgreSQL SERIAL syntax which doesn't work in SQLite.
This migration recreates the tables with proper INTEGER PRIMARY KEY AUTOINCREMENT.

Usage:
    PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/fix_sqlite_autoincrement.py
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
        print("✓ PostgreSQL detected - no migration needed (SERIAL is correct)")
        return "postgresql"
    elif "sqlite" in db_url:
        print("⚠ SQLite detected - migration needed (SERIAL → INTEGER PRIMARY KEY AUTOINCREMENT)")
        return "sqlite"
    else:
        print(f"✗ Unknown database type: {db_url}")
        return "unknown"


def migrate_sqlite(force=False):
    """Recreate storage optimizer tables with SQLite-compatible syntax."""

    session = SessionLocal()

    try:
        # Check if tables exist
        result = session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('storage_scans', 'cleanup_candidates')"
            )
        ).fetchall()

        existing_tables = [row[0] for row in result]
        print(f"\nExisting tables: {existing_tables}")

        if not existing_tables:
            print("✗ No storage optimizer tables found - run add_storage_optimizer_tables.py first")
            return 1

        # Backup data if exists
        if "storage_scans" in existing_tables:
            scan_count = session.execute(text("SELECT COUNT(*) FROM storage_scans")).scalar()
            print(f"  storage_scans: {scan_count} rows")

            if scan_count > 0 and not force:
                print("\n⚠ WARNING: Existing data will be lost!")
                response = input("Continue with migration? [y/N]: ").lower()
                if response != "y":
                    print("Migration cancelled")
                    return 0
            elif scan_count > 0 and force:
                print("\n⚠ WARNING: --force flag set, dropping existing data...")

        # Drop tables in correct order (FK constraints)
        print("\nDropping existing tables...")
        if "cleanup_candidates" in existing_tables:
            session.execute(text("DROP TABLE IF EXISTS cleanup_candidates"))
            print("  ✓ Dropped cleanup_candidates")

        if "storage_scans" in existing_tables:
            session.execute(text("DROP TABLE IF EXISTS storage_scans"))
            print("  ✓ Dropped storage_scans")

        session.commit()

        # Create tables with SQLite-compatible syntax
        print("\nCreating tables with INTEGER PRIMARY KEY AUTOINCREMENT...")

        # storage_scans table
        session.execute(
            text(
                """
            CREATE TABLE storage_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                scan_type VARCHAR(20) NOT NULL,
                scan_target VARCHAR(500) NOT NULL,
                max_depth INTEGER,
                max_items INTEGER,
                policy_version VARCHAR(50),

                total_items_scanned INTEGER NOT NULL,
                total_size_bytes BIGINT NOT NULL,
                cleanup_candidates_count INTEGER NOT NULL,
                potential_savings_bytes BIGINT NOT NULL,

                scan_duration_seconds INTEGER,

                created_by VARCHAR(100),
                notes TEXT
            )
        """
            )
        )
        print("  ✓ Created storage_scans")

        # Create indexes
        session.execute(
            text("CREATE INDEX idx_storage_scans_timestamp ON storage_scans(timestamp DESC)")
        )
        session.execute(
            text(
                "CREATE INDEX idx_storage_scans_type_target ON storage_scans(scan_type, scan_target)"
            )
        )
        print("  ✓ Created indexes for storage_scans")

        # cleanup_candidates table
        session.execute(
            text(
                """
            CREATE TABLE cleanup_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL REFERENCES storage_scans(id) ON DELETE CASCADE,

                path TEXT NOT NULL,
                size_bytes BIGINT NOT NULL,
                age_days INTEGER,
                last_modified DATETIME,

                category VARCHAR(50) NOT NULL,
                reason TEXT NOT NULL,
                requires_approval BOOLEAN NOT NULL,

                approval_status VARCHAR(20) DEFAULT 'pending',
                approved_by VARCHAR(100),
                approved_at DATETIME,
                rejection_reason TEXT,

                execution_status VARCHAR(20),
                executed_at DATETIME,
                execution_error TEXT,

                compressed BOOLEAN DEFAULT 0,
                compressed_path TEXT,
                compression_ratio DECIMAL(5, 2),
                compression_duration_seconds INTEGER,

                user_feedback TEXT,
                learned_rule_id INTEGER REFERENCES learned_rules(id)
            )
        """
            )
        )
        print("  ✓ Created cleanup_candidates")

        # Create indexes
        session.execute(
            text("CREATE INDEX idx_cleanup_candidates_scan_id ON cleanup_candidates(scan_id)")
        )
        session.execute(
            text("CREATE INDEX idx_cleanup_candidates_category ON cleanup_candidates(category)")
        )
        session.execute(
            text(
                "CREATE INDEX idx_cleanup_candidates_approval_status ON cleanup_candidates(approval_status)"
            )
        )
        session.execute(
            text("CREATE INDEX idx_cleanup_candidates_size ON cleanup_candidates(size_bytes DESC)")
        )
        print("  ✓ Created indexes for cleanup_candidates")

        session.commit()

        print("\n✅ Migration complete!")
        print("\nNext steps:")
        print("  1. Run a scan with --save-to-db to test")
        print("  2. Verify database persistence works")

        return 0

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        session.rollback()
        return 1
    finally:
        session.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix SQLite auto-increment for storage optimizer tables"
    )
    parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt (drops existing data)"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("STORAGE OPTIMIZER - SQLite Auto-Increment Fix")
    print("=" * 80)

    db_type = check_database_type()

    if db_type == "postgresql":
        print("\nNo migration needed - PostgreSQL uses SERIAL correctly")
        return 0
    elif db_type == "sqlite":
        return migrate_sqlite(force=args.force)
    else:
        print("\n✗ Cannot determine database type")
        return 1


if __name__ == "__main__":
    sys.exit(main())
