"""
Tests for batch upload API endpoint.
"""

import io
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture
def mock_queue_processing():
    """Mock the queue_batch_processing function."""
    with patch("src.backend.api.batch.queue_batch_processing") as mock:
        yield mock


@pytest.fixture
def mock_validate_file():
    """Mock the validate_file function."""
    with patch("src.backend.api.batch.validate_file") as mock:
        mock.return_value = {
            "valid": True,
            "mime_type": "image/jpeg",
            "error": None,
        }
        yield mock


def create_test_file(filename: str, content: bytes = b"test content") -> tuple:
    """Create a test file for upload."""
    return (filename, io.BytesIO(content), "image/jpeg")


def test_upload_batch_success(client: TestClient, mock_queue_processing, mock_validate_file):
    """Test successful batch upload."""
    files = [
        create_test_file("test1.jpg"),
        create_test_file("test2.jpg"),
    ]

    response = client.post(
        "/api/v1/batch/upload",
        files=[("files", file) for file in files],
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()

    assert "batch_id" in data
    assert data["total_files"] == 2
    assert data["accepted_files"] == 2
    assert data["rejected_files"] == 0
    assert len(data["jobs"]) == 2
    assert len(data["errors"]) == 0

    # Verify each job has required fields
    for job in data["jobs"]:
        assert "file_id" in job
        assert "filename" in job
        assert "job_id" in job
        assert job["status"] == "queued"

    # Verify queue_batch_processing was called for each file
    assert mock_queue_processing.call_count == 2


def test_upload_batch_no_files(client: TestClient):
    """Test batch upload with no files."""
    response = client.post("/api/v1/batch/upload")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_upload_batch_exceeds_limit(client: TestClient):
    """Test batch upload exceeding maximum batch size."""
    # Create more files than allowed
    files = [create_test_file(f"test{i}.jpg") for i in range(51)]

    response = client.post(
        "/api/v1/batch/upload",
        files=[("files", file) for file in files],
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "exceeds maximum" in response.json()["detail"]


def test_upload_batch_invalid_file_type(client: TestClient, mock_queue_processing):
    """Test batch upload with invalid file type."""
    with patch("src.backend.api.batch.validate_file") as mock_validate:
        mock_validate.return_value = {
            "valid": False,
            "mime_type": "text/plain",
            "error": "File type 'text/plain' is not supported",
        }

        files = [create_test_file("test.txt")]

        response = client.post(
            "/api/v1/batch/upload",
            files=[("files", file) for file in files],
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No valid files" in response.json()["detail"]


def test_upload_batch_mixed_valid_invalid(
    client: TestClient, mock_queue_processing
):
    """Test batch upload with mix of valid and invalid files."""
    files = [
        create_test_file("valid.jpg"),
        create_test_file("invalid.txt"),
    ]

    def validate_side_effect(content, filename, max_size, allowed_types):
        if filename == "valid.jpg":
            return {"valid": True, "mime_type": "image/jpeg", "error": None}
        else:
            return {
                "valid": False,
                "mime_type": "text/plain",
                "error": "File type not supported",
            }

    with patch("src.backend.api.batch.validate_file", side_effect=validate_side_effect):
        response = client.post(
            "/api/v1/batch/upload",
            files=[("files", file) for file in files],
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()

        assert data["total_files"] == 2
        assert data["accepted_files"] == 1
        assert data["rejected_files"] == 1
        assert len(data["jobs"]) == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["filename"] == "invalid.txt"


def test_get_batch_status_not_implemented(client: TestClient):
    """Test batch status endpoint (not yet implemented)."""
    response = client.get("/api/v1/batch/test-batch-id/status")

    assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


@pytest.fixture
def client():
    """Create test client."""
    from src.backend.main import app
    return TestClient(app)
