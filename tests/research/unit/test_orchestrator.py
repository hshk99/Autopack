"""Unit tests for research orchestrator."""

import pytest
from unittest.mock import AsyncMock, patch

from autopack.research.orchestrator import ResearchOrchestrator, ResearchSession
from autopack.research.models import ResearchQuery, ResearchStage


class TestResearchOrchestrator:
    """Test suite for ResearchOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance for testing."""
        return ResearchOrchestrator()

    @pytest.fixture
    def sample_query(self):
        """Create sample research query."""
        return ResearchQuery(
            query="What are the best practices for API design?",
            context={"domain": "software_engineering"},
            constraints={"max_sources": 10, "time_limit": 300},
        )

    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initializes correctly."""
        assert orchestrator is not None
        assert hasattr(orchestrator, "sessions")
        assert len(orchestrator.sessions) == 0

    @pytest.mark.asyncio
    async def test_create_session(self, orchestrator, sample_query):
        """Test creating a new research session."""
        session = await orchestrator.create_session(sample_query)

        assert session is not None
        assert session.session_id is not None
        assert session.query == sample_query
        assert session.stage == ResearchStage.INTENT_CLARIFICATION
        assert session.status == "active"

    @pytest.mark.asyncio
    async def test_execute_pipeline_stages(self, orchestrator, sample_query):
        """Test pipeline executes all stages in order."""
        session = await orchestrator.create_session(sample_query)

        with (
            patch.object(
                orchestrator, "_execute_intent_clarification", new_callable=AsyncMock
            ) as mock_intent,
            patch.object(
                orchestrator, "_execute_source_discovery", new_callable=AsyncMock
            ) as mock_discovery,
            patch.object(
                orchestrator, "_execute_evidence_gathering", new_callable=AsyncMock
            ) as mock_gathering,
            patch.object(
                orchestrator, "_execute_synthesis", new_callable=AsyncMock
            ) as mock_synthesis,
            patch.object(
                orchestrator, "_execute_validation", new_callable=AsyncMock
            ) as mock_validation,
        ):
            await orchestrator.execute_pipeline(session.session_id)

            mock_intent.assert_called_once()
            mock_discovery.assert_called_once()
            mock_gathering.assert_called_once()
            mock_synthesis.assert_called_once()
            mock_validation.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_state_transitions(self, orchestrator, sample_query):
        """Test session transitions through stages correctly."""
        session = await orchestrator.create_session(sample_query)
        initial_stage = session.stage

        assert initial_stage == ResearchStage.INTENT_CLARIFICATION

        # Simulate stage progression
        session.stage = ResearchStage.SOURCE_DISCOVERY
        assert session.stage == ResearchStage.SOURCE_DISCOVERY

        session.stage = ResearchStage.EVIDENCE_GATHERING
        assert session.stage == ResearchStage.EVIDENCE_GATHERING

    @pytest.mark.asyncio
    async def test_error_handling_in_pipeline(self, orchestrator, sample_query):
        """Test pipeline handles errors gracefully."""
        session = await orchestrator.create_session(sample_query)

        with patch.object(
            orchestrator, "_execute_intent_clarification", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception) as exc_info:
                await orchestrator.execute_pipeline(session.session_id)

            assert "Test error" in str(exc_info.value)
            assert session.status == "error"

    def test_get_session(self, orchestrator):
        """Test retrieving a session by ID."""
        session = ResearchSession(
            session_id="test123",
            query=ResearchQuery(query="test"),
            stage=ResearchStage.INTENT_CLARIFICATION,
        )
        orchestrator.sessions["test123"] = session

        retrieved = orchestrator.get_session("test123")
        assert retrieved == session

        not_found = orchestrator.get_session("nonexistent")
        assert not_found is None

    def test_list_sessions(self, orchestrator):
        """Test listing all sessions."""
        session1 = ResearchSession(
            session_id="test1",
            query=ResearchQuery(query="query1"),
            stage=ResearchStage.INTENT_CLARIFICATION,
        )
        session2 = ResearchSession(
            session_id="test2",
            query=ResearchQuery(query="query2"),
            stage=ResearchStage.SOURCE_DISCOVERY,
        )

        orchestrator.sessions["test1"] = session1
        orchestrator.sessions["test2"] = session2

        sessions = orchestrator.list_sessions()
        assert len(sessions) == 2
        assert session1 in sessions
        assert session2 in sessions
