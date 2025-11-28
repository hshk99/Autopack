"""
Documents API endpoints
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.document_service import DocumentService
from app.models.document import Document
from pydantic import BaseModel

router = APIRouter()


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_size: int
    file_type: str
    status: str
    extracted_text: str | None
    ocr_confidence: float | None

    class Config:
        from_attributes = True


@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a document for processing"""
    try:
        service = DocumentService(db)
        file_data = await file.read()
        document = service.upload_document(file.filename, file_data)
        return document
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/documents/{document_id}/process", response_model=DocumentResponse)
async def process_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Process document (extract text via OCR)"""
    try:
        service = DocumentService(db)
        document = service.process_document(document_id)
        return document
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Get document by ID"""
    service = DocumentService(db)
    document = service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(db: Session = Depends(get_db)):
    """List all documents"""
    service = DocumentService(db)
    return service.list_documents()


"""
Document update endpoints (append to existing documents.py)
"""

from pydantic import BaseModel as PydanticBaseModel


class UpdateCategoryRequest(PydanticBaseModel):
    category_id: int


class ApprovalRequest(PydanticBaseModel):
    approved: bool


@router.patch("/documents/{document_id}/category")
async def update_document_category(
    document_id: int,
    request: UpdateCategoryRequest,
    db: Session = Depends(get_db)
):
    """Update document's assigned category"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify category exists
    category = db.query(Category).filter(Category.id == request.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    document.assigned_category_id = request.category_id
    # Manual override = 100% confidence
    document.classification_confidence = 100.0
    db.commit()
    db.refresh(document)

    return {
        "message": "Category updated successfully",
        "document_id": document_id,
        "category_id": request.category_id
    }


@router.post("/documents/{document_id}/approve")
async def approve_document(
    document_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db)
):
    """Mark document as approved/rejected"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Add approval status to document metadata (could be a separate table in production)
    # For now, we'll just update confidence to 100% for approved documents
    if request.approved:
        document.classification_confidence = 100.0

    db.commit()
    db.refresh(document)

    return {
        "message": "Document approval status updated",
        "document_id": document_id,
        "approved": request.approved
    }


@router.get("/documents/search")
async def search_documents(
    filename: str = None,
    category_id: int = None,
    min_confidence: float = None,
    max_confidence: float = None,
    db: Session = Depends(get_db)
):
    """Search and filter documents"""
    query = db.query(Document)

    if filename:
        query = query.filter(Document.filename.contains(filename))

    if category_id:
        query = query.filter(Document.assigned_category_id == category_id)

    if min_confidence is not None:
        query = query.filter(Document.classification_confidence >= min_confidence)

    if max_confidence is not None:
        query = query.filter(Document.classification_confidence <= max_confidence)

    documents = query.all()
    return documents
