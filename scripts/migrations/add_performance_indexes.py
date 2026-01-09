"""Add performance indexes for dashboard queries - BUILD-146 P12

IMPORTANT: This is a manual migration script, NOT Alembic.

Run with:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="..." python scripts/migrations/add_performance_indexes.py

Supports both PostgreSQL and SQLite.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError


def get_database_url() -> str:
    """Get DATABASE_URL from environment with helpful error."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "="*80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print("\nSet DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\"", file=sys.stderr)
        print("  python scripts/migrations/add_performance_indexes.py\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"sqlite:///autopack.db\"", file=sys.stderr)
        print("  python scripts/migrations/add_performance_indexes.py\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def is_sqlite(db_url: str) -> bool:
    """Check if database is SQLite."""
    return db_url.startswith("sqlite")


def index_exists(engine, index_name: str, table_name: str) -> bool:
    """Check if index already exists.

    Args:
        engine: SQLAlchemy engine
        index_name: Name of index to check
        table_name: Name of table index belongs to

    Returns:
        True if index exists, False otherwise
    """
    with engine.connect() as conn:
        if is_sqlite(str(engine.url)):
            # SQLite: Use PRAGMA index_list
            result = conn.execute(text(f"PRAGMA index_list({table_name})"))
            existing_indexes = [row[1] for row in result.fetchall()]
            return index_name in existing_indexes
        else:
            # PostgreSQL: Query pg_indexes
            result = conn.execute(text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = :table_name AND indexname = :index_name
            """), {"table_name": table_name, "index_name": index_name})
            return result.fetchone() is not None


def add_indexes(engine):
    """Add performance indexes for dashboard queries.

    BUILD-146 P12: Optimizes queries for consolidated metrics and dashboard endpoints.

    Indexes created:
    - idx_phase_metrics_run_id: For filtering phase_metrics by run_id
    - idx_phase_metrics_created_at: For sorting by timestamp
    - idx_phase_metrics_run_created: Composite index for run_id + timestamp queries
    - idx_dashboard_events_run_id: For filtering dashboard_events by run_id
    - idx_dashboard_events_event_type: For filtering by event type
    - idx_phases_run_state: For run + state queries
    - idx_llm_usage_events_run_id: For LLM usage queries
    - idx_token_efficiency_run_id: For token efficiency queries
    """
    print("Adding performance indexes...")
    print()

    indexes_to_create = [
        # PhaseMetrics indexes (if table exists)
        {
            "name": "idx_phase_metrics_run_id",
            "table": "phase_metrics",
            "sql": "CREATE INDEX IF NOT EXISTS idx_phase_metrics_run_id ON phase_metrics(run_id)",
            "description": "Index on phase_metrics.run_id for filtering"
        },
        {
            "name": "idx_phase_metrics_created_at",
            "table": "phase_metrics",
            "sql": "CREATE INDEX IF NOT EXISTS idx_phase_metrics_created_at ON phase_metrics(created_at DESC)",
            "description": "Index on phase_metrics.created_at for sorting"
        },
        {
            "name": "idx_phase_metrics_run_created",
            "table": "phase_metrics",
            "sql": "CREATE INDEX IF NOT EXISTS idx_phase_metrics_run_created ON phase_metrics(run_id, created_at DESC)",
            "description": "Composite index on phase_metrics(run_id, created_at) for dashboard queries"
        },

        # DashboardEvent indexes (if table exists)
        {
            "name": "idx_dashboard_events_run_id",
            "table": "dashboard_events",
            "sql": "CREATE INDEX IF NOT EXISTS idx_dashboard_events_run_id ON dashboard_events(run_id)",
            "description": "Index on dashboard_events.run_id for filtering"
        },
        {
            "name": "idx_dashboard_events_event_type",
            "table": "dashboard_events",
            "sql": "CREATE INDEX IF NOT EXISTS idx_dashboard_events_event_type ON dashboard_events(event_type)",
            "description": "Index on dashboard_events.event_type for pattern analysis"
        },

        # Phase indexes
        {
            "name": "idx_phases_run_state",
            "table": "phases",
            "sql": "CREATE INDEX IF NOT EXISTS idx_phases_run_state ON phases(run_id, state)",
            "description": "Composite index on phases(run_id, state) for status queries"
        },

        # LLM usage events indexes (for consolidated metrics)
        {
            "name": "idx_llm_usage_events_run_id",
            "table": "llm_usage_events",
            "sql": "CREATE INDEX IF NOT EXISTS idx_llm_usage_events_run_id ON llm_usage_events(run_id)",
            "description": "Index on llm_usage_events.run_id for token aggregation"
        },

        # Token efficiency metrics indexes
        {
            "name": "idx_token_efficiency_run_id",
            "table": "token_efficiency_metrics",
            "sql": "CREATE INDEX IF NOT EXISTS idx_token_efficiency_run_id ON token_efficiency_metrics(run_id)",
            "description": "Index on token_efficiency_metrics.run_id for efficiency queries"
        },

        # Phase6 metrics indexes (for Phase 6 stats)
        {
            "name": "idx_phase6_metrics_run_id",
            "table": "phase6_metrics",
            "sql": "CREATE INDEX IF NOT EXISTS idx_phase6_metrics_run_id ON phase6_metrics(run_id)",
            "description": "Index on phase6_metrics.run_id for Phase 6 stats"
        },
    ]

    created_count = 0
    skipped_count = 0
    error_count = 0

    with engine.begin() as conn:
        for index_info in indexes_to_create:
            index_name = index_info["name"]
            table_name = index_info["table"]
            sql = index_info["sql"]
            description = index_info["description"]

            try:
                # Check if table exists first
                if is_sqlite(str(engine.url)):
                    # SQLite: Check with PRAGMA
                    result = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
                    table_exists = result.fetchone() is not None
                else:
                    # PostgreSQL: Check pg_tables
                    result = conn.execute(text("SELECT tablename FROM pg_tables WHERE tablename = :table_name"), {"table_name": table_name})
                    table_exists = result.fetchone() is not None

                if not table_exists:
                    print(f"⊘ Skipping {index_name} (table '{table_name}' does not exist)")
                    skipped_count += 1
                    continue

                # Check if index already exists
                if index_exists(engine, index_name, table_name):
                    print(f"✓ Index {index_name} already exists")
                    skipped_count += 1
                    continue

                # Create index
                conn.execute(text(sql))
                print(f"✓ Created {index_name}")
                print(f"  → {description}")
                created_count += 1

            except (OperationalError, ProgrammingError) as e:
                # Handle errors gracefully (e.g., table doesn't exist)
                print(f"⚠ Error creating {index_name}: {e}")
                error_count += 1
                continue

    print()
    print("="*80)
    print("INDEX CREATION SUMMARY")
    print("="*80)
    print(f"Created: {created_count}")
    print(f"Skipped (already exist or table missing): {skipped_count}")
    print(f"Errors: {error_count}")
    print()

    if created_count > 0:
        print("✅ Performance indexes added successfully")
    elif skipped_count > 0 and error_count == 0:
        print("✅ All indexes already exist or tables not present")
    else:
        print("⚠ Some indexes could not be created (see errors above)")

    return created_count, skipped_count, error_count


def verify_indexes(engine):
    """Verify indexes were created successfully.

    Prints index list for key tables.
    """
    print()
    print("="*80)
    print("INDEX VERIFICATION")
    print("="*80)
    print()

    tables_to_check = [
        "phase_metrics",
        "dashboard_events",
        "phases",
        "llm_usage_events",
        "token_efficiency_metrics",
        "phase6_metrics",
    ]

    with engine.connect() as conn:
        for table_name in tables_to_check:
            # Check if table exists
            if is_sqlite(str(engine.url)):
                result = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
                table_exists = result.fetchone() is not None
            else:
                result = conn.execute(text("SELECT tablename FROM pg_tables WHERE tablename = :table_name"), {"table_name": table_name})
                table_exists = result.fetchone() is not None

            if not table_exists:
                continue

            print(f"Indexes on '{table_name}':")

            if is_sqlite(str(engine.url)):
                # SQLite: Use PRAGMA index_list
                result = conn.execute(text(f"PRAGMA index_list({table_name})"))
                indexes = result.fetchall()
                if indexes:
                    for idx in indexes:
                        # idx format: (seq, name, unique, origin, partial)
                        print(f"  - {idx[1]}")
                else:
                    print("  (no indexes)")
            else:
                # PostgreSQL: Query pg_indexes
                result = conn.execute(text("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = :table_name
                    ORDER BY indexname
                """), {"table_name": table_name})
                indexes = result.fetchall()
                if indexes:
                    for idx in indexes:
                        print(f"  - {idx[0]}")
                else:
                    print("  (no indexes)")

            print()


def main():
    """Main entry point."""
    print("BUILD-146 P12: Performance Index Migration")
    print("="*80)
    print()

    # Get database connection
    db_url = get_database_url()
    print(f"Database: {db_url}")
    print(f"Database type: {'SQLite' if is_sqlite(db_url) else 'PostgreSQL'}")
    print()

    # Create engine
    engine = create_engine(db_url)

    # Add indexes
    created, skipped, errors = add_indexes(engine)

    # Verify indexes
    if created > 0 or skipped > 0:
        verify_indexes(engine)

    # Exit with appropriate code
    if errors > 0:
        print("⚠ Migration completed with errors")
        sys.exit(1)
    else:
        print("✅ Migration completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
