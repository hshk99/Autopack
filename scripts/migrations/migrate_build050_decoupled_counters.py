"""BUILD-050 Phase 2: Database migration for decoupled attempt counters

This script adds three new columns to the Phase model:
- retry_attempt: Monotonic retry counter (for hints accumulation and model escalation)
- revision_epoch: Replan counter (increments when Doctor revises approach)
- escalation_level: Model escalation level (0=base, 1=escalated, etc.)

Usage:
    python scripts/migrations/migrate_build050_decoupled_counters.py
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import SessionLocal, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Run BUILD-050 Phase 2 migration"""
    logger.info("Starting BUILD-050 Phase 2 migration...")

    # Get database URL to check dialect
    db_url = str(engine.url)
    is_sqlite = "sqlite" in db_url.lower()

    session = SessionLocal()
    try:
        # Check if columns already exist
        result = session.execute(text("SELECT * FROM phases LIMIT 1"))
        columns = result.keys()

        if "retry_attempt" in columns:
            logger.info("Migration already applied - columns exist")
            return

        logger.info("Adding new columns to phases table...")

        # Add new columns
        if is_sqlite:
            # SQLite doesn't support adding multiple columns in one statement
            session.execute(
                text("ALTER TABLE phases ADD COLUMN retry_attempt INTEGER NOT NULL DEFAULT 0")
            )
            session.execute(
                text("ALTER TABLE phases ADD COLUMN revision_epoch INTEGER NOT NULL DEFAULT 0")
            )
            session.execute(
                text("ALTER TABLE phases ADD COLUMN escalation_level INTEGER NOT NULL DEFAULT 0")
            )
        else:
            # PostgreSQL supports adding multiple columns
            session.execute(text("""
                ALTER TABLE phases
                ADD COLUMN retry_attempt INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN revision_epoch INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN escalation_level INTEGER NOT NULL DEFAULT 0
            """))

        session.commit()
        logger.info("New columns added successfully")

        # Migrate existing data
        logger.info("Migrating existing data: copying attempts_used to retry_attempt...")
        session.execute(
            text("UPDATE phases SET retry_attempt = attempts_used WHERE retry_attempt = 0")
        )
        session.commit()
        logger.info("Data migration complete")

        logger.info("✅ BUILD-050 Phase 2 migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
