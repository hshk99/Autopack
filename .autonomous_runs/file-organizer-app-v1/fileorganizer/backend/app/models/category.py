"""
Category model - Classification categories within scenario packs
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    scenario_pack_id = Column(Integer, ForeignKey("scenario_packs.id"), nullable=False)

    # Examples for few-shot learning
    example_documents = Column(Text, nullable=True)  # JSON array of example texts

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"
