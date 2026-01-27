"""Unit tests for IMP-COST-005: Cost attribution by phase type and intent

Validates cost aggregation by phase type (build/audit/test/tidy/doctor)
and by intent (feature/bugfix/refactor/docs).
"""

from datetime import datetime, timedelta

import pytest

from autopack.telemetry.cost_aggregator import CostAggregation, CostAggregator
from autopack.usage_recorder import LlmUsageEvent, UsageEventData, record_usage


class TestCostAggregationDataclass:
    """Test CostAggregation dataclass validation"""

    def test_cost_aggregation_creation(self):
        """Test CostAggregation object creation"""
        agg = CostAggregation(
            category="phase_type",
            category_value="build",
            total_tokens=10000,
            total_cost_usd=0.15,
            run_count=10,
            avg_tokens_per_run=1000.0,
            avg_cost_per_run=0.015,
        )
        assert agg.category == "phase_type"
        assert agg.category_value == "build"
        assert agg.total_tokens == 10000
        assert agg.total_cost_usd == 0.15
        assert agg.run_count == 10
        assert agg.avg_tokens_per_run == 1000.0
        assert agg.avg_cost_per_run == 0.015

    def test_cost_aggregation_negative_tokens_raises(self):
        """Test that negative tokens raise ValueError"""
        with pytest.raises(ValueError, match="total_tokens must be non-negative"):
            CostAggregation(
                category="phase_type",
                category_value="build",
                total_tokens=-100,
                total_cost_usd=0.0,
                run_count=0,
                avg_tokens_per_run=0.0,
                avg_cost_per_run=0.0,
            )

    def test_cost_aggregation_negative_cost_raises(self):
        """Test that negative cost raises ValueError"""
        with pytest.raises(ValueError, match="total_cost_usd must be non-negative"):
            CostAggregation(
                category="phase_type",
                category_value="build",
                total_tokens=0,
                total_cost_usd=-0.5,
                run_count=0,
                avg_tokens_per_run=0.0,
                avg_cost_per_run=0.0,
            )

    def test_cost_aggregation_negative_run_count_raises(self):
        """Test that negative run count raises ValueError"""
        with pytest.raises(ValueError, match="run_count must be non-negative"):
            CostAggregation(
                category="phase_type",
                category_value="build",
                total_tokens=0,
                total_cost_usd=0.0,
                run_count=-1,
                avg_tokens_per_run=0.0,
                avg_cost_per_run=0.0,
            )


class TestLlmUsageEventModel:
    """Test LlmUsageEvent model with new cost attribution fields"""

    def test_llm_usage_event_with_phase_type_and_intent(self, db_session):
        """Test recording LLM usage with phase_type and intent"""
        event = UsageEventData(
            provider="anthropic",
            model="claude-3-5-sonnet",
            run_id="run-123",
            phase_id="phase-456",
            role="builder",
            total_tokens=5000,
            prompt_tokens=3000,
            completion_tokens=2000,
            phase_type="build",
            intent="feature",
        )

        record = record_usage(db_session, event)

        assert record.phase_type == "build"
        assert record.intent == "feature"
        assert record.total_tokens == 5000

        # Query back from DB
        fetched = db_session.query(LlmUsageEvent).filter_by(id=record.id).first()
        assert fetched.phase_type == "build"
        assert fetched.intent == "feature"

    def test_llm_usage_event_null_phase_type_intent(self, db_session):
        """Test recording LLM usage with null phase_type and intent"""
        event = UsageEventData(
            provider="openai",
            model="gpt-4o",
            run_id="run-789",
            phase_id="phase-xyz",
            role="auditor",
            total_tokens=8000,
            prompt_tokens=4000,
            completion_tokens=4000,
            phase_type=None,
            intent=None,
        )

        record = record_usage(db_session, event)

        assert record.phase_type is None
        assert record.intent is None

    def test_multiple_events_different_phase_types(self, db_session):
        """Test recording multiple events with different phase types"""
        phase_types = ["build", "audit", "test", "tidy", "doctor"]
        for phase_type in phase_types:
            event = UsageEventData(
                provider="anthropic",
                model="claude-3-5-sonnet",
                run_id="run-multi",
                phase_id=f"phase-{phase_type}",
                role="builder",
                total_tokens=1000,
                prompt_tokens=600,
                completion_tokens=400,
                phase_type=phase_type,
                intent="feature",
            )
            record_usage(db_session, event)

        # Query all events for this run
        records = db_session.query(LlmUsageEvent).filter_by(run_id="run-multi").all()
        assert len(records) == 5
        recorded_types = {r.phase_type for r in records}
        assert recorded_types == set(phase_types)

    def test_multiple_events_different_intents(self, db_session):
        """Test recording multiple events with different intents"""
        intents = ["feature", "bugfix", "refactor", "docs"]
        for intent in intents:
            event = UsageEventData(
                provider="anthropic",
                model="claude-3-5-sonnet",
                run_id="run-intents",
                phase_id=f"phase-{intent}",
                role="builder",
                total_tokens=2000,
                prompt_tokens=1200,
                completion_tokens=800,
                phase_type="build",
                intent=intent,
            )
            record_usage(db_session, event)

        # Query all events for this run
        records = db_session.query(LlmUsageEvent).filter_by(run_id="run-intents").all()
        assert len(records) == 4
        recorded_intents = {r.intent for r in records}
        assert recorded_intents == set(intents)


class TestCostAggregatorByPhaseType:
    """Test CostAggregator.by_phase_type() functionality"""

    def test_by_phase_type_empty_result(self, db_session):
        """Test aggregation returns empty list when no data exists"""
        aggregator = CostAggregator(session=db_session)
        results = aggregator.by_phase_type(days=30)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_by_phase_type_single_phase_type(self, db_session):
        """Test aggregation with single phase type"""
        # Insert test data
        for i in range(5):
            event = UsageEventData(
                provider="anthropic",
                model="claude-3-5-sonnet",
                run_id=f"run-{i}",
                phase_id=f"phase-{i}",
                role="builder",
                total_tokens=2000,
                prompt_tokens=1200,
                completion_tokens=800,
                phase_type="build",
                intent="feature",
            )
            record_usage(db_session, event)

        aggregator = CostAggregator(session=db_session)
        results = aggregator.by_phase_type(days=30)

        assert len(results) == 1
        assert results[0].category == "phase_type"
        assert results[0].category_value == "build"
        assert results[0].total_tokens == 10000  # 5 events * 2000 tokens
        assert results[0].run_count == 5
        assert results[0].avg_tokens_per_run == 2000.0
        assert results[0].avg_cost_per_run > 0

    def test_by_phase_type_multiple_phase_types(self, db_session):
        """Test aggregation with multiple phase types"""
        phase_types = [
            ("build", 3, 1000),
            ("audit", 2, 5000),
            ("test", 4, 1500),
        ]

        for phase_type, count, tokens in phase_types:
            for i in range(count):
                event = UsageEventData(
                    provider="anthropic",
                    model="claude-3-5-sonnet",
                    run_id=f"run-{phase_type}-{i}",
                    phase_id=f"phase-{phase_type}-{i}",
                    role="builder",
                    total_tokens=tokens,
                    prompt_tokens=int(tokens * 0.6),
                    completion_tokens=int(tokens * 0.4),
                    phase_type=phase_type,
                    intent="feature",
                )
                record_usage(db_session, event)

        aggregator = CostAggregator(session=db_session)
        results = aggregator.by_phase_type(days=30)

        assert len(results) == 3
        result_dict = {r.category_value: r for r in results}

        assert result_dict["build"].total_tokens == 3000
        assert result_dict["audit"].total_tokens == 10000
        assert result_dict["test"].total_tokens == 6000

        assert result_dict["build"].run_count == 3
        assert result_dict["audit"].run_count == 2
        assert result_dict["test"].run_count == 4

    def test_by_phase_type_time_filtering(self, db_session):
        """Test that aggregation respects time window"""
        # Create old event (30+ days ago)
        old_event = LlmUsageEvent(
            provider="anthropic",
            model="claude-3-5-sonnet",
            run_id="run-old",
            phase_id="phase-old",
            role="builder",
            total_tokens=5000,
            prompt_tokens=3000,
            completion_tokens=2000,
            is_doctor_call=False,
            phase_type="build",
            intent="feature",
            created_at=datetime.utcnow() - timedelta(days=35),
        )
        db_session.add(old_event)

        # Create recent event
        recent_event = LlmUsageEvent(
            provider="anthropic",
            model="claude-3-5-sonnet",
            run_id="run-recent",
            phase_id="phase-recent",
            role="builder",
            total_tokens=2000,
            prompt_tokens=1200,
            completion_tokens=800,
            is_doctor_call=False,
            phase_type="build",
            intent="feature",
            created_at=datetime.utcnow(),
        )
        db_session.add(recent_event)
        db_session.commit()

        aggregator = CostAggregator(session=db_session)

        # Query last 30 days - should only include recent event
        results = aggregator.by_phase_type(days=30)
        assert len(results) == 1
        assert results[0].total_tokens == 2000
        assert results[0].run_count == 1

        # Query last 40 days - should include both
        results = aggregator.by_phase_type(days=40)
        assert len(results) == 1
        assert results[0].total_tokens == 7000
        assert results[0].run_count == 2


class TestCostAggregatorByIntent:
    """Test CostAggregator.by_intent() functionality"""

    def test_by_intent_empty_result(self, db_session):
        """Test aggregation returns empty list when no data exists"""
        aggregator = CostAggregator(session=db_session)
        results = aggregator.by_intent(days=30)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_by_intent_multiple_intents(self, db_session):
        """Test aggregation with multiple intents"""
        intents = [
            ("feature", 3, 3000),
            ("bugfix", 2, 4000),
            ("refactor", 4, 1000),
            ("docs", 1, 500),
        ]

        for intent, count, tokens in intents:
            for i in range(count):
                event = UsageEventData(
                    provider="anthropic",
                    model="claude-3-5-sonnet",
                    run_id=f"run-{intent}-{i}",
                    phase_id=f"phase-{intent}-{i}",
                    role="builder",
                    total_tokens=tokens,
                    prompt_tokens=int(tokens * 0.6),
                    completion_tokens=int(tokens * 0.4),
                    phase_type="build",
                    intent=intent,
                )
                record_usage(db_session, event)

        aggregator = CostAggregator(session=db_session)
        results = aggregator.by_intent(days=30)

        assert len(results) == 4
        result_dict = {r.category_value: r for r in results}

        assert result_dict["feature"].total_tokens == 9000
        assert result_dict["bugfix"].total_tokens == 8000
        assert result_dict["refactor"].total_tokens == 4000
        assert result_dict["docs"].total_tokens == 500

        assert result_dict["feature"].run_count == 3
        assert result_dict["bugfix"].run_count == 2


class TestCostAggregatorReport:
    """Test CostAggregator.generate_report() functionality"""

    def test_generate_report_structure(self, db_session):
        """Test report has correct structure"""
        # Insert test data
        event = UsageEventData(
            provider="anthropic",
            model="claude-3-5-sonnet",
            run_id="run-report",
            phase_id="phase-report",
            role="builder",
            total_tokens=5000,
            prompt_tokens=3000,
            completion_tokens=2000,
            phase_type="build",
            intent="feature",
        )
        record_usage(db_session, event)

        aggregator = CostAggregator(session=db_session)
        report = aggregator.generate_report(days=30)

        assert "period_days" in report
        assert "generated_at" in report
        assert "by_phase_type" in report
        assert "by_intent" in report
        assert "insights" in report

        assert report["period_days"] == 30
        assert isinstance(report["by_phase_type"], list)
        assert isinstance(report["by_intent"], list)
        assert isinstance(report["insights"], list)

    def test_generate_report_insights(self, db_session):
        """Test report generates cost insights"""
        # Create data with clear cost differences
        phase_types = [
            ("build", 5, 2000),  # 5 runs * 2000 = 10000 tokens
            ("audit", 2, 10000),  # 2 runs * 10000 = 20000 tokens (most expensive per run)
        ]

        for phase_type, count, tokens in phase_types:
            for i in range(count):
                event = UsageEventData(
                    provider="anthropic",
                    model="claude-3-5-sonnet",
                    run_id=f"run-{phase_type}-{i}",
                    phase_id=f"phase-{phase_type}-{i}",
                    role="builder",
                    total_tokens=tokens,
                    prompt_tokens=int(tokens * 0.6),
                    completion_tokens=int(tokens * 0.4),
                    phase_type=phase_type,
                    intent="feature",
                )
                record_usage(db_session, event)

        aggregator = CostAggregator(session=db_session)
        report = aggregator.generate_report(days=30)

        insights = report["insights"]
        assert len(insights) > 0

        # Check for most expensive phase type insight
        most_expensive_insight = [i for i in insights if "Most expensive" in i]
        assert len(most_expensive_insight) > 0
        assert "audit" in most_expensive_insight[0]

    def test_generate_report_empty_db(self, db_session):
        """Test report structure when database is empty"""
        aggregator = CostAggregator(session=db_session)
        report = aggregator.generate_report(days=30)

        assert report["period_days"] == 30
        assert report["by_phase_type"] == []
        assert report["by_intent"] == []
        assert isinstance(report["insights"], list)


class TestCostAggregatorSessionManagement:
    """Test CostAggregator session management"""

    def test_aggregator_with_external_session(self, db_session):
        """Test aggregator uses provided session without closing it"""
        # Insert test data
        event = UsageEventData(
            provider="anthropic",
            model="claude-3-5-sonnet",
            run_id="run-session",
            phase_id="phase-session",
            role="builder",
            total_tokens=3000,
            prompt_tokens=1800,
            completion_tokens=1200,
            phase_type="build",
            intent="feature",
        )
        record_usage(db_session, event)

        # Aggregator should not close the session it didn't create
        aggregator = CostAggregator(session=db_session)
        results = aggregator.by_phase_type(days=30)

        assert len(results) == 1
        # Session should still be usable
        assert db_session.is_active

    def test_aggregator_creates_own_session(self, db_engine):
        """Test aggregator manages its own session"""
        from sqlalchemy.orm import sessionmaker

        from autopack.database import Base

        # Ensure tables are created on the engine
        Base.metadata.create_all(bind=db_engine)

        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        session = TestingSessionLocal()

        # Insert test data
        event = UsageEventData(
            provider="anthropic",
            model="claude-3-5-sonnet",
            run_id="run-own-session",
            phase_id="phase-own",
            role="builder",
            total_tokens=1000,
            prompt_tokens=600,
            completion_tokens=400,
            phase_type="audit",
            intent="bugfix",
        )
        record_usage(session, event)
        session.close()

        # Create aggregator with the database engine's session factory
        TestingSessionLocal2 = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        new_session = TestingSessionLocal2()
        try:
            aggregator = CostAggregator(session=new_session)
            results = aggregator.by_phase_type(days=30)

            assert len(results) == 1
            assert results[0].category_value == "audit"
        finally:
            new_session.close()
