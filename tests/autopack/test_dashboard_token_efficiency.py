"""Tests for dashboard token efficiency integration (BUILD-145 deployment hardening)"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from autopack.database import Base, get_db
from autopack.usage_recorder import record_token_efficiency_metrics
from autopack.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def test_db():
    """Create in-memory test database"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(test_db):
    """Create database session for direct DB access"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestDashboardTokenEfficiencyIntegration:
    """Test dashboard endpoint integration with token efficiency stats"""

    def test_dashboard_no_metrics(self, db_session, client):
        """Dashboard should return None for token_efficiency when no metrics exist"""
        from autopack import models

        # Create a run
        run = models.Run(
            id="test-run-empty",
            state=models.RunState.PHASE_EXECUTION,
            tokens_used=5000,
            token_cap=10000,
        )
        db_session.add(run)
        db_session.commit()

        # Call dashboard endpoint
        response = client.get("/dashboard/runs/test-run-empty/status")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == "test-run-empty"
        assert data["token_efficiency"] is None  # No metrics recorded

    def test_dashboard_with_basic_metrics(self, db_session, client):
        """Dashboard should include token efficiency stats when metrics exist"""
        from autopack import models

        # Create a run
        run = models.Run(
            id="test-run-metrics",
            state=models.RunState.PHASE_EXECUTION,
            tokens_used=15000,
            token_cap=50000,
        )
        db_session.add(run)
        db_session.commit()

        # Record some metrics
        for i in range(3):
            record_token_efficiency_metrics(
                db=db_session,
                run_id="test-run-metrics",
                phase_id=f"phase-{i:03d}",
                artifact_substitutions=2,
                tokens_saved_artifacts=1000,
                budget_mode="semantic",
                budget_used=5000,
                budget_cap=10000,
                files_kept=10,
                files_omitted=2,
                phase_outcome="COMPLETE",
            )

        # Call dashboard endpoint
        response = client.get("/dashboard/runs/test-run-metrics/status")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == "test-run-metrics"
        assert data["token_efficiency"] is not None

        # Verify aggregated stats
        efficiency = data["token_efficiency"]
        assert efficiency["total_phases"] == 3
        assert efficiency["total_artifact_substitutions"] == 6  # 2 * 3
        assert efficiency["total_tokens_saved_artifacts"] == 3000  # 1000 * 3
        assert efficiency["semantic_mode_count"] == 3
        assert efficiency["lexical_mode_count"] == 0
        assert efficiency["avg_artifact_substitutions_per_phase"] == 2.0
        assert efficiency["avg_tokens_saved_per_phase"] == 1000.0
        assert efficiency["budget_utilization"] == 0.5  # 15000 / 30000

    def test_dashboard_with_phase_outcome_breakdown(self, db_session, client):
        """Dashboard should include phase outcome breakdown"""
        from autopack import models

        # Create a run
        run = models.Run(
            id="test-run-outcomes",
            state=models.RunState.DONE_SUCCESS,
            tokens_used=20000,
            token_cap=50000,
        )
        db_session.add(run)
        db_session.commit()

        # Record metrics with different outcomes
        outcomes = ["COMPLETE", "COMPLETE", "COMPLETE", "FAILED", "BLOCKED"]
        for i, outcome in enumerate(outcomes):
            record_token_efficiency_metrics(
                db=db_session,
                run_id="test-run-outcomes",
                phase_id=f"phase-{i:03d}",
                artifact_substitutions=1,
                tokens_saved_artifacts=500,
                budget_mode="semantic",
                budget_used=4000,
                budget_cap=10000,
                files_kept=8,
                files_omitted=1,
                phase_outcome=outcome,
            )

        # Call dashboard endpoint
        response = client.get("/dashboard/runs/test-run-outcomes/status")
        assert response.status_code == 200

        data = response.json()
        efficiency = data["token_efficiency"]

        # Verify outcome breakdown
        assert "phase_outcome_counts" in efficiency
        outcome_counts = efficiency["phase_outcome_counts"]
        assert outcome_counts["COMPLETE"] == 3
        assert outcome_counts["FAILED"] == 1
        assert outcome_counts["BLOCKED"] == 1

    def test_dashboard_with_enriched_telemetry(self, db_session, client):
        """Dashboard should handle enriched telemetry fields"""
        from autopack import models

        # Create a run
        run = models.Run(
            id="test-run-enriched",
            state=models.RunState.PHASE_EXECUTION,
            tokens_used=10000,
            token_cap=50000,
        )
        db_session.add(run)
        db_session.commit()

        # Record metrics with enriched telemetry
        record_token_efficiency_metrics(
            db=db_session,
            run_id="test-run-enriched",
            phase_id="phase-001",
            artifact_substitutions=3,
            tokens_saved_artifacts=1500,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=12,
            files_omitted=3,
            phase_outcome="COMPLETE",
            # Enriched telemetry
            embedding_cache_hits=8,
            embedding_cache_misses=4,
            embedding_calls_made=4,
            embedding_cap_value=100,
            embedding_fallback_reason=None,
            deliverables_count=5,
            context_files_total=15,
        )

        # Call dashboard endpoint
        response = client.get("/dashboard/runs/test-run-enriched/status")
        assert response.status_code == 200

        data = response.json()
        assert data["token_efficiency"] is not None
        # Stats are aggregated but enriched fields exist in database
        assert data["token_efficiency"]["total_phases"] == 1

    def test_dashboard_backward_compatibility(self, db_session, client):
        """Dashboard should be backward compatible with old metrics (no enriched fields)"""
        from autopack import models

        # Create a run
        run = models.Run(
            id="test-run-legacy",
            state=models.RunState.PHASE_EXECUTION,
            tokens_used=8000,
            token_cap=20000,
        )
        db_session.add(run)
        db_session.commit()

        # Record metrics without enriched fields (legacy)
        record_token_efficiency_metrics(
            db=db_session,
            run_id="test-run-legacy",
            phase_id="phase-001",
            artifact_substitutions=2,
            tokens_saved_artifacts=800,
            budget_mode="lexical",
            budget_used=8000,
            budget_cap=10000,
            files_kept=10,
            files_omitted=0,
            # No phase_outcome, no enriched fields
        )

        # Call dashboard endpoint
        response = client.get("/dashboard/runs/test-run-legacy/status")
        assert response.status_code == 200

        data = response.json()
        efficiency = data["token_efficiency"]
        assert efficiency is not None
        assert efficiency["total_phases"] == 1
        assert "phase_outcome_counts" in efficiency
        # Legacy records have NULL outcome -> "UNKNOWN"
        assert efficiency["phase_outcome_counts"].get("UNKNOWN", 0) == 1

    def test_dashboard_mixed_budget_modes(self, db_session, client):
        """Dashboard should aggregate stats across mixed budget modes"""
        from autopack import models

        # Create a run
        run = models.Run(
            id="test-run-mixed",
            state=models.RunState.PHASE_EXECUTION,
            tokens_used=12000,
            token_cap=50000,
        )
        db_session.add(run)
        db_session.commit()

        # Record metrics with different budget modes
        modes = ["semantic", "semantic", "lexical", "semantic", "lexical"]
        for i, mode in enumerate(modes):
            record_token_efficiency_metrics(
                db=db_session,
                run_id="test-run-mixed",
                phase_id=f"phase-{i:03d}",
                artifact_substitutions=1,
                tokens_saved_artifacts=400,
                budget_mode=mode,
                budget_used=2400,
                budget_cap=5000,
                files_kept=6,
                files_omitted=1,
                phase_outcome="COMPLETE",
            )

        # Call dashboard endpoint
        response = client.get("/dashboard/runs/test-run-mixed/status")
        assert response.status_code == 200

        data = response.json()
        efficiency = data["token_efficiency"]
        assert efficiency["semantic_mode_count"] == 3
        assert efficiency["lexical_mode_count"] == 2
        assert efficiency["total_phases"] == 5

    def test_dashboard_graceful_error_handling(self, db_session, client, monkeypatch):
        """Dashboard should handle errors in token efficiency stats gracefully"""
        from autopack import models

        # Create a run
        run = models.Run(
            id="test-run-error",
            state=models.RunState.PHASE_EXECUTION,
            tokens_used=5000,
            token_cap=10000,
        )
        db_session.add(run)
        db_session.commit()

        # Mock get_token_efficiency_stats to raise exception
        def mock_get_stats(db, run_id):
            raise Exception("Database connection error")

        monkeypatch.setattr("autopack.usage_recorder.get_token_efficiency_stats", mock_get_stats)

        # Call dashboard endpoint - should not crash
        response = client.get("/dashboard/runs/test-run-error/status")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == "test-run-error"
        # token_efficiency should be None due to error, but endpoint still works
        assert data["token_efficiency"] is None
