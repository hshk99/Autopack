"""Add goal_anchor column to runs table

The goal_anchor field is used for goal drift detection but was missing from the database schema.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import SessionLocal, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add goal_anchor column to runs table"""
    logger.info("Adding goal_anchor column to runs table...")

    # Get database URL to check dialect
    db_url = str(engine.url)
    is_sqlite = "sqlite" in db_url.lower()

    session = SessionLocal()
    try:
        # Check if column already exists
        result = session.execute(text("SELECT * FROM runs LIMIT 1"))
        columns = result.keys()

        if "goal_anchor" in columns:
            logger.info("Migration already applied - goal_anchor column exists")
            return

        logger.info("Adding goal_anchor column...")

        # Add new column
        session.execute(text("ALTER TABLE runs ADD COLUMN goal_anchor TEXT"))
        session.commit()
        logger.info("goal_anchor column added successfully")

        logger.info("✅ Migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    migrate()
