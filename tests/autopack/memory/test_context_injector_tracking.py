"""Tests for context injection impact tracking (IMP-LOOP-021).

Tests cover:
- ContextInjectionMetadata dataclass
- get_injection_metadata method
- get_enriched_injection_metadata method
- PhaseOutcomeEvent context_injected field
- TelemetryAnalyzer.analyze_context_injection_impact method
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.memory.context_injector import (ContextInjection,
                                              ContextInjectionMetadata,
                                              ContextInjector,
                                              EnrichedContextInjection)
from autopack.memory.memory_service import ContextMetadata
from autopack.models import Base, PhaseOutcomeEvent
from autopack.telemetry.analyzer import (ContextInjectionImpact,
                                         TelemetryAnalyzer)

# ---------------------------------------------------------------------------
# IMP-LOOP-021: ContextInjectionMetadata Dataclass Tests
# ---------------------------------------------------------------------------


class TestContextInjectionMetadataDataclass:
    """Tests for ContextInjectionMetadata dataclass."""

    def test_metadata_has_all_required_fields(self):
        """IMP-LOOP-021: ContextInjectionMetadata should have all required fields."""
        metadata = ContextInjectionMetadata(
            context_injected=True,
            context_item_count=5,
            errors_count=1,
            strategies_count=1,
            hints_count=1,
            insights_count=1,
            discovery_count=1,
        )

        assert metadata.context_injected is True
        assert metadata.context_item_count == 5
        assert metadata.errors_count == 1
        assert metadata.strategies_count == 1
        assert metadata.hints_count == 1
        assert metadata.insights_count == 1
        assert metadata.discovery_count == 1

    def test_metadata_with_no_context(self):
        """IMP-LOOP-021: Metadata should reflect when no context is injected."""
        metadata = ContextInjectionMetadata(
            context_injected=False,
            context_item_count=0,
            errors_count=0,
            strategies_count=0,
            hints_count=0,
            insights_count=0,
            discovery_count=0,
        )

        assert metadata.context_injected is False
        assert metadata.context_item_count == 0


# ---------------------------------------------------------------------------
# IMP-LOOP-021: get_injection_metadata Tests
# ---------------------------------------------------------------------------


class TestGetInjectionMetadata:
    """Tests for get_injection_metadata method."""

    def test_get_injection_metadata_with_context(self):
        """IMP-LOOP-021: Should return correct metadata when context is present."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        injection = ContextInjection(
            past_errors=["error1", "error2"],
            successful_strategies=["strategy1"],
            doctor_hints=["hint1", "hint2", "hint3"],
            relevant_insights=["insight1"],
            discovery_insights=["discovery1", "discovery2"],
            total_token_estimate=200,
        )

        metadata = injector.get_injection_metadata(injection)

        assert metadata.context_injected is True
        assert metadata.context_item_count == 9  # 2+1+3+1+2
        assert metadata.errors_count == 2
        assert metadata.strategies_count == 1
        assert metadata.hints_count == 3
        assert metadata.insights_count == 1
        assert metadata.discovery_count == 2

    def test_get_injection_metadata_without_context(self):
        """IMP-LOOP-021: Should return correct metadata when no context."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        injection = ContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=0,
        )

        metadata = injector.get_injection_metadata(injection)

        assert metadata.context_injected is False
        assert metadata.context_item_count == 0

    def test_get_injection_metadata_partial_context(self):
        """IMP-LOOP-021: Should handle partial context correctly."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        injection = ContextInjection(
            past_errors=["error1"],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=50,
        )

        metadata = injector.get_injection_metadata(injection)

        assert metadata.context_injected is True
        assert metadata.context_item_count == 1
        assert metadata.errors_count == 1


# ---------------------------------------------------------------------------
# IMP-LOOP-021: get_enriched_injection_metadata Tests
# ---------------------------------------------------------------------------


class TestGetEnrichedInjectionMetadata:
    """Tests for get_enriched_injection_metadata method."""

    def test_get_enriched_injection_metadata_with_context(self):
        """IMP-LOOP-021: Should return correct metadata from enriched context."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        error_meta = ContextMetadata(
            content="error1",
            relevance_score=0.8,
            age_hours=5.0,
            confidence=0.7,
            is_low_confidence=False,
        )
        strategy_meta = ContextMetadata(
            content="strategy1",
            relevance_score=0.9,
            age_hours=10.0,
            confidence=0.8,
            is_low_confidence=False,
        )

        enriched = EnrichedContextInjection(
            past_errors=[error_meta],
            successful_strategies=[strategy_meta],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=["discovery1"],
            total_token_estimate=100,
        )

        metadata = injector.get_enriched_injection_metadata(enriched)

        assert metadata.context_injected is True
        assert metadata.context_item_count == 3
        assert metadata.errors_count == 1
        assert metadata.strategies_count == 1
        assert metadata.discovery_count == 1

    def test_get_enriched_injection_metadata_without_context(self):
        """IMP-LOOP-021: Should return correct metadata when enriched context is empty."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        enriched = EnrichedContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=0,
        )

        metadata = injector.get_enriched_injection_metadata(enriched)

        assert metadata.context_injected is False
        assert metadata.context_item_count == 0


# ---------------------------------------------------------------------------
# IMP-LOOP-021: PhaseOutcomeEvent Model Tests
# ---------------------------------------------------------------------------


class TestPhaseOutcomeEventContextFields:
    """Tests for context_injected fields in PhaseOutcomeEvent model."""

    def test_phase_outcome_event_has_context_injected_field(self):
        """IMP-LOOP-021: PhaseOutcomeEvent should have context_injected field."""
        event = PhaseOutcomeEvent(
            run_id="test-run",
            phase_id="test-phase",
            phase_outcome="SUCCESS",
            context_injected=True,
            context_item_count=5,
        )

        assert event.context_injected is True
        assert event.context_item_count == 5

    def test_phase_outcome_event_context_fields_nullable(self):
        """IMP-LOOP-021: Context fields should be nullable for backward compat."""
        event = PhaseOutcomeEvent(
            run_id="test-run",
            phase_id="test-phase",
            phase_outcome="SUCCESS",
        )

        assert event.context_injected is None
        assert event.context_item_count is None


# ---------------------------------------------------------------------------
# IMP-LOOP-021: ContextInjectionImpact Dataclass Tests
# ---------------------------------------------------------------------------


class TestContextInjectionImpactDataclass:
    """Tests for ContextInjectionImpact dataclass."""

    def test_impact_has_all_required_fields(self):
        """IMP-LOOP-021: ContextInjectionImpact should have all required fields."""
        impact = ContextInjectionImpact(
            with_context_success_rate=0.8,
            without_context_success_rate=0.6,
            delta=0.2,
            with_context_count=50,
            without_context_count=100,
            avg_context_item_count=4.5,
            impact_significant=True,
        )

        assert impact.with_context_success_rate == 0.8
        assert impact.without_context_success_rate == 0.6
        assert impact.delta == 0.2
        assert impact.with_context_count == 50
        assert impact.without_context_count == 100
        assert impact.avg_context_item_count == 4.5
        assert impact.impact_significant is True


# ---------------------------------------------------------------------------
# IMP-LOOP-021: TelemetryAnalyzer.analyze_context_injection_impact Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestAnalyzeContextInjectionImpact:
    """Tests for TelemetryAnalyzer.analyze_context_injection_impact method."""

    def test_analyze_context_injection_impact_empty_database(self, db_session):
        """IMP-LOOP-021: Should return zeros when no data."""
        analyzer = TelemetryAnalyzer(db_session)

        impact = analyzer.analyze_context_injection_impact()

        assert impact.with_context_count == 0
        assert impact.without_context_count == 0
        assert impact.with_context_success_rate == 0.0
        assert impact.without_context_success_rate == 0.0
        assert impact.delta == 0.0
        assert impact.impact_significant is False

    def test_analyze_context_injection_impact_with_data(self, db_session):
        """IMP-LOOP-021: Should calculate impact correctly with data."""
        # Add phases with context injection
        for i in range(20):
            event = PhaseOutcomeEvent(
                run_id=f"run-{i}",
                phase_id=f"phase-{i}",
                phase_outcome="SUCCESS" if i < 16 else "FAILED",  # 80% success
                context_injected=True,
                context_item_count=5,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(event)

        # Add phases without context injection
        for i in range(20, 40):
            event = PhaseOutcomeEvent(
                run_id=f"run-{i}",
                phase_id=f"phase-{i}",
                phase_outcome="SUCCESS" if i < 32 else "FAILED",  # 60% success
                context_injected=False,
                context_item_count=0,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(event)

        db_session.commit()

        analyzer = TelemetryAnalyzer(db_session)
        impact = analyzer.analyze_context_injection_impact()

        assert impact.with_context_count == 20
        assert impact.without_context_count == 20
        assert impact.with_context_success_rate == pytest.approx(0.8)
        assert impact.without_context_success_rate == pytest.approx(0.6)
        assert impact.delta == pytest.approx(0.2)
        assert impact.impact_significant is True

    def test_analyze_context_injection_impact_respects_window(self, db_session):
        """IMP-LOOP-021: Should only include events within time window."""
        # Add recent events (within 7 days)
        for i in range(10):
            event = PhaseOutcomeEvent(
                run_id=f"recent-run-{i}",
                phase_id=f"recent-phase-{i}",
                phase_outcome="SUCCESS",
                context_injected=True,
                context_item_count=5,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(event)

        # Add old events (outside 7 days)
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=10)
        for i in range(10):
            event = PhaseOutcomeEvent(
                run_id=f"old-run-{i}",
                phase_id=f"old-phase-{i}",
                phase_outcome="FAILED",
                context_injected=True,
                context_item_count=5,
                timestamp=old_timestamp,
            )
            db_session.add(event)

        db_session.commit()

        analyzer = TelemetryAnalyzer(db_session)
        impact = analyzer.analyze_context_injection_impact(window_days=7)

        # Should only see the 10 recent SUCCESS events
        assert impact.with_context_count == 10
        assert impact.with_context_success_rate == 1.0

    def test_analyze_context_injection_impact_null_context_injected(self, db_session):
        """IMP-LOOP-021: Should treat NULL context_injected as without context."""
        # Add events with NULL context_injected (legacy data)
        for i in range(10):
            event = PhaseOutcomeEvent(
                run_id=f"legacy-run-{i}",
                phase_id=f"legacy-phase-{i}",
                phase_outcome="SUCCESS" if i < 5 else "FAILED",
                context_injected=None,  # NULL
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(event)

        db_session.commit()

        analyzer = TelemetryAnalyzer(db_session)
        impact = analyzer.analyze_context_injection_impact()

        # NULL should be counted as without context
        assert impact.with_context_count == 0
        assert impact.without_context_count == 10

    def test_analyze_context_injection_impact_calculates_avg_items(self, db_session):
        """IMP-LOOP-021: Should calculate average context item count."""
        for i, item_count in enumerate([3, 5, 7, 9, 11]):
            event = PhaseOutcomeEvent(
                run_id=f"run-{i}",
                phase_id=f"phase-{i}",
                phase_outcome="SUCCESS",
                context_injected=True,
                context_item_count=item_count,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(event)

        db_session.commit()

        analyzer = TelemetryAnalyzer(db_session)
        impact = analyzer.analyze_context_injection_impact()

        # Average should be (3+5+7+9+11)/5 = 7
        assert impact.avg_context_item_count == 7.0

    def test_analyze_context_injection_impact_significance_threshold(self, db_session):
        """IMP-LOOP-021: Should only mark significant if delta > 5% and n >= 10."""
        # Add 5 events each - not enough for significance
        for i in range(5):
            db_session.add(
                PhaseOutcomeEvent(
                    run_id=f"with-{i}",
                    phase_id=f"with-phase-{i}",
                    phase_outcome="SUCCESS",
                    context_injected=True,
                    context_item_count=5,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            db_session.add(
                PhaseOutcomeEvent(
                    run_id=f"without-{i}",
                    phase_id=f"without-phase-{i}",
                    phase_outcome="FAILED",
                    context_injected=False,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        db_session.commit()

        analyzer = TelemetryAnalyzer(db_session)
        impact = analyzer.analyze_context_injection_impact()

        # High delta but not enough samples
        assert impact.delta == 1.0  # 100% - 0%
        assert impact.impact_significant is False  # Only 5 samples each


# ---------------------------------------------------------------------------
# IMP-LOOP-021: Integration Tests
# ---------------------------------------------------------------------------


class TestContextInjectionTrackingIntegration:
    """Integration tests for full context injection tracking flow."""

    def test_full_flow_context_injection_to_analysis(self, db_session):
        """IMP-LOOP-021: Test full flow from injection to analysis."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        # Create a context injection
        injection = ContextInjection(
            past_errors=["error1"],
            successful_strategies=["strategy1"],
            doctor_hints=["hint1"],
            relevant_insights=["insight1"],
            discovery_insights=["discovery1"],
            total_token_estimate=100,
        )

        # Get metadata
        metadata = injector.get_injection_metadata(injection)

        # Simulate recording phase outcome with metadata
        event = PhaseOutcomeEvent(
            run_id="integration-run",
            phase_id="integration-phase",
            phase_outcome="SUCCESS",
            context_injected=metadata.context_injected,
            context_item_count=metadata.context_item_count,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(event)
        db_session.commit()

        # Analyze impact
        analyzer = TelemetryAnalyzer(db_session)
        impact = analyzer.analyze_context_injection_impact()

        assert impact.with_context_count == 1
        assert impact.with_context_success_rate == 1.0
        assert impact.avg_context_item_count == 5.0  # 5 items injected


# ---------------------------------------------------------------------------
# IMP-LOOP-029: Injection Tracking Record Tests
# ---------------------------------------------------------------------------


class TestInjectionTrackingRecord:
    """Tests for InjectionTrackingRecord dataclass."""

    def test_record_has_all_required_fields(self):
        """IMP-LOOP-029: InjectionTrackingRecord should have all required fields."""
        from autopack.memory.context_injector import InjectionTrackingRecord

        record = InjectionTrackingRecord(
            injection_id="phase_1_abc12345",
            phase_id="phase_1",
            timestamp="2024-01-01T12:00:00",
            memory_count=5,
            had_context=True,
        )

        assert record.injection_id == "phase_1_abc12345"
        assert record.phase_id == "phase_1"
        assert record.timestamp == "2024-01-01T12:00:00"
        assert record.memory_count == 5
        assert record.had_context is True
        assert record.outcome is None
        assert record.metrics == {}

    def test_record_to_dict(self):
        """IMP-LOOP-029: to_dict should serialize all fields."""
        from autopack.memory.context_injector import InjectionTrackingRecord

        record = InjectionTrackingRecord(
            injection_id="phase_1_abc12345",
            phase_id="phase_1",
            timestamp="2024-01-01T12:00:00",
            memory_count=5,
            had_context=True,
            outcome={"success": True, "correlated_at": "2024-01-01T12:05:00"},
            metrics={"tokens": 100},
        )

        result = record.to_dict()

        assert result["injection_id"] == "phase_1_abc12345"
        assert result["phase_id"] == "phase_1"
        assert result["had_context"] is True
        assert result["outcome"]["success"] is True


# ---------------------------------------------------------------------------
# IMP-LOOP-029: Injection Tracking Methods Tests
# ---------------------------------------------------------------------------


class TestContextInjectorInjectionTracking:
    """Tests for ContextInjector injection tracking methods."""

    def test_track_injection_generates_id(self):
        """IMP-LOOP-029: track_injection should generate unique injection ID."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        injection_id = injector.track_injection(
            phase_id="test_phase",
            memory_count=3,
            had_context=True,
        )

        assert injection_id.startswith("test_phase_")
        assert len(injection_id) > len("test_phase_")

    def test_track_injection_stores_record(self):
        """IMP-LOOP-029: track_injection should store injection record."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        injection_id = injector.track_injection(
            phase_id="test_phase",
            memory_count=5,
            had_context=True,
        )

        record = injector.get_injection_record(injection_id)
        assert record is not None
        assert record.phase_id == "test_phase"
        assert record.memory_count == 5
        assert record.had_context is True
        assert record.outcome is None

    def test_correlate_outcome_updates_record(self):
        """IMP-LOOP-029: correlate_outcome should update injection record."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        injection_id = injector.track_injection(
            phase_id="test_phase",
            memory_count=5,
            had_context=True,
        )

        success = injector.correlate_outcome(
            injection_id=injection_id,
            success=True,
            metrics={"tokens_used": 100},
        )

        assert success is True

        record = injector.get_injection_record(injection_id)
        assert record.outcome is not None
        assert record.outcome["success"] is True
        assert record.metrics["tokens_used"] == 100

    def test_correlate_outcome_missing_id_returns_false(self):
        """IMP-LOOP-029: correlate_outcome should return False for missing ID."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        success = injector.correlate_outcome(
            injection_id="nonexistent_id",
            success=True,
        )

        assert success is False

    def test_get_all_injection_records(self):
        """IMP-LOOP-029: get_all_injection_records should return all records."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        # Track multiple injections
        injector.track_injection("phase_1", 3, True)
        injector.track_injection("phase_2", 0, False)
        injector.track_injection("phase_3", 5, True)

        records = injector.get_all_injection_records()
        assert len(records) == 3

    def test_get_correlated_records(self):
        """IMP-LOOP-029: get_correlated_records should return only correlated."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        # Track and correlate some injections
        id1 = injector.track_injection("phase_1", 3, True)
        injector.track_injection("phase_2", 0, False)  # Not correlated
        id3 = injector.track_injection("phase_3", 5, True)

        injector.correlate_outcome(id1, True)
        injector.correlate_outcome(id3, False)

        correlated = injector.get_correlated_records()
        assert len(correlated) == 2

    def test_calculate_effectiveness_summary(self):
        """IMP-LOOP-029: calculate_effectiveness_summary should compute stats."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        # Track and correlate injections with context (80% success)
        for i in range(10):
            id_ = injector.track_injection(f"phase_with_{i}", 5, True)
            injector.correlate_outcome(id_, success=(i < 8))

        # Track and correlate injections without context (60% success)
        for i in range(10):
            id_ = injector.track_injection(f"phase_without_{i}", 0, False)
            injector.correlate_outcome(id_, success=(i < 6))

        summary = injector.calculate_effectiveness_summary()

        assert summary["with_context_count"] == 10
        assert summary["without_context_count"] == 10
        assert summary["with_context_success_rate"] == pytest.approx(0.8)
        assert summary["without_context_success_rate"] == pytest.approx(0.6)
        assert summary["delta"] == pytest.approx(0.2)
        assert summary["is_significant"] is True  # n>=10 and delta>=0.05

    def test_clear_injection_records(self):
        """IMP-LOOP-029: clear_injection_records should clear all records."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        injector.track_injection("phase_1", 3, True)
        injector.track_injection("phase_2", 0, False)

        count = injector.clear_injection_records()
        assert count == 2

        records = injector.get_all_injection_records()
        assert len(records) == 0
