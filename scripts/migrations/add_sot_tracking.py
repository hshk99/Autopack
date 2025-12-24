"""
BUILD-129 Phase 3 P3: Database Migration - Add SOT File Tracking to Token Telemetry

Adds SOT (Source of Truth) file tracking columns to token_estimation_v2_events table:
- is_sot_file: Boolean flag for SOT file updates (BUILD_LOG.md, BUILD_HISTORY.md, etc.)
- sot_file_name: String basename of SOT file being updated
- sot_entry_count_hint: Integer proxy for number of entries to write

These fields enable:
1. Specialized estimation for SOT files (different from regular docs)
2. Tracking SOT-specific estimation accuracy
3. Refinement of SOT estimation model (context + entries + overhead)

SOT files showed 84.2% SMAPE with DOC_SYNTHESIS model because they require:
- Global context reconstruction (repo/run state)
- Structured ledger output (not narrative)
- Cost scaling with entries (not investigation depth)

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/add_sot_tracking.py upgrade
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/add_sot_tracking.py downgrade
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
    """Add SOT file tracking columns to token_estimation_v2_events table"""
    print("=" * 70)
    print("BUILD-129 Phase 3 P3: Add SOT File Tracking Columns")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if columns already exist
        if check_column_exists(engine, "token_estimation_v2_events", "is_sot_file"):
            print("✓ SOT tracking columns already exist, skipping migration")
            return

        print("\n[1/3] Adding column: is_sot_file (Boolean, nullable, default=False)")
        print("      Purpose: Flag updates to SOT files (BUILD_LOG.md, BUILD_HISTORY.md, etc.)")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN is_sot_file BOOLEAN DEFAULT FALSE
        """))
        print("      ✓ Column 'is_sot_file' added")

        print("\n[2/3] Adding column: sot_file_name (String, nullable)")
        print("      Purpose: Store basename of SOT file (e.g., 'build_log.md')")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN sot_file_name VARCHAR
        """))
        print("      ✓ Column 'sot_file_name' added")

        print("\n[3/3] Adding column: sot_entry_count_hint (Integer, nullable)")
        print("      Purpose: Proxy for number of entries to write (affects token cost)")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN sot_entry_count_hint INTEGER
        """))
        print("      ✓ Column 'sot_entry_count_hint' added")

        # Create index on is_sot_file for efficient filtering
        print("\n[Index] Creating index: idx_telemetry_sot")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_sot
            ON token_estimation_v2_events (is_sot_file, sot_file_name)
        """))
        print("      ✓ Index 'idx_telemetry_sot' created")

        # Verify existing events
        result = conn.execute(text("SELECT COUNT(*) FROM token_estimation_v2_events"))
        event_count = result.scalar() or 0

        print(f"\n✓ Migration complete!")
        print(f"  - {event_count} existing telemetry events updated with defaults:")
        print(f"    - is_sot_file = FALSE")
        print(f"    - sot_file_name = NULL")
        print(f"    - sot_entry_count_hint = NULL")

    print("\n" + "=" * 70)
    print("BUILD-129 Phase 3 P3 Migration: SUCCESS")
    print("=" * 70)


def downgrade(engine: Engine) -> None:
    """Remove SOT file tracking columns from token_estimation_v2_events table"""
    print("=" * 70)
    print("BUILD-129 Phase 3 P3 Rollback: Remove SOT File Tracking")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if columns exist before trying to drop
        if not check_column_exists(engine, "token_estimation_v2_events", "is_sot_file"):
            print("✓ SOT tracking columns already removed, nothing to rollback")
            return

        print("\n[1/4] Dropping index: idx_telemetry_sot")
        conn.execute(text("DROP INDEX IF EXISTS idx_telemetry_sot"))
        print("      ✓ Index 'idx_telemetry_sot' dropped")

        print("\n[2/4] Dropping column: sot_entry_count_hint")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS sot_entry_count_hint"))
        print("      ✓ Column 'sot_entry_count_hint' dropped")

        print("\n[3/4] Dropping column: sot_file_name")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS sot_file_name"))
        print("      ✓ Column 'sot_file_name' dropped")

        print("\n[4/4] Dropping column: is_sot_file")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS is_sot_file"))
        print("      ✓ Column 'is_sot_file' dropped")

    print("\n" + "=" * 70)
    print("BUILD-129 Phase 3 P3 Rollback: SUCCESS")
    print("=" * 70)


def main():
    """Main entry point for migration script"""
    if len(sys.argv) < 2:
        print("Usage: python add_sot_tracking.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command not in ["upgrade", "downgrade"]:
        print(f"Error: Invalid command '{command}'")
        print("Usage: python add_sot_tracking.py [upgrade|downgrade]")
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
