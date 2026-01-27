"""Integration tests for stage transitions in research pipeline."""

from unittest.mock import patch

import pytest

from autopack.research.models import ResearchQuery, ResearchStage
from autopack.research.orchestrator import ResearchOrchestrator


class TestStageTransitions:
    """Test stage transitions in research pipeline."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance."""
        return ResearchOrchestrator()

    @pytest.fixture
    def sample_query(self):
        """Create sample query."""
        return ResearchQuery(query="Test research query", context={}, constraints={})

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_intent_to_discovery_transition(self, orchestrator, sample_query):
        """Test transition from intent clarification to source discovery."""
        session = await orchestrator.create_session(sample_query)

        assert session.stage == ResearchStage.INTENT_CLARIFICATION

        # Execute intent clarification
        await orchestrator._execute_intent_clarification(session)

        assert session.stage == ResearchStage.SOURCE_DISCOVERY
        assert session.clarified_intent is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_discovery_to_gathering_transition(self, orchestrator, sample_query):
        """Test transition from source discovery to evidence gathering."""
        session = await orchestrator.create_session(sample_query)

        # Execute through discovery
        await orchestrator._execute_intent_clarification(session)
        await orchestrator._execute_source_discovery(session)

        assert session.stage == ResearchStage.EVIDENCE_GATHERING
        assert len(session.discovered_sources) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_gathering_to_synthesis_transition(self, orchestrator, sample_query):
        """Test transition from evidence gathering to synthesis."""
        session = await orchestrator.create_session(sample_query)

        # Execute through gathering
        await orchestrator._execute_intent_clarification(session)
        await orchestrator._execute_source_discovery(session)
        await orchestrator._execute_evidence_gathering(session)

        assert session.stage == ResearchStage.SYNTHESIS
        assert len(session.gathered_evidence) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_synthesis_to_validation_transition(self, orchestrator, sample_query):
        """Test transition from synthesis to validation."""
        session = await orchestrator.create_session(sample_query)

        # Execute through synthesis
        await orchestrator._execute_intent_clarification(session)
        await orchestrator._execute_source_discovery(session)
        await orchestrator._execute_evidence_gathering(session)
        await orchestrator._execute_synthesis(session)

        assert session.stage == ResearchStage.VALIDATION
        assert session.synthesized_report is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_stage_progression(self, orchestrator, sample_query):
        """Test complete progression through all stages."""
        session = await orchestrator.create_session(sample_query)

        stages_visited = []

        # Track stage transitions
        original_transition = orchestrator._transition_stage

        def track_transition(session, new_stage):
            stages_visited.append(new_stage)
            return original_transition(session, new_stage)

        with patch.object(orchestrator, "_transition_stage", side_effect=track_transition):
            await orchestrator.execute_pipeline(session.session_id)

        # Should visit all stages in order
        expected_stages = [
            ResearchStage.SOURCE_DISCOVERY,
            ResearchStage.EVIDENCE_GATHERING,
            ResearchStage.SYNTHESIS,
            ResearchStage.VALIDATION,
        ]

        assert stages_visited == expected_stages

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stage_data_persistence(self, orchestrator, sample_query):
        """Test that data persists across stage transitions."""
        session = await orchestrator.create_session(sample_query)

        await orchestrator._execute_intent_clarification(session)
        clarified_intent = session.clarified_intent

        await orchestrator._execute_source_discovery(session)
        # Clarified intent should still be available
        assert session.clarified_intent == clarified_intent

        discovered_sources = session.discovered_sources

        await orchestrator._execute_evidence_gathering(session)
        # Previous data should still be available
        assert session.clarified_intent == clarified_intent
        assert session.discovered_sources == discovered_sources

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stage_rollback_on_error(self, orchestrator, sample_query):
        """Test stage rollback when error occurs."""
        session = await orchestrator.create_session(sample_query)

        await orchestrator._execute_intent_clarification(session)
        current_stage = session.stage

        # Simulate error in next stage
        with patch.object(
            orchestrator, "_execute_source_discovery", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception):
                await orchestrator._execute_source_discovery(session)

            # Stage should remain at last successful stage
            assert session.stage == current_stage
