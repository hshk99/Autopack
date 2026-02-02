"""Research Intent Clarification - Clarify vague research queries.

This module provides functionality to clarify vague research queries by
extracting key concepts, generating sub-questions, and defining scope.

IMP-RESEARCH-004: Implements automated Q&A loop for intent clarification
that generates clarification questions and re-runs research based on answers.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class ResearchScope:
    """Research scope definition."""

    domain: str = ""
    time_period: str = ""
    geographical_focus: str = ""
    constraints: List[str] = field(default_factory=list)


@dataclass
class ClarifiedIntent:
    """Clarified research intent with detailed breakdown.

    Attributes:
        original_query: Original user query
        clarified_aspects: Specific aspects to investigate
        key_concepts: Key concepts extracted from query
        key_questions: Sub-questions to guide research
        scope: Research scope definition
        dimensions: Research dimensions (technical, historical, practical, etc.)
    """

    original_query: str
    clarified_aspects: List[str] = field(default_factory=list)
    key_concepts: List[str] = field(default_factory=list)
    key_questions: List[str] = field(default_factory=list)
    scope: Optional[ResearchScope] = None
    dimensions: List[str] = field(default_factory=list)


class IntentClarificationAgent:
    """Agent for clarifying research intent."""

    def __init__(self):
        """Initialize intent clarification agent."""
        pass

    async def clarify_intent(self, query: Any) -> ClarifiedIntent:
        """Clarify research intent from a query.

        Args:
            query: ResearchQuery object or string

        Returns:
            ClarifiedIntent with detailed breakdown
        """
        # Extract query string
        if hasattr(query, "query"):
            query_str = query.query
            context = getattr(query, "context", {})
        else:
            query_str = str(query)
            context = {}

        # Extract key concepts (simple heuristic: important words)
        key_concepts = self._extract_concepts(query_str)

        # Generate clarified aspects
        clarified_aspects = self._identify_aspects(query_str, key_concepts)

        # Generate sub-questions
        key_questions = self._generate_questions(query_str, clarified_aspects)

        # Identify research dimensions
        dimensions = self._identify_dimensions(query_str)

        # Define scope
        scope = ResearchScope(
            domain=context.get("domain", ""),
            time_period=self._extract_time_period(query_str),
            geographical_focus="",
            constraints=[],
        )

        return ClarifiedIntent(
            original_query=query_str,
            clarified_aspects=clarified_aspects,
            key_concepts=key_concepts,
            key_questions=key_questions,
            scope=scope,
            dimensions=dimensions,
        )

    def _extract_concepts(self, query: str) -> List[str]:
        """Extract key concepts from query.

        Args:
            query: Query string

        Returns:
            List of key concepts
        """
        # Simple heuristic: extract important words (> 3 chars, not common words)
        stop_words = {
            "the",
            "and",
            "for",
            "are",
            "what",
            "how",
            "why",
            "when",
            "where",
            "who",
            "which",
            "that",
            "this",
            "with",
            "from",
            "about",
            "tell",
        }
        words = query.lower().split()
        concepts = [w.strip("?.,!") for w in words if len(w) > 3 and w.lower() not in stop_words]
        return concepts[:10]  # Limit to top 10

    def _identify_aspects(self, query: str, concepts: List[str]) -> List[str]:
        """Identify specific aspects to investigate.

        Args:
            query: Query string
            concepts: Key concepts

        Returns:
            List of clarified aspects
        """
        aspects = []

        # Check for common aspect patterns
        query_lower = query.lower()

        if "best practices" in query_lower:
            aspects.append("Best practices and standards")
        if "design" in query_lower:
            aspects.append("Design patterns and architecture")
        if "performance" in query_lower or "optimization" in query_lower:
            aspects.append("Performance optimization")
        if "security" in query_lower:
            aspects.append("Security considerations")
        if "implementation" in query_lower or "how to" in query_lower:
            aspects.append("Implementation approaches")
        if "comparison" in query_lower or "vs" in query_lower:
            aspects.append("Comparative analysis")

        # If no specific aspects found, use concepts
        if not aspects:
            aspects = [f"{concept} fundamentals" for concept in concepts[:3]]

        return aspects[:5]  # Limit to 5 aspects

    def _generate_questions(self, query: str, aspects: List[str]) -> List[str]:
        """Generate sub-questions to guide research.

        Args:
            query: Query string
            aspects: Clarified aspects

        Returns:
            List of key questions
        """
        questions = []

        # Generate questions based on aspects
        for aspect in aspects:
            if "best practices" in aspect.lower():
                questions.append("What are the established best practices?")
            elif "design" in aspect.lower():
                questions.append("What are the common design patterns?")
            elif "performance" in aspect.lower():
                questions.append("What are the key performance considerations?")
            elif "security" in aspect.lower():
                questions.append("What are the security implications?")
            elif "implementation" in aspect.lower():
                questions.append("How is this typically implemented?")
            else:
                questions.append(f"What are the key aspects of {aspect}?")

        # Ensure at least 3 questions
        while len(questions) < 3:
            questions.append("What are the main challenges?")
            questions.append("What are the current trends?")
            questions.append("What are the practical applications?")

        return questions[:10]  # Limit to 10 questions

    def _identify_dimensions(self, query: str) -> List[str]:
        """Identify research dimensions.

        Args:
            query: Query string

        Returns:
            List of research dimensions
        """
        dimensions = []
        query_lower = query.lower()

        if any(word in query_lower for word in ["how", "implementation", "code", "example"]):
            dimensions.append("practical")
        if any(word in query_lower for word in ["why", "theory", "concept", "principle"]):
            dimensions.append("theoretical")
        if any(word in query_lower for word in ["history", "evolution", "origin"]):
            dimensions.append("historical")
        if any(word in query_lower for word in ["technical", "architecture", "design"]):
            dimensions.append("technical")
        if any(word in query_lower for word in ["compare", "versus", "vs", "difference"]):
            dimensions.append("comparative")

        # Default dimension if none found
        if not dimensions:
            dimensions.append("practical")

        return dimensions

    def _extract_time_period(self, query: str) -> str:
        """Extract time period from query.

        Args:
            query: Query string

        Returns:
            Time period string or empty
        """
        import re

        # Look for years
        year_match = re.search(r"\b(20\d{2})\b", query)
        if year_match:
            return year_match.group(1)

        # Look for relative time
        if "latest" in query.lower() or "recent" in query.lower():
            return "recent"
        if "current" in query.lower():
            return "current"

        return ""


class ClarificationQuestionType(Enum):
    """Types of clarification questions."""

    PIVOT_INTENT = "pivot_intent"  # Missing pivot intention
    SCOPE_BOUNDARY = "scope_boundary"  # Unclear scope boundaries
    REQUIREMENT = "requirement"  # Missing requirement details
    CONSTRAINT = "constraint"  # Unclear constraints
    GENERAL = "general"  # General clarification


class ClarificationPriority(Enum):
    """Priority levels for clarification questions."""

    CRITICAL = "critical"  # Must be answered to proceed
    HIGH = "high"  # Strongly recommended
    MEDIUM = "medium"  # Helpful but not blocking
    LOW = "low"  # Nice to have


@dataclass
class ClarificationQuestion:
    """A single clarification question.

    IMP-RESEARCH-004: Represents a question generated during intent clarification
    that needs an answer to proceed with research.

    Attributes:
        question_id: Unique identifier for the question
        question_text: The question text to present to the user
        question_type: Type of clarification question
        priority: Priority level of the question
        context: Additional context for the question
        related_pivot: Optional pivot type this question relates to
        default_answer: Optional default answer if not provided
        answered: Whether the question has been answered
        answer: The provided answer
    """

    question_id: str
    question_text: str
    question_type: ClarificationQuestionType
    priority: ClarificationPriority
    context: str = ""
    related_pivot: Optional[str] = None
    default_answer: Optional[str] = None
    answered: bool = False
    answer: Optional[str] = None
    asked_at: datetime = field(default_factory=datetime.now)
    answered_at: Optional[datetime] = None

    def mark_answered(self, answer: str) -> None:
        """Mark this question as answered.

        Args:
            answer: The provided answer
        """
        self.answered = True
        self.answer = answer
        self.answered_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "question_type": self.question_type.value,
            "priority": self.priority.value,
            "context": self.context,
            "related_pivot": self.related_pivot,
            "default_answer": self.default_answer,
            "answered": self.answered,
            "answer": self.answer,
            "asked_at": self.asked_at.isoformat(),
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
        }


@dataclass
class ClarificationAnswer:
    """An answer to a clarification question.

    Attributes:
        question_id: ID of the question being answered
        answer_text: The answer text
        confidence: Confidence in the answer (0-1)
        source: Source of the answer (user, default, inferred)
        timestamp: When the answer was provided
    """

    question_id: str
    answer_text: str
    confidence: float = 1.0
    source: str = "user"
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "question_id": self.question_id,
            "answer_text": self.answer_text,
            "confidence": self.confidence,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class QALoopConfig:
    """Configuration for the Q&A loop.

    IMP-RESEARCH-004: Controls the behavior of the automated Q&A loop.

    Attributes:
        max_iterations: Maximum Q&A iterations before stopping
        max_questions_per_iteration: Max questions to ask per iteration
        require_critical_answers: Whether critical questions must be answered
        use_defaults_if_unanswered: Use default answers if not provided
        min_answer_confidence: Minimum confidence for answers to be accepted
        timeout_seconds: Timeout for answer collection
    """

    max_iterations: int = 3
    max_questions_per_iteration: int = 5
    require_critical_answers: bool = True
    use_defaults_if_unanswered: bool = False
    min_answer_confidence: float = 0.5
    timeout_seconds: int = 300


@dataclass
class QALoopIteration:
    """Result of a single Q&A iteration.

    Attributes:
        iteration_number: The iteration number (1-indexed)
        questions_asked: Questions asked in this iteration
        answers_received: Answers received
        questions_remaining: Questions still unanswered
        should_continue: Whether more iterations are needed
    """

    iteration_number: int
    questions_asked: List[ClarificationQuestion]
    answers_received: List[ClarificationAnswer]
    questions_remaining: List[ClarificationQuestion]
    should_continue: bool
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "iteration_number": self.iteration_number,
            "questions_asked": [q.to_dict() for q in self.questions_asked],
            "answers_received": [a.to_dict() for a in self.answers_received],
            "questions_remaining": [q.to_dict() for q in self.questions_remaining],
            "should_continue": self.should_continue,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class QALoopResult:
    """Result of the complete Q&A loop.

    IMP-RESEARCH-004: Final result of the automated Q&A loop including
    all iterations, collected answers, and final clarified intent.

    Attributes:
        success: Whether the loop completed successfully
        iterations_completed: Number of iterations completed
        total_questions_asked: Total questions asked across all iterations
        total_answers_received: Total answers received
        all_iterations: List of all iteration results
        final_clarified_intent: The final clarified intent after Q&A
        unanswered_critical: List of unanswered critical questions
        error_message: Error message if loop failed
    """

    success: bool
    iterations_completed: int
    total_questions_asked: int
    total_answers_received: int
    all_iterations: List[QALoopIteration] = field(default_factory=list)
    final_clarified_intent: Optional[ClarifiedIntent] = None
    unanswered_critical: List[ClarificationQuestion] = field(default_factory=list)
    error_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    total_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "qa_loop_result": {
                "success": self.success,
                "iterations_completed": self.iterations_completed,
                "total_questions_asked": self.total_questions_asked,
                "total_answers_received": self.total_answers_received,
                "all_iterations": [it.to_dict() for it in self.all_iterations],
                "final_clarified_intent": (
                    {
                        "original_query": self.final_clarified_intent.original_query,
                        "clarified_aspects": self.final_clarified_intent.clarified_aspects,
                        "key_concepts": self.final_clarified_intent.key_concepts,
                        "key_questions": self.final_clarified_intent.key_questions,
                        "dimensions": self.final_clarified_intent.dimensions,
                    }
                    if self.final_clarified_intent
                    else None
                ),
                "unanswered_critical": [q.to_dict() for q in self.unanswered_critical],
                "error_message": self.error_message,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "total_time_ms": self.total_time_ms,
            }
        }


# Type aliases for answer provider callbacks
# Synchronous answer provider: takes questions, returns answers
AnswerProvider = Callable[[List[ClarificationQuestion]], List[ClarificationAnswer]]
# Asynchronous answer provider
AsyncAnswerProvider = Callable[
    [List[ClarificationQuestion]], "asyncio.Future[List[ClarificationAnswer]]"
]


class AnswerProviderProtocol(Protocol):
    """Protocol for answer providers.

    IMP-RESEARCH-004: Defines the interface for answer providers
    that can be used with the Q&A loop.
    """

    def provide_answers(self, questions: List[ClarificationQuestion]) -> List[ClarificationAnswer]:
        """Provide answers to the given questions.

        Args:
            questions: List of questions to answer

        Returns:
            List of answers
        """
        ...


class IntentClarificationQALoop:
    """Automated Q&A loop for intent clarification.

    IMP-RESEARCH-004: Implements an automated loop that generates clarification
    questions based on validate_pivot_completeness() and re-runs research
    based on answers.

    Example usage:
        ```python
        loop = IntentClarificationQALoop()

        # Register an answer provider
        def get_answers(questions: List[ClarificationQuestion]) -> List[ClarificationAnswer]:
            return [ClarificationAnswer(q.question_id, "user answer") for q in questions]

        loop.register_answer_provider(get_answers)

        # Run the Q&A loop
        result = await loop.run_qa_loop_async(initial_query)
        if result.success:
            print(f"Final intent: {result.final_clarified_intent}")
        ```
    """

    # Pivot type to question mapping
    PIVOT_QUESTIONS = {
        "north_star": {
            "text": "What are the desired outcomes and success signals for this project?",
            "priority": ClarificationPriority.CRITICAL,
        },
        "safety_risk": {
            "text": "What operations must never be allowed, and what requires approval?",
            "priority": ClarificationPriority.HIGH,
        },
        "evidence_verification": {
            "text": "What checks must pass (hard blocks) and what proof artifacts are required?",
            "priority": ClarificationPriority.HIGH,
        },
        "scope_boundaries": {
            "text": "Which paths are allowed for writes, and which are protected?",
            "priority": ClarificationPriority.MEDIUM,
        },
        "budget_cost": {
            "text": "What are the token/time budget caps and cost escalation policy?",
            "priority": ClarificationPriority.MEDIUM,
        },
        "memory_continuity": {
            "text": "What should persist to SOT ledgers and what are the retention rules?",
            "priority": ClarificationPriority.LOW,
        },
        "governance_review": {
            "text": "What is the approval policy and what auto-approval rules apply?",
            "priority": ClarificationPriority.MEDIUM,
        },
        "parallelism_isolation": {
            "text": "Is parallelism allowed, and if so, what isolation model is required?",
            "priority": ClarificationPriority.LOW,
        },
        "deployment": {
            "text": "What are the deployment requirements and secrets configuration?",
            "priority": ClarificationPriority.MEDIUM,
        },
    }

    def __init__(self, config: Optional[QALoopConfig] = None):
        """Initialize the Q&A loop.

        Args:
            config: Configuration for the loop (uses defaults if not provided)
        """
        self.config = config or QALoopConfig()
        self._clarification_agent = IntentClarificationAgent()
        self._question_counter = 0
        self._answer_providers: List[AnswerProvider] = []
        self._async_answer_providers: List[AsyncAnswerProvider] = []
        self._all_questions: Dict[str, ClarificationQuestion] = {}
        self._all_answers: Dict[str, ClarificationAnswer] = {}

    def register_answer_provider(self, provider: AnswerProvider) -> None:
        """Register a synchronous answer provider.

        IMP-RESEARCH-004: Answer providers are called during Q&A iterations
        to collect answers to clarification questions.

        Args:
            provider: Function that takes questions and returns answers

        Example:
            ```python
            def interactive_provider(questions):
                answers = []
                for q in questions:
                    user_input = input(f"{q.question_text}: ")
                    answers.append(ClarificationAnswer(q.question_id, user_input))
                return answers

            loop.register_answer_provider(interactive_provider)
            ```
        """
        if provider not in self._answer_providers:
            self._answer_providers.append(provider)
            logger.debug(
                f"[IMP-RESEARCH-004] Registered answer provider "
                f"(total: {len(self._answer_providers)})"
            )

    def register_async_answer_provider(self, provider: AsyncAnswerProvider) -> None:
        """Register an asynchronous answer provider.

        IMP-RESEARCH-004: Async providers enable non-blocking answer collection
        such as API calls or external service queries.

        Args:
            provider: Async function that takes questions and returns answers
        """
        if provider not in self._async_answer_providers:
            self._async_answer_providers.append(provider)
            logger.debug(
                f"[IMP-RESEARCH-004] Registered async answer provider "
                f"(total: {len(self._async_answer_providers)})"
            )

    def unregister_answer_provider(self, provider: AnswerProvider) -> bool:
        """Unregister a synchronous answer provider.

        Args:
            provider: The provider to unregister

        Returns:
            True if provider was found and removed
        """
        try:
            self._answer_providers.remove(provider)
            return True
        except ValueError:
            return False

    def unregister_async_answer_provider(self, provider: AsyncAnswerProvider) -> bool:
        """Unregister an asynchronous answer provider.

        Args:
            provider: The async provider to unregister

        Returns:
            True if provider was found and removed
        """
        try:
            self._async_answer_providers.remove(provider)
            return True
        except ValueError:
            return False

    def get_provider_count(self) -> int:
        """Get total number of registered providers.

        Returns:
            Total provider count (sync + async)
        """
        return len(self._answer_providers) + len(self._async_answer_providers)

    def _generate_question_id(self) -> str:
        """Generate unique question ID."""
        self._question_counter += 1
        return f"clarify-q-{self._question_counter:03d}"

    def generate_questions_from_pivot_validation(
        self,
        missing_pivots: List[str],
    ) -> List[ClarificationQuestion]:
        """Generate clarification questions from missing pivot types.

        IMP-RESEARCH-004: Uses validate_pivot_completeness() output to generate
        structured clarification questions.

        Args:
            missing_pivots: List of pivot types that are incomplete

        Returns:
            List of ClarificationQuestion objects
        """
        questions = []

        for pivot_type in missing_pivots:
            if pivot_type in self.PIVOT_QUESTIONS:
                pivot_info = self.PIVOT_QUESTIONS[pivot_type]
                question = ClarificationQuestion(
                    question_id=self._generate_question_id(),
                    question_text=pivot_info["text"],
                    question_type=ClarificationQuestionType.PIVOT_INTENT,
                    priority=pivot_info["priority"],
                    context=f"Missing {pivot_type} pivot intention",
                    related_pivot=pivot_type,
                )
                questions.append(question)
                self._all_questions[question.question_id] = question

        # Sort by priority (critical first)
        priority_order = {
            ClarificationPriority.CRITICAL: 0,
            ClarificationPriority.HIGH: 1,
            ClarificationPriority.MEDIUM: 2,
            ClarificationPriority.LOW: 3,
        }
        questions.sort(key=lambda q: priority_order.get(q.priority, 4))

        return questions[: self.config.max_questions_per_iteration]

    def generate_questions_from_intent(
        self,
        clarified_intent: ClarifiedIntent,
    ) -> List[ClarificationQuestion]:
        """Generate additional clarification questions from intent analysis.

        Args:
            clarified_intent: Current clarified intent

        Returns:
            List of additional ClarificationQuestion objects
        """
        questions = []

        # Generate questions for vague aspects
        for aspect in clarified_intent.clarified_aspects:
            if "fundamentals" in aspect.lower():
                # This aspect might need more specificity
                question = ClarificationQuestion(
                    question_id=self._generate_question_id(),
                    question_text=f"Can you provide more specific details about {aspect}?",
                    question_type=ClarificationQuestionType.REQUIREMENT,
                    priority=ClarificationPriority.MEDIUM,
                    context=f"Clarifying vague aspect: {aspect}",
                )
                questions.append(question)
                self._all_questions[question.question_id] = question

        # Check if scope needs clarification
        if clarified_intent.scope and not clarified_intent.scope.domain:
            question = ClarificationQuestion(
                question_id=self._generate_question_id(),
                question_text="What domain or industry should this research focus on?",
                question_type=ClarificationQuestionType.SCOPE_BOUNDARY,
                priority=ClarificationPriority.HIGH,
                context="Missing domain specification",
            )
            questions.append(question)
            self._all_questions[question.question_id] = question

        return questions[: self.config.max_questions_per_iteration]

    def _collect_answers_sync(
        self,
        questions: List[ClarificationQuestion],
    ) -> List[ClarificationAnswer]:
        """Collect answers using synchronous providers.

        Args:
            questions: Questions to get answers for

        Returns:
            List of collected answers
        """
        all_answers: List[ClarificationAnswer] = []

        if not self._answer_providers:
            logger.warning("[IMP-RESEARCH-004] No answer providers registered")
            return all_answers

        for provider in self._answer_providers:
            try:
                answers = provider(questions)
                for answer in answers:
                    if answer.confidence >= self.config.min_answer_confidence:
                        all_answers.append(answer)
                        self._all_answers[answer.question_id] = answer

                        # Mark the question as answered
                        if answer.question_id in self._all_questions:
                            self._all_questions[answer.question_id].mark_answered(
                                answer.answer_text
                            )
            except Exception as e:
                logger.warning(f"[IMP-RESEARCH-004] Answer provider failed: {e}")

        return all_answers

    async def _collect_answers_async(
        self,
        questions: List[ClarificationQuestion],
    ) -> List[ClarificationAnswer]:
        """Collect answers using async providers.

        Args:
            questions: Questions to get answers for

        Returns:
            List of collected answers
        """
        all_answers: List[ClarificationAnswer] = []

        # Try sync providers first
        all_answers.extend(self._collect_answers_sync(questions))

        # Then async providers
        for provider in self._async_answer_providers:
            try:
                if asyncio.iscoroutinefunction(provider):
                    answers = await provider(questions)
                else:
                    loop = asyncio.get_event_loop()
                    answers = await loop.run_in_executor(None, provider, questions)

                for answer in answers:
                    if answer.confidence >= self.config.min_answer_confidence:
                        all_answers.append(answer)
                        self._all_answers[answer.question_id] = answer

                        # Mark the question as answered
                        if answer.question_id in self._all_questions:
                            self._all_questions[answer.question_id].mark_answered(
                                answer.answer_text
                            )
            except Exception as e:
                logger.warning(f"[IMP-RESEARCH-004] Async answer provider failed: {e}")

        return all_answers

    def _apply_default_answers(
        self,
        questions: List[ClarificationQuestion],
    ) -> List[ClarificationAnswer]:
        """Apply default answers to unanswered questions.

        Args:
            questions: Questions to apply defaults to

        Returns:
            List of answers created from defaults
        """
        default_answers = []

        for question in questions:
            if not question.answered and question.default_answer:
                answer = ClarificationAnswer(
                    question_id=question.question_id,
                    answer_text=question.default_answer,
                    confidence=0.5,  # Lower confidence for defaults
                    source="default",
                )
                default_answers.append(answer)
                question.mark_answered(question.default_answer)
                self._all_answers[answer.question_id] = answer

        return default_answers

    def _integrate_answers_into_intent(
        self,
        clarified_intent: ClarifiedIntent,
        answers: List[ClarificationAnswer],
    ) -> ClarifiedIntent:
        """Integrate collected answers into the clarified intent.

        IMP-RESEARCH-004: Updates the clarified intent based on Q&A answers
        to produce a more refined research intent.

        Args:
            clarified_intent: Current clarified intent
            answers: Collected answers

        Returns:
            Updated ClarifiedIntent
        """
        # Create enhanced aspects based on answers
        enhanced_aspects = list(clarified_intent.clarified_aspects)
        enhanced_concepts = list(clarified_intent.key_concepts)
        enhanced_questions = list(clarified_intent.key_questions)

        for answer in answers:
            question = self._all_questions.get(answer.question_id)
            if not question:
                continue

            # Add answer content to relevant fields
            answer_words = answer.answer_text.lower().split()

            # Extract new concepts from answers
            for word in answer_words:
                if len(word) > 4 and word not in enhanced_concepts:
                    enhanced_concepts.append(word)

            # Add aspect based on answer content
            if question.question_type == ClarificationQuestionType.PIVOT_INTENT:
                aspect = f"{question.related_pivot}: {answer.answer_text[:50]}"
                if aspect not in enhanced_aspects:
                    enhanced_aspects.append(aspect)

            # Add refined question based on answer
            if question.related_pivot:
                refined_question = (
                    f"How to implement {question.related_pivot} given: {answer.answer_text[:30]}?"
                )
                if refined_question not in enhanced_questions:
                    enhanced_questions.append(refined_question)

        # Update scope if domain answer was provided
        scope = clarified_intent.scope
        for answer in answers:
            question = self._all_questions.get(answer.question_id)
            if question and question.question_type == ClarificationQuestionType.SCOPE_BOUNDARY:
                if scope:
                    scope = ResearchScope(
                        domain=answer.answer_text,
                        time_period=scope.time_period,
                        geographical_focus=scope.geographical_focus,
                        constraints=scope.constraints,
                    )

        return ClarifiedIntent(
            original_query=clarified_intent.original_query,
            clarified_aspects=enhanced_aspects[:10],  # Limit aspects
            key_concepts=enhanced_concepts[:15],  # Limit concepts
            key_questions=enhanced_questions[:15],  # Limit questions
            scope=scope,
            dimensions=clarified_intent.dimensions,
        )

    def _get_unanswered_questions(self) -> List[ClarificationQuestion]:
        """Get all unanswered questions.

        Returns:
            List of unanswered questions
        """
        return [q for q in self._all_questions.values() if not q.answered]

    def _get_unanswered_critical(self) -> List[ClarificationQuestion]:
        """Get unanswered critical questions.

        Returns:
            List of unanswered critical questions
        """
        return [
            q
            for q in self._all_questions.values()
            if not q.answered and q.priority == ClarificationPriority.CRITICAL
        ]

    def _should_continue_loop(
        self,
        iteration: int,
        unanswered: List[ClarificationQuestion],
    ) -> bool:
        """Determine if the Q&A loop should continue.

        Args:
            iteration: Current iteration number
            unanswered: List of unanswered questions

        Returns:
            True if loop should continue
        """
        # Hard limit on iterations
        if iteration >= self.config.max_iterations:
            logger.debug(
                f"[IMP-RESEARCH-004] Stopping: max iterations ({self.config.max_iterations}) reached"
            )
            return False

        # No more questions to ask
        if not unanswered:
            logger.debug("[IMP-RESEARCH-004] Stopping: all questions answered")
            return False

        # Check for unanswered critical questions
        critical_unanswered = [
            q for q in unanswered if q.priority == ClarificationPriority.CRITICAL
        ]
        if self.config.require_critical_answers and critical_unanswered:
            logger.debug(
                f"[IMP-RESEARCH-004] Continuing: {len(critical_unanswered)} critical questions remain"
            )
            return True

        return len(unanswered) > 0

    def run_qa_loop(
        self,
        initial_query: Any,
        pivot_questions: Optional[List[str]] = None,
    ) -> QALoopResult:
        """Run the Q&A loop synchronously.

        IMP-RESEARCH-004: Executes the automated Q&A loop, generating questions
        and collecting answers until completion or max iterations.

        Args:
            initial_query: Initial research query (string or ResearchQuery)
            pivot_questions: Optional list of pivot question texts from
                           validate_pivot_completeness()

        Returns:
            QALoopResult with all iterations and final clarified intent
        """
        import time

        start_time = time.time()
        iterations: List[QALoopIteration] = []

        # Reset state
        self._all_questions.clear()
        self._all_answers.clear()
        self._question_counter = 0

        # Initial intent clarification
        loop = asyncio.new_event_loop()
        try:
            clarified_intent = loop.run_until_complete(
                self._clarification_agent.clarify_intent(initial_query)
            )
        finally:
            loop.close()

        # Generate initial questions from pivot validation
        missing_pivots = []
        if pivot_questions:
            # Extract pivot types from question texts
            for q_text in pivot_questions:
                for pivot_type, info in self.PIVOT_QUESTIONS.items():
                    if info["text"].lower() in q_text.lower():
                        missing_pivots.append(pivot_type)

        initial_questions = self.generate_questions_from_pivot_validation(missing_pivots)

        # Add questions from intent analysis
        initial_questions.extend(self.generate_questions_from_intent(clarified_intent))

        current_questions = initial_questions
        iteration = 0

        while self._should_continue_loop(iteration, current_questions):
            iteration += 1
            logger.info(f"[IMP-RESEARCH-004] Starting Q&A iteration {iteration}")

            # Collect answers
            answers = self._collect_answers_sync(current_questions)

            # Apply defaults if configured
            if self.config.use_defaults_if_unanswered:
                answers.extend(self._apply_default_answers(current_questions))

            # Calculate remaining questions
            remaining = self._get_unanswered_questions()

            # Create iteration result
            iter_result = QALoopIteration(
                iteration_number=iteration,
                questions_asked=current_questions,
                answers_received=answers,
                questions_remaining=remaining,
                should_continue=self._should_continue_loop(iteration, remaining),
            )
            iterations.append(iter_result)

            # Update clarified intent with answers
            if answers:
                clarified_intent = self._integrate_answers_into_intent(clarified_intent, answers)

            # Prepare for next iteration
            current_questions = remaining[: self.config.max_questions_per_iteration]

            if not iter_result.should_continue:
                break

        # Calculate final result
        total_time_ms = int((time.time() - start_time) * 1000)
        unanswered_critical = self._get_unanswered_critical()

        success = len(unanswered_critical) == 0 or not self.config.require_critical_answers

        result = QALoopResult(
            success=success,
            iterations_completed=len(iterations),
            total_questions_asked=len(self._all_questions),
            total_answers_received=len(self._all_answers),
            all_iterations=iterations,
            final_clarified_intent=clarified_intent,
            unanswered_critical=unanswered_critical,
            error_message=None if success else "Critical questions remain unanswered",
            completed_at=datetime.now(),
            total_time_ms=total_time_ms,
        )

        logger.info(
            f"[IMP-RESEARCH-004] Q&A loop completed: "
            f"{result.iterations_completed} iterations, "
            f"{result.total_answers_received}/{result.total_questions_asked} answered, "
            f"success={result.success}"
        )

        return result

    async def run_qa_loop_async(
        self,
        initial_query: Any,
        pivot_questions: Optional[List[str]] = None,
    ) -> QALoopResult:
        """Run the Q&A loop asynchronously.

        IMP-RESEARCH-004: Async version of run_qa_loop() that supports
        concurrent answer collection.

        Args:
            initial_query: Initial research query (string or ResearchQuery)
            pivot_questions: Optional list of pivot question texts from
                           validate_pivot_completeness()

        Returns:
            QALoopResult with all iterations and final clarified intent
        """
        import time

        start_time = time.time()
        iterations: List[QALoopIteration] = []

        # Reset state
        self._all_questions.clear()
        self._all_answers.clear()
        self._question_counter = 0

        # Initial intent clarification
        clarified_intent = await self._clarification_agent.clarify_intent(initial_query)

        # Generate initial questions from pivot validation
        missing_pivots = []
        if pivot_questions:
            # Extract pivot types from question texts
            for q_text in pivot_questions:
                for pivot_type, info in self.PIVOT_QUESTIONS.items():
                    if info["text"].lower() in q_text.lower():
                        missing_pivots.append(pivot_type)

        initial_questions = self.generate_questions_from_pivot_validation(missing_pivots)

        # Add questions from intent analysis
        initial_questions.extend(self.generate_questions_from_intent(clarified_intent))

        current_questions = initial_questions
        iteration = 0

        while self._should_continue_loop(iteration, current_questions):
            iteration += 1
            logger.info(f"[IMP-RESEARCH-004] Starting async Q&A iteration {iteration}")

            # Collect answers asynchronously
            answers = await self._collect_answers_async(current_questions)

            # Apply defaults if configured
            if self.config.use_defaults_if_unanswered:
                answers.extend(self._apply_default_answers(current_questions))

            # Calculate remaining questions
            remaining = self._get_unanswered_questions()

            # Create iteration result
            iter_result = QALoopIteration(
                iteration_number=iteration,
                questions_asked=current_questions,
                answers_received=answers,
                questions_remaining=remaining,
                should_continue=self._should_continue_loop(iteration, remaining),
            )
            iterations.append(iter_result)

            # Update clarified intent with answers
            if answers:
                clarified_intent = self._integrate_answers_into_intent(clarified_intent, answers)

            # Prepare for next iteration
            current_questions = remaining[: self.config.max_questions_per_iteration]

            if not iter_result.should_continue:
                break

        # Calculate final result
        total_time_ms = int((time.time() - start_time) * 1000)
        unanswered_critical = self._get_unanswered_critical()

        success = len(unanswered_critical) == 0 or not self.config.require_critical_answers

        result = QALoopResult(
            success=success,
            iterations_completed=len(iterations),
            total_questions_asked=len(self._all_questions),
            total_answers_received=len(self._all_answers),
            all_iterations=iterations,
            final_clarified_intent=clarified_intent,
            unanswered_critical=unanswered_critical,
            error_message=None if success else "Critical questions remain unanswered",
            completed_at=datetime.now(),
            total_time_ms=total_time_ms,
        )

        logger.info(
            f"[IMP-RESEARCH-004] Async Q&A loop completed: "
            f"{result.iterations_completed} iterations, "
            f"{result.total_answers_received}/{result.total_questions_asked} answered, "
            f"success={result.success}"
        )

        return result


__all__ = [
    "AnswerProvider",
    "AnswerProviderProtocol",
    "AsyncAnswerProvider",
    "ClarificationAnswer",
    "ClarificationPriority",
    "ClarificationQuestion",
    "ClarificationQuestionType",
    "ClarifiedIntent",
    "IntentClarificationAgent",
    "IntentClarificationQALoop",
    "QALoopConfig",
    "QALoopIteration",
    "QALoopResult",
    "ResearchScope",
]
