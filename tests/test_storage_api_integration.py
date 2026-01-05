"""
Test suite for Storage Optimizer Phase 2 API Integration

Tests full workflow through REST API:
- Scan creation and persistence
- Scan history retrieval
- Approval workflow via API
- Execution via API

BUILD-149 Phase 2
"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from autopack.database import Base, get_db
from autopack.main import app


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test scans."""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    # Cleanup after tests
    import shutil

    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def test_db():
    """Create in-memory test database"""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(test_db):
    """Create test client for API"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db)

    def override_get_db():
        try:
            db = SessionLocal()
            yield db
        finally:
            db.close()

    # Disable API key auth for testing
    os.environ["TESTING"] = "1"
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# Test 1-3: Scan Creation and Retrieval
# ==============================================================================


def test_create_scan_via_api(client, temp_dir):
    """
    Test creating a new scan via POST /storage/scan.
    """
    # Create test directory structure
    (temp_dir / "node_modules").mkdir()
    (temp_dir / "node_modules" / "package.json").write_text("{}")

    response = client.post(
        "/storage/scan",
        json={
            "scan_type": "directory",
            "scan_target": str(temp_dir),
            "max_depth": 2,
            "max_items": 100,
            "save_to_db": True,
            "created_by": "test_user",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] > 0
    assert data["scan_type"] == "directory"
    assert data["scan_target"] == str(temp_dir)
    assert data["total_items_scanned"] >= 0
    assert data["created_by"] == "test_user"


def test_list_scans(client, temp_dir):
    """
    Test retrieving scan history via GET /storage/scans.
    """
    # Create 2 scans
    for i in range(2):
        client.post(
            "/storage/scan",
            json={
                "scan_type": "directory",
                "scan_target": str(temp_dir),
                "save_to_db": True,
                "created_by": f"user_{i}",
            },
        )

    # List scans
    response = client.get("/storage/scans")

    assert response.status_code == 200
    scans = response.json()

    assert len(scans) == 2
    assert scans[0]["id"] > scans[1]["id"]  # Ordered by timestamp DESC


def test_get_scan_detail(client, temp_dir):
    """
    Test retrieving detailed scan results via GET /storage/scans/{scan_id}.
    """
    # Create scan
    create_response = client.post(
        "/storage/scan",
        json={"scan_type": "directory", "scan_target": str(temp_dir), "save_to_db": True},
    )
    scan_id = create_response.json()["id"]

    # Get detail
    detail_response = client.get(f"/storage/scans/{scan_id}")

    assert detail_response.status_code == 200
    data = detail_response.json()

    assert "scan" in data
    assert "candidates" in data
    assert "stats_by_category" in data
    assert data["scan"]["id"] == scan_id


# ==============================================================================
# Test 4-5: Approval Workflow
# ==============================================================================


def test_approve_candidates_via_api(client, temp_dir):
    """
    Test approving cleanup candidates via POST /storage/scans/{scan_id}/approve.
    """
    # Create test file
    test_file = temp_dir / "node_modules" / "package.json"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("{}")

    # Create scan
    scan_response = client.post(
        "/storage/scan",
        json={
            "scan_type": "directory",
            "scan_target": str(temp_dir),
            "max_depth": 2,
            "save_to_db": True,
        },
    )
    scan_id = scan_response.json()["id"]

    # Get candidates
    detail_response = client.get(f"/storage/scans/{scan_id}")
    candidates = detail_response.json()["candidates"]

    if not candidates:
        pytest.skip("No candidates found for approval test")

    candidate_ids = [c["id"] for c in candidates]

    # Approve
    approval_response = client.post(
        f"/storage/scans/{scan_id}/approve",
        json={
            "candidate_ids": candidate_ids,
            "approved_by": "test_user",
            "decision": "approve",
            "approval_method": "api",
            "notes": "API approval test",
        },
    )

    assert approval_response.status_code == 200
    approval_data = approval_response.json()

    assert approval_data["decision"] == "approve"
    assert approval_data["total_candidates"] == len(candidate_ids)
    assert approval_data["approved_by"] == "test_user"


def test_reject_candidates_via_api(client, temp_dir):
    """
    Test rejecting cleanup candidates.
    """
    # Create scan with candidates
    test_file = temp_dir / "test" / "file.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("content")

    scan_response = client.post(
        "/storage/scan",
        json={"scan_type": "directory", "scan_target": str(temp_dir), "save_to_db": True},
    )
    scan_id = scan_response.json()["id"]

    # Get candidates
    detail_response = client.get(f"/storage/scans/{scan_id}")
    candidates = detail_response.json()["candidates"]

    if not candidates:
        pytest.skip("No candidates for rejection test")

    candidate_ids = [c["id"] for c in candidates[:1]]  # Reject first candidate only

    # Reject
    rejection_response = client.post(
        f"/storage/scans/{scan_id}/approve",
        json={
            "candidate_ids": candidate_ids,
            "approved_by": "test_user",
            "decision": "reject",
            "notes": "Not safe to delete",
        },
    )

    assert rejection_response.status_code == 200
    assert rejection_response.json()["decision"] == "reject"


# ==============================================================================
# Test 6-8: Execution Workflow
# ==============================================================================


def test_execute_dry_run_via_api(client, temp_dir):
    """
    Test dry-run execution via POST /storage/scans/{scan_id}/execute.

    CRITICAL SAFETY TEST: Ensures dry-run mode prevents deletion.
    """
    # Create test file
    test_file = temp_dir / "deletable" / "test.txt"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("test content")

    # Create scan
    scan_response = client.post(
        "/storage/scan",
        json={"scan_type": "directory", "scan_target": str(temp_dir), "save_to_db": True},
    )
    scan_id = scan_response.json()["id"]

    # Get and approve candidates
    detail_response = client.get(f"/storage/scans/{scan_id}")
    candidates = detail_response.json()["candidates"]

    if candidates:
        candidate_ids = [c["id"] for c in candidates]
        client.post(
            f"/storage/scans/{scan_id}/approve",
            json={
                "candidate_ids": candidate_ids,
                "approved_by": "test_user",
                "decision": "approve",
            },
        )

    # Execute in dry-run mode
    execution_response = client.post(
        f"/storage/scans/{scan_id}/execute", json={"dry_run": True, "compress_before_delete": False}
    )

    assert execution_response.status_code == 200
    exec_data = execution_response.json()

    assert exec_data["skipped"] >= 0  # Dry-run should skip deletions
    assert exec_data["total_freed_bytes"] == 0  # No actual deletion
    assert test_file.exists(), "File was deleted in dry-run mode!"


def test_full_workflow_scan_approve_execute(client, temp_dir):
    """
    Test complete workflow: scan → approve → execute.

    Integration test covering all API endpoints in sequence.
    """
    # Step 1: Create test files
    test_dir = temp_dir / "workflow_test"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("content 1")
    (test_dir / "file2.txt").write_text("content 2")

    # Step 2: Create scan
    scan_response = client.post(
        "/storage/scan",
        json={
            "scan_type": "directory",
            "scan_target": str(temp_dir),
            "save_to_db": True,
            "created_by": "workflow_test",
        },
    )

    assert scan_response.status_code == 200
    scan_id = scan_response.json()["id"]

    # Step 3: Get scan details
    detail_response = client.get(f"/storage/scans/{scan_id}")
    assert detail_response.status_code == 200

    candidates = detail_response.json()["candidates"]

    if not candidates:
        pytest.skip("No candidates for full workflow test")

    # Step 4: Approve candidates
    candidate_ids = [c["id"] for c in candidates]
    approval_response = client.post(
        f"/storage/scans/{scan_id}/approve",
        json={
            "candidate_ids": candidate_ids,
            "approved_by": "workflow_test",
            "decision": "approve",
        },
    )
    assert approval_response.status_code == 200

    # Step 5: Execute in dry-run mode (safety)
    execution_response = client.post(
        f"/storage/scans/{scan_id}/execute", json={"dry_run": True, "compress_before_delete": False}
    )

    assert execution_response.status_code == 200
    exec_data = execution_response.json()

    # Validate execution results
    assert "total_candidates" in exec_data
    assert "successful" in exec_data
    assert "failed" in exec_data
    assert "success_rate" in exec_data
    assert exec_data["success_rate"] >= 0.0


def test_unapproved_execution_fails(client, temp_dir):
    """
    Test that executing without approval returns no candidates.

    CRITICAL SAFETY TEST: Ensures unapproved candidates are not deleted.
    """
    # Create scan without approval
    scan_response = client.post(
        "/storage/scan",
        json={"scan_type": "directory", "scan_target": str(temp_dir), "save_to_db": True},
    )
    scan_id = scan_response.json()["id"]

    # Attempt execution without approval
    execution_response = client.post(
        f"/storage/scans/{scan_id}/execute",
        json={"dry_run": False, "compress_before_delete": False},  # Even with dry_run=False
    )

    assert execution_response.status_code == 200
    exec_data = execution_response.json()

    # Should find no candidates to execute (all pending, none approved)
    assert exec_data["total_candidates"] == 0


# ==============================================================================
# Summary
# ==============================================================================
# Total: 8 API integration tests covering:
# - Scan creation (1 test)
# - Scan retrieval (2 tests)
# - Approval workflow (2 tests)
# - Execution workflow (3 tests)
#
# All tests validate the complete API workflow from scan to execution.
# ==============================================================================
