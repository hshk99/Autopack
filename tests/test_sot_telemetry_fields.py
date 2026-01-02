"""
BUILD-155: Test SOT retrieval telemetry field validation.

Tests that telemetry events are correctly recorded to the sot_retrieval_events
table with all required fields populated accurately.

Validates:
1. Telemetry only recorded when TELEMETRY_DB_ENABLED=1
2. All required fields are present and non-null
3. Metrics are calculated correctly (budget utilization, truncation detection)
4. Foreign key constraints to (run_id, phase_id) are satisfied
"""

import pytest
import os
from unittest.mock import patch, MagicMock, Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from autopack.models import Base, Run, Tier, Phase, SOTRetrievalEvent


@pytest.fixture
def test_db():
    """Create an in-memory test database"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_run_and_phase(test_db):
    """Create a test run and phase for telemetry"""
    from datetime import datetime, timezone

    run = Run(
        id="test-build155-telemetry",
        project_name="test-project",
        created_at=datetime.now(timezone.utc),
        state="EXECUTING"
    )
    test_db.add(run)
    test_db.commit()

    tier = Tier(
        run_id=run.id,
        tier_id="T1",
        tier_index=0,
        name="Test Tier",
        state="EXECUTING"
    )
    test_db.add(tier)
    test_db.commit()

    phase = Phase(
        run_id=run.id,
        tier_id=tier.id,
        phase_id="test-phase-1",
        phase_index=0,
        name="Test Phase",
        state="EXECUTING"
    )
    test_db.add(phase)
    test_db.commit()

    return run, phase


class TestSOTTelemetryFields:
    """Test telemetry event recording and field validation"""

    @pytest.fixture
    def executor(self, test_run_and_phase):
        """Create a mock executor with the _record_sot_retrieval_telemetry method"""
        from autopack.autonomous_executor import AutonomousExecutor

        run, phase = test_run_and_phase

        # Create mock executor instance
        executor = Mock(spec=AutonomousExecutor)
        executor.run_id = run.id

        # Bind the actual method to the mock
        executor._record_sot_retrieval_telemetry = AutonomousExecutor._record_sot_retrieval_telemetry.__get__(executor, AutonomousExecutor)

        return executor

    def test_telemetry_skipped_when_disabled(self, test_db, test_run_and_phase, executor):
        """Telemetry should not be recorded when TELEMETRY_DB_ENABLED != 1"""
        run, phase = test_run_and_phase

        # Ensure TELEMETRY_DB_ENABLED is not set
        with patch.dict(os.environ, {"TELEMETRY_DB_ENABLED": "0"}, clear=False):
            with patch("autopack.database.SessionLocal", return_value=test_db):
                executor._record_sot_retrieval_telemetry(
                    phase_id=phase.phase_id,
                    include_sot=True,
                    max_context_chars=8000,
                    retrieved_context={"sot": [], "code": []},
                    formatted_context="test context",
                )

        # No telemetry event should be created
        events = test_db.query(SOTRetrievalEvent).all()
        assert len(events) == 0, "Telemetry should not be recorded when disabled"

    def test_telemetry_recorded_with_required_fields(self, test_db, test_run_and_phase, executor):
        """All required telemetry fields should be populated correctly"""
        run, phase = test_run_and_phase

        # Enable telemetry
        with patch.dict(os.environ, {"TELEMETRY_DB_ENABLED": "1"}, clear=False):
            with patch("autopack.database.SessionLocal", return_value=test_db):
                with patch("autopack.config.settings") as mock_settings:
                    mock_settings.autopack_sot_retrieval_enabled = True
                    mock_settings.autopack_sot_retrieval_max_chars = 4000
                    mock_settings.autopack_sot_retrieval_top_k = 3

                    retrieved_context = {
                        "sot": [
                            {"content": "t" * 1000, "metadata": {}},
                            {"content": "t" * 1000, "metadata": {}},
                        ],
                        "code": [],
                        "errors": []
                    }

                    executor._record_sot_retrieval_telemetry(
                        phase_id=phase.phase_id,
                        include_sot=True,
                        max_context_chars=8000,
                        retrieved_context=retrieved_context,
                        formatted_context="t" * 1500,  # Formatted output (truncated)
                    )

        # Verify event was created with all required fields
        events = test_db.query(SOTRetrievalEvent).all()
        assert len(events) == 1, "Exactly one telemetry event should be recorded"

        event = events[0]
        assert event.run_id == run.id
        assert event.phase_id == phase.phase_id
        assert event.include_sot is True
        assert event.max_context_chars == 8000
        assert event.sot_budget_chars == 4000
        assert event.sot_chunks_retrieved == 2
        assert event.sot_chars_raw == 2000  # 2 chunks * 1000 chars
        assert event.total_context_chars == 1500
        assert event.budget_utilization_pct == pytest.approx(18.75, rel=0.01)  # 1500/8000 * 100
        assert event.retrieval_enabled is True
        assert event.top_k == 3
        assert event.timestamp is not None
        assert event.created_at is not None

    def test_budget_utilization_calculation(self, test_db, test_run_and_phase, executor):
        """Budget utilization percentage should be calculated correctly"""
        run, phase = test_run_and_phase

        with patch.dict(os.environ, {"TELEMETRY_DB_ENABLED": "1"}, clear=False):
            with patch("autopack.database.SessionLocal", return_value=test_db):
                with patch("autopack.config.settings") as mock_settings:
                    mock_settings.autopack_sot_retrieval_enabled = True
                    mock_settings.autopack_sot_retrieval_max_chars = 4000
                    mock_settings.autopack_sot_retrieval_top_k = 3

                    # 100% utilization test
                    executor._record_sot_retrieval_telemetry(
                        phase_id=phase.phase_id,
                        include_sot=False,
                        max_context_chars=2000,
                        retrieved_context={"sot": [], "code": []},
                        formatted_context="x" * 2000,  # Exactly at cap
                    )

        event = test_db.query(SOTRetrievalEvent).first()
        assert event.budget_utilization_pct == pytest.approx(100.0, rel=0.01)

    def test_sot_truncation_detection(self, test_db, test_run_and_phase, executor):
        """Truncation flag should be set when output is near cap"""
        run, phase = test_run_and_phase

        with patch.dict(os.environ, {"TELEMETRY_DB_ENABLED": "1"}, clear=False):
            with patch("autopack.database.SessionLocal", return_value=test_db):
                with patch("autopack.config.settings") as mock_settings:
                    mock_settings.autopack_sot_retrieval_enabled = True
                    mock_settings.autopack_sot_retrieval_max_chars = 4000
                    mock_settings.autopack_sot_retrieval_top_k = 3

                    # Scenario: large raw SOT, but output capped → truncation likely
                    retrieved_context = {
                        "sot": [{"content": "t" * 5000, "metadata": {}}],
                        "code": [],
                        "errors": []
                    }

                    executor._record_sot_retrieval_telemetry(
                        phase_id=phase.phase_id,
                        include_sot=True,
                        max_context_chars=2000,
                        retrieved_context=retrieved_context,
                        formatted_context="t" * 1950,  # 97.5% of cap (within 5% threshold)
                    )

        event = test_db.query(SOTRetrievalEvent).first()
        assert event.sot_truncated is True, (
            "Truncation flag should be set when output is near cap (>= 95%)"
        )

    def test_sections_included_tracking(self, test_db, test_run_and_phase, executor):
        """Telemetry should track which context sections were included"""
        run, phase = test_run_and_phase

        with patch.dict(os.environ, {"TELEMETRY_DB_ENABLED": "1"}, clear=False):
            with patch("autopack.database.SessionLocal", return_value=test_db):
                with patch("autopack.config.settings") as mock_settings:
                    mock_settings.autopack_sot_retrieval_enabled = True
                    mock_settings.autopack_sot_retrieval_max_chars = 4000
                    mock_settings.autopack_sot_retrieval_top_k = 3

                    retrieved_context = {
                        "sot": [{"content": "t", "metadata": {}}],
                        "code": [{"content": "c", "metadata": {}}],
                        "errors": [{"content": "e", "metadata": {}}],
                        "hints": [],  # Empty section (not included)
                        "summaries": []  # Empty section (not included)
                    }

                    executor._record_sot_retrieval_telemetry(
                        phase_id=phase.phase_id,
                        include_sot=True,
                        max_context_chars=8000,
                        retrieved_context=retrieved_context,
                        formatted_context="test",
                    )

        event = test_db.query(SOTRetrievalEvent).first()
        assert "sot" in event.sections_included
        assert "code" in event.sections_included
        assert "errors" in event.sections_included
        assert "hints" not in event.sections_included, "Empty sections should be excluded"

    def test_foreign_key_constraint_validation(self, test_db, test_run_and_phase):
        """Telemetry event must reference valid (run_id, phase_id)"""
        run, phase = test_run_and_phase

        # Attempt to create event with invalid phase_id (should fail FK constraint)
        from datetime import datetime, timezone

        with pytest.raises(Exception):  # SQLite raises IntegrityError
            invalid_event = SOTRetrievalEvent(
                run_id=run.id,
                phase_id="nonexistent-phase",  # Invalid FK
                timestamp=datetime.now(timezone.utc),
                include_sot=False,
                max_context_chars=4000,
                sot_budget_chars=4000,
                sot_chunks_retrieved=0,
                sot_chars_raw=0,
                total_context_chars=0,
                budget_utilization_pct=0.0,
                sot_truncated=False,
                retrieval_enabled=True,
                created_at=datetime.now(timezone.utc),
            )
            test_db.add(invalid_event)
            test_db.commit()
