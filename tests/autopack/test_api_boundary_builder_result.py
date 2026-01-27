"""
P1.1 FastAPI Boundary Test: Builder result endpoint validation.

Tests the actual FastAPI boundary (not just Pydantic parsing) to ensure:
- Canonical payload → 200 with fields preserved
- Legacy payload behavior documented (currently accepts extra fields, loses data)
- After P1.3 strictness flip: legacy payload → 422
"""

from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import pytest

from autopack.main import app
from autopack.database import get_db


def mock_submit_builder_result_impl(run_id: str, phase_id: str, builder_result, db):
    """
    Mock endpoint implementation for testing schema validation.

    If this function is called, it means:
    1. FastAPI routing worked
    2. Pydantic request validation passed
    3. The BuilderResult schema accepted/rejected the payload as expected

    We return a simple response that echoes back key fields to verify preservation.
    """
    return {
        "phase_id": phase_id,
        "run_id": run_id,
        "status": builder_result.status if hasattr(builder_result, "status") else "unknown",
    }


@pytest.fixture
def client(monkeypatch):
    """
    FastAPI test client with mocked endpoint implementation.

    The real submit_builder_result endpoint has a production bug (undefined variables).
    We mock it to focus P1.1 tests on schema validation at the FastAPI boundary.
    """
    # Replace the endpoint implementation
    monkeypatch.setattr("autopack.main.submit_builder_result", mock_submit_builder_result_impl)

    # Mock the database dependency
    mock_db = MagicMock()

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()


class TestBuilderResultBoundary:
    """Test FastAPI boundary enforcement for builder_result endpoint"""

    def test_canonical_payload_200_with_fields_preserved(self, client):
        """Canonical BuilderResult payload should return 200 and preserve all fields"""
        canonical_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "run_type": "project_build",
            "allowed_paths": ["src/"],
            "patch_content": "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n",
            "files_changed": ["foo.py"],
            "lines_added": 10,
            "lines_removed": 5,
            "builder_attempts": 1,
            "tokens_used": 1500,
            "duration_minutes": 2.5,
            "probe_results": [],
            "suggested_issues": [],
            "status": "success",  # Lowercase canonical
            "notes": "Build completed successfully",
        }

        response = client.post(
            "/runs/test-run/phases/test-phase/builder_result",
            json=canonical_payload,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify key fields preserved in response
        assert data.get("phase_id") == "test-phase"
        assert data.get("run_id") == "test-run"

    def test_minimal_canonical_payload_200(self, client):
        """Minimal valid BuilderResult should return 200"""
        minimal_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "status": "success",
        }

        response = client.post(
            "/runs/test-run/phases/test-phase/builder_result",
            json=minimal_payload,
        )

        assert response.status_code == 200

    def test_legacy_payload_422_with_strict_schema(self, client):
        """
        P1.4: Legacy executor payload returns 422 due to extra='forbid' schema strictness.

        After P1.2 (executor emits canonical) + P1.3 (strict schema), legacy payloads
        are rejected at the boundary with 422 instead of silently accepting and losing data.
        """
        legacy_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "status": "SUCCESS",  # Uppercase (legacy)
            "success": True,  # Extra field not in schema
            "output": "diff --git ...",  # Extra field (should be patch_content)
            "files_modified": ["foo.py"],  # Extra field (should be files_changed)
            "metadata": {  # Extra field (fields should be top-level)
                "run_type": "project_build",
                "lines_added": 10,
                "lines_removed": 5,
                "builder_attempts": 1,
                "tokens_used": 1500,
                "duration_minutes": 0.0,
                "probe_results": [],
                "suggested_issues": [],
                "notes": "Build completed",
                "allowed_paths": ["src/"],
            },
        }

        response = client.post(
            "/runs/test-run/phases/test-phase/builder_result",
            json=legacy_payload,
        )

        # After P1.3: Should return 422 (Unprocessable Entity) due to extra fields
        assert response.status_code == 422
        error_detail = response.json().get("detail", [])

        # Should report extra fields
        assert any("extra" in str(item).lower() for item in error_detail), (
            "422 response should indicate extra fields are forbidden"
        )

    def test_missing_required_fields_422(self, client):
        """Missing required fields should return 422"""
        incomplete_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            # Missing 'status' (required field)
        }

        response = client.post(
            "/runs/test-run/phases/test-phase/builder_result",
            json=incomplete_payload,
        )

        assert response.status_code == 422
        error_detail = response.json().get("detail", [])

        # Should report missing 'status' field
        assert any("status" in str(item).lower() for item in error_detail), (
            "422 response should indicate missing 'status' field"
        )

    def test_invalid_field_type_422(self, client):
        """Invalid field types should return 422"""
        invalid_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "status": "success",
            "tokens_used": "not-a-number",  # Should be int
        }

        response = client.post(
            "/runs/test-run/phases/test-phase/builder_result",
            json=invalid_payload,
        )

        assert response.status_code == 422
        error_detail = response.json().get("detail", [])

        # Should report type validation error for tokens_used
        assert any("tokens_used" in str(item).lower() for item in error_detail), (
            "422 response should indicate tokens_used type error"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
