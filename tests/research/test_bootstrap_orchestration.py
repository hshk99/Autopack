"""Unit tests for Bootstrap Orchestration functionality.

Tests the BootstrapSession model, ResearchCache, and the
start_bootstrap_session() method of ResearchOrchestrator.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from autopack.research.idea_parser import ParsedIdea, ProjectType, RiskProfile
from autopack.research.models.bootstrap_session import (
    BootstrapPhase,
    BootstrapSession,
    ResearchPhaseResult,
    generate_idea_hash,
)
from autopack.research.orchestrator import ResearchCache, ResearchOrchestrator


class TestBootstrapSessionModel:
    """Test suite for BootstrapSession model."""

    def test_create_bootstrap_session(self):
        """Test creating a basic BootstrapSession."""
        session = BootstrapSession(
            session_id="test-session-123",
            idea_hash="abc123",
            parsed_idea_title="Test Project",
            parsed_idea_type="ecommerce",
        )

        assert session.session_id == "test-session-123"
        assert session.idea_hash == "abc123"
        assert session.parsed_idea_title == "Test Project"
        assert session.parsed_idea_type == "ecommerce"
        assert session.current_phase == BootstrapPhase.INITIALIZED

    def test_session_phase_transitions(self):
        """Test session phase tracking."""
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="abc123",
        )

        assert session.current_phase == BootstrapPhase.INITIALIZED

        # Simulate phase progression
        session.mark_phase_started(BootstrapPhase.MARKET_RESEARCH)
        assert session.market_research.status == "running"
        assert session.market_research.started_at is not None

        session.mark_phase_completed(BootstrapPhase.MARKET_RESEARCH, {"score": 5})
        assert session.market_research.status == "completed"
        assert session.market_research.data == {"score": 5}

    def test_session_completion_check(self):
        """Test session completion detection."""
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="abc123",
        )

        # Initially not complete
        assert session.is_complete() is False

        # Complete all phases
        session.mark_phase_started(BootstrapPhase.MARKET_RESEARCH)
        session.mark_phase_completed(BootstrapPhase.MARKET_RESEARCH, {"score": 5})

        session.mark_phase_started(BootstrapPhase.COMPETITIVE_ANALYSIS)
        session.mark_phase_completed(BootstrapPhase.COMPETITIVE_ANALYSIS, {"score": 3})

        session.mark_phase_started(BootstrapPhase.TECHNICAL_FEASIBILITY)
        session.mark_phase_completed(BootstrapPhase.TECHNICAL_FEASIBILITY, {"score": 4})

        assert session.is_complete() is True
        assert session.current_phase == BootstrapPhase.SYNTHESIS

    def test_session_failure_tracking(self):
        """Test session failure tracking."""
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="abc123",
        )

        session.mark_phase_started(BootstrapPhase.MARKET_RESEARCH)
        session.mark_phase_failed(BootstrapPhase.MARKET_RESEARCH, ["API error", "Timeout"])

        assert session.market_research.status == "failed"
        assert len(session.market_research.errors) == 2
        assert "API error" in session.market_research.errors

        failed_phases = session.get_failed_phases()
        assert len(failed_phases) == 1
        assert failed_phases[0][0] == BootstrapPhase.MARKET_RESEARCH

    def test_session_cache_validity(self):
        """Test session cache validity checking."""
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="abc123",
        )

        # No expiry set
        assert session.is_cached_valid() is False

        # Set expiry in future
        session.expires_at = datetime.now() + timedelta(hours=1)
        assert session.is_cached_valid() is True

        # Set expiry in past
        session.expires_at = datetime.now() - timedelta(hours=1)
        assert session.is_cached_valid() is False

    def test_get_completed_phases(self):
        """Test getting list of completed phases."""
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="abc123",
        )

        assert session.get_completed_phases() == []

        session.mark_phase_started(BootstrapPhase.MARKET_RESEARCH)
        session.mark_phase_completed(BootstrapPhase.MARKET_RESEARCH, {})
        session.mark_phase_started(BootstrapPhase.COMPETITIVE_ANALYSIS)
        session.mark_phase_completed(BootstrapPhase.COMPETITIVE_ANALYSIS, {})

        completed = session.get_completed_phases()
        assert len(completed) == 2
        assert BootstrapPhase.MARKET_RESEARCH in completed
        assert BootstrapPhase.COMPETITIVE_ANALYSIS in completed


class TestResearchPhaseResult:
    """Test suite for ResearchPhaseResult model."""

    def test_create_phase_result(self):
        """Test creating a ResearchPhaseResult."""
        result = ResearchPhaseResult(phase=BootstrapPhase.MARKET_RESEARCH)

        assert result.phase == BootstrapPhase.MARKET_RESEARCH
        assert result.status == "pending"
        assert result.started_at is None
        assert result.completed_at is None
        assert result.data == {}
        assert result.errors == []

    def test_phase_result_with_data(self):
        """Test ResearchPhaseResult with data."""
        result = ResearchPhaseResult(
            phase=BootstrapPhase.MARKET_RESEARCH,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            data={"market_size": "large", "growth_rate": 0.15},
            duration_seconds=5.5,
        )

        assert result.status == "completed"
        assert result.data["market_size"] == "large"
        assert result.duration_seconds == 5.5


class TestIdeaHashGeneration:
    """Test suite for idea hash generation."""

    def test_generate_idea_hash(self):
        """Test generating hash for parsed idea."""
        hash1 = generate_idea_hash("Test Project", "A test description", "ecommerce")
        hash2 = generate_idea_hash("Test Project", "A test description", "ecommerce")
        hash3 = generate_idea_hash("Different Project", "A test description", "ecommerce")

        # Same inputs should produce same hash
        assert hash1 == hash2
        # Different inputs should produce different hash
        assert hash1 != hash3

    def test_hash_normalization(self):
        """Test that hash normalizes case and whitespace."""
        hash1 = generate_idea_hash("Test Project", "A description", "ecommerce")
        hash2 = generate_idea_hash("TEST PROJECT", "A DESCRIPTION", "ecommerce")
        hash3 = generate_idea_hash("  Test Project  ", "  A description  ", "ecommerce")

        # Case and whitespace should be normalized
        assert hash1 == hash2
        assert hash1 == hash3


class TestResearchCache:
    """Test suite for ResearchCache."""

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = ResearchCache(ttl_hours=12)
        assert cache.ttl_hours == 12

    def test_cache_get_miss(self):
        """Test cache miss."""
        cache = ResearchCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_set_and_get(self):
        """Test setting and getting from cache."""
        cache = ResearchCache(ttl_hours=24)
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
        )

        cache.set("test-hash", session)
        cached = cache.get("test-hash")

        assert cached is not None
        assert cached.session_id == "test-session"
        assert cached.expires_at is not None

    def test_cache_expiry(self):
        """Test that expired entries are not returned."""
        cache = ResearchCache(ttl_hours=24)
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
        )

        cache.set("test-hash", session)

        # Manually expire the session
        session.expires_at = datetime.now() - timedelta(hours=1)

        cached = cache.get("test-hash")
        assert cached is None

    def test_cache_invalidate(self):
        """Test cache invalidation."""
        cache = ResearchCache()
        session = BootstrapSession(
            session_id="test-session",
            idea_hash="test-hash",
        )

        cache.set("test-hash", session)
        assert cache.get("test-hash") is not None

        result = cache.invalidate("test-hash")
        assert result is True
        assert cache.get("test-hash") is None

        # Invalidating non-existent entry
        result = cache.invalidate("nonexistent")
        assert result is False

    def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = ResearchCache()

        for i in range(5):
            session = BootstrapSession(
                session_id=f"session-{i}",
                idea_hash=f"hash-{i}",
            )
            cache.set(f"hash-{i}", session)

        cache.clear()

        for i in range(5):
            assert cache.get(f"hash-{i}") is None

    def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = ResearchCache(ttl_hours=24)

        # Add some sessions
        for i in range(3):
            session = BootstrapSession(
                session_id=f"session-{i}",
                idea_hash=f"hash-{i}",
            )
            cache.set(f"hash-{i}", session)

        # Manually expire some
        cache._cache["hash-0"].expires_at = datetime.now() - timedelta(hours=1)
        cache._cache["hash-1"].expires_at = datetime.now() - timedelta(hours=1)

        removed = cache.cleanup_expired()
        assert removed == 2
        assert cache.get("hash-0") is None
        assert cache.get("hash-1") is None
        assert cache.get("hash-2") is not None


class TestResearchOrchestratorBootstrap:
    """Test suite for ResearchOrchestrator bootstrap functionality."""

    def test_orchestrator_initialization_with_cache(self):
        """Test orchestrator initialization includes cache."""
        orchestrator = ResearchOrchestrator(cache_ttl_hours=12)
        assert orchestrator._cache is not None
        assert orchestrator._cache.ttl_hours == 12

    @pytest.mark.asyncio
    async def test_start_bootstrap_session_basic(self):
        """Test starting a basic bootstrap session."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Test E-commerce Store",
            description="An online store for selling products",
            detected_project_type=ProjectType.ECOMMERCE,
            risk_profile=RiskProfile.MEDIUM,
            raw_requirements=["User login", "Product catalog", "Shopping cart"],
            confidence_score=0.8,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session is not None
        assert session.parsed_idea_title == "Test E-commerce Store"
        assert session.parsed_idea_type == "ecommerce"
        assert session.is_complete()

    @pytest.mark.asyncio
    async def test_start_bootstrap_session_with_cache(self):
        """Test that bootstrap sessions are cached."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Test Project for Caching",
            description="A project to test caching",
            detected_project_type=ProjectType.CONTENT,
            confidence_score=0.75,
        )

        # First call should create new session
        session1 = await orchestrator.start_bootstrap_session(parsed_idea)

        # Second call should return cached session
        session2 = await orchestrator.start_bootstrap_session(parsed_idea)

        # Should be the same session (from cache)
        assert session1.session_id == session2.session_id
        assert session1.idea_hash == session2.idea_hash

    @pytest.mark.asyncio
    async def test_start_bootstrap_session_bypass_cache(self):
        """Test bypassing cache for bootstrap sessions."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Test No Cache",
            description="A project without cache",
            detected_project_type=ProjectType.AUTOMATION,
            confidence_score=0.8,
        )

        session1 = await orchestrator.start_bootstrap_session(parsed_idea, use_cache=True)
        session2 = await orchestrator.start_bootstrap_session(parsed_idea, use_cache=False)

        # Should be different sessions
        assert session1.session_id != session2.session_id

    @pytest.mark.asyncio
    async def test_start_bootstrap_session_parallel_execution(self):
        """Test that parallel execution is used by default."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Parallel Test",
            description="Testing parallel execution",
            detected_project_type=ProjectType.TRADING,
            risk_profile=RiskProfile.HIGH,
            confidence_score=0.85,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea, parallel=True)

        assert session.parallel_execution_used is True
        assert session.is_complete()

    @pytest.mark.asyncio
    async def test_start_bootstrap_session_sequential_execution(self):
        """Test sequential execution option."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Sequential Test",
            description="Testing sequential execution",
            detected_project_type=ProjectType.CONTENT,
            confidence_score=0.75,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea, parallel=False)

        assert session.parallel_execution_used is False
        assert session.is_complete()

    @pytest.mark.asyncio
    async def test_bootstrap_session_synthesis(self):
        """Test that completed sessions have synthesis data."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Synthesis Test",
            description="Testing synthesis of research results",
            detected_project_type=ProjectType.ECOMMERCE,
            raw_requirements=["Req 1", "Req 2", "Req 3", "Req 4"],
            dependencies=["Stripe", "Auth0"],
            confidence_score=0.9,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session.synthesis is not None
        assert "overall_recommendation" in session.synthesis
        assert "scores" in session.synthesis
        assert session.synthesis["project_type"] == "ecommerce"

    @pytest.mark.asyncio
    async def test_bootstrap_session_all_project_types(self):
        """Test bootstrap sessions for all project types."""
        orchestrator = ResearchOrchestrator()

        project_configs = [
            (ProjectType.ECOMMERCE, RiskProfile.MEDIUM),
            (ProjectType.TRADING, RiskProfile.HIGH),
            (ProjectType.CONTENT, RiskProfile.LOW),
            (ProjectType.AUTOMATION, RiskProfile.MEDIUM),
            (ProjectType.OTHER, RiskProfile.MEDIUM),
        ]

        for project_type, expected_risk in project_configs:
            parsed_idea = ParsedIdea(
                title=f"Test {project_type.value}",
                description=f"A {project_type.value} project",
                detected_project_type=project_type,
                risk_profile=expected_risk,
                confidence_score=0.8,
            )

            session = await orchestrator.start_bootstrap_session(parsed_idea, use_cache=False)

            assert session.is_complete(), f"Failed for {project_type.value}"
            assert session.parsed_idea_type == project_type.value

    def test_get_bootstrap_session(self):
        """Test retrieving bootstrap session by ID."""
        orchestrator = ResearchOrchestrator()

        # Run bootstrap session
        parsed_idea = ParsedIdea(
            title="Retrieval Test",
            description="Testing session retrieval",
            detected_project_type=ProjectType.CONTENT,
            confidence_score=0.8,
        )

        session = asyncio.run(orchestrator.start_bootstrap_session(parsed_idea))

        # Retrieve by ID
        retrieved = orchestrator.get_bootstrap_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

        # Non-existent ID
        assert orchestrator.get_bootstrap_session("nonexistent") is None

    def test_get_cached_session(self):
        """Test getting cached session by parsed idea."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Cache Lookup Test",
            description="Testing cached session lookup",
            detected_project_type=ProjectType.AUTOMATION,
            confidence_score=0.85,
        )

        # Before bootstrap, should be None
        assert orchestrator.get_cached_session(parsed_idea) is None

        # After bootstrap, should be cached
        asyncio.run(orchestrator.start_bootstrap_session(parsed_idea))
        cached = orchestrator.get_cached_session(parsed_idea)

        assert cached is not None
        assert cached.parsed_idea_title == "Cache Lookup Test"

    def test_invalidate_cache(self):
        """Test invalidating cache for a parsed idea."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Invalidation Test",
            description="Testing cache invalidation",
            detected_project_type=ProjectType.TRADING,
            confidence_score=0.9,
        )

        asyncio.run(orchestrator.start_bootstrap_session(parsed_idea))
        assert orchestrator.get_cached_session(parsed_idea) is not None

        result = orchestrator.invalidate_cache(parsed_idea)
        assert result is True
        assert orchestrator.get_cached_session(parsed_idea) is None


class TestBootstrapResearchPhases:
    """Test suite for individual research phases."""

    @pytest.mark.asyncio
    async def test_market_research_phase(self):
        """Test market research phase completion."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Market Test",
            description="Testing market research",
            detected_project_type=ProjectType.ECOMMERCE,
            raw_requirements=["Req 1", "Req 2", "Req 3"],
            confidence_score=0.8,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session.market_research.status == "completed"
        assert "attractiveness_score" in session.market_research.data
        assert "indicators_evaluated" in session.market_research.data

    @pytest.mark.asyncio
    async def test_competitive_analysis_phase(self):
        """Test competitive analysis phase completion."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Competitive Test",
            description="Testing competitive analysis",
            detected_project_type=ProjectType.TRADING,
            dependencies=["API1", "API2", "API3"],
            confidence_score=0.85,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session.competitive_analysis.status == "completed"
        assert "intensity_score" in session.competitive_analysis.data
        assert "factors_evaluated" in session.competitive_analysis.data

    @pytest.mark.asyncio
    async def test_technical_feasibility_phase(self):
        """Test technical feasibility phase completion."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Feasibility Test",
            description="Testing technical feasibility",
            detected_project_type=ProjectType.AUTOMATION,
            risk_profile=RiskProfile.LOW,
            dependencies=["Docker", "Kubernetes"],
            confidence_score=0.9,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session.technical_feasibility.status == "completed"
        assert "feasibility_score" in session.technical_feasibility.data
        assert "risk_profile" in session.technical_feasibility.data


class TestBootstrapSynthesis:
    """Test suite for research synthesis."""

    @pytest.mark.asyncio
    async def test_synthesis_recommendation_proceed(self):
        """Test synthesis generates proceed recommendation for good projects."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Good Project",
            description="A well-defined project with clear requirements",
            detected_project_type=ProjectType.CONTENT,
            raw_requirements=["Req 1", "Req 2", "Req 3", "Req 4", "Req 5"],
            confidence_score=0.95,
            risk_profile=RiskProfile.LOW,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session.synthesis["overall_recommendation"] in ["proceed", "proceed_with_caution"]

    @pytest.mark.asyncio
    async def test_synthesis_contains_scores(self):
        """Test synthesis contains all score components."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Score Test",
            description="Testing score synthesis",
            detected_project_type=ProjectType.TRADING,
            confidence_score=0.8,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        scores = session.synthesis.get("scores", {})
        assert "market_attractiveness" in scores
        assert "competitive_intensity" in scores
        assert "technical_feasibility" in scores
        assert "total" in scores

    @pytest.mark.asyncio
    async def test_synthesis_metadata(self):
        """Test synthesis contains metadata."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Metadata Test",
            description="Testing synthesis metadata",
            detected_project_type=ProjectType.ECOMMERCE,
            raw_requirements=["Req 1", "Req 2"],
            dependencies=["Dep 1"],
            confidence_score=0.85,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session.synthesis["project_title"] == "Metadata Test"
        assert session.synthesis["project_type"] == "ecommerce"
        assert session.synthesis["requirements_count"] == 2
        assert session.synthesis["key_dependencies"] == ["Dep 1"]
        assert session.synthesis["parallel_execution"] is True


class TestBootstrapDuration:
    """Test suite for bootstrap session duration tracking."""

    @pytest.mark.asyncio
    async def test_phase_duration_tracking(self):
        """Test that phase durations are tracked."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Duration Test",
            description="Testing duration tracking",
            detected_project_type=ProjectType.CONTENT,
            confidence_score=0.8,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        # All phases should have duration set
        assert session.market_research.duration_seconds is not None
        assert session.competitive_analysis.duration_seconds is not None
        assert session.technical_feasibility.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_total_duration_tracking(self):
        """Test that total session duration is tracked."""
        orchestrator = ResearchOrchestrator()
        parsed_idea = ParsedIdea(
            title="Total Duration Test",
            description="Testing total duration",
            detected_project_type=ProjectType.AUTOMATION,
            confidence_score=0.85,
        )

        session = await orchestrator.start_bootstrap_session(parsed_idea)

        assert session.total_duration_seconds is not None
        assert session.total_duration_seconds >= 0
