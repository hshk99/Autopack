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
