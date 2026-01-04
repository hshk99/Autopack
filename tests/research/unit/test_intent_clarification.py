"""Unit tests for intent clarification agent."""
import pytest

from autopack.research.intent_clarification import IntentClarificationAgent, ClarifiedIntent
from autopack.research.models import ResearchQuery


class TestIntentClarificationAgent:
    """Test suite for IntentClarificationAgent."""

    @pytest.fixture
    def agent(self):
        """Create agent instance for testing."""
        return IntentClarificationAgent()

    @pytest.fixture
    def vague_query(self):
        """Create a vague research query."""
        return ResearchQuery(
            query="Tell me about AI",
            context={}
        )

    @pytest.fixture
    def specific_query(self):
        """Create a specific research query."""
        return ResearchQuery(
            query="What are the latest transformer architectures for natural language processing in 2024?",
            context={"domain": "machine_learning"}
        )

    @pytest.mark.asyncio
    async def test_clarify_vague_query(self, agent, vague_query):
        """Test clarifying a vague query."""
        result = await agent.clarify_intent(vague_query)
        
        assert isinstance(result, ClarifiedIntent)
        assert result.original_query == vague_query.query
        assert len(result.clarified_aspects) > 0
        assert result.scope is not None
        assert len(result.key_questions) > 0

    @pytest.mark.asyncio
    async def test_clarify_specific_query(self, agent, specific_query):
        """Test clarifying an already specific query."""
        result = await agent.clarify_intent(specific_query)
        
        assert isinstance(result, ClarifiedIntent)
        assert result.original_query == specific_query.query
        assert result.scope is not None

    @pytest.mark.asyncio
    async def test_extract_key_concepts(self, agent, specific_query):
        """Test extracting key concepts from query."""
        result = await agent.clarify_intent(specific_query)
        
        assert "transformer" in result.key_concepts or "transformers" in result.key_concepts
        assert "natural language processing" in result.key_concepts or "NLP" in result.key_concepts

    @pytest.mark.asyncio
    async def test_identify_research_dimensions(self, agent, vague_query):
        """Test identifying research dimensions."""
        result = await agent.clarify_intent(vague_query)
        
        assert len(result.dimensions) > 0
        # Common dimensions might include: technical, historical, practical, etc.

    @pytest.mark.asyncio
    async def test_generate_sub_questions(self, agent, vague_query):
        """Test generating sub-questions for research."""
        result = await agent.clarify_intent(vague_query)
        
        assert len(result.key_questions) >= 3
        for question in result.key_questions:
            assert isinstance(question, str)
            assert len(question) > 0

    @pytest.mark.asyncio
    async def test_scope_definition(self, agent, specific_query):
        """Test scope definition includes boundaries."""
        result = await agent.clarify_intent(specific_query)
        
        assert result.scope is not None
        assert hasattr(result.scope, 'included_topics')
        assert hasattr(result.scope, 'excluded_topics')
        assert hasattr(result.scope, 'time_range')

    @pytest.mark.asyncio
    async def test_context_incorporation(self, agent):
        """Test that context is incorporated into clarification."""
        query = ResearchQuery(
            query="Best practices",
            context={
                "domain": "software_engineering",
                "focus": "API design",
                "audience": "senior developers"
            }
        )
        
        result = await agent.clarify_intent(query)
        
        # Clarification should reflect the context
        clarified_text = " ".join(result.clarified_aspects).lower()
        assert "api" in clarified_text or "software" in clarified_text
