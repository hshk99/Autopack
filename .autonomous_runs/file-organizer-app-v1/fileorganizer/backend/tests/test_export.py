"""
Test export functionality
"""
import pytest
from pathlib import Path


def test_pdf_export(client, db):
    """Test PDF export generation"""
    from app.models.document import Document, ProcessingStatus
    from app.models.category import Category
    from app.models.scenario_pack import ScenarioPack

    # Create test data
    pack = ScenarioPack(name="Test Pack", template_path="test.yaml")
    db.add(pack)
    db.commit()

    category = Category(name="Income", description="Income documents", scenario_pack_id=pack.id)
    db.add(category)
    db.commit()

    document = Document(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        file_size=1000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED,
        assigned_category_id=category.id,
        classification_confidence=95.0
    )
    db.add(document)
    db.commit()

    # Export PDF
    response = client.get(f"/api/v1/export/pdf/{pack.id}")
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'


def test_excel_export(client, db):
    """Test Excel export generation"""
    from app.models.document import Document, ProcessingStatus
    from app.models.category import Category
    from app.models.scenario_pack import ScenarioPack

    # Create test data
    pack = ScenarioPack(name="Test Pack", template_path="test.yaml")
    db.add(pack)
    db.commit()

    category = Category(name="Income", description="Income documents", scenario_pack_id=pack.id)
    db.add(category)
    db.commit()

    document = Document(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        file_size=1000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED,
        assigned_category_id=category.id,
        classification_confidence=95.0
    )
    db.add(document)
    db.commit()

    # Export Excel
    response = client.get(f"/api/v1/export/excel/{pack.id}")
    assert response.status_code == 200
    assert 'spreadsheet' in response.headers['content-type']


def test_csv_export(client, db):
    """Test CSV export generation"""
    from app.models.document import Document, ProcessingStatus
    from app.models.category import Category
    from app.models.scenario_pack import ScenarioPack

    # Create test data
    pack = ScenarioPack(name="Test Pack", template_path="test.yaml")
    db.add(pack)
    db.commit()

    category = Category(name="Income", description="Income documents", scenario_pack_id=pack.id)
    db.add(category)
    db.commit()

    document = Document(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        file_size=1000,
        file_type=".pdf",
        status=ProcessingStatus.COMPLETED,
        assigned_category_id=category.id,
        classification_confidence=95.0
    )
    db.add(document)
    db.commit()

    # Export CSV
    response = client.get(f"/api/v1/export/csv/{pack.id}")
    assert response.status_code == 200
    assert response.headers['content-type'] == 'text/csv; charset=utf-8'
