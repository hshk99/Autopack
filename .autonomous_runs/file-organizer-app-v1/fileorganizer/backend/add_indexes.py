"""
Database optimization migration - Add indexes
"""
from sqlalchemy import create_engine, Index
from app.db.session import Base
from app.models.document import Document
from app.models.category import Category
from app.core.config import settings


def add_indexes():
    """Add database indexes for performance"""
    engine = create_engine(settings.DATABASE_URL)

    # Add indexes to Document table
    Index('idx_document_status', Document.status).create(engine, checkfirst=True)
    Index('idx_document_category', Document.assigned_category_id).create(engine, checkfirst=True)
    Index('idx_document_confidence', Document.classification_confidence).create(engine, checkfirst=True)
    Index('idx_document_filename', Document.filename).create(engine, checkfirst=True)

    # Add index to Category table
    Index('idx_category_pack', Category.scenario_pack_id).create(engine, checkfirst=True)

    print("[OK] Database indexes added successfully")


if __name__ == "__main__":
    add_indexes()
