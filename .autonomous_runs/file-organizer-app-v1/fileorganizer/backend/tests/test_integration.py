"""
Full integration test suite
"""
import pytest
from pathlib import Path


class TestFullWorkflow:
    """Test complete end-to-end workflows"""

    def test_tax_pack_workflow(self, client, db):
        """Test complete Tax pack workflow"""
        from app.services.pack_service import ScenarioPackService
        from app.models.document import Document, ProcessingStatus

        # 1. Load Tax pack
        pack_service = ScenarioPackService(db)
        pack_path = Path("packs/tax_generic.yaml")

        if not pack_path.exists():
            pytest.skip("Tax pack not found")

        pack = pack_service.load_pack_from_yaml(pack_path)
        categories = pack_service.get_pack_categories(pack.id)

        assert len(categories) > 0
        income_cat = next(c for c in categories if "income" in c.name.lower())

        # 2. Create test document
        doc = Document(
            filename="w2_form.pdf",
            original_path="/tmp/w2.pdf",
            file_size=5000,
            file_type=".pdf",
            status=ProcessingStatus.COMPLETED,
            extracted_text="W-2 Wage and Tax Statement for 2024. Employer: ABC Corp. Wages: $75,000",
            ocr_confidence=95.0
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # 3. Classify document
        doc.assigned_category_id = income_cat.id
        doc.classification_confidence = 90.0
        db.commit()

        # 4. Approve document
        response = client.post(
            f"/api/v1/documents/{doc.id}/approve",
            json={"approved": True}
        )
        assert response.status_code == 200

        # 5. Export pack
        response = client.get(f"/api/v1/export/pdf/{pack.id}")
        assert response.status_code == 200
        assert len(response.content) > 0

        print("[OK] Tax pack workflow completed successfully")

    def test_immigration_pack_workflow(self, client, db):
        """Test complete Immigration pack workflow"""
        from app.services.pack_service import ScenarioPackService
        from app.models.document import Document, ProcessingStatus

        # Load Immigration pack
        pack_service = ScenarioPackService(db)
        pack_path = Path("packs/immigration_generic.yaml")

        if not pack_path.exists():
            pytest.skip("Immigration pack not found")

        pack = pack_service.load_pack_from_yaml(pack_path)
        categories = pack_service.get_pack_categories(pack.id)

        # Create multiple documents
        test_docs = [
            ("passport.pdf", "identity", "Passport of John Doe, valid until 2030"),
            ("bank_statement.pdf", "financial", "Bank statement showing balance $50,000"),
            ("employment_letter.pdf", "employment", "Employment letter from XYZ Inc"),
        ]

        for filename, cat_hint, text in test_docs:
            doc = Document(
                filename=filename,
                original_path=f"/tmp/{filename}",
                file_size=3000,
                file_type=".pdf",
                status=ProcessingStatus.COMPLETED,
                extracted_text=text,
                ocr_confidence=92.0
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            # Assign category
            matching_cat = next(
                (c for c in categories if cat_hint in c.name.lower()),
                categories[0]
            )
            doc.assigned_category_id = matching_cat.id
            doc.classification_confidence = 88.0
            db.commit()

        # Export all formats
        for format_type in ['pdf', 'excel', 'csv']:
            response = client.get(f"/api/v1/export/{format_type}/{pack.id}")
            assert response.status_code == 200

        print("[OK] Immigration pack workflow completed successfully")

    def test_error_handling(self, client, db):
        """Test error handling scenarios"""
        # Test 404 errors
        response = client.get("/api/v1/documents/99999")
        assert response.status_code == 404

        response = client.get("/api/v1/packs/99999")
        assert response.status_code == 404

        # Test invalid operations
        response = client.post(
            "/api/v1/documents/99999/approve",
            json={"approved": True}
        )
        assert response.status_code == 404

        print("[OK] Error handling tests passed")


class TestAPIEndpoints:
    """Test all API endpoints"""

    def test_health_endpoints(self, client):
        """Test health check endpoints"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

        response = client.get("/api/v1/health/db")
        assert response.status_code == 200

    def test_document_endpoints(self, client):
        """Test document endpoints"""
        # List documents
        response = client.get("/api/v1/documents")
        assert response.status_code == 200

        # Search documents
        response = client.get("/api/v1/documents/search?filename=test")
        assert response.status_code == 200

    def test_pack_endpoints(self, client, db):
        """Test pack endpoints"""
        from app.services.pack_service import ScenarioPackService

        # Load a pack first
        pack_service = ScenarioPackService(db)
        pack_path = Path("packs/tax_generic.yaml")

        if not pack_path.exists():
            pytest.skip("Tax pack not found")

        pack = pack_service.load_pack_from_yaml(pack_path)

        # List packs
        response = client.get("/api/v1/packs")
        assert response.status_code == 200
        packs = response.json()
        assert len(packs) > 0

        # Get specific pack
        response = client.get(f"/api/v1/packs/{pack.id}")
        assert response.status_code == 200

        # Get pack categories
        response = client.get(f"/api/v1/packs/{pack.id}/categories")
        assert response.status_code == 200
        categories = response.json()
        assert len(categories) > 0


def test_all_packs_functional(db):
    """Verify all pack templates are functional"""
    from app.services.pack_service import ScenarioPackService

    pack_service = ScenarioPackService(db)
    packs_dir = Path("packs")

    yaml_files = list(packs_dir.glob("*.yaml"))
    assert len(yaml_files) >= 3, "Expected at least 3 pack templates"

    for yaml_file in yaml_files:
        pack = pack_service.load_pack_from_yaml(yaml_file)
        categories = pack_service.get_pack_categories(pack.id)

        assert pack.name
        assert len(categories) > 0

        # Verify each category has required fields
        for cat in categories:
            assert cat.name
            assert cat.scenario_pack_id == pack.id

    print(f"[OK] All {len(yaml_files)} packs are functional")
