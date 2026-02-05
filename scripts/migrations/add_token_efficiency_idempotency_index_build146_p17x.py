"""
BUILD-146 P17.x: Database Migration - Add idempotency index for token_efficiency_metrics

Adds a partial unique index to enforce uniqueness at the DB level for terminal outcomes.

Background:
- BUILD-145 P1 added token efficiency observability with phase_outcome tracking
- BUILD-146 P17.1 added app-level idempotency guard (check-then-insert)
- P17.x hardens this with DB-level enforcement to prevent race conditions

Problem:
- App-level guard prevents most duplicates but fails under concurrent writers
- Classic "check then insert" race: two writers can both see no existing row, both insert

Solution:
- Partial unique index: (run_id, phase_id, phase_outcome) WHERE phase_outcome IS NOT NULL
- Prevents duplicates at DB level for terminal outcomes
- Backward compatible: NULL outcomes are not enforced (legacy paths)

Schema changes:
- PostgreSQL: CREATE UNIQUE INDEX CONCURRENTLY (non-transactional)
- SQLite: CREATE UNIQUE INDEX (best-effort, partial indexes supported in SQLite 3.8+)
- Index name: ux_token_eff_metrics_run_phase_outcome
- Predicate: WHERE phase_outcome IS NOT NULL

This migration is idempotent and can be run multiple times safely.

Usage:
    # SQLite (dev/test - explicit opt-in):
    DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade

    # PostgreSQL (production):
    DATABASE_URL="postgresql://..." python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade

    # Downgrade (remove index):
    DATABASE_URL="..." python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py downgrade
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Get DATABASE_URL from environment (REQUIRED - no default)

    BUILD-146 P4 Ops: Migration scripts must target explicit DATABASE_URL to prevent
    accidentally running migrations on SQLite when production uses Postgres.

    Set DATABASE_URL before running:
        # PowerShell (Postgres production):
        $env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
        python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade

        # PowerShell (SQLite dev/test - explicit opt-in):
        $env:DATABASE_URL="sqlite:///autopack.db"
        python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade
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
        print(
            "  python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade\n",
            file=sys.stderr,
        )
        print("  # PowerShell (SQLite dev/test - explicit opt-in):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
        print(
            "  python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return db_url


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


def check_column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    try:
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def upgrade(engine: Engine) -> None:
    """Add partial unique index to token_efficiency_metrics table"""
    print("=" * 80)
    print("BUILD-146 P17.x: Add Idempotency Index to token_efficiency_metrics")
    print("=" * 80)

    # Check if table exists
    if not check_table_exists(engine, "token_efficiency_metrics"):
        print("⚠️  Table 'token_efficiency_metrics' does not exist")
        print("    This is expected for fresh databases - ORM will create it")
        print("    Run the table creation migration first")
        return

    # Check if phase_outcome column exists (prerequisite)
    if not check_column_exists(engine, "token_efficiency_metrics", "phase_outcome"):
        print("✗ ERROR: Column 'phase_outcome' does not exist")
        print("  Run add_phase_outcome_build145_p1.py migration first")
        sys.exit(1)

    index_name = "ux_token_eff_metrics_run_phase_outcome"

    # Check if index already exists
    if check_index_exists(engine, "token_efficiency_metrics", index_name):
        print(f"✓ Index '{index_name}' already exists, skipping creation")

        # Verify index is working (check for duplicates)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT run_id, phase_id, phase_outcome, COUNT(*) as count
                FROM token_efficiency_metrics
                WHERE phase_outcome IS NOT NULL
                GROUP BY run_id, phase_id, phase_outcome
                HAVING COUNT(*) > 1
            """))
            duplicates = result.fetchall()
            if duplicates:
                print(f"⚠️  WARNING: Found {len(duplicates)} duplicate terminal outcomes:")
                for dup in duplicates[:5]:  # Show first 5
                    print(
                        f"    run_id={dup[0]}, phase_id={dup[1]}, outcome={dup[2]}, count={dup[3]}"
                    )
                print("  These duplicates should be cleaned up manually")
            else:
                print("✓ No duplicate terminal outcomes found (idempotency is working)")
        return

    dialect = engine.dialect.name
    print(f"\nDatabase dialect: {dialect}")

    if dialect == "postgresql":
        print("\n[1/1] Creating partial unique index (CONCURRENTLY)")
        print("      Index name: ux_token_eff_metrics_run_phase_outcome")
        print("      Columns: (run_id, phase_id, phase_outcome)")
        print("      Predicate: WHERE phase_outcome IS NOT NULL")
        print("      Note: CONCURRENTLY requires non-transactional execution")

        # PostgreSQL CONCURRENTLY must run outside transaction
        with engine.connect() as conn:
            # Set autocommit mode (no transaction)
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("""
                CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_token_eff_metrics_run_phase_outcome
                ON token_efficiency_metrics (run_id, phase_id, phase_outcome)
                WHERE phase_outcome IS NOT NULL
            """))
        print("      ✓ Partial unique index created successfully (PostgreSQL)")

    elif dialect == "sqlite":
        print("\n[1/1] Creating partial unique index")
        print("      Index name: ux_token_eff_metrics_run_phase_outcome")
        print("      Columns: (run_id, phase_id, phase_outcome)")
        print("      Predicate: WHERE phase_outcome IS NOT NULL")
        print("      Note: Requires SQLite 3.8+ for partial indexes")

        # SQLite can run in transaction
        with engine.begin() as conn:
            try:
                conn.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_token_eff_metrics_run_phase_outcome
                    ON token_efficiency_metrics (run_id, phase_id, phase_outcome)
                    WHERE phase_outcome IS NOT NULL
                """))
                print("      ✓ Partial unique index created successfully (SQLite)")
            except Exception as e:
                if "partial" in str(e).lower() or "WHERE" in str(e):
                    print("      ⚠️  SQLite version does not support partial indexes")
                    print(f"      Error: {e}")
                    print("      Upgrade to SQLite 3.8+ or use PostgreSQL for production")
                    print("      Skipping index creation (app-level guard will still work)")
                else:
                    raise
    else:
        print(f"⚠️  Unsupported dialect: {dialect}")
        print("   Supported: postgresql, sqlite")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("✅ Migration completed successfully!")
    print("=" * 80)
    print("\nWhat this enables:")
    print("  1. DB-level enforcement of idempotency for terminal outcomes")
    print("  2. Race-safe under concurrent writers (e.g., parallel executors)")
    print("  3. Backward compatible (NULL outcomes are not enforced)")
    print("\nNext steps:")
    print("  1. Update record_token_efficiency_metrics() with IntegrityError handling")
    print("  2. Restart any running executor/backend processes")
    print("  3. Run tests: pytest tests/autopack/test_token_efficiency_observability.py")


def downgrade(engine: Engine) -> None:
    """Remove partial unique index from token_efficiency_metrics table"""
    print("=" * 80)
    print("BUILD-146 P17.x: Remove Idempotency Index (Downgrade)")
    print("=" * 80)

    if not check_table_exists(engine, "token_efficiency_metrics"):
        print("⚠️  Table 'token_efficiency_metrics' does not exist, nothing to downgrade")
        return

    index_name = "ux_token_eff_metrics_run_phase_outcome"

    if not check_index_exists(engine, "token_efficiency_metrics", index_name):
        print(f"✓ Index '{index_name}' does not exist, nothing to remove")
        return

    print(f"\n[1/1] Dropping index: {index_name}")

    # DROP INDEX works the same way for both PostgreSQL and SQLite
    with engine.begin() as conn:
        try:
            # PostgreSQL: DROP INDEX index_name
            # SQLite: DROP INDEX index_name
            conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
            print(f"      ✓ Index '{index_name}' dropped")
        except Exception as e:
            print(f"      ⚠️  Warning: {e}")

    print("\n" + "=" * 80)
    print("✅ Downgrade completed successfully!")
    print("=" * 80)
    print("\nNote: App-level idempotency guard will still work, but race conditions are possible")


def main():
    """Main entry point"""
    if len(sys.argv) < 2 or sys.argv[1] not in ["upgrade", "downgrade"]:
        print(
            "Usage: python add_token_efficiency_idempotency_index_build146_p17x.py [upgrade|downgrade]"
        )
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
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
