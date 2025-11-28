"""
ScenarioPack model - Document organization templates (Tax, Immigration, Legal)
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.db.session import Base


class ScenarioPack(Base):
    __tablename__ = "scenario_packs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # YAML template path (e.g., "packs/tax_generic.yaml")
    template_path = Column(String(255), nullable=False)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ScenarioPack(id={self.id}, name='{self.name}')>"
