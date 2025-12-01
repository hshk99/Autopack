"""Search API Router"""

from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/api/search")
async def search(
    full_text: str,
    document_type: str,
    pack_name: str,
    confidence_min: float,
    confidence_max: float,
    date_from: str,
    date_to: str,
    page: int = 1,
    page_size: int = 10
):
    """
    Search endpoint that currently returns a 404 response.
    """
    raise HTTPException(status_code=404, detail="Search functionality not implemented yet.")

def include_router(app):
    """
    Function to include the search router in the FastAPI app.
    """
    app.include_router(router)
