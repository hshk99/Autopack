"""Health check endpoints."""

from fastapi import APIRouter
from datetime import datetime
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns the current status and timestamp.
    """
    return HealthResponse(status="healthy", timestamp=datetime.utcnow().isoformat())

