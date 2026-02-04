"""
IMP-TEL-001: Database Migration - Add client_id column to llm_usage_events

Adds client_id column and composite index for SaaS cost attribution.

Background:
- Token usage is recorded per run/phase but not by client identity
- Downstream monetized projects cannot attribute costs to end users
- This migration adds client_id column for per-client usage tracking

Schema changes:
- llm_usage_events.client_id: VARCHAR NULLABLE (for backward compatibility)
- Index: ix_llm_usage_events_client_id (single column index)
- Index: ix_client_created (composite index on client_id, created_at)

This migration is idempotent and can be run multiple times safely.

Usage:
    # SQLite (default):
    python scripts/migrations/add_client_id_to_usage.py upgrade

    # PostgreSQL:
    DATABASE_URL="postgresql://..." python scripts/migrations/add_client_id_to_usage.py upgrade

    # Downgrade (remove column and indexes):
    python scripts/migrations/add_client_id_to_usage.py downgrade
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Get DATABASE_URL from environment (REQUIRED - no default)

    IMP-TEL-001: Migration scripts must target explicit DATABASE_URL to prevent
    accidentally running migrations on SQLite when production uses Postgres.

    Set DATABASE_URL before running:
        # PowerShell (Postgres production):
        $env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
        python scripts/migrations/add_client_id_to_usage.py upgrade

        # PowerShell (SQLite dev/test - explicit opt-in):
        $env:DATABASE_URL="sqlite:///autopack.db"
        python scripts/migrations/add_client_id_to_usage.py upgrade
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "=" * 80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(
            "\nMigration scripts require explicit DATABASE_URL to prevent footguns.",
            file=sys.stderr,
        )
        print("Production uses Postgres; SQLite is only for dev/test.\n", file=sys.stderr)
        print("Set DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print(
            '  $env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"',
            file=sys.stderr,
        )
        print("  python scripts/migrations/add_client_id_to_usage.py upgrade\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test - explicit opt-in):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
        print("  python scripts/migrations/add_client_id_to_usage.py upgrade\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def check_column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    try:
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def check_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists"""
    try:
        inspector = inspect(engine)
        return table_name in inspector.get_table_names()
    except Exception:
        return False


def check_index_exists(engine: Engine, table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table"""
    try:
        inspector = inspect(engine)
        indexes = inspector.get_indexes(table_name)
        return any(idx["name"] == index_name for idx in indexes)
    except Exception:
        return False


def upgrade(engine: Engine) -> None:
    """Add client_id column and indexes to llm_usage_events table"""
    print("=" * 80)
    print("IMP-TEL-001: Add client_id Column to llm_usage_events")
    print("=" * 80)

    # Check if table exists
    if not check_table_exists(engine, "llm_usage_events"):
        print("[!] Table 'llm_usage_events' does not exist")
        print("    This is expected for fresh databases - ORM will create it with client_id")
        return

    db_url = get_database_url()
    is_sqlite = "sqlite" in db_url.lower()

    with engine.begin() as conn:
        # Step 1: Add client_id column if it doesn't exist
        if check_column_exists(engine, "llm_usage_events", "client_id"):
            print("[x] Column 'client_id' already exists, skipping column creation")
        else:
            print("\n[1/3] Adding column: client_id (VARCHAR NULLABLE)")
            print("      Purpose: Enable per-client cost attribution for SaaS billing")
            conn.execute(
                text("""
                ALTER TABLE llm_usage_events
                ADD COLUMN client_id VARCHAR NULL
            """)
            )
            print("      [x] Column 'client_id' added")

        # Step 2: Add single-column index on client_id
        if check_index_exists(engine, "llm_usage_events", "ix_llm_usage_events_client_id"):
            print("[x] Index 'ix_llm_usage_events_client_id' already exists")
        else:
            print("\n[2/3] Creating index: ix_llm_usage_events_client_id")
            print("      Purpose: Fast lookups by client_id")
            conn.execute(
                text("""
                CREATE INDEX ix_llm_usage_events_client_id
                ON llm_usage_events (client_id)
            """)
            )
            print("      [x] Index 'ix_llm_usage_events_client_id' created")

        # Step 3: Add composite index on (client_id, created_at)
        if check_index_exists(engine, "llm_usage_events", "ix_client_created"):
            print("[x] Index 'ix_client_created' already exists")
        else:
            print("\n[3/3] Creating composite index: ix_client_created")
            print("      Purpose: Efficient time-range queries per client for billing")
            conn.execute(
                text("""
                CREATE INDEX ix_client_created
                ON llm_usage_events (client_id, created_at)
            """)
            )
            print("      [x] Index 'ix_client_created' created")

        # Verification
        print("\n[Verification]")
        result = conn.execute(
            text("""
            SELECT COUNT(*) as total_rows,
                   COUNT(client_id) as rows_with_client_id
            FROM llm_usage_events
        """)
        )
        row = result.fetchone()
        if row:
            print(f"      Total rows: {row[0]}")
            print(f"      Rows with client_id: {row[1]}")
            print(f"      Rows without client_id: {row[0] - row[1]} (expected for existing data)")

    print("\n" + "=" * 80)
    print("[OK] Migration completed successfully!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Restart any running executor/backend processes")
    print("  2. Update API callers to pass client_id parameter")
    print("  3. Run tests: pytest tests/llm/test_usage_client_attribution.py")


def downgrade(engine: Engine) -> None:
    """Remove client_id column and indexes from llm_usage_events table"""
    print("=" * 80)
    print("IMP-TEL-001: Remove client_id Column (Downgrade)")
    print("=" * 80)

    if not check_table_exists(engine, "llm_usage_events"):
        print("[!] Table 'llm_usage_events' does not exist, nothing to downgrade")
        return

    db_url = get_database_url()
    is_sqlite = "sqlite" in db_url.lower()

    with engine.begin() as conn:
        # Step 1: Drop composite index
        if check_index_exists(engine, "llm_usage_events", "ix_client_created"):
            print("\n[1/3] Dropping index: ix_client_created")
            conn.execute(text("DROP INDEX ix_client_created"))
            print("      [x] Index 'ix_client_created' dropped")
        else:
            print("[x] Index 'ix_client_created' does not exist")

        # Step 2: Drop single-column index
        if check_index_exists(engine, "llm_usage_events", "ix_llm_usage_events_client_id"):
            print("\n[2/3] Dropping index: ix_llm_usage_events_client_id")
            conn.execute(text("DROP INDEX ix_llm_usage_events_client_id"))
            print("      [x] Index 'ix_llm_usage_events_client_id' dropped")
        else:
            print("[x] Index 'ix_llm_usage_events_client_id' does not exist")

        # Step 3: Drop column
        if not check_column_exists(engine, "llm_usage_events", "client_id"):
            print("[x] Column 'client_id' does not exist, nothing to remove")
        elif is_sqlite:
            print("\n[3/3] Dropping column: client_id")
            print("      [!] SQLite detected - column drop requires table recreation")
            print("      For safety, manual intervention recommended:")
            print("      1. Backup database")
            print("      2. Recreate table without client_id")
            print("      3. Copy data from backup")
            print("\n      Skipping automatic column drop for SQLite")
        else:
            # PostgreSQL and other databases support DROP COLUMN
            print("\n[3/3] Dropping column: client_id")
            conn.execute(
                text("""
                ALTER TABLE llm_usage_events
                DROP COLUMN client_id
            """)
            )
            print("      [x] Column 'client_id' dropped")

    print("\n" + "=" * 80)
    print("[OK] Downgrade completed successfully!")
    print("=" * 80)


def main():
    """Main entry point"""
    if len(sys.argv) < 2 or sys.argv[1] not in ["upgrade", "downgrade"]:
        print("Usage: python add_client_id_to_usage.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]
    db_url = get_database_url()

    print(f"\nDatabase URL: {db_url}")
    print(f"Command: {command}\n")

    try:
        engine = create_engine(db_url)

        if command == "upgrade":
            upgrade(engine)
        else:
            downgrade(engine)

    except Exception as e:
        print(f"\n[X] Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
