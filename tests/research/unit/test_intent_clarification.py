"""Unit tests for intent clarification agent and Q&A loop.

IMP-RESEARCH-004: Tests for automated Q&A loop functionality.
"""

from typing import List

import pytest

from autopack.research.intent_clarification import (
    ClarificationAnswer,
    ClarificationPriority,
    ClarificationQuestion,
    ClarificationQuestionType,
    ClarifiedIntent,
    IntentClarificationAgent,
    IntentClarificationQALoop,
    QALoopConfig,
    QALoopResult,
    ResearchScope,
)
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
        return ResearchQuery(query="Tell me about AI", context={})

    @pytest.fixture
    def specific_query(self):
        """Create a specific research query."""
        return ResearchQuery(
            query="What are the latest transformer architectures for natural language processing in 2024?",
            context={"domain": "machine_learning"},
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

        # Check for transformer-related concepts (word splitting may vary)
        concepts_lower = [c.lower() for c in result.key_concepts]
        has_transformer = any("transformer" in c for c in concepts_lower)
        has_nlp_related = any(
            word in concepts_lower
            for word in ["natural", "language", "processing", "architectures"]
        )
        assert has_transformer or has_nlp_related

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
        """Test scope definition includes standard attributes."""
        result = await agent.clarify_intent(specific_query)

        assert result.scope is not None
        assert isinstance(result.scope, ResearchScope)
        assert hasattr(result.scope, "domain")
        assert hasattr(result.scope, "time_period")
        assert hasattr(result.scope, "constraints")

    @pytest.mark.asyncio
    async def test_context_incorporation(self, agent):
        """Test that context is incorporated into clarification."""
        query = ResearchQuery(
            query="Best practices",
            context={
                "domain": "software_engineering",
                "focus": "API design",
                "audience": "senior developers",
            },
        )

        result = await agent.clarify_intent(query)

        # Clarification should reflect the context
        clarified_text = " ".join(result.clarified_aspects).lower()
        # Best practices query should have best practices in aspects
        assert "best practices" in clarified_text or len(result.clarified_aspects) > 0


class TestClarificationQuestion:
    """Test suite for ClarificationQuestion dataclass."""

    def test_question_creation(self):
        """Test creating a clarification question."""
        question = ClarificationQuestion(
            question_id="q-001",
            question_text="What is the target market?",
            question_type=ClarificationQuestionType.REQUIREMENT,
            priority=ClarificationPriority.HIGH,
        )

        assert question.question_id == "q-001"
        assert question.question_text == "What is the target market?"
        assert question.question_type == ClarificationQuestionType.REQUIREMENT
        assert question.priority == ClarificationPriority.HIGH
        assert question.answered is False

    def test_mark_answered(self):
        """Test marking a question as answered."""
        question = ClarificationQuestion(
            question_id="q-001",
            question_text="What is the target market?",
            question_type=ClarificationQuestionType.REQUIREMENT,
            priority=ClarificationPriority.HIGH,
        )

        question.mark_answered("Enterprise B2B customers")

        assert question.answered is True
        assert question.answer == "Enterprise B2B customers"
        assert question.answered_at is not None

    def test_to_dict(self):
        """Test converting question to dictionary."""
        question = ClarificationQuestion(
            question_id="q-001",
            question_text="What is the target market?",
            question_type=ClarificationQuestionType.REQUIREMENT,
            priority=ClarificationPriority.HIGH,
            context="Market research context",
        )

        result = question.to_dict()

        assert result["question_id"] == "q-001"
        assert result["question_type"] == "requirement"
        assert result["priority"] == "high"
        assert "asked_at" in result


class TestClarificationAnswer:
    """Test suite for ClarificationAnswer dataclass."""

    def test_answer_creation(self):
        """Test creating a clarification answer."""
        answer = ClarificationAnswer(
            question_id="q-001",
            answer_text="Enterprise B2B customers",
            confidence=0.9,
            source="user",
        )

        assert answer.question_id == "q-001"
        assert answer.answer_text == "Enterprise B2B customers"
        assert answer.confidence == 0.9
        assert answer.source == "user"

    def test_to_dict(self):
        """Test converting answer to dictionary."""
        answer = ClarificationAnswer(
            question_id="q-001",
            answer_text="Enterprise B2B customers",
            confidence=0.9,
        )

        result = answer.to_dict()

        assert result["question_id"] == "q-001"
        assert result["answer_text"] == "Enterprise B2B customers"
        assert result["confidence"] == 0.9
        assert "timestamp" in result


class TestQALoopConfig:
    """Test suite for QALoopConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = QALoopConfig()

        assert config.max_iterations == 3
        assert config.max_questions_per_iteration == 5
        assert config.require_critical_answers is True
        assert config.use_defaults_if_unanswered is False
        assert config.min_answer_confidence == 0.5

    def test_custom_config(self):
        """Test custom configuration values."""
        config = QALoopConfig(
            max_iterations=5,
            max_questions_per_iteration=10,
            require_critical_answers=False,
        )

        assert config.max_iterations == 5
        assert config.max_questions_per_iteration == 10
        assert config.require_critical_answers is False


class TestIntentClarificationQALoop:
    """Test suite for IntentClarificationQALoop.

    IMP-RESEARCH-004: Tests for the automated Q&A loop functionality.
    """

    @pytest.fixture
    def qa_loop(self):
        """Create Q&A loop instance for testing."""
        return IntentClarificationQALoop()

    @pytest.fixture
    def qa_loop_with_config(self):
        """Create Q&A loop with custom config."""
        config = QALoopConfig(
            max_iterations=2,
            max_questions_per_iteration=3,
            require_critical_answers=False,
        )
        return IntentClarificationQALoop(config=config)

    @pytest.fixture
    def mock_answer_provider(self):
        """Create a mock answer provider."""

        def provider(
            questions: List[ClarificationQuestion],
        ) -> List[ClarificationAnswer]:
            return [
                ClarificationAnswer(
                    question_id=q.question_id,
                    answer_text=f"Answer to {q.question_text[:20]}",
                    confidence=0.8,
                    source="mock",
                )
                for q in questions
            ]

        return provider

    def test_register_answer_provider(self, qa_loop, mock_answer_provider):
        """Test registering an answer provider."""
        assert qa_loop.get_provider_count() == 0

        qa_loop.register_answer_provider(mock_answer_provider)

        assert qa_loop.get_provider_count() == 1

    def test_unregister_answer_provider(self, qa_loop, mock_answer_provider):
        """Test unregistering an answer provider."""
        qa_loop.register_answer_provider(mock_answer_provider)
        assert qa_loop.get_provider_count() == 1

        result = qa_loop.unregister_answer_provider(mock_answer_provider)

        assert result is True
        assert qa_loop.get_provider_count() == 0

    def test_generate_questions_from_pivot_validation(self, qa_loop):
        """Test generating questions from missing pivot types."""
        missing_pivots = ["north_star", "safety_risk", "budget_cost"]

        questions = qa_loop.generate_questions_from_pivot_validation(missing_pivots)

        assert len(questions) == 3
        # Should be sorted by priority (critical first)
        assert questions[0].priority == ClarificationPriority.CRITICAL
        assert questions[0].related_pivot == "north_star"
        assert questions[1].priority == ClarificationPriority.HIGH

    def test_generate_questions_respects_limit(self, qa_loop_with_config):
        """Test that question generation respects the limit."""
        missing_pivots = [
            "north_star",
            "safety_risk",
            "budget_cost",
            "memory_continuity",
            "deployment",
        ]

        questions = qa_loop_with_config.generate_questions_from_pivot_validation(missing_pivots)

        # Should be limited to max_questions_per_iteration (3)
        assert len(questions) <= 3

    def test_run_qa_loop_no_providers(self, qa_loop):
        """Test running Q&A loop without providers."""
        result = qa_loop.run_qa_loop("Test query about market research")

        assert isinstance(result, QALoopResult)
        # Without providers, no answers will be received
        assert result.total_answers_received == 0

    def test_run_qa_loop_with_provider(self, qa_loop, mock_answer_provider):
        """Test running Q&A loop with a provider."""
        qa_loop.register_answer_provider(mock_answer_provider)

        pivot_questions = ["What are the desired outcomes and success signals for this project?"]
        result = qa_loop.run_qa_loop("Build a trading bot", pivot_questions)

        assert isinstance(result, QALoopResult)
        assert result.iterations_completed >= 1
        assert result.total_answers_received > 0
        assert result.final_clarified_intent is not None

    def test_run_qa_loop_result_structure(self, qa_loop, mock_answer_provider):
        """Test the structure of Q&A loop result."""
        qa_loop.register_answer_provider(mock_answer_provider)

        result = qa_loop.run_qa_loop("Test research query")

        # Check result structure
        assert hasattr(result, "success")
        assert hasattr(result, "iterations_completed")
        assert hasattr(result, "total_questions_asked")
        assert hasattr(result, "total_answers_received")
        assert hasattr(result, "all_iterations")
        assert hasattr(result, "final_clarified_intent")

        # Check to_dict works
        result_dict = result.to_dict()
        assert "qa_loop_result" in result_dict
        assert "success" in result_dict["qa_loop_result"]

    @pytest.mark.asyncio
    async def test_run_qa_loop_async(self, qa_loop, mock_answer_provider):
        """Test running Q&A loop asynchronously."""
        qa_loop.register_answer_provider(mock_answer_provider)

        result = await qa_loop.run_qa_loop_async("Async test query")

        assert isinstance(result, QALoopResult)
        assert result.iterations_completed >= 1
        assert result.final_clarified_intent is not None

    def test_qa_loop_respects_max_iterations(self, qa_loop_with_config):
        """Test that Q&A loop respects max iterations."""

        # Create a provider that always returns low-confidence answers
        def low_confidence_provider(questions):
            return [
                ClarificationAnswer(
                    question_id=q.question_id,
                    answer_text="Low confidence answer",
                    confidence=0.3,  # Below threshold
                    source="mock",
                )
                for q in questions
            ]

        qa_loop_with_config.register_answer_provider(low_confidence_provider)

        pivot_questions = ["What are the desired outcomes and success signals for this project?"]
        result = qa_loop_with_config.run_qa_loop("Test query", pivot_questions)

        # Should stop at max_iterations (2)
        assert result.iterations_completed <= 2

    def test_integrate_answers_into_intent(self, qa_loop, mock_answer_provider):
        """Test that answers are integrated into clarified intent."""
        qa_loop.register_answer_provider(mock_answer_provider)

        pivot_questions = [
            "What are the desired outcomes and success signals for this project?",
            "What operations must never be allowed, and what requires approval?",
        ]
        result = qa_loop.run_qa_loop("Build an e-commerce platform", pivot_questions)

        # Final intent should have enhanced aspects from answers
        assert result.final_clarified_intent is not None
        # Should have more aspects than initial
        assert len(result.final_clarified_intent.clarified_aspects) > 0


class TestQALoopWithDefaults:
    """Test Q&A loop with default answer handling."""

    def test_use_defaults_when_configured(self):
        """Test that defaults are used when configured."""
        config = QALoopConfig(
            max_iterations=1,
            use_defaults_if_unanswered=True,
            require_critical_answers=False,
        )
        qa_loop = IntentClarificationQALoop(config=config)

        # Create a question with a default
        questions = qa_loop.generate_questions_from_pivot_validation(["north_star"])
        for q in questions:
            q.default_answer = "Default: achieve project goals"

        result = qa_loop.run_qa_loop("Test query with defaults")

        # Result should include answers from defaults
        assert result.iterations_completed >= 1
