"""Tests for insight_provenance.py (IMP-LOOP-015).

Tests cover:
- InsightProvenance dataclass and explain() method
- TaskRecommendation dataclass and explain() method
- ProvenanceTracker.record_insight_source()
- ProvenanceTracker.record_task_recommendation()
- ProvenanceTracker.get_recommendation_explanation()
- ProvenanceTracker.get_full_lineage()
- Provenance serialization/deserialization
"""

from autopack.memory.insight_provenance import (
    InsightProvenance,
    ProvenanceTracker,
    TaskRecommendation,
)


class TestInsightProvenance:
    """Tests for InsightProvenance dataclass."""

    def test_insight_provenance_creation(self):
        """InsightProvenance should store all required fields."""
        provenance = InsightProvenance(
            insight_id="insight:test:001",
            source_telemetry_events=["event1", "event2"],
            analysis_logic_id="cost_analyzer_v1",
            supporting_data={"avg_cost": 1500, "threshold": 1000},
            confidence_evidence=["Cost exceeded threshold by 50%"],
        )

        assert provenance.insight_id == "insight:test:001"
        assert len(provenance.source_telemetry_events) == 2
        assert provenance.analysis_logic_id == "cost_analyzer_v1"
        assert provenance.supporting_data["avg_cost"] == 1500
        assert len(provenance.confidence_evidence) == 1

    def test_insight_provenance_with_optional_fields(self):
        """InsightProvenance should handle optional fields."""
        provenance = InsightProvenance(
            insight_id="insight:test:002",
            source_telemetry_events=["event1"],
            analysis_logic_id="failure_detector",
            supporting_data={},
            confidence_evidence=[],
            insight_type="failure_mode",
            severity="high",
        )

        assert provenance.insight_type == "failure_mode"
        assert provenance.severity == "high"

    def test_insight_provenance_explain_basic(self):
        """explain() should return human-readable explanation."""
        provenance = InsightProvenance(
            insight_id="insight:test:003",
            source_telemetry_events=["event1", "event2", "event3"],
            analysis_logic_id="pattern_detector",
            supporting_data={},
            confidence_evidence=["Pattern detected in 3 events"],
        )

        explanation = provenance.explain()

        assert "insight:test:003" in explanation
        assert "pattern_detector" in explanation
        assert "3 telemetry events" in explanation
        assert "Pattern detected in 3 events" in explanation

    def test_insight_provenance_explain_with_supporting_data(self):
        """explain() should include supporting data."""
        provenance = InsightProvenance(
            insight_id="insight:test:004",
            source_telemetry_events=["event1"],
            analysis_logic_id="cost_analyzer",
            supporting_data={"avg_cost": 1500, "max_cost": 3000},
            confidence_evidence=[],
        )

        explanation = provenance.explain()

        assert "avg_cost" in explanation
        assert "1500" in explanation
        assert "max_cost" in explanation

    def test_insight_provenance_explain_truncates_long_values(self):
        """explain() should truncate long supporting data values."""
        long_value = "x" * 200
        provenance = InsightProvenance(
            insight_id="insight:test:005",
            source_telemetry_events=["event1"],
            analysis_logic_id="analyzer",
            supporting_data={"long_field": long_value},
            confidence_evidence=[],
        )

        explanation = provenance.explain()

        # Should be truncated to 97 chars + "..." (100 total, not full 200 chars)
        assert "x" * 97 in explanation
        assert "x" * 101 not in explanation
        assert "..." in explanation

    def test_insight_provenance_to_dict(self):
        """to_dict() should serialize provenance to dictionary."""
        provenance = InsightProvenance(
            insight_id="insight:test:006",
            source_telemetry_events=["event1"],
            analysis_logic_id="analyzer",
            supporting_data={"key": "value"},
            confidence_evidence=["evidence1"],
            insight_type="cost_sink",
            severity="medium",
        )

        data = provenance.to_dict()

        assert data["insight_id"] == "insight:test:006"
        assert data["source_telemetry_events"] == ["event1"]
        assert data["analysis_logic_id"] == "analyzer"
        assert data["supporting_data"] == {"key": "value"}
        assert data["confidence_evidence"] == ["evidence1"]
        assert data["insight_type"] == "cost_sink"
        assert data["severity"] == "medium"
        assert "created_at" in data

    def test_insight_provenance_from_dict(self):
        """from_dict() should deserialize provenance from dictionary."""
        data = {
            "insight_id": "insight:test:007",
            "source_telemetry_events": ["event1", "event2"],
            "analysis_logic_id": "analyzer",
            "supporting_data": {"key": "value"},
            "confidence_evidence": ["evidence1"],
            "created_at": "2025-01-15T10:30:00+00:00",
            "insight_type": "failure_mode",
            "severity": "high",
        }

        provenance = InsightProvenance.from_dict(data)

        assert provenance.insight_id == "insight:test:007"
        assert len(provenance.source_telemetry_events) == 2
        assert provenance.insight_type == "failure_mode"
        assert provenance.severity == "high"

    def test_insight_provenance_from_dict_with_missing_optional_fields(self):
        """from_dict() should handle missing optional fields."""
        data = {
            "insight_id": "insight:test:008",
        }

        provenance = InsightProvenance.from_dict(data)

        assert provenance.insight_id == "insight:test:008"
        assert provenance.source_telemetry_events == []
        assert provenance.analysis_logic_id == "unknown"
        assert provenance.supporting_data == {}
        assert provenance.confidence_evidence == []


class TestTaskRecommendation:
    """Tests for TaskRecommendation dataclass."""

    def test_task_recommendation_creation(self):
        """TaskRecommendation should store all required fields."""
        recommendation = TaskRecommendation(
            task_id="task:001",
            task_description="Optimize token usage in phase X",
            source_insight_ids=["insight:001", "insight:002"],
            priority_score=0.85,
            rationale="High cost detected in multiple phases",
            expected_impact="30% token reduction",
        )

        assert recommendation.task_id == "task:001"
        assert recommendation.priority_score == 0.85
        assert len(recommendation.source_insight_ids) == 2

    def test_task_recommendation_explain(self):
        """explain() should return human-readable explanation."""
        recommendation = TaskRecommendation(
            task_id="task:002",
            task_description="Fix retry loop",
            source_insight_ids=["insight:001"],
            priority_score=0.9,
            rationale="Excessive retries detected",
            expected_impact="Reduced latency",
        )

        explanation = recommendation.explain()

        assert "task:002" in explanation
        assert "Fix retry loop" in explanation
        assert "0.90" in explanation
        assert "Excessive retries detected" in explanation
        assert "insight:001" in explanation


class TestProvenanceTracker:
    """Tests for ProvenanceTracker class."""

    def test_record_insight_source_basic(self):
        """record_insight_source should create and store provenance."""
        tracker = ProvenanceTracker()

        provenance = tracker.record_insight_source(
            insight_id="insight:test:001",
            telemetry_events=["event1", "event2"],
            analysis_logic="cost_analyzer",
            supporting_data={"avg_cost": 1500},
        )

        assert provenance.insight_id == "insight:test:001"
        assert tracker.insight_count == 1

    def test_record_insight_source_with_all_options(self):
        """record_insight_source should accept all optional parameters."""
        tracker = ProvenanceTracker()

        provenance = tracker.record_insight_source(
            insight_id="insight:test:002",
            telemetry_events=["event1"],
            analysis_logic="failure_detector",
            supporting_data={},
            confidence_evidence=["High confidence due to pattern match"],
            insight_type="failure_mode",
            severity="critical",
        )

        assert provenance.insight_type == "failure_mode"
        assert provenance.severity == "critical"
        assert len(provenance.confidence_evidence) == 1

    def test_record_task_recommendation(self):
        """record_task_recommendation should store recommendation and link to insights."""
        tracker = ProvenanceTracker()

        # First record an insight
        tracker.record_insight_source(
            insight_id="insight:001",
            telemetry_events=["event1"],
            analysis_logic="analyzer",
            supporting_data={},
        )

        # Then record a recommendation based on that insight
        recommendation = tracker.record_task_recommendation(
            task_id="task:001",
            task_description="Fix the issue",
            source_insight_ids=["insight:001"],
            priority_score=0.8,
            rationale="High priority issue",
            expected_impact="Improved reliability",
        )

        assert recommendation.task_id == "task:001"
        assert tracker.recommendation_count == 1
        assert tracker.get_tasks_for_insight("insight:001") == ["task:001"]

    def test_get_insight_provenance(self):
        """get_insight_provenance should return stored provenance."""
        tracker = ProvenanceTracker()

        tracker.record_insight_source(
            insight_id="insight:lookup:001",
            telemetry_events=["event1"],
            analysis_logic="analyzer",
            supporting_data={"key": "value"},
        )

        provenance = tracker.get_insight_provenance("insight:lookup:001")

        assert provenance is not None
        assert provenance.insight_id == "insight:lookup:001"

    def test_get_insight_provenance_not_found(self):
        """get_insight_provenance should return None for unknown insight."""
        tracker = ProvenanceTracker()

        provenance = tracker.get_insight_provenance("nonexistent")

        assert provenance is None

    def test_get_recommendation(self):
        """get_recommendation should return stored recommendation."""
        tracker = ProvenanceTracker()

        tracker.record_task_recommendation(
            task_id="task:lookup:001",
            task_description="Test task",
            source_insight_ids=[],
            priority_score=0.5,
            rationale="Test",
            expected_impact="Test",
        )

        recommendation = tracker.get_recommendation("task:lookup:001")

        assert recommendation is not None
        assert recommendation.task_id == "task:lookup:001"

    def test_get_recommendation_not_found(self):
        """get_recommendation should return None for unknown task."""
        tracker = ProvenanceTracker()

        recommendation = tracker.get_recommendation("nonexistent")

        assert recommendation is None

    def test_get_recommendation_explanation(self):
        """get_recommendation_explanation should provide full trace."""
        tracker = ProvenanceTracker()

        # Record insight with provenance
        tracker.record_insight_source(
            insight_id="insight:explain:001",
            telemetry_events=["event1", "event2"],
            analysis_logic="cost_analyzer",
            supporting_data={"avg_cost": 2000},
            confidence_evidence=["Cost threshold exceeded"],
        )

        # Record recommendation
        tracker.record_task_recommendation(
            task_id="task:explain:001",
            task_description="Reduce token usage",
            source_insight_ids=["insight:explain:001"],
            priority_score=0.9,
            rationale="High cost detected",
            expected_impact="30% cost reduction",
        )

        explanation = tracker.get_recommendation_explanation("task:explain:001")

        # Should include task details
        assert "task:explain:001" in explanation
        assert "Reduce token usage" in explanation

        # Should include insight details
        assert "insight:explain:001" in explanation
        assert "cost_analyzer" in explanation
        assert "Cost threshold exceeded" in explanation

    def test_get_recommendation_explanation_not_found(self):
        """get_recommendation_explanation should handle missing task."""
        tracker = ProvenanceTracker()

        explanation = tracker.get_recommendation_explanation("nonexistent")

        assert "No recommendation found" in explanation

    def test_get_full_lineage(self):
        """get_full_lineage should return complete provenance chain."""
        tracker = ProvenanceTracker()

        # Record multiple insights
        tracker.record_insight_source(
            insight_id="insight:lineage:001",
            telemetry_events=["event1", "event2"],
            analysis_logic="analyzer1",
            supporting_data={"metric": 100},
        )

        tracker.record_insight_source(
            insight_id="insight:lineage:002",
            telemetry_events=["event3"],
            analysis_logic="analyzer2",
            supporting_data={"metric": 200},
        )

        # Record recommendation based on both insights
        tracker.record_task_recommendation(
            task_id="task:lineage:001",
            task_description="Combined fix",
            source_insight_ids=["insight:lineage:001", "insight:lineage:002"],
            priority_score=0.95,
            rationale="Multiple issues detected",
            expected_impact="Comprehensive improvement",
        )

        lineage = tracker.get_full_lineage("task:lineage:001")

        assert "task" in lineage
        assert lineage["task"]["id"] == "task:lineage:001"

        assert "insights" in lineage
        assert len(lineage["insights"]) == 2

        assert "telemetry_events" in lineage
        assert sorted(lineage["telemetry_events"]) == ["event1", "event2", "event3"]

    def test_get_full_lineage_not_found(self):
        """get_full_lineage should handle missing task."""
        tracker = ProvenanceTracker()

        lineage = tracker.get_full_lineage("nonexistent")

        assert "error" in lineage

    def test_get_tasks_for_insight(self):
        """get_tasks_for_insight should return all derived tasks."""
        tracker = ProvenanceTracker()

        tracker.record_insight_source(
            insight_id="insight:multi:001",
            telemetry_events=["event1"],
            analysis_logic="analyzer",
            supporting_data={},
        )

        # Record multiple tasks from same insight
        tracker.record_task_recommendation(
            task_id="task:multi:001",
            task_description="First task",
            source_insight_ids=["insight:multi:001"],
            priority_score=0.8,
            rationale="Test",
            expected_impact="Test",
        )

        tracker.record_task_recommendation(
            task_id="task:multi:002",
            task_description="Second task",
            source_insight_ids=["insight:multi:001"],
            priority_score=0.7,
            rationale="Test",
            expected_impact="Test",
        )

        tasks = tracker.get_tasks_for_insight("insight:multi:001")

        assert len(tasks) == 2
        assert "task:multi:001" in tasks
        assert "task:multi:002" in tasks

    def test_get_tasks_for_insight_not_found(self):
        """get_tasks_for_insight should return empty list for unknown insight."""
        tracker = ProvenanceTracker()

        tasks = tracker.get_tasks_for_insight("nonexistent")

        assert tasks == []

    def test_generate_insight_id(self):
        """generate_insight_id should create deterministic IDs."""
        tracker = ProvenanceTracker()

        id1 = tracker.generate_insight_id("cost_analyzer", "phase_001")
        id2 = tracker.generate_insight_id("cost_analyzer", "phase_001")
        id3 = tracker.generate_insight_id("cost_analyzer", "phase_002")

        # Same inputs should produce same ID
        assert id1 == id2

        # Different inputs should produce different IDs
        assert id1 != id3

        # Should have expected format
        assert id1.startswith("insight:cost_analyzer:")

    def test_clear(self):
        """clear() should remove all tracked data."""
        tracker = ProvenanceTracker()

        tracker.record_insight_source(
            insight_id="insight:clear:001",
            telemetry_events=["event1"],
            analysis_logic="analyzer",
            supporting_data={},
        )

        tracker.record_task_recommendation(
            task_id="task:clear:001",
            task_description="Test",
            source_insight_ids=["insight:clear:001"],
            priority_score=0.5,
            rationale="Test",
            expected_impact="Test",
        )

        assert tracker.insight_count == 1
        assert tracker.recommendation_count == 1

        tracker.clear()

        assert tracker.insight_count == 0
        assert tracker.recommendation_count == 0

    def test_insight_count_property(self):
        """insight_count should return correct count."""
        tracker = ProvenanceTracker()

        assert tracker.insight_count == 0

        tracker.record_insight_source(
            insight_id="insight:count:001",
            telemetry_events=[],
            analysis_logic="analyzer",
            supporting_data={},
        )

        assert tracker.insight_count == 1

    def test_recommendation_count_property(self):
        """recommendation_count should return correct count."""
        tracker = ProvenanceTracker()

        assert tracker.recommendation_count == 0

        tracker.record_task_recommendation(
            task_id="task:count:001",
            task_description="Test",
            source_insight_ids=[],
            priority_score=0.5,
            rationale="Test",
            expected_impact="Test",
        )

        assert tracker.recommendation_count == 1


class TestProvenanceTrackerEdgeCases:
    """Edge case tests for ProvenanceTracker."""

    def test_recommendation_with_missing_insight_provenance(self):
        """Explanation should handle insights without recorded provenance."""
        tracker = ProvenanceTracker()

        # Record recommendation referencing non-existent insight
        tracker.record_task_recommendation(
            task_id="task:missing:001",
            task_description="Test",
            source_insight_ids=["nonexistent:insight"],
            priority_score=0.5,
            rationale="Test",
            expected_impact="Test",
        )

        explanation = tracker.get_recommendation_explanation("task:missing:001")

        assert "nonexistent:insight" in explanation
        assert "provenance not recorded" in explanation

    def test_empty_telemetry_events(self):
        """Should handle insights with no telemetry events."""
        tracker = ProvenanceTracker()

        provenance = tracker.record_insight_source(
            insight_id="insight:empty:001",
            telemetry_events=[],
            analysis_logic="manual_entry",
            supporting_data={"source": "human_reported"},
        )

        explanation = provenance.explain()

        assert "0 telemetry events" in explanation

    def test_empty_confidence_evidence(self):
        """Should handle insights with no confidence evidence."""
        tracker = ProvenanceTracker()

        provenance = tracker.record_insight_source(
            insight_id="insight:noevidence:001",
            telemetry_events=["event1"],
            analysis_logic="analyzer",
            supporting_data={},
            confidence_evidence=[],
        )

        explanation = provenance.explain()

        assert "Evidence:" not in explanation

    def test_recommendation_with_zero_priority(self):
        """Should handle zero priority score."""
        tracker = ProvenanceTracker()

        recommendation = tracker.record_task_recommendation(
            task_id="task:zero:001",
            task_description="Low priority task",
            source_insight_ids=[],
            priority_score=0.0,
            rationale="Test",
            expected_impact="Test",
        )

        explanation = recommendation.explain()

        assert "0.00" in explanation
