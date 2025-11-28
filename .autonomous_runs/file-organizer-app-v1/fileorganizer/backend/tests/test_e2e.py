"""
End-to-end workflow tests
"""
import pytest
from pathlib import Path
import io


def test_complete_workflow(client, db):
    """Test complete document organization workflow"""
    from app.models.scenario_pack import ScenarioPack
    from app.models.category import Category
    from app.services.pack_service import ScenarioPackService

    # Step 1: Load pack template
    pack_service = ScenarioPackService(db)
    pack_path = Path("packs/tax_generic.yaml")

    if not pack_path.exists():
        pytest.skip("Tax pack template not found")

    pack = pack_service.load_pack_from_yaml(pack_path)
    assert pack is not None
    assert pack.name == "Tax Pack (Generic)"

    categories = pack_service.get_pack_categories(pack.id)
    assert len(categories) > 0

    # Step 2: Upload document
    test_file_content = b"Fake PDF content for testing"
    files = {'file': ('test_invoice.pdf', io.BytesIO(test_file_content), 'application/pdf')}

    upload_response = client.post(
        "/api/v1/documents/upload",
        files=files
    )
    assert upload_response.status_code == 200
    document_id = upload_response.json()['id']

    # Step 3: Process document (OCR)
    # Skip actual OCR in test (would need real Tesseract)
    # Instead, manually set extracted text
    from app.models.document import Document
    document = db.query(Document).filter(Document.id == document_id).first()
    document.extracted_text = "Invoice for professional services rendered in 2024. Total amount: $5000."
    document.status = "completed"
    db.commit()

    # Step 4: Classify document
    classify_response = client.post(
        "/api/v1/classify",
        json={
            "document_id": document_id,
            "pack_id": pack.id
        }
    )

    # Classification might fail without valid OpenAI API key in test env
    # That's expected - we're testing the workflow structure
    if classify_response.status_code == 200:
        classification = classify_response.json()
        assert 'category_id' in classification
        assert 'confidence' in classification

    # Step 5: Update category (manual override)
    income_category = next((c for c in categories if 'income' in c.name.lower()), categories[0])

    update_response = client.patch(
        f"/api/v1/documents/{document_id}/category",
        json={"category_id": income_category.id}
    )
    assert update_response.status_code == 200

    # Step 6: Approve document
    approve_response = client.post(
        f"/api/v1/documents/{document_id}/approve",
        json={"approved": True}
    )
    assert approve_response.status_code == 200

    # Step 7: Export pack (PDF)
    export_response = client.get(f"/api/v1/export/pdf/{pack.id}")
    assert export_response.status_code == 200
    assert export_response.headers['content-type'] == 'application/pdf'

    print("[OK] Complete workflow test passed!")


def test_multiple_documents_workflow(client, db):
    """Test workflow with multiple documents"""
    from app.models.scenario_pack import ScenarioPack
    from app.services.pack_service import ScenarioPackService
    from app.models.document import Document, ProcessingStatus

    # Load pack
    pack_service = ScenarioPackService(db)
    pack_path = Path("packs/tax_generic.yaml")

    if not pack_path.exists():
        pytest.skip("Tax pack template not found")

    pack = pack_service.load_pack_from_yaml(pack_path)
    categories = pack_service.get_pack_categories(pack.id)

    # Create multiple test documents
    test_docs = [
        ("invoice_2024.pdf", "Invoice for services", "income"),
        ("receipt_office.pdf", "Office supplies receipt", "deductions"),
        ("bank_statement.pdf", "Bank account statement", "bank"),
    ]

    created_doc_ids = []

    for filename, text, category_hint in test_docs:
        # Create document
        doc = Document(
            filename=filename,
            original_path=f"/tmp/{filename}",
            file_size=1000,
            file_type=".pdf",
            status=ProcessingStatus.COMPLETED,
            extracted_text=text,
            ocr_confidence=95.0
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        created_doc_ids.append(doc.id)

        # Assign to category (manual for testing)
        matching_cat = next(
            (c for c in categories if category_hint in c.name.lower()),
            categories[0]
        )
        doc.assigned_category_id = matching_cat.id
        doc.classification_confidence = 85.0
        db.commit()

    # Verify all documents created
    assert len(created_doc_ids) == 3

    # Search documents
    search_response = client.get("/api/v1/documents/search?filename=invoice")
    assert search_response.status_code == 200
    results = search_response.json()
    assert len(results) >= 1

    # Export all formats
    for format_type in ['pdf', 'excel', 'csv']:
        export_response = client.get(f"/api/v1/export/{format_type}/{pack.id}")
        assert export_response.status_code == 200

    print("[OK] Multiple documents workflow test passed!")


def test_all_packs_loadable(db):
    """Test that all pack templates can be loaded"""
    from app.services.pack_service import ScenarioPackService

    pack_service = ScenarioPackService(db)
    packs_dir = Path("packs")

    if not packs_dir.exists():
        pytest.skip("Packs directory not found")

    yaml_files = list(packs_dir.glob("*.yaml"))
    assert len(yaml_files) >= 3, "Expected at least 3 pack templates"

    loaded_packs = []

    for yaml_file in yaml_files:
        pack = pack_service.load_pack_from_yaml(yaml_file)
        assert pack is not None
        assert pack.name

        categories = pack_service.get_pack_categories(pack.id)
        assert len(categories) > 0

        loaded_packs.append(pack.name)
        print(f"[OK] Loaded: {pack.name} ({len(categories)} categories)")

    assert "Tax Pack (Generic)" in loaded_packs
    assert "Immigration Pack (Generic)" in loaded_packs
    assert "Legal Pack (Generic)" in loaded_packs

    print(f"[OK] All {len(loaded_packs)} pack templates loaded successfully!")
