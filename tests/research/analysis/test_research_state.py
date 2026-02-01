"""
Comprehensive tests for research_state tracker module.

Tests cover:
- Research state creation and persistence
- Gap detection (coverage, recency, depth)
- Coverage metrics calculation
- Query and source deduplication
- Checkpoint creation and recovery
- State validation and repair
- Partial results handling
- Async failure recovery
- Edge cases and error handling
"""

import json

import pytest

pytestmark = pytest.mark.research
from datetime import datetime, timedelta

from autopack.research.analysis.research_state import (
    CompletedQuery,
    CoverageMetrics,
    DiscoveredSource,
    GapPriority,
    GapType,
    ResearchCheckpoint,
    ResearchDepth,
    ResearchGap,
    ResearchRequirements,
    ResearchState,
    ResearchStateTracker,
)


class TestGapType:
    """Tests for GapType enum."""

    def test_all_gap_types_exist(self):
        """Test that all expected gap types are defined."""
        gap_types = {g.value for g in GapType}
        expected = {"coverage", "entity", "depth", "recency", "validation"}
        assert gap_types == expected


class TestGapPriority:
    """Tests for GapPriority enum."""

    def test_all_priorities_exist(self):
        """Test that all expected priorities are defined."""
        priorities = {p.value for p in GapPriority}
        expected = {"critical", "high", "medium", "low"}
        assert priorities == expected


class TestResearchDepth:
    """Tests for ResearchDepth enum."""

    def test_all_depths_exist(self):
        """Test that all expected depths are defined."""
        depths = {d.value for d in ResearchDepth}
        expected = {"shallow", "medium", "deep"}
        assert depths == expected


class TestCompletedQuery:
    """Tests for CompletedQuery data class."""

    def test_basic_initialization(self):
        """Test basic initialization."""
        now = datetime.now()
        query = CompletedQuery(
            query="market size analysis",
            agent="market-research-agent",
            timestamp=now,
            sources_found=5,
            quality_score=0.85,
            key_findings_hash="abc123",
        )
        assert query.query == "market size analysis"
        assert query.agent == "market-research-agent"
        assert query.sources_found == 5
        assert query.quality_score == 0.85
        assert query.gap_id is None

    def test_initialization_with_gap_id(self):
        """Test initialization with gap ID."""
        query = CompletedQuery(
            query="test query",
            agent="test-agent",
            timestamp=datetime.now(),
            sources_found=3,
            quality_score=0.7,
            key_findings_hash="def456",
            gap_id="gap-001",
        )
        assert query.gap_id == "gap-001"


class TestDiscoveredSource:
    """Tests for DiscoveredSource data class."""

    def test_basic_initialization(self):
        """Test basic initialization."""
        source = DiscoveredSource(
            url="https://example.com",
            source_type="blog",
            accessed_at=datetime.now(),
            content_hash="xyz789",
            relevance_score=0.95,
        )
        assert source.url == "https://example.com"
        assert source.source_type == "blog"
        assert source.relevance_score == 0.95
        assert source.used_in == []

    def test_initialization_with_used_in(self):
        """Test initialization with used_in tracking."""
        source = DiscoveredSource(
            url="https://example.com",
            source_type="documentation",
            accessed_at=datetime.now(),
            content_hash="hash123",
            relevance_score=0.88,
            used_in=["market-research-agent", "competitive-analysis-agent"],
        )
        assert len(source.used_in) == 2


class TestResearchGap:
    """Tests for ResearchGap data class."""

    def test_basic_initialization(self):
        """Test basic initialization."""
        gap = ResearchGap(
            gap_id="gap-001",
            gap_type=GapType.COVERAGE,
            category="market_research",
            description="Market size coverage at 40%, need 70%",
            priority=GapPriority.HIGH,
        )
        assert gap.gap_id == "gap-001"
        assert gap.gap_type == GapType.COVERAGE
        assert gap.status == "pending"
        assert gap.addressed_at is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        gap = ResearchGap(
            gap_id="gap-001",
            gap_type=GapType.COVERAGE,
            category="market_research",
            description="Coverage gap",
            priority=GapPriority.HIGH,
            suggested_queries=["query1", "query2"],
        )
        gap_dict = gap.to_dict()

        assert gap_dict["gap_id"] == "gap-001"
        assert gap_dict["gap_type"] == "coverage"
        assert gap_dict["priority"] == "high"
        assert len(gap_dict["suggested_queries"]) == 2


class TestCoverageMetrics:
    """Tests for CoverageMetrics data class."""

    def test_initialization(self):
        """Test initialization with defaults."""
        metrics = CoverageMetrics()

        assert metrics.overall_percentage == 0.0
        assert len(metrics.by_category) == 6  # Should have all default categories
        assert all(v == 0.0 for v in metrics.by_category.values())

    def test_custom_categories(self):
        """Test initialization with custom categories."""
        metrics = CoverageMetrics(
            by_category={
                "category1": 50.0,
                "category2": 75.0,
            }
        )
        assert metrics.by_category["category1"] == 50.0
        assert metrics.by_category["category2"] == 75.0

    def test_recalculate_overall(self):
        """Test recalculating overall coverage."""
        metrics = CoverageMetrics(
            by_category={
                "market_research": 100.0,
                "competitive_analysis": 80.0,
                "technical_feasibility": 60.0,
                "legal_policy": 40.0,
                "social_sentiment": 20.0,
                "tool_availability": 0.0,
            }
        )
        metrics.recalculate_overall()

        expected_overall = (100 + 80 + 60 + 40 + 20 + 0) / 6
        assert metrics.overall_percentage == pytest.approx(expected_overall)

    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = CoverageMetrics(
            by_category={"market_research": 75.5, "competitive_analysis": 60.3}
        )
        metrics.recalculate_overall()

        metrics_dict = metrics.to_dict()
        assert "overall_percentage" in metrics_dict
        assert "by_category" in metrics_dict
        assert metrics_dict["by_category"]["market_research"] == 75.5


class TestResearchState:
    """Tests for ResearchState data class."""

    def test_initialization(self):
        """Test basic initialization."""
        state = ResearchState(project_id="project-001")

        assert state.project_id == "project-001"
        assert state.version == 1
        assert isinstance(state.created_at, datetime)
        assert isinstance(state.last_updated, datetime)
        assert len(state.completed_queries) == 0
        assert len(state.discovered_sources) == 0
        assert len(state.identified_gaps) == 0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        state = ResearchState(project_id="project-001")
        state_dict = state.to_dict()

        assert "research_state" in state_dict
        assert state_dict["research_state"]["project_id"] == "project-001"
        assert "created_at" in state_dict["research_state"]
        assert "completed_queries" in state_dict["research_state"]

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        original = ResearchState(project_id="project-001")
        state_dict = original.to_dict()

        loaded = ResearchState.from_dict(state_dict)

        assert loaded.project_id == "project-001"
        assert loaded.version == original.version

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are consistent."""
        original = ResearchState(project_id="project-001")
        original.coverage.by_category["market_research"] = 75.0

        query = CompletedQuery(
            query="test query",
            agent="test-agent",
            timestamp=datetime.now(),
            sources_found=3,
            quality_score=0.8,
            key_findings_hash="hash123",
        )
        original.completed_queries.append(query)

        # Serialize and deserialize
        dict_form = original.to_dict()
        loaded = ResearchState.from_dict(dict_form)

        assert loaded.project_id == original.project_id
        assert loaded.coverage.by_category["market_research"] == 75.0
        assert len(loaded.completed_queries) == 1


class TestResearchRequirements:
    """Tests for ResearchRequirements data class."""

    def test_initialization_with_defaults(self):
        """Test initialization with default requirements."""
        req = ResearchRequirements()

        assert req.min_sources == 2
        assert "market_research" in req.min_coverage
        assert req.min_coverage["market_research"] == 70
        assert "market-research-agent" in req.max_age_days

    def test_custom_requirements(self):
        """Test initialization with custom requirements."""
        req = ResearchRequirements(
            min_coverage={"category1": 50},
            min_sources=5,
            max_age_days={"agent1": 14},
        )
        assert req.min_sources == 5
        assert req.min_coverage["category1"] == 50


class TestResearchCheckpoint:
    """Tests for ResearchCheckpoint data class."""

    def test_initialization(self):
        """Test basic initialization."""
        checkpoint = ResearchCheckpoint(checkpoint_id="cp-001")

        assert checkpoint.checkpoint_id == "cp-001"
        assert checkpoint.phase == ""
        assert checkpoint.is_recoverable is True
        assert len(checkpoint.completed_steps) == 0
        assert len(checkpoint.failed_tasks) == 0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        checkpoint = ResearchCheckpoint(
            checkpoint_id="cp-001",
            phase="market_research",
            completed_steps=["step1", "step2"],
        )
        cp_dict = checkpoint.to_dict()

        assert cp_dict["checkpoint_id"] == "cp-001"
        assert cp_dict["phase"] == "market_research"
        assert len(cp_dict["completed_steps"]) == 2

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        original = ResearchCheckpoint(
            checkpoint_id="cp-001",
            phase="test_phase",
        )
        cp_dict = original.to_dict()

        loaded = ResearchCheckpoint.from_dict(cp_dict)

        assert loaded.checkpoint_id == "cp-001"
        assert loaded.phase == "test_phase"


class TestResearchStateTracker:
    """Tests for ResearchStateTracker main class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        return tmp_path / "test_project"

    @pytest.fixture
    def tracker(self, temp_project):
        """Create a ResearchStateTracker instance."""
        return ResearchStateTracker(temp_project)

    def test_initialization(self, tracker):
        """Test tracker initialization."""
        assert tracker.state_dir == tracker.project_root / ".autopack"
        assert tracker.state_file == tracker.state_dir / "research_state.json"
        assert tracker._state is None

    def test_load_or_create_new_state(self, tracker):
        """Test loading or creating a new state."""
        state = tracker.load_or_create_state("project-001")

        assert state.project_id == "project-001"
        assert tracker._state is not None
        assert tracker.state_dir.exists()

    def test_load_existing_state(self, tracker):
        """Test loading existing state from file."""
        # Create initial state
        initial_state = tracker.load_or_create_state("project-001")
        tracker.save_state()

        # Create new tracker and load
        tracker2 = ResearchStateTracker(tracker.project_root)
        loaded_state = tracker2.load_or_create_state("project-001")

        assert loaded_state.project_id == "project-001"
        # Version should be 2 after save (incremented from 1)
        assert loaded_state.version == 2

    def test_save_state_increments_version(self, tracker):
        """Test that saving state increments version."""
        tracker.load_or_create_state("project-001")
        assert tracker._state.version == 1

        tracker.save_state()
        assert tracker._state.version == 2

        tracker.save_state()
        assert tracker._state.version == 3

    def test_state_file_created_on_save(self, tracker):
        """Test that state file is created on save."""
        tracker.load_or_create_state("project-001")
        tracker.save_state()

        assert tracker.state_file.exists()

        # Verify it's valid JSON
        with open(tracker.state_file, "r") as f:
            data = json.load(f)
            assert "research_state" in data

    def test_record_completed_query(self, tracker):
        """Test recording a completed query."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_completed_query(
            query="test query",
            agent="test-agent",
            sources_found=3,
            quality_score=0.8,
            findings={"key": "value"},
        )

        assert len(tracker._state.completed_queries) == 1
        assert tracker._state.completed_queries[0].query == "test query"

    def test_record_discovered_source(self, tracker):
        """Test recording a discovered source."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_discovered_source(
            url="https://example.com",
            source_type="blog",
            content_hash="hash123",
            relevance_score=0.9,
            agent="test-agent",
        )

        assert len(tracker._state.discovered_sources) == 1
        assert tracker._state.discovered_sources[0].url == "https://example.com"

    def test_source_deduplication(self, tracker):
        """Test that sources are deduplicated by URL."""
        state = tracker.load_or_create_state("project-001")

        # Record same URL twice
        tracker.record_discovered_source(
            url="https://example.com",
            source_type="blog",
            content_hash="hash1",
            relevance_score=0.9,
            agent="agent1",
        )
        tracker.record_discovered_source(
            url="https://example.com",
            source_type="blog",
            content_hash="hash1",
            relevance_score=0.9,
            agent="agent2",
        )

        # Should only have one source, but used by both agents
        assert len(tracker._state.discovered_sources) == 1
        assert "agent1" in tracker._state.discovered_sources[0].used_in
        assert "agent2" in tracker._state.discovered_sources[0].used_in

    def test_should_skip_query_exact_match(self, tracker):
        """Test query skip detection with exact match."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_completed_query(
            query="market size analysis",
            agent="test-agent",
            sources_found=3,
            quality_score=0.8,
            findings={},
        )

        # Exact match should be skipped
        assert tracker.should_skip_query("market size analysis") is True

    def test_should_skip_query_case_insensitive(self, tracker):
        """Test query skip detection is case-insensitive."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_completed_query(
            query="Market Size Analysis",
            agent="test-agent",
            sources_found=3,
            quality_score=0.8,
            findings={},
        )

        assert tracker.should_skip_query("market size analysis") is True

    def test_should_skip_query_similarity(self, tracker):
        """Test query skip detection with similar queries."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_completed_query(
            query="market size and growth projections",
            agent="test-agent",
            sources_found=3,
            quality_score=0.8,
            findings={},
            gap_id="gap-001",
        )

        # Similar query (80% overlap) and recent should be skipped
        similar = "market size projections and growth"
        assert tracker.should_skip_query(similar) is True

    def test_is_new_source_by_url(self, tracker):
        """Test new source detection by URL."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_discovered_source(
            url="https://example.com",
            source_type="blog",
            content_hash="hash1",
            relevance_score=0.9,
            agent="agent1",
        )

        # Same URL is not new
        assert tracker.is_new_source("https://example.com") is False
        # Different URL is new
        assert tracker.is_new_source("https://different.com") is True

    def test_is_new_source_by_content_hash(self, tracker):
        """Test new source detection by content hash."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_discovered_source(
            url="https://example1.com",
            source_type="blog",
            content_hash="abc123",
            relevance_score=0.9,
            agent="agent1",
        )

        # Same hash is not new
        assert tracker.is_new_source("https://example2.com", content_hash="abc123") is False

    def test_update_coverage(self, tracker):
        """Test updating coverage for a category."""
        state = tracker.load_or_create_state("project-001")

        tracker.update_coverage("market_research", 85.0)

        assert tracker._state.coverage.by_category["market_research"] == 85.0

    def test_update_coverage_capped_at_100(self, tracker):
        """Test that coverage is capped at 100%."""
        state = tracker.load_or_create_state("project-001")

        tracker.update_coverage("market_research", 150.0)

        assert tracker._state.coverage.by_category["market_research"] == 100.0

    def test_detect_gaps_coverage_gap(self, tracker):
        """Test detecting coverage gaps."""
        state = tracker.load_or_create_state("project-001")

        # Set low coverage
        tracker.update_coverage("market_research", 30.0)

        gaps = tracker.detect_gaps()

        # Should find coverage gap
        coverage_gaps = [g for g in gaps if g.gap_type == GapType.COVERAGE]
        assert len(coverage_gaps) > 0
        assert any(g.category == "market_research" for g in coverage_gaps)

    def test_detect_gaps_recency_gap(self, tracker):
        """Test detecting recency gaps."""
        state = tracker.load_or_create_state("project-001")

        # Record old query (older than max_age_days)
        old_timestamp = datetime.now() - timedelta(days=40)
        old_query = CompletedQuery(
            query="old query",
            agent="market-research-agent",
            timestamp=old_timestamp,
            sources_found=3,
            quality_score=0.8,
            key_findings_hash="hash123",
        )
        tracker._state.completed_queries.append(old_query)

        gaps = tracker.detect_gaps()

        # Should find recency gap
        recency_gaps = [g for g in gaps if g.gap_type == GapType.RECENCY]
        assert len(recency_gaps) > 0

    def test_detect_gaps_depth_gap(self, tracker):
        """Test detecting depth gaps."""
        state = tracker.load_or_create_state("project-001")

        # Leave critical topics at shallow depth
        gaps = tracker.detect_gaps()

        # Should find depth gaps for critical topics
        depth_gaps = [g for g in gaps if g.gap_type == GapType.DEPTH]
        assert len(depth_gaps) > 0

    def test_gap_priority_calculation(self, tracker):
        """Test that gap priorities are calculated correctly."""
        state = tracker.load_or_create_state("project-001")

        # Large gap should be critical
        tracker.update_coverage("market_research", 0.0)

        gaps = tracker.detect_gaps()
        coverage_gaps = [
            g for g in gaps if g.gap_type == GapType.COVERAGE and g.category == "market_research"
        ]

        assert len(coverage_gaps) > 0
        assert coverage_gaps[0].priority == GapPriority.CRITICAL

    def test_validate_state_consistency(self, tracker):
        """Test state validation."""
        state = tracker.load_or_create_state("project-001")

        errors = tracker.validate_state_consistency()

        # Should have no errors for valid state
        assert len(errors) == 0

    def test_validate_state_coverage_range(self, tracker):
        """Test validation detects coverage out of range."""
        state = tracker.load_or_create_state("project-001")

        # Set invalid coverage
        tracker._state.coverage.by_category["market_research"] = 150.0

        errors = tracker.validate_state_consistency()

        # Should detect invalid coverage
        assert any("Coverage" in str(e) and "market_research" in str(e) for e in errors)

    def test_validate_state_duplicate_gaps(self, tracker):
        """Test validation detects duplicate gap IDs."""
        state = tracker.load_or_create_state("project-001")

        # Add duplicate gap IDs
        gap1 = ResearchGap(
            gap_id="gap-001",
            gap_type=GapType.COVERAGE,
            category="test",
            description="test",
            priority=GapPriority.HIGH,
        )
        gap2 = ResearchGap(
            gap_id="gap-001",  # Duplicate ID
            gap_type=GapType.COVERAGE,
            category="test",
            description="test",
            priority=GapPriority.HIGH,
        )
        tracker._state.identified_gaps.append(gap1)
        tracker._state.identified_gaps.append(gap2)

        errors = tracker.validate_state_consistency()

        # Should detect duplicate gap IDs
        assert any("Duplicate" in str(e) for e in errors)

    def test_repair_state_coverage(self, tracker):
        """Test state repair for invalid coverage."""
        state = tracker.load_or_create_state("project-001")

        # Introduce invalid data
        tracker._state.coverage.by_category["market_research"] = 150.0

        # Repair
        result = tracker.repair_state()

        assert result["repair_successful"] is True
        assert tracker._state.coverage.by_category["market_research"] == 100.0

    def test_create_checkpoint(self, tracker):
        """Test creating a checkpoint."""
        state = tracker.load_or_create_state("project-001")

        checkpoint = tracker.create_checkpoint("market_research")

        assert checkpoint.phase == "market_research"
        assert checkpoint.checkpoint_id is not None
        assert checkpoint.state_snapshot is not None

    def test_checkpoint_file_created(self, tracker):
        """Test that checkpoint file is created."""
        state = tracker.load_or_create_state("project-001")

        checkpoint = tracker.create_checkpoint("test_phase")

        cp_file = tracker.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        assert cp_file.exists()

    def test_handle_partial_results(self, tracker):
        """Test handling partial results."""
        state = tracker.load_or_create_state("project-001")

        results = {
            "item1": {"data": "value1"},
            "item2": {"data": "value2"},
        }

        processed = tracker.handle_partial_results("test_phase", results)

        assert processed["partial_results_stored"] is True
        assert processed["items_processed"] == 2

    def test_handle_async_failure(self, tracker):
        """Test handling async task failure."""
        state = tracker.load_or_create_state("project-001")

        result = tracker.handle_async_failure(
            task_id="task-001",
            error="Connection timeout",
            fallback_action="Retry with exponential backoff",
        )

        assert result["recovery_initiated"] is True
        assert result["task_id"] == "task-001"

    def test_handle_interrupted_research_with_checkpoint(self, tracker):
        """Test recovery from interrupted research."""
        # Create initial state and checkpoint
        state = tracker.load_or_create_state("project-001")
        checkpoint = tracker.create_checkpoint("market_research")

        # Add some data to state
        tracker.update_coverage("market_research", 50.0)
        tracker.save_state()

        # Create new tracker and attempt recovery
        tracker2 = ResearchStateTracker(tracker.project_root)
        recovered, recovered_checkpoint = tracker2.handle_interrupted_research("project-001")

        assert recovered is True
        assert recovered_checkpoint is not None

    def test_get_session_summary(self, tracker):
        """Test getting session summary."""
        state = tracker.load_or_create_state("project-001")

        tracker.record_completed_query(
            query="test query",
            agent="test-agent",
            sources_found=3,
            quality_score=0.8,
            findings={},
        )
        tracker.record_discovered_source(
            url="https://example.com",
            source_type="blog",
            content_hash="hash123",
            relevance_score=0.9,
            agent="test-agent",
        )

        summary = tracker.get_session_summary()

        assert "state_tracker_output" in summary
        assert summary["state_tracker_output"]["total_queries_completed"] == 1
        assert summary["state_tracker_output"]["total_sources_discovered"] == 1

    def test_mark_gap_addressed(self, tracker):
        """Test marking gap as addressed."""
        state = tracker.load_or_create_state("project-001")

        gap = ResearchGap(
            gap_id="gap-001",
            gap_type=GapType.COVERAGE,
            category="test",
            description="test gap",
            priority=GapPriority.HIGH,
        )
        tracker.add_gap(gap)

        tracker.mark_gap_addressed("gap-001")

        assert tracker._state.identified_gaps[0].status == "addressed"
        assert tracker._state.identified_gaps[0].addressed_at is not None

    def test_add_researched_entity(self, tracker):
        """Test adding researched entity."""
        state = tracker.load_or_create_state("project-001")

        tracker.add_researched_entity("competitor", "Company A")
        tracker.add_researched_entity("competitor", "Company B")

        assert "competitor" in tracker._state.entities_researched
        assert len(tracker._state.entities_researched["competitor"]) == 2

    def test_entity_deduplication(self, tracker):
        """Test that entities are deduplicated."""
        state = tracker.load_or_create_state("project-001")

        tracker.add_researched_entity("competitor", "Company A")
        tracker.add_researched_entity("competitor", "Company A")

        # Should only have one instance
        assert len(tracker._state.entities_researched["competitor"]) == 1


class TestResearchStateTrackerIntegration:
    """Integration tests for research state tracker."""

    def test_complete_research_workflow(self, tmp_path):
        """Test complete research workflow with tracker."""
        tracker = ResearchStateTracker(tmp_path / "project")

        # Initialize state
        state = tracker.load_or_create_state("project-001")
        assert state is not None

        # Record research activity
        tracker.update_coverage("market_research", 60.0)
        tracker.record_completed_query(
            query="market size",
            agent="market-research-agent",
            sources_found=5,
            quality_score=0.85,
            findings={"market_size": "$10B"},
        )
        tracker.record_discovered_source(
            url="https://market-report.com",
            source_type="report",
            content_hash="hash1",
            relevance_score=0.95,
            agent="market-research-agent",
        )

        # Detect gaps
        gaps = tracker.detect_gaps()
        assert len(gaps) > 0  # Should have some gaps still

        # Create checkpoint
        checkpoint = tracker.create_checkpoint("phase1")
        assert checkpoint is not None

        # Save state
        tracker.save_state()

        # Verify persistence
        tracker2 = ResearchStateTracker(tmp_path / "project")
        loaded_state = tracker2.load_or_create_state("project-001")

        assert loaded_state.project_id == "project-001"
        assert loaded_state.coverage.by_category["market_research"] == 60.0

    def test_state_history_management(self, tmp_path):
        """Test that state history is properly managed."""
        tracker = ResearchStateTracker(tmp_path / "project")
        state = tracker.load_or_create_state("project-001")

        # Create multiple versions
        for i in range(6):
            tracker.update_coverage("market_research", float(i * 10))
            tracker.save_state()

        # Check history directory
        history_files = list(tracker.history_dir.glob("state_v*.json"))

        # Should keep only last 5 versions
        assert len(history_files) <= 5


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_tracker_with_missing_state_file(self, tmp_path):
        """Test tracker behavior with corrupted state file."""
        tracker = ResearchStateTracker(tmp_path / "project")

        # Create a corrupted state file
        tracker._ensure_directories()
        with open(tracker.state_file, "w") as f:
            f.write("invalid json {")

        # Should recover and create new state
        state = tracker.load_or_create_state("project-001")

        assert state is not None
        assert state.project_id == "project-001"

    def test_query_deduplication_after_expiry(self, tmp_path):
        """Test that old similar queries are NOT skipped if > 7 days old."""
        tracker = ResearchStateTracker(tmp_path / "project")
        state = tracker.load_or_create_state("project-001")

        # Record SIMILAR query from 30 days ago (beyond 7-day recency window)
        old_timestamp = datetime.now() - timedelta(days=30)
        old_query = CompletedQuery(
            query="old market research analysis",
            agent="market-research-agent",
            timestamp=old_timestamp,
            sources_found=3,
            quality_score=0.8,
            key_findings_hash="hash1",
        )
        tracker._state.completed_queries.append(old_query)

        # Similar query that's 30 days old should NOT be skipped (> 7 days)
        similar_query = "market research analysis study"
        assert tracker.should_skip_query(similar_query) is False

    def test_concurrent_checkpoint_writes(self, tmp_path):
        """Test creating checkpoints sequentially."""
        tracker = ResearchStateTracker(tmp_path / "project")
        state = tracker.load_or_create_state("project-001")

        # Create multiple checkpoints
        cp1 = tracker.create_checkpoint("phase1")
        cp2 = tracker.create_checkpoint("phase2")
        cp3 = tracker.create_checkpoint("phase3")

        # All should have different IDs
        assert cp1.checkpoint_id != cp2.checkpoint_id
        assert cp2.checkpoint_id != cp3.checkpoint_id

        # All should exist
        assert (tracker.checkpoint_dir / f"{cp1.checkpoint_id}.json").exists()
        assert (tracker.checkpoint_dir / f"{cp2.checkpoint_id}.json").exists()
        assert (tracker.checkpoint_dir / f"{cp3.checkpoint_id}.json").exists()
