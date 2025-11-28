"""
Scenario Packs API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.pack_service import ScenarioPackService
from pydantic import BaseModel

router = APIRouter()


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str | None

    class Config:
        from_attributes = True


class PackResponse(BaseModel):
    id: int
    name: str
    description: str | None
    template_path: str

    class Config:
        from_attributes = True


@router.get("/packs", response_model=list[PackResponse])
async def list_packs(db: Session = Depends(get_db)):
    """List all available scenario packs"""
    service = ScenarioPackService(db)
    return service.list_packs()


@router.get("/packs/{pack_id}", response_model=PackResponse)
async def get_pack(pack_id: int, db: Session = Depends(get_db)):
    """Get scenario pack by ID"""
    service = ScenarioPackService(db)
    pack = service.get_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    return pack


@router.get("/packs/{pack_id}/categories", response_model=list[CategoryResponse])
async def get_pack_categories(pack_id: int, db: Session = Depends(get_db)):
    """Get all categories for a pack"""
    service = ScenarioPackService(db)
    categories = service.get_pack_categories(pack_id)
    return categories
