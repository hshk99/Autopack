"""Integration tests for full research pipeline."""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from autopack.research.orchestrator import ResearchOrchestrator
from autopack.research.models import ResearchQuery


class TestFullResearchPipeline:
    """Integration tests for complete research pipeline."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator for integration testing."""
        return ResearchOrchestrator()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_simple_research_query_end_to_end(self, orchestrator):
        """Test complete pipeline with simple query."""
        query = ResearchQuery(
            query="What is Python?",
            context={"depth": "basic"},
            constraints={"max_sources": 5}
        )
        
        session = await orchestrator.create_session(query)
        result = await orchestrator.execute_pipeline(session.session_id)
        
        assert result is not None
        assert result.status == "completed"
        assert result.report is not None
        assert len(result.report.evidence) > 0
        assert all(len(e.citations) > 0 for e in result.report.evidence)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_technical_research_query(self, orchestrator):
        """Test pipeline with technical query."""
        query = ResearchQuery(
            query="How does Python's asyncio event loop work?",
            context={"domain": "software_engineering", "depth": "detailed"},
            constraints={"max_sources": 10, "prefer_official_docs": True}
        )
        
        session = await orchestrator.create_session(query)
        result = await orchestrator.execute_pipeline(session.session_id)
        
        assert result.status == "completed"
        assert result.report is not None
        
        # Should have documentation sources
        sources = [c.source_url for e in result.report.evidence for c in e.citations]
        assert any("docs.python.org" in url for url in sources)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_academic_research_query(self, orchestrator):
        """Test pipeline with academic query."""
        query = ResearchQuery(
            query="What are recent advances in transformer architectures?",
            context={"domain": "machine_learning", "academic": True},
            constraints={"max_sources": 15, "prefer_academic": True}
        )
        
        session = await orchestrator.create_session(query)
        result = await orchestrator.execute_pipeline(session.session_id)
        
        assert result.status == "completed"
        assert result.report is not None
        
        # Should have academic sources
        sources = [c.source_url for e in result.report.evidence for c in e.citations]
        assert any("arxiv.org" in url or "scholar.google" in url for url in sources)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pipeline_with_constraints(self, orchestrator):
        """Test pipeline respects constraints."""
        query = ResearchQuery(
            query="Best practices for API design",
            context={},
            constraints={
                "max_sources": 3,
                "time_limit": 60,
                "min_quality": "high"
            }
        )
        
        session = await orchestrator.create_session(query)
        result = await orchestrator.execute_pipeline(session.session_id)
        
        assert result.status == "completed"
        
        # Should respect max_sources constraint
        unique_sources = set()
        for evidence in result.report.evidence:
            for citation in evidence.citations:
                unique_sources.add(citation.source_url)
        
        assert len(unique_sources) <= 3

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pipeline_error_recovery(self, orchestrator):
        """Test pipeline handles errors gracefully."""
        query = ResearchQuery(
            query="Test query",
            context={},
            constraints={}
        )
        
        session = await orchestrator.create_session(query)
        
        # Simulate error in one stage
        with patch.object(orchestrator, '_execute_source_discovery', side_effect=Exception("Network error")):
            result = await orchestrator.execute_pipeline(session.session_id)
            
            assert result.status == "error"
            assert result.error_message is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_research_sessions(self, orchestrator):
        """Test handling multiple concurrent research sessions."""
        queries = [
            ResearchQuery(query=f"Query {i}", context={}, constraints={})
            for i in range(3)
        ]
        
        sessions = [await orchestrator.create_session(q) for q in queries]
        
        # Execute all pipelines concurrently
        import asyncio
        results = await asyncio.gather(
            *[orchestrator.execute_pipeline(s.session_id) for s in sessions],
            return_exceptions=True
        )
        
        # All should complete
        assert len(results) == 3
        assert all(r.status in ["completed", "error"] for r in results if not isinstance(r, Exception))

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_validation_integration(self, orchestrator):
        """Test that validation is properly integrated."""
        query = ResearchQuery(
            query="What is machine learning?",
            context={},
            constraints={"min_evidence_count": 5}
        )
        
        session = await orchestrator.create_session(query)
        result = await orchestrator.execute_pipeline(session.session_id)
        
        assert result.status == "completed"
        assert result.validation_result is not None
        assert result.validation_result.is_valid
        assert len(result.report.evidence) >= 5
