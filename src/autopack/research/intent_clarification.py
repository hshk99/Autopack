"""Research Intent Clarification - Clarify vague research queries.

This module provides functionality to clarify vague research queries by
extracting key concepts, generating sub-questions, and defining scope.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional


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
            constraints=[]
        )

        return ClarifiedIntent(
            original_query=query_str,
            clarified_aspects=clarified_aspects,
            key_concepts=key_concepts,
            key_questions=key_questions,
            scope=scope,
            dimensions=dimensions
        )

    def _extract_concepts(self, query: str) -> List[str]:
        """Extract key concepts from query.

        Args:
            query: Query string

        Returns:
            List of key concepts
        """
        # Simple heuristic: extract important words (> 3 chars, not common words)
        stop_words = {"the", "and", "for", "are", "what", "how", "why", "when", "where",
                     "who", "which", "that", "this", "with", "from", "about", "tell"}
        words = query.lower().split()
        concepts = [w.strip("?.,!") for w in words
                   if len(w) > 3 and w.lower() not in stop_words]
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
        year_match = re.search(r'\b(20\d{2})\b', query)
        if year_match:
            return year_match.group(1)

        # Look for relative time
        if "latest" in query.lower() or "recent" in query.lower():
            return "recent"
        if "current" in query.lower():
            return "current"

        return ""


__all__ = [
    "ClarifiedIntent",
    "IntentClarificationAgent",
    "ResearchScope",
]
