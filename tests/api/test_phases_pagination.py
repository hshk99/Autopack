"""Tests for phases endpoint pagination (IMP-044)"""

from datetime import datetime, timezone

import pytest

from autopack import models


@pytest.fixture
def test_run_and_tier(db_session):
    """Create a test run and tier for pagination testing"""
    # Create a run
    run = models.Run(
        id="pagination-test-run",
        state=models.RunState.PHASE_EXECUTION,
        safety_profile="normal",
        run_scope="multi_tier",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.flush()

    # Create a tier
    tier = models.Tier(
        run_id="pagination-test-run",
        tier_id="T1",
        tier_index=0,
        name="Test Tier",
        state=models.TierState.IN_PROGRESS,
        cleanliness="clean",
    )
    db_session.add(tier)
    db_session.commit()

    return run.id, tier.id


@pytest.fixture
def setup_phases_for_pagination(db_session, test_run_and_tier):
    """Create 100 test phases for pagination testing"""
    run_id, tier_id = test_run_and_tier

    # Create 100 phases
    for i in range(100):
        phase = models.Phase(
            phase_id=f"phase-{i:03d}",
            run_id=run_id,
            tier_id=tier_id,
            phase_index=i,
            name=f"Test Phase {i}",
            description=f"Description for phase {i}",
            state=models.PhaseState.QUEUED,
        )
        db_session.add(phase)

    db_session.commit()
    return run_id


def test_phases_pagination_page_1(client, setup_phases_for_pagination):
    """Verify phases endpoint returns first page correctly"""
    response = client.get("/phases?page=1&page_size=50")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 50
    assert data["total"] == 100
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert data["has_next"] is True


def test_phases_pagination_page_2(client, setup_phases_for_pagination):
    """Verify phases endpoint returns second page correctly"""
    response = client.get("/phases?page=2&page_size=50")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 50
    assert data["total"] == 100
    assert data["page"] == 2
    assert data["page_size"] == 50
    assert data["has_next"] is False


def test_phases_pagination_beyond_last_page(client, setup_phases_for_pagination):
    """Verify phases endpoint returns empty items when page is beyond total"""
    response = client.get("/phases?page=3&page_size=50")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 0
    assert data["total"] == 100
    assert data["page"] == 3
    assert data["page_size"] == 50
    assert data["has_next"] is False


def test_phases_pagination_max_page_size(client, setup_phases_for_pagination):
    """Verify page_size is capped at 100"""
    response = client.get("/phases?page_size=999")

    assert response.status_code == 200
    data = response.json()

    # Should return first 100 items (all of them) because page_size is capped at 100
    assert len(data["items"]) == 100
    assert data["page_size"] == 100
    assert data["has_next"] is False


def test_phases_pagination_min_page_size(client):
    """Verify page_size minimum is 1"""
    response = client.get("/phases?page_size=0")

    assert response.status_code == 200
    data = response.json()

    # page_size should be at least 1
    assert data["page_size"] >= 1


def test_phases_pagination_custom_page_size(client, setup_phases_for_pagination):
    """Verify custom page_size works correctly"""
    response = client.get("/phases?page=1&page_size=25")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 25
    assert data["page_size"] == 25
    assert data["has_next"] is True


def test_phases_pagination_with_run_id_filter(db_session, client, test_run_and_tier):
    """Verify pagination works with run_id filter"""
    run_id, tier_id = test_run_and_tier

    # Create phases for the test run
    for i in range(30):
        phase = models.Phase(
            phase_id=f"run1-phase-{i:03d}",
            run_id=run_id,
            tier_id=tier_id,
            phase_index=i,
            name=f"Run 1 Phase {i}",
        )
        db_session.add(phase)

    # Create a second run with different phases
    run2 = models.Run(
        id="run-2",
        state=models.RunState.PHASE_EXECUTION,
        safety_profile="normal",
        run_scope="multi_tier",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run2)
    db_session.flush()

    # Create tier for run 2
    tier2 = models.Tier(
        run_id="run-2",
        tier_id="T1",
        tier_index=0,
        name="Tier 1",
        state=models.TierState.PENDING,
        cleanliness="clean",
    )
    db_session.add(tier2)
    db_session.flush()

    # Add phases for run 2
    for i in range(20):
        phase = models.Phase(
            phase_id=f"run2-phase-{i:03d}",
            run_id="run-2",
            tier_id=tier2.id,
            phase_index=i,
            name=f"Run 2 Phase {i}",
        )
        db_session.add(phase)

    db_session.commit()

    # Query phases for test_run_id with pagination
    response = client.get(f"/phases?run_id={run_id}&page=1&page_size=20")

    assert response.status_code == 200
    data = response.json()

    # Should return only phases from run_id
    assert len(data["items"]) == 20
    assert data["total"] == 30
    assert data["has_next"] is True

    # Verify all items belong to run_id
    for item in data["items"]:
        assert item["run_id"] == run_id


def test_phases_pagination_response_structure(db_session, client, test_run_and_tier):
    """Verify pagination response has required fields"""
    run_id, tier_id = test_run_and_tier

    # Create a single phase
    phase = models.Phase(
        phase_id="test-phase-001",
        run_id=run_id,
        tier_id=tier_id,
        phase_index=0,
        name="Test Phase",
    )
    db_session.add(phase)
    db_session.commit()

    response = client.get("/phases?page=1&page_size=10")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "has_next" in data

    # Verify types
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert isinstance(data["page"], int)
    assert isinstance(data["page_size"], int)
    assert isinstance(data["has_next"], bool)


def test_phases_pagination_min_page(client):
    """Verify page minimum is 1"""
    response = client.get("/phases?page=0")

    assert response.status_code == 200
    data = response.json()

    # page should be at least 1
    assert data["page"] >= 1
