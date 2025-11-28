"""
Classification API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.classification_service import ClassificationService
from app.services.embeddings_service import EmbeddingsService
from app.services.pack_service import ScenarioPackService
from app.models.document import Document
from pydantic import BaseModel

router = APIRouter()


class ClassificationRequest(BaseModel):
    document_id: int
    pack_id: int


class ClassificationResponse(BaseModel):
    document_id: int
    category_id: int
    category_name: str
    confidence: float
    embedding_generated: bool

    class Config:
        from_attributes = True


@router.post("/classify", response_model=ClassificationResponse)
async def classify_document(
    request: ClassificationRequest,
    db: Session = Depends(get_db)
):
    """Classify a document using LLM and generate embeddings"""
    # Get document
    document = db.query(Document).filter(Document.id == request.document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.extracted_text:
        raise HTTPException(status_code=400, detail="Document has no extracted text")

    # Get pack categories
    pack_service = ScenarioPackService(db)
    categories = pack_service.get_pack_categories(request.pack_id)

    if not categories:
        raise HTTPException(status_code=400, detail="No categories found for pack")

    try:
        # Classify document
        classification_service = ClassificationService()
        category_id, confidence = classification_service.classify_document(
            document.extracted_text,
            categories
        )

        # Generate embedding
        embeddings_service = EmbeddingsService()
        embedding = embeddings_service.generate_embedding(document.extracted_text)
        embedding_str = embeddings_service.serialize_embedding(embedding)

        # Update document
        document.assigned_category_id = category_id
        document.classification_confidence = confidence
        document.embedding_vector = embedding_str
        db.commit()
        db.refresh(document)

        # Get category name
        category = next((c for c in categories if c.id == category_id), None)
        category_name = category.name if category else "Unknown"

        return ClassificationResponse(
            document_id=document.id,
            category_id=category_id,
            category_name=category_name,
            confidence=confidence,
            embedding_generated=True
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify/batch")
async def classify_batch(
    pack_id: int,
    db: Session = Depends(get_db)
):
    """Classify all unclassified documents for a pack"""
    # Get all documents without classification
    documents = db.query(Document).filter(
        Document.assigned_category_id == None,
        Document.extracted_text != None
    ).all()

    if not documents:
        return {"message": "No documents to classify", "count": 0}

    # Get pack categories
    pack_service = ScenarioPackService(db)
    categories = pack_service.get_pack_categories(pack_id)

    if not categories:
        raise HTTPException(status_code=400, detail="No categories found for pack")

    classification_service = ClassificationService()
    embeddings_service = EmbeddingsService()

    classified_count = 0

    for document in documents:
        try:
            # Classify
            category_id, confidence = classification_service.classify_document(
                document.extracted_text,
                categories
            )

            # Generate embedding
            embedding = embeddings_service.generate_embedding(document.extracted_text)
            embedding_str = embeddings_service.serialize_embedding(embedding)

            # Update document
            document.assigned_category_id = category_id
            document.classification_confidence = confidence
            document.embedding_vector = embedding_str

            classified_count += 1

        except Exception as e:
            print(f"Failed to classify document {document.id}: {str(e)}")
            continue

    db.commit()

    return {
        "message": f"Classified {classified_count} documents",
        "count": classified_count
    }


from concurrent.futures import ThreadPoolExecutor, as_completed


@router.post("/classify/batch/optimized")
async def classify_batch_optimized(
    pack_id: int,
    max_workers: int = 3,
    db: Session = Depends(get_db)
):
    """Classify all unclassified documents using parallel processing"""
    # Get all documents without classification
    documents = db.query(Document).filter(
        Document.assigned_category_id == None,
        Document.extracted_text != None
    ).all()

    if not documents:
        return {"message": "No documents to classify", "count": 0}

    # Get pack categories
    pack_service = ScenarioPackService(db)
    categories = pack_service.get_pack_categories(pack_id)

    if not categories:
        raise HTTPException(status_code=400, detail="No categories found for pack")

    classification_service = ClassificationService()
    embeddings_service = EmbeddingsService()

    classified_count = 0
    failed_count = 0

    def classify_document(doc):
        """Classify a single document"""
        try:
            # Classify
            category_id, confidence = classification_service.classify_document(
                doc.extracted_text,
                categories
            )

            # Generate embedding
            embedding = embeddings_service.generate_embedding(doc.extracted_text)
            embedding_str = embeddings_service.serialize_embedding(embedding)

            return (doc.id, category_id, confidence, embedding_str, None)

        except Exception as e:
            return (doc.id, None, None, None, str(e))

    # Process documents in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(classify_document, doc): doc for doc in documents}

        for future in as_completed(futures):
            doc_id, category_id, confidence, embedding_str, error = future.result()

            if error:
                failed_count += 1
                print(f"Failed to classify document {doc_id}: {error}")
                continue

            # Update document in database
            document = db.query(Document).filter(Document.id == doc_id).first()
            if document:
                document.assigned_category_id = category_id
                document.classification_confidence = confidence
                document.embedding_vector = embedding_str
                classified_count += 1

    db.commit()

    return {
        "message": f"Classified {classified_count} documents ({failed_count} failed)",
        "count": classified_count,
        "failed": failed_count
    }
