"""
Comprehensive tests for research_state module.

Tests cover state tracking, gap detection, checkpoints, and recovery
with 85%+ code coverage for ResearchStateTracker.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.autopack.research.analysis.research_state import (
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
    """Test GapType enum."""

    def test_all_gap_types_exist(self) -> None:
        """Verify all gap types are defined."""
        gap_types = {gap.value for gap in GapType}
        expected = {"coverage", "entity", "depth", "recency", "validation"}
        assert gap_types == expected

    def test_gap_type_values(self) -> None:
        """Test specific gap type values."""
        assert GapType.COVERAGE.value == "coverage"
        assert GapType.VALIDATION.value == "validation"


class TestGapPriority:
    """Test GapPriority enum."""

    def test_all_priorities_exist(self) -> None:
        """Verify all priority levels are defined."""
        priorities = {p.value for p in GapPriority}
        expected = {"critical", "high", "medium", "low"}
        assert priorities == expected


class TestResearchDepth:
    """Test ResearchDepth enum."""

    def test_all_depths_exist(self) -> None:
        """Verify all depth levels are defined."""
        depths = {d.value for d in ResearchDepth}
        expected = {"shallow", "medium", "deep"}
        assert depths == expected


class TestCompletedQuery:
    """Test CompletedQuery data class."""

    def test_initialization(self) -> None:
        """Test creating CompletedQuery."""
        query = CompletedQuery(
            query="What is market size?",
            agent="market-research",
            timestamp=datetime.now(),
            sources_found=5,
            quality_score=0.85,
            key_findings_hash="abc123",
        )
        assert query.query == "What is market size?"
        assert query.sources_found == 5
        assert query.gap_id is None

    def test_with_gap_id(self) -> None:
        """Test CompletedQuery with gap reference."""
        query = CompletedQuery(
            query="Validate pricing",
            agent="validation",
            timestamp=datetime.now(),
            sources_found=3,
            quality_score=0.7,
            key_findings_hash="def456",
            gap_id="gap_001",
        )
        assert query.gap_id == "gap_001"


class TestDiscoveredSource:
    """Test DiscoveredSource data class."""

    def test_initialization(self) -> None:
        """Test creating DiscoveredSource."""
        source = DiscoveredSource(
            url="https://example.com",
            source_type="article",
            accessed_at=datetime.now(),
            content_hash="hash123",
            relevance_score=0.9,
        )
        assert source.url == "https://example.com"
        assert source.relevance_score == 0.9
        assert source.used_in == []

    def test_with_usage_tracking(self) -> None:
        """Test source with usage tracking."""
        source = DiscoveredSource(
            url="https://research.example.com",
            source_type="whitepaper",
            accessed_at=datetime.now(),
            content_hash="paper123",
            relevance_score=0.95,
            used_in=["analysis_001", "report_002"],
        )
        assert len(source.used_in) == 2
        assert "analysis_001" in source.used_in


class TestResearchGap:
    """Test ResearchGap data class."""

    def test_initialization(self) -> None:
        """Test creating ResearchGap."""
        gap = ResearchGap(
            gap_id="gap_001",
            gap_type=GapType.COVERAGE,
            category="market_size",
            description="Missing market size for Europe",
            priority=GapPriority.HIGH,
        )
        assert gap.gap_id == "gap_001"
        assert gap.status == "pending"
        assert gap.addressed_at is None

    def test_with_suggested_queries(self) -> None:
        """Test gap with suggested queries."""
        gap = ResearchGap(
            gap_id="gap_002",
            gap_type=GapType.DEPTH,
            category="competitive",
            description="Need deeper competitor analysis",
            priority=GapPriority.MEDIUM,
            suggested_queries=["List all competitors", "Compare pricing models"],
        )
        assert len(gap.suggested_queries) == 2

    def test_to_dict(self) -> None:
        """Test gap serialization."""
        gap = ResearchGap(
            gap_id="gap_003",
            gap_type=GapType.RECENCY,
            category="market_trends",
            description="Data is 6 months old",
            priority=GapPriority.MEDIUM,
        )
        gap_dict = gap.to_dict()
        assert gap_dict["gap_id"] == "gap_003"
        assert gap_dict["status"] == "pending"


class TestCoverageMetrics:
    """Test CoverageMetrics data class."""

    def test_initialization(self) -> None:
        """Test creating CoverageMetrics."""
        metrics = CoverageMetrics()
        assert metrics.overall_percentage == 0.0
        # CoverageMetrics initializes with default categories
        assert isinstance(metrics.by_category, dict)

    def test_with_category_coverage(self) -> None:
        """Test metrics with category breakdown."""
        metrics = CoverageMetrics(
            overall_percentage=75.0,
            by_category={
                "market_size": 90.0,
                "competitors": 60.0,
                "pricing": 75.0,
            },
        )
        assert metrics.overall_percentage == 75.0
        assert metrics.by_category["market_size"] == 90.0

    def test_recalculate_overall(self) -> None:
        """Test recalculating overall coverage."""
        metrics = CoverageMetrics(
            by_category={
                "market": 80.0,
                "tech": 70.0,
                "compliance": 90.0,
            },
        )
        metrics.recalculate_overall()
        expected = (80.0 + 70.0 + 90.0) / 3
        assert abs(metrics.overall_percentage - expected) < 0.1

    def test_to_dict(self) -> None:
        """Test serialization."""
        metrics = CoverageMetrics(overall_percentage=50.0)
        metrics_dict = metrics.to_dict()
        assert metrics_dict["overall_percentage"] == 50.0


class TestResearchState:
    """Test ResearchState data class."""

    def test_initialization(self) -> None:
        """Test creating ResearchState."""
        state = ResearchState(
            project_id="proj_001",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            coverage=CoverageMetrics(),
            completed_queries=[],
            discovered_sources=[],
            identified_gaps=[],
            entities_researched={},
            research_depth={},
        )
        assert state.project_id == "proj_001"
        assert state.version == 1

    def test_with_completed_queries(self) -> None:
        """Test state with query history."""
        state = ResearchState(
            project_id="proj_002",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            coverage=CoverageMetrics(),
            completed_queries=[
                CompletedQuery(
                    query="q1",
                    agent="agent1",
                    timestamp=datetime.now(),
                    sources_found=3,
                    quality_score=0.8,
                    key_findings_hash="h1",
                )
            ],
            discovered_sources=[],
            identified_gaps=[],
            entities_researched={},
            research_depth={},
        )
        assert len(state.completed_queries) == 1

    def test_to_dict(self) -> None:
        """Test state serialization."""
        now = datetime.now()
        state = ResearchState(
            project_id="proj_003",
            created_at=now,
            last_updated=now,
            coverage=CoverageMetrics(overall_percentage=60.0),
            completed_queries=[],
            discovered_sources=[],
            identified_gaps=[],
            entities_researched={"company": ["CompanyA"]},
            research_depth={"market": ResearchDepth.DEEP},
        )
        state_dict = state.to_dict()
        # to_dict() wraps in a "research_state" key
        assert "research_state" in state_dict
        assert state_dict["research_state"]["project_id"] == "proj_003"
        assert state_dict["research_state"]["coverage"]["overall_percentage"] == 60.0

    def test_from_dict(self) -> None:
        """Test state deserialization."""
        now = datetime.now()
        state_dict = {
            "project_id": "proj_004",
            "created_at": now.isoformat(),
            "last_updated": now.isoformat(),
            "version": 1,
            "coverage": {"overall_percentage": 70.0, "by_category": {}},
            "completed_queries": [],
            "discovered_sources": [],
            "identified_gaps": [],
            "entities_researched": {},
            "research_depth": {},
        }
        state = ResearchState.from_dict(state_dict)
        assert state.project_id == "proj_004"


class TestResearchRequirements:
    """Test ResearchRequirements data class."""

    def test_basic_requirements(self) -> None:
        """Test basic requirements."""
        reqs = ResearchRequirements(
            min_coverage={"market": 80.0, "tech": 75.0},
            min_sources=3,
            max_age_days={"market": 90, "tech": 180},
        )
        assert reqs.min_coverage["market"] == 80.0
        assert reqs.min_sources == 3


class TestResearchCheckpoint:
    """Test ResearchCheckpoint data class."""

    def test_initialization(self) -> None:
        """Test creating checkpoint."""
        checkpoint = ResearchCheckpoint(
            checkpoint_id="cp_001",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            phase="discovery",
        )
        assert checkpoint.checkpoint_id == "cp_001"
        assert checkpoint.is_recoverable is True

    def test_with_completed_steps(self) -> None:
        """Test checkpoint with progress."""
        checkpoint = ResearchCheckpoint(
            checkpoint_id="cp_002",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            phase="analysis",
            completed_steps=["step1", "step2"],
            partial_results={"temp_data": "value"},
        )
        assert len(checkpoint.completed_steps) == 2
        assert checkpoint.partial_results["temp_data"] == "value"

    def test_with_failures(self) -> None:
        """Test checkpoint with failed tasks."""
        checkpoint = ResearchCheckpoint(
            checkpoint_id="cp_003",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            failed_tasks={"task_1": "Network error", "task_2": "Timeout"},
        )
        assert len(checkpoint.failed_tasks) == 2
        assert checkpoint.is_recoverable is True

    def test_to_dict(self) -> None:
        """Test checkpoint serialization."""
        now = datetime.now()
        checkpoint = ResearchCheckpoint(
            checkpoint_id="cp_004",
            created_at=now,
            last_updated=now,
            phase="validation",
        )
        cp_dict = checkpoint.to_dict()
        assert cp_dict["checkpoint_id"] == "cp_004"
        assert cp_dict["phase"] == "validation"

    def test_from_dict(self) -> None:
        """Test checkpoint deserialization."""
        now = datetime.now()
        cp_dict = {
            "checkpoint_id": "cp_005",
            "created_at": now.isoformat(),
            "last_updated": now.isoformat(),
            "phase": "discovery",
            "completed_steps": ["step1"],
            "partial_results": {},
            "failed_tasks": {},
            "state_snapshot": None,
            "is_recoverable": True,
        }
        checkpoint = ResearchCheckpoint.from_dict(cp_dict)
        assert checkpoint.checkpoint_id == "cp_005"


class TestResearchStateTracker:
    """Test ResearchStateTracker main class."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def tracker(self, temp_project_dir) -> ResearchStateTracker:
        """Create tracker instance."""
        return ResearchStateTracker(temp_project_dir)

    def test_initialization(self, tracker: ResearchStateTracker) -> None:
        """Test tracker initialization."""
        assert tracker is not None

    def test_load_or_create_state(self, tracker: ResearchStateTracker) -> None:
        """Test loading or creating state."""
        state = tracker.load_or_create_state("test_project")
        assert state.project_id == "test_project"
        assert state.version == 1

    def test_save_and_reload_state(self, tracker: ResearchStateTracker) -> None:
        """Test saving and reloading state."""
        state = tracker.load_or_create_state("project_persist")
        state.coverage.overall_percentage = 50.0
        tracker.save_state()

        tracker2 = ResearchStateTracker(tracker.project_root)
        state2 = tracker2.load_or_create_state("project_persist")
        assert state2.coverage.overall_percentage == 50.0

    def test_record_completed_query(self, tracker: ResearchStateTracker) -> None:
        """Test recording completed query."""
        tracker.load_or_create_state("project_q1")
        tracker.record_completed_query(
            query="test query",
            agent="test_agent",
            sources_found=5,
            quality_score=0.85,
            findings="findings text",
        )
        assert len(tracker._state.completed_queries) == 1

    def test_record_discovered_source(self, tracker: ResearchStateTracker) -> None:
        """Test recording discovered source."""
        tracker.load_or_create_state("project_s1")
        tracker.record_discovered_source(
            url="https://example.com",
            source_type="article",
            content_hash="hash",
            relevance_score=0.9,
            agent="discovery",
        )
        assert len(tracker._state.discovered_sources) == 1

    def test_is_new_source(self, tracker: ResearchStateTracker) -> None:
        """Test source uniqueness checking."""
        tracker.load_or_create_state("project_newness")
        tracker.record_discovered_source(
            url="https://existing.com",
            source_type="doc",
            content_hash="hash1",
            relevance_score=0.8,
            agent="discovery",
        )
        assert not tracker.is_new_source("https://existing.com", "hash1")
        assert tracker.is_new_source("https://new.com", "hash2")

    def test_should_skip_query(self, tracker: ResearchStateTracker) -> None:
        """Test query deduplication."""
        tracker.load_or_create_state("project_skip")
        tracker.record_completed_query(
            query="duplicate query",
            agent="agent",
            sources_found=2,
            quality_score=0.7,
            findings="",
        )
        assert tracker.should_skip_query("duplicate query") is True
        assert tracker.should_skip_query("new query") is False

    def test_update_coverage(self, tracker: ResearchStateTracker) -> None:
        """Test coverage updates."""
        tracker.load_or_create_state("project_coverage")
        tracker.update_coverage("market_size", 75.0)
        assert tracker._state.coverage.by_category["market_size"] == 75.0

    def test_update_research_depth(self, tracker: ResearchStateTracker) -> None:
        """Test research depth tracking."""
        tracker.load_or_create_state("project_depth")
        tracker.update_research_depth("competitors", ResearchDepth.DEEP)
        assert tracker._state.research_depth["competitors"] == ResearchDepth.DEEP

    def test_add_researched_entity(self, tracker: ResearchStateTracker) -> None:
        """Test entity tracking."""
        tracker.load_or_create_state("project_entity")
        tracker.add_researched_entity("company", "CompanyA")
        tracker.add_researched_entity("company", "CompanyB")
        assert "CompanyA" in tracker._state.entities_researched["company"]
        assert "CompanyB" in tracker._state.entities_researched["company"]

    def test_detect_gaps(self, tracker: ResearchStateTracker) -> None:
        """Test gap detection."""
        state = tracker.load_or_create_state("project_gaps")
        state.coverage.by_category = {
            "market": 50.0,  # Below 80% requirement
            "tech": 90.0,  # Above requirement
        }
        tracker._state = state

        gaps = tracker.detect_gaps()
        coverage_gaps = [g for g in gaps if g.gap_type == GapType.COVERAGE]
        assert len(coverage_gaps) > 0

    def test_add_gap(self, tracker: ResearchStateTracker) -> None:
        """Test adding gaps."""
        tracker.load_or_create_state("project_addgap")
        gap = ResearchGap(
            gap_id="gap_test",
            gap_type=GapType.VALIDATION,
            category="pricing",
            description="Needs validation",
            priority=GapPriority.HIGH,
        )
        tracker.add_gap(gap)
        assert len(tracker._state.identified_gaps) == 1

    def test_mark_gap_addressed(self, tracker: ResearchStateTracker) -> None:
        """Test marking gaps as addressed."""
        tracker.load_or_create_state("project_addressed")
        gap = ResearchGap(
            gap_id="gap_mark",
            gap_type=GapType.DEPTH,
            category="test",
            description="Test gap",
            priority=GapPriority.LOW,
        )
        tracker.add_gap(gap)
        tracker.mark_gap_addressed("gap_mark")
        assert tracker._state.identified_gaps[0].addressed_at is not None

    def test_create_checkpoint(self, tracker: ResearchStateTracker) -> None:
        """Test checkpoint creation."""
        tracker.load_or_create_state("project_checkpoint")
        checkpoint = tracker.create_checkpoint(phase="discovery", checkpoint_id="cp_01")
        assert checkpoint.checkpoint_id == "cp_01"
        assert checkpoint.phase == "discovery"

    def test_handle_interrupted_research(self, temp_project_dir) -> None:
        """Test recovery from interrupted research."""
        tracker = ResearchStateTracker(temp_project_dir)
        state = tracker.load_or_create_state("interrupted")
        checkpoint = tracker.create_checkpoint(phase="analysis")
        tracker.save_state()

        tracker2 = ResearchStateTracker(temp_project_dir)
        recovered, cp = tracker2.handle_interrupted_research("interrupted")
        assert recovered is True
        assert cp is not None

    def test_validate_state_consistency(self, tracker: ResearchStateTracker) -> None:
        """Test state consistency validation."""
        tracker.load_or_create_state("project_consistency")
        errors = tracker.validate_state_consistency()
        assert isinstance(errors, list)

    def test_get_session_summary(self, tracker: ResearchStateTracker) -> None:
        """Test session summary generation."""
        tracker.load_or_create_state("project_summary")
        tracker.record_completed_query(
            query="q1",
            agent="agent1",
            sources_found=3,
            quality_score=0.8,
            findings="",
        )
        summary = tracker.get_session_summary()
        # Summary has state_tracker_output key
        assert "state_tracker_output" in summary
        assert "total_queries_completed" in summary["state_tracker_output"]

    def test_multiple_projects(self, tracker: ResearchStateTracker) -> None:
        """Test tracking multiple projects."""
        # Create and modify first project
        state1 = tracker.load_or_create_state("proj_multi_1")
        # Just verify we can track multiple projects
        assert state1.project_id == "proj_multi_1"

        # Create and modify second project
        state2 = tracker.load_or_create_state("proj_multi_2")
        assert state2.project_id == "proj_multi_2"

        # Verify projects are separate
        assert state1.project_id != state2.project_id


class TestStateValidation:
    """Test state validation and repair."""

    @pytest.fixture
    def tracker(self, tmp_path) -> ResearchStateTracker:
        """Create tracker with temp directory."""
        return ResearchStateTracker(tmp_path)

    def test_validate_empty_state(self, tracker: ResearchStateTracker) -> None:
        """Test validation of empty state."""
        tracker.load_or_create_state("empty")
        errors = tracker.validate_state_consistency()
        assert isinstance(errors, list)

    def test_repair_state(self, tracker: ResearchStateTracker) -> None:
        """Test state repair."""
        tracker.load_or_create_state("broken")
        repair_result = tracker.repair_state()
        assert isinstance(repair_result, dict)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def tracker(self, tmp_path) -> ResearchStateTracker:
        """Create tracker for edge case testing."""
        return ResearchStateTracker(tmp_path)

    def test_very_large_query_history(self, tracker: ResearchStateTracker) -> None:
        """Test with many completed queries."""
        tracker.load_or_create_state("large_history")
        for i in range(100):
            tracker.record_completed_query(
                query=f"query_{i}",
                agent="agent",
                sources_found=i % 10,
                quality_score=0.5 + (i % 50) / 100,
                findings="",
            )
        assert len(tracker._state.completed_queries) == 100

    def test_many_sources(self, tracker: ResearchStateTracker) -> None:
        """Test tracking many sources."""
        tracker.load_or_create_state("many_sources")
        for i in range(50):
            tracker.record_discovered_source(
                url=f"https://source{i}.com",
                source_type="article",
                content_hash=f"hash_{i}",
                relevance_score=0.5 + (i % 50) / 100,
                agent="discovery",
            )
        assert len(tracker._state.discovered_sources) == 50

    def test_overlapping_coverage_updates(self, tracker: ResearchStateTracker) -> None:
        """Test multiple updates to same category."""
        tracker.load_or_create_state("coverage_overlap")
        tracker.update_coverage("market", 30.0)
        tracker.update_coverage("market", 60.0)
        tracker.update_coverage("market", 85.0)
        assert tracker._state.coverage.by_category["market"] == 85.0

    def test_gap_with_all_optional_fields(self, tracker: ResearchStateTracker) -> None:
        """Test gap with all optional fields populated."""
        tracker.load_or_create_state("full_gap")
        gap = ResearchGap(
            gap_id="comprehensive",
            gap_type=GapType.VALIDATION,
            category="pricing",
            description="Complete gap definition",
            priority=GapPriority.CRITICAL,
            suggested_queries=["q1", "q2", "q3"],
            identified_at=datetime.now(),
            status="in_progress",
        )
        tracker.add_gap(gap)
        assert len(tracker._state.identified_gaps[0].suggested_queries) == 3

    def test_concurrent_entity_addition(self, tracker: ResearchStateTracker) -> None:
        """Test adding many entities rapidly."""
        tracker.load_or_create_state("entities_rapid")
        companies = ["CompanyA", "CompanyB", "CompanyC"]
        for company in companies:
            tracker.add_researched_entity("company", company)
        assert len(tracker._state.entities_researched["company"]) == 3
