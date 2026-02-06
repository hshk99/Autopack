"""
BUILD-155: Database Migration - Add SOT Retrieval Telemetry Table

Creates the sot_retrieval_events table to track per-phase SOT context retrieval metrics.
This enables:
1. Monitoring SOT budget gating decisions (include_sot flag)
2. Tracking actual SOT character usage vs budget caps
3. Preventing silent prompt bloat from uncapped retrieval
4. Post-hoc optimization of SOT retrieval budgets

Schema:
- Links to (run_id, phase_id) composite key
- Tracks both raw retrieval and formatted output metrics
- Records budget utilization and truncation events
- Stores context composition for analysis

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/add_sot_retrieval_telemetry_build155.py upgrade
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/add_sot_retrieval_telemetry_build155.py downgrade
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


def check_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists in the database"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def upgrade(engine: Engine) -> None:
    """Create sot_retrieval_events table"""
    print("=" * 70)
    print("BUILD-155: Add SOT Retrieval Telemetry Table")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if table already exists
        if check_table_exists(engine, "sot_retrieval_events"):
            print("✓ Table 'sot_retrieval_events' already exists - skipping creation")
            return

        print("Creating table 'sot_retrieval_events'...")

        # Detect database dialect
        dialect = engine.dialect.name

        if dialect == "sqlite":
            # SQLite version
            conn.execute(text("""
                CREATE TABLE sot_retrieval_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    phase_id TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,

                    include_sot BOOLEAN NOT NULL,
                    max_context_chars INTEGER NOT NULL,
                    sot_budget_chars INTEGER NOT NULL,

                    sot_chunks_retrieved INTEGER NOT NULL DEFAULT 0,
                    sot_chars_raw INTEGER NOT NULL DEFAULT 0,

                    total_context_chars INTEGER NOT NULL,
                    sot_chars_formatted INTEGER,

                    budget_utilization_pct REAL NOT NULL,
                    sot_truncated BOOLEAN NOT NULL DEFAULT 0,

                    sections_included TEXT,

                    retrieval_enabled BOOLEAN NOT NULL,
                    top_k INTEGER,

                    created_at DATETIME NOT NULL,

                    FOREIGN KEY (run_id, phase_id) REFERENCES phases (run_id, phase_id) ON DELETE CASCADE,
                    FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
                )
            """))

            # Create indexes
            conn.execute(
                text("CREATE INDEX ix_sot_retrieval_events_run_id ON sot_retrieval_events (run_id)")
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_phase_id ON sot_retrieval_events (phase_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_timestamp ON sot_retrieval_events (timestamp)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_include_sot ON sot_retrieval_events (include_sot)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_created_at ON sot_retrieval_events (created_at)"
                )
            )

        elif dialect == "postgresql":
            # PostgreSQL version
            conn.execute(text("""
                CREATE TABLE sot_retrieval_events (
                    event_id SERIAL PRIMARY KEY,
                    run_id VARCHAR NOT NULL,
                    phase_id VARCHAR NOT NULL,
                    timestamp TIMESTAMP NOT NULL,

                    include_sot BOOLEAN NOT NULL,
                    max_context_chars INTEGER NOT NULL,
                    sot_budget_chars INTEGER NOT NULL,

                    sot_chunks_retrieved INTEGER NOT NULL DEFAULT 0,
                    sot_chars_raw INTEGER NOT NULL DEFAULT 0,

                    total_context_chars INTEGER NOT NULL,
                    sot_chars_formatted INTEGER,

                    budget_utilization_pct REAL NOT NULL,
                    sot_truncated BOOLEAN NOT NULL DEFAULT FALSE,

                    sections_included JSONB,

                    retrieval_enabled BOOLEAN NOT NULL,
                    top_k INTEGER,

                    created_at TIMESTAMP NOT NULL,

                    CONSTRAINT fk_sot_retrieval_run_phase
                        FOREIGN KEY (run_id, phase_id)
                        REFERENCES phases (run_id, phase_id)
                        ON DELETE CASCADE,
                    CONSTRAINT fk_sot_retrieval_run
                        FOREIGN KEY (run_id)
                        REFERENCES runs (id)
                        ON DELETE CASCADE
                )
            """))

            # Create indexes
            conn.execute(
                text("CREATE INDEX ix_sot_retrieval_events_run_id ON sot_retrieval_events (run_id)")
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_phase_id ON sot_retrieval_events (phase_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_timestamp ON sot_retrieval_events (timestamp)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_include_sot ON sot_retrieval_events (include_sot)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_sot_retrieval_events_created_at ON sot_retrieval_events (created_at)"
                )
            )

        else:
            raise ValueError(f"Unsupported database dialect: {dialect}")

        print("✓ Table 'sot_retrieval_events' created successfully")
        print("✓ Indexes created successfully")


def downgrade(engine: Engine) -> None:
    """Drop sot_retrieval_events table"""
    print("=" * 70)
    print("BUILD-155: Remove SOT Retrieval Telemetry Table")
    print("=" * 70)

    with engine.begin() as conn:
        if not check_table_exists(engine, "sot_retrieval_events"):
            print("✓ Table 'sot_retrieval_events' does not exist - nothing to do")
            return

        print("Dropping table 'sot_retrieval_events'...")
        conn.execute(text("DROP TABLE sot_retrieval_events"))
        print("✓ Table dropped successfully")


def main():
    """CLI entry point"""
    if len(sys.argv) < 2:
        print("Usage: python add_sot_retrieval_telemetry_build155.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]
    if command not in ("upgrade", "downgrade"):
        print(f"Error: Unknown command '{command}'. Use 'upgrade' or 'downgrade'.")
        sys.exit(1)

    try:
        db_url = get_database_url()
        print(f"Database URL: {db_url[:30]}...")

        engine = create_engine(db_url)

        if command == "upgrade":
            upgrade(engine)
            print("\n✅ Migration completed successfully!")
        else:
            downgrade(engine)
            print("\n✅ Downgrade completed successfully!")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
