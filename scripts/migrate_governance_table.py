"""
Database migration script for BUILD-127 Phase 2: Add governance_requests table.

This script manually creates the governance_requests table in existing databases.
For new databases, the table will be automatically created via init_db().

Usage:
    python scripts/migrate_governance_table.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import engine
from sqlalchemy import text


def migrate():
    """Create governance_requests table if it doesn't exist."""

    # SQL for creating the table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS governance_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id VARCHAR UNIQUE NOT NULL,
        run_id VARCHAR NOT NULL,
        phase_id VARCHAR NOT NULL,
        requested_paths TEXT NOT NULL,
        justification TEXT,
        risk_level VARCHAR,
        auto_approved BOOLEAN NOT NULL DEFAULT 0,
        approved BOOLEAN,
        approved_by VARCHAR,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (run_id) REFERENCES runs(id)
    );
    """

    # SQL for creating indexes
    create_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS ix_governance_requests_request_id ON governance_requests(request_id);",
        "CREATE INDEX IF NOT EXISTS ix_governance_requests_run_id ON governance_requests(run_id);",
        "CREATE INDEX IF NOT EXISTS ix_governance_requests_phase_id ON governance_requests(phase_id);",
        "CREATE INDEX IF NOT EXISTS ix_governance_requests_approved ON governance_requests(approved);",
        "CREATE INDEX IF NOT EXISTS ix_governance_requests_created_at ON governance_requests(created_at);",
    ]

    print("[Migration] Creating governance_requests table...")

    with engine.connect() as conn:
        # Create table
        conn.execute(text(create_table_sql))
        conn.commit()
        print("[Migration] ✓ Table created")

        # Create indexes
        for idx_sql in create_indexes_sql:
            conn.execute(text(idx_sql))
        conn.commit()
        print(f"[Migration] ✓ Created {len(create_indexes_sql)} indexes")

    print("[Migration] Migration complete!")


if __name__ == "__main__":
    migrate()
