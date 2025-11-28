"""
Test error handling
"""
import pytest


def test_document_not_found(client):
    """Test 404 error for non-existent document"""
    response = client.get("/api/v1/documents/99999")
    assert response.status_code == 404
    data = response.json()
    assert 'error' in data or 'detail' in data


def test_invalid_file_upload(client):
    """Test file upload validation"""
    import io

    # Try to upload unsupported file type
    files = {'file': ('test.exe', io.BytesIO(b'fake exe'), 'application/exe')}

    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code in [400, 422, 500]


def test_pack_not_found(client):
    """Test 404 error for non-existent pack"""
    response = client.get("/api/v1/packs/99999")
    assert response.status_code == 404


def test_classification_without_text(client, db):
    """Test classification error handling"""
    from app.models.document import Document, ProcessingStatus
    from app.models.scenario_pack import ScenarioPack

    # Create document without extracted text
    document = Document(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        file_size=1000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED
    )
    db.add(document)
    db.commit()

    # Create pack
    pack = ScenarioPack(name="Test Pack", template_path="test.yaml")
    db.add(pack)
    db.commit()

    # Try to classify
    response = client.post(
        "/api/v1/classify",
        json={
            "document_id": document.id,
            "pack_id": pack.id
        }
    )

    # Should fail with 400 or 500
    assert response.status_code in [400, 500]
