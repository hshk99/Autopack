"""
BUILD-145 Deployment Hardening: Database Migration - Add telemetry enrichment columns

Adds embedding cache and budgeting context observability columns to token_efficiency_metrics.

Background:
- BUILD-145 P1 Hardening implemented core token efficiency observability
- Deployment hardening adds fine-grained telemetry for embedding cache effectiveness
  and budgeting context analysis

Schema changes:
- token_efficiency_metrics.embedding_cache_hits: INTEGER NULL (cache hit count)
- token_efficiency_metrics.embedding_cache_misses: INTEGER NULL (cache miss count)
- token_efficiency_metrics.embedding_calls_made: INTEGER NULL (total API calls)
- token_efficiency_metrics.embedding_cap_value: INTEGER NULL (cap value used)
- token_efficiency_metrics.embedding_fallback_reason: VARCHAR(100) NULL (fallback reason)
- token_efficiency_metrics.deliverables_count: INTEGER NULL (number of deliverables)
- token_efficiency_metrics.context_files_total: INTEGER NULL (total files before budgeting)

All nullable for backward compatibility with existing rows.

This migration is idempotent and can be run multiple times safely.

Usage:
    # SQLite (default):
    python scripts/migrations/add_telemetry_enrichment_build145_deploy.py upgrade

    # PostgreSQL:
    DATABASE_URL="postgresql://..." python scripts/migrations/add_telemetry_enrichment_build145_deploy.py upgrade

    # Downgrade (remove columns):
    python scripts/migrations/add_telemetry_enrichment_build145_deploy.py downgrade
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
        python scripts/migrations/add_telemetry_enrichment_build145_deploy.py upgrade

        # PowerShell (SQLite dev/test - explicit opt-in):
        $env:DATABASE_URL="sqlite:///autopack.db"
        python scripts/migrations/add_telemetry_enrichment_build145_deploy.py upgrade
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "="*80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print("\nMigration scripts require explicit DATABASE_URL to prevent footguns.", file=sys.stderr)
        print("Production uses Postgres; SQLite is only for dev/test.\n", file=sys.stderr)
        print("Set DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\"", file=sys.stderr)
        print("  python scripts/migrations/add_telemetry_enrichment_build145_deploy.py upgrade\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test - explicit opt-in):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"sqlite:///autopack.db\"", file=sys.stderr)
        print("  python scripts/migrations/add_telemetry_enrichment_build145_deploy.py upgrade\n", file=sys.stderr)
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


def upgrade(engine: Engine) -> None:
    """Add telemetry enrichment columns to token_efficiency_metrics table"""
    print("=" * 80)
    print("BUILD-145 Deployment: Add Telemetry Enrichment Columns")
    print("=" * 80)

    # Check if table exists
    if not check_table_exists(engine, "token_efficiency_metrics"):
        print("⚠️  Table 'token_efficiency_metrics' does not exist")
        print("    This is expected for fresh databases - ORM will create it with all columns")
        return

    # Define new columns to add
    new_columns = [
        ("embedding_cache_hits", "INTEGER NULL", "Cache hit count"),
        ("embedding_cache_misses", "INTEGER NULL", "Cache miss count"),
        ("embedding_calls_made", "INTEGER NULL", "Total embedding API calls"),
        ("embedding_cap_value", "INTEGER NULL", "Embedding cap value used"),
        ("embedding_fallback_reason", "VARCHAR(100) NULL", "Reason for lexical fallback"),
        ("deliverables_count", "INTEGER NULL", "Number of deliverables in phase"),
        ("context_files_total", "INTEGER NULL", "Total files before budgeting"),
    ]

    with engine.begin() as conn:
        columns_added = 0
        columns_skipped = 0

        for col_name, col_type, col_desc in new_columns:
            if check_column_exists(engine, "token_efficiency_metrics", col_name):
                print(f"✓ Column '{col_name}' already exists, skipping")
                columns_skipped += 1
            else:
                print(f"\n[{columns_added + 1}] Adding column: {col_name} ({col_type})")
                print(f"    Purpose: {col_desc}")
                conn.execute(text(f"""
                    ALTER TABLE token_efficiency_metrics
                    ADD COLUMN {col_name} {col_type}
                """))
                print(f"    ✓ Column '{col_name}' added")
                columns_added += 1

        print("\n" + "=" * 80)
        print(f"✅ Migration completed successfully!")
        print(f"   Columns added: {columns_added}")
        print(f"   Columns skipped (already exist): {columns_skipped}")
        print("=" * 80)
        print("\nNext steps:")
        print("  1. Restart any running executor/backend processes")
        print("  2. Run tests: pytest tests/autopack/test_token_efficiency_observability.py")
        print("  3. New telemetry will include embedding cache and budgeting stats")


def downgrade(engine: Engine) -> None:
    """Remove telemetry enrichment columns from token_efficiency_metrics table"""
    print("=" * 80)
    print("BUILD-145 Deployment: Remove Telemetry Enrichment Columns (Downgrade)")
    print("=" * 80)

    if not check_table_exists(engine, "token_efficiency_metrics"):
        print("⚠️  Table 'token_efficiency_metrics' does not exist, nothing to downgrade")
        return

    # Columns to remove
    columns_to_remove = [
        "embedding_cache_hits",
        "embedding_cache_misses",
        "embedding_calls_made",
        "embedding_cap_value",
        "embedding_fallback_reason",
        "deliverables_count",
        "context_files_total",
    ]

    with engine.begin() as conn:
        columns_removed = 0
        columns_not_found = 0

        for col_name in columns_to_remove:
            if not check_column_exists(engine, "token_efficiency_metrics", col_name):
                print(f"✓ Column '{col_name}' does not exist, skipping")
                columns_not_found += 1
                continue

            print(f"\n[{columns_removed + 1}] Dropping column: {col_name}")

            # SQLite requires special handling for column drops
            db_url = get_database_url()
            if "sqlite" in db_url.lower():
                print("      ⚠️  SQLite detected - column drop requires table recreation")
                print("      For safety, manual intervention recommended:")
                print("      1. Backup database")
                print("      2. Recreate table without enrichment columns")
                print("      3. Copy data from backup")
                print(f"\n      Skipping automatic downgrade for column '{col_name}'")
                continue
            else:
                # PostgreSQL and other databases support DROP COLUMN
                conn.execute(text(f"""
                    ALTER TABLE token_efficiency_metrics
                    DROP COLUMN {col_name}
                """))
                print(f"      ✓ Column '{col_name}' dropped")
                columns_removed += 1

    print("\n" + "=" * 80)
    print(f"✅ Downgrade completed!")
    print(f"   Columns removed: {columns_removed}")
    print(f"   Columns not found: {columns_not_found}")
    print("=" * 80)


def main():
    """Main entry point"""
    if len(sys.argv) < 2 or sys.argv[1] not in ["upgrade", "downgrade"]:
        print("Usage: python add_telemetry_enrichment_build145_deploy.py [upgrade|downgrade]")
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
