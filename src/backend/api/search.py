"""
Advanced search API endpoint with comprehensive filtering capabilities.

Provides search functionality for documents with filters for:
- Date range (created_at, updated_at)
- Document type
- Confidence score range
- Pack name
- Full-text search on extracted text

Returns paginated results with metadata.
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator

from ..database import get_db
from ..models.document import Document


router = APIRouter(prefix="/api/v1/search", tags=["search"])


class SearchFilters(BaseModel):
    """Search filter parameters."""

    query: Optional[str] = Field(
        None,
        description="Full-text search query for extracted text",
        max_length=500
    )
    document_type: Optional[str] = Field(
        None,
        description="Filter by document type (e.g., 'invoice', 'receipt', 'contract')",
        max_length=100
    )
    pack_name: Optional[str] = Field(
        None,
        description="Filter by pack name",
        max_length=200
    )
    min_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score (0.0 to 1.0)"
    )
    max_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Maximum confidence score (0.0 to 1.0)"
    )
    date_from: Optional[datetime] = Field(
        None,
        description="Filter documents created on or after this date"
    )
    date_to: Optional[datetime] = Field(
        None,
        description="Filter documents created on or before this date"
    )
    updated_from: Optional[datetime] = Field(
        None,
        description="Filter documents updated on or after this date"
    )
    updated_to: Optional[datetime] = Field(
        None,
        description="Filter documents updated on or before this date"
    )

    @validator("max_confidence")
    def validate_confidence_range(cls, v, values):
        """Ensure max_confidence is greater than min_confidence."""
        if v is not None and "min_confidence" in values and values["min_confidence"] is not None:
            if v < values["min_confidence"]:
                raise ValueError("max_confidence must be greater than or equal to min_confidence")
        return v

    @validator("date_to")
    def validate_date_range(cls, v, values):
        """Ensure date_to is after date_from."""
        if v is not None and "date_from" in values and values["date_from"] is not None:
            if v < values["date_from"]:
                raise ValueError("date_to must be greater than or equal to date_from")
        return v

    @validator("updated_to")
    def validate_updated_range(cls, v, values):
        """Ensure updated_to is after updated_from."""
        if v is not None and "updated_from" in values and values["updated_from"] is not None:
            if v < values["updated_from"]:
                raise ValueError("updated_to must be greater than or equal to updated_from")
        return v


class DocumentResult(BaseModel):
    """Document search result."""

    id: int
    filename: str
    document_type: Optional[str]
    pack_name: Optional[str]
    confidence_score: Optional[float]
    extracted_text: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: Optional[dict] = None

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Paginated search response."""

    results: List[DocumentResult]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


@router.get("/documents", response_model=SearchResponse)
async def search_documents(
    query: Optional[str] = Query(None, description="Full-text search query"),
    document_type: Optional[str] = Query(None, description="Document type filter"),
    pack_name: Optional[str] = Query(None, description="Pack name filter"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence"),
    max_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Maximum confidence"),
    date_from: Optional[datetime] = Query(None, description="Created from date"),
    date_to: Optional[datetime] = Query(None, description="Created to date"),
    updated_from: Optional[datetime] = Query(None, description="Updated from date"),
    updated_to: Optional[datetime] = Query(None, description="Updated to date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    db: Session = Depends(get_db)
) -> SearchResponse:
    """
    Search documents with advanced filtering and pagination.

    Args:
        query: Full-text search on extracted text
        document_type: Filter by document type
        pack_name: Filter by pack name
        min_confidence: Minimum confidence score
        max_confidence: Maximum confidence score
        date_from: Filter documents created from this date
        date_to: Filter documents created until this date
        updated_from: Filter documents updated from this date
        updated_to: Filter documents updated until this date
        page: Page number (1-indexed)
        page_size: Number of results per page (max 100)
        db: Database session

    Returns:
        SearchResponse with paginated results and metadata
    """
    # Validate filters
    filters = SearchFilters(
        query=query,
        document_type=document_type,
        pack_name=pack_name,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        date_from=date_from,
        date_to=date_to,
        updated_from=updated_from,
        updated_to=updated_to
    )

    # Build query
    query_builder = db.query(Document)
    conditions = []

    # Full-text search on extracted text
    if filters.query:
        conditions.append(Document.extracted_text.ilike(f"%{filters.query}%"))

    # Document type filter
    if filters.document_type:
        conditions.append(Document.document_type == filters.document_type)

    # Pack name filter
    if filters.pack_name:
        conditions.append(Document.pack_name == filters.pack_name)

    # Confidence score range
    if filters.min_confidence is not None:
        conditions.append(Document.confidence_score >= filters.min_confidence)
    if filters.max_confidence is not None:
        conditions.append(Document.confidence_score <= filters.max_confidence)

    # Date range filters
    if filters.date_from:
        conditions.append(Document.created_at >= filters.date_from)
    if filters.date_to:
        conditions.append(Document.created_at <= filters.date_to)
    if filters.updated_from:
        conditions.append(Document.updated_at >= filters.updated_from)
    if filters.updated_to:
        conditions.append(Document.updated_at <= filters.updated_to)

    # Apply all conditions
    if conditions:
        query_builder = query_builder.filter(and_(*conditions))

    # Get total count
    total = query_builder.count()

    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Execute query with pagination
    results = query_builder.order_by(Document.created_at.desc()).offset(offset).limit(page_size).all()

    return SearchResponse(
        results=[DocumentResult.from_orm(doc) for doc in results],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1
    )
