"""
BUILD-149 Storage Optimizer Phase 2: PostgreSQL Integration

Creates tables:
- storage_scans: Scan metadata (timestamp, target, totals)
- cleanup_candidates: Files/folders eligible for cleanup
- approval_decisions: User approval/rejection records

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://user:pass@host:5432/autopack" python scripts/migrations/add_storage_optimizer_tables.py upgrade
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://user:pass@host:5432/autopack" python scripts/migrations/add_storage_optimizer_tables.py downgrade

Safety:
    - Idempotent: Can be run multiple times safely
    - Works with both PostgreSQL and SQLite
    - Uses explicit CASCADE for foreign key deletion
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Get DATABASE_URL from environment (production safety requirement)."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "DATABASE_URL environment variable not set. "
            "Example: DATABASE_URL=postgresql://user:pass@host:5432/autopack"
        )
    return db_url


def check_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def upgrade(engine: Engine) -> None:
    """Create storage optimizer tables."""
    print("=" * 70)
    print("BUILD-149 Storage Optimizer Phase 2: PostgreSQL Integration")
    print("=" * 70)

    with engine.begin() as conn:
        # Check idempotency
        if check_table_exists(engine, "storage_scans"):
            print("\n✓ Storage optimizer tables already exist, skipping migration")
            print("  (Tables: storage_scans, cleanup_candidates, approval_decisions)")
            return

        print("\n[1/3] Creating table: storage_scans")
        conn.execute(
            text("""
            CREATE TABLE storage_scans (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                scan_type VARCHAR(20) NOT NULL,
                scan_target VARCHAR(500) NOT NULL,
                max_depth INTEGER,
                max_items INTEGER,
                policy_version VARCHAR(50),

                total_items_scanned INTEGER NOT NULL,
                total_size_bytes BIGINT NOT NULL,
                cleanup_candidates_count INTEGER NOT NULL DEFAULT 0,
                potential_savings_bytes BIGINT NOT NULL DEFAULT 0,

                scan_duration_seconds INTEGER,

                created_by VARCHAR(100),
                notes TEXT
            )
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_storage_scans_timestamp
            ON storage_scans(timestamp DESC)
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_storage_scans_type_target
            ON storage_scans(scan_type, scan_target)
        """)
        )

        print("      ✓ Table 'storage_scans' created with 2 indexes")

        print("\n[2/3] Creating table: cleanup_candidates")
        conn.execute(
            text("""
            CREATE TABLE cleanup_candidates (
                id SERIAL PRIMARY KEY,
                scan_id INTEGER NOT NULL REFERENCES storage_scans(id) ON DELETE CASCADE,

                path TEXT NOT NULL,
                size_bytes BIGINT NOT NULL,
                age_days INTEGER,
                last_modified TIMESTAMP,

                category VARCHAR(50) NOT NULL,
                reason TEXT NOT NULL,
                requires_approval BOOLEAN NOT NULL,

                approval_status VARCHAR(20) DEFAULT 'pending',
                approved_by VARCHAR(100),
                approved_at TIMESTAMP,
                rejection_reason TEXT,

                execution_status VARCHAR(20),
                executed_at TIMESTAMP,
                execution_error TEXT,

                compressed BOOLEAN DEFAULT FALSE,
                compressed_path TEXT,
                compression_ratio DECIMAL(5, 2),
                compression_duration_seconds INTEGER
            )
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_cleanup_candidates_scan_id
            ON cleanup_candidates(scan_id)
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_cleanup_candidates_category
            ON cleanup_candidates(category)
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_cleanup_candidates_approval_status
            ON cleanup_candidates(approval_status)
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_cleanup_candidates_size
            ON cleanup_candidates(size_bytes DESC)
        """)
        )

        print("      ✓ Table 'cleanup_candidates' created with 4 indexes")

        print("\n[3/3] Creating table: approval_decisions")
        conn.execute(
            text("""
            CREATE TABLE approval_decisions (
                id SERIAL PRIMARY KEY,
                scan_id INTEGER NOT NULL REFERENCES storage_scans(id) ON DELETE CASCADE,

                approved_by VARCHAR(100) NOT NULL,
                approved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                approval_method VARCHAR(50),

                total_candidates INTEGER NOT NULL,
                total_size_bytes BIGINT NOT NULL,

                decision VARCHAR(20) NOT NULL,
                notes TEXT
            )
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_approval_decisions_scan_id
            ON approval_decisions(scan_id)
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX idx_approval_decisions_approved_at
            ON approval_decisions(approved_at DESC)
        """)
        )

        print("      ✓ Table 'approval_decisions' created with 2 indexes")


def downgrade(engine: Engine) -> None:
    """Drop storage optimizer tables (reverse of upgrade)."""
    print("=" * 70)
    print("BUILD-149 Storage Optimizer Phase 2 Rollback")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if tables exist
        if not check_table_exists(engine, "storage_scans"):
            print("\n✓ Storage optimizer tables already removed, nothing to rollback")
            return

        print("\n[1/3] Dropping table: approval_decisions")
        conn.execute(text("DROP TABLE IF EXISTS approval_decisions CASCADE"))
        print("      ✓ Table 'approval_decisions' dropped")

        print("\n[2/3] Dropping table: cleanup_candidates")
        conn.execute(text("DROP TABLE IF EXISTS cleanup_candidates CASCADE"))
        print("      ✓ Table 'cleanup_candidates' dropped")

        print("\n[3/3] Dropping table: storage_scans")
        conn.execute(text("DROP TABLE IF EXISTS storage_scans CASCADE"))
        print("      ✓ Table 'storage_scans' dropped")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python add_storage_optimizer_tables.py [upgrade|downgrade]")
        print("\nExample:")
        print('  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \\')
        print("    python scripts/migrations/add_storage_optimizer_tables.py upgrade")
        sys.exit(1)

    command = sys.argv[1].lower()
    if command not in ["upgrade", "downgrade"]:
        print(f"Error: Invalid command '{command}'. Must be 'upgrade' or 'downgrade'.")
        sys.exit(1)

    try:
        db_url = get_database_url()
        # Mask password in output for security
        safe_url = db_url.split("@")[1] if "@" in db_url else db_url
        print(f"\nDatabase: ...@{safe_url}")

        engine = create_engine(db_url)

        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        print("✓ Database connection successful")

        if command == "upgrade":
            upgrade(engine)
        else:
            downgrade(engine)

        print("\n" + "=" * 70)
        print("✓ Migration completed successfully")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
