"""
Test triage board functionality
"""


def test_update_document_category(client, db):
    """Test updating document category"""
    from app.models.document import Document, ProcessingStatus
    from app.models.category import Category
    from app.models.scenario_pack import ScenarioPack

    # Create test pack and category
    pack = ScenarioPack(name="Test Pack", template_path="test.yaml")
    db.add(pack)
    db.commit()

    category = Category(name="Test Category", scenario_pack_id=pack.id)
    db.add(category)
    db.commit()

    # Create test document
    document = Document(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        file_size=1000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED
    )
    db.add(document)
    db.commit()

    # Update category
    response = client.patch(
        f"/api/v1/documents/{document.id}/category",
        json={"category_id": category.id}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["category_id"] == category.id

    # Verify database update
    db.refresh(document)
    assert document.assigned_category_id == category.id
    assert document.classification_confidence == 100.0  # Manual override


def test_approve_document(client, db):
    """Test approving document"""
    from app.models.document import Document, ProcessingStatus

    # Create test document
    document = Document(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        file_size=1000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED,
        classification_confidence=75.0
    )
    db.add(document)
    db.commit()

    # Approve document
    response = client.post(
        f"/api/v1/documents/{document.id}/approve",
        json={"approved": True}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is True

    # Verify confidence updated
    db.refresh(document)
    assert document.classification_confidence == 100.0


def test_search_documents(client, db):
    """Test document search and filtering"""
    from app.models.document import Document, ProcessingStatus
    from app.models.category import Category
    from app.models.scenario_pack import ScenarioPack

    # Create test data
    pack = ScenarioPack(name="Test Pack", template_path="test.yaml")
    db.add(pack)
    db.commit()

    category = Category(name="Income", scenario_pack_id=pack.id)
    db.add(category)
    db.commit()

    # Create documents
    doc1 = Document(
        filename="invoice_2024.pdf",
        original_path="/tmp/invoice.pdf",
        file_size=1000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED,
        assigned_category_id=category.id,
        classification_confidence=85.0
    )

    doc2 = Document(
        filename="receipt.pdf",
        original_path="/tmp/receipt.pdf",
        file_size=2000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED,
        assigned_category_id=category.id,
        classification_confidence=60.0
    )

    db.add_all([doc1, doc2])
    db.commit()

    # Search by filename
    response = client.get("/api/v1/documents/search?filename=invoice")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["filename"] == "invoice_2024.pdf"

    # Filter by confidence
    response = client.get("/api/v1/documents/search?min_confidence=80")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["classification_confidence"] >= 80
