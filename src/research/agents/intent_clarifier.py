"""Intent Clarification Agent.

This module provides the IntentClarifier class for refining and clarifying
research intents by extracting key elements, identifying topics, and
structuring research objectives.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ResearchIntent:
    """Structured representation of a research intent."""

    raw_input: str
    topics: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    constraints: Dict[str, str] = field(default_factory=dict)
    scope: str = "general"
    priority: str = "medium"

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "raw_input": self.raw_input,
            "topics": self.topics,
            "questions": self.questions,
            "keywords": self.keywords,
            "constraints": self.constraints,
            "scope": self.scope,
            "priority": self.priority,
        }


class IntentClarifier:
    """Agent for clarifying and structuring research intents."""

    def __init__(self):
        """Initialize the intent clarifier."""
        self.question_patterns = [
            r"\bhow\s+(?:do|does|can|to)\b",
            r"\bwhat\s+(?:is|are|does)\b",
            r"\bwhy\s+(?:is|are|does)\b",
            r"\bwhen\s+(?:is|are|does|should)\b",
            r"\bwhere\s+(?:is|are|can)\b",
            r"\bwhich\s+(?:is|are)\b",
            r"\bwho\s+(?:is|are)\b",
        ]

        self.constraint_patterns = {
            "language": r"\b(?:in|using|with)\s+(python|javascript|java|rust|go|c\+\+|typescript)\b",
            "framework": r"\b(?:using|with|in)\s+(react|vue|angular|django|flask|fastapi|express|spring)\b",
            "platform": r"\b(?:on|for)\s+(linux|windows|macos|android|ios|web)\b",
            "version": r"\bversion\s+([0-9]+(?:\.[0-9]+)*)\b",
        }

        self.scope_keywords = {
            "specific": ["specific", "particular", "exact", "precise"],
            "general": ["general", "overview", "introduction", "basics"],
            "comprehensive": ["comprehensive", "complete", "full", "detailed", "in-depth"],
            "quick": ["quick", "brief", "summary", "short"],
        }

        self.priority_keywords = {
            "high": ["urgent", "critical", "important", "asap", "priority"],
            "low": ["optional", "nice to have", "eventually", "when possible"],
        }

    def clarify(self, raw_input: str) -> ResearchIntent:
        """Clarify a raw research input into a structured intent.

        Args:
            raw_input: Raw research query or statement

        Returns:
            ResearchIntent: Structured research intent
        """
        intent = ResearchIntent(raw_input=raw_input)

        # Extract topics
        intent.topics = self._extract_topics(raw_input)

        # Extract questions
        intent.questions = self._extract_questions(raw_input)

        # Extract keywords
        intent.keywords = self._extract_keywords(raw_input)

        # Extract constraints
        intent.constraints = self._extract_constraints(raw_input)

        # Determine scope
        intent.scope = self._determine_scope(raw_input)

        # Determine priority
        intent.priority = self._determine_priority(raw_input)

        return intent

    def _extract_topics(self, text: str) -> List[str]:
        """Extract main topics from text.

        Args:
            text: Input text

        Returns:
            List of identified topics
        """
        topics = []

        # Extract noun phrases (simplified approach)
        # Look for capitalized words and technical terms
        words = text.split()
        for i, word in enumerate(words):
            # Capitalized words (potential proper nouns)
            if word[0].isupper() and len(word) > 2:
                topics.append(word.strip(".,!?;:"))

            # Technical terms with special characters
            if re.search(r"[A-Z][a-z]+[A-Z]", word):  # CamelCase
                topics.append(word.strip(".,!?;:"))

            # Hyphenated technical terms
            if "-" in word and len(word) > 4:
                topics.append(word.strip(".,!?;:"))

        # Remove duplicates while preserving order
        seen = set()
        unique_topics = []
        for topic in topics:
            if topic.lower() not in seen:
                seen.add(topic.lower())
                unique_topics.append(topic)

        return unique_topics[:10]  # Limit to top 10

    def _extract_questions(self, text: str) -> List[str]:
        """Extract questions from text.

        Args:
            text: Input text

        Returns:
            List of identified questions
        """
        questions = []

        # Split by sentence
        sentences = re.split(r"[.!?]+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check if sentence matches question patterns
            for pattern in self.question_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    questions.append(sentence)
                    break

            # Also check for explicit question marks
            if "?" in sentence:
                questions.append(sentence.replace("?", "").strip())

        return questions

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from text.

        Args:
            text: Input text

        Returns:
            List of keywords
        """
        # Remove common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "what",
            "which",
            "who",
            "when",
            "where",
            "why",
            "how",
        }

        # Extract words
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]*\b", text.lower())

        # Filter and count
        word_freq = {}
        for word in words:
            if word not in stop_words and len(word) > 2:
                word_freq[word] = word_freq.get(word, 0) + 1

        # Sort by frequency and return top keywords
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:15]]

    def _extract_constraints(self, text: str) -> Dict[str, str]:
        """Extract constraints from text.

        Args:
            text: Input text

        Returns:
            Dictionary of constraint type to value
        """
        constraints = {}

        for constraint_type, pattern in self.constraint_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                constraints[constraint_type] = match.group(1).lower()

        return constraints

    def _determine_scope(self, text: str) -> str:
        """Determine the scope of the research.

        Args:
            text: Input text

        Returns:
            Scope identifier
        """
        text_lower = text.lower()

        # Ensure more specific scopes win over generic/default matches.
        # E.g. "quick overview" should map to "quick", not "general".
        scope_priority = ["comprehensive", "specific", "quick", "general"]
        for scope in scope_priority:
            keywords = self.scope_keywords.get(scope, [])
            for keyword in keywords:
                if keyword in text_lower:
                    return scope

        return "general"

    def _determine_priority(self, text: str) -> str:
        """Determine the priority of the research.

        Args:
            text: Input text

        Returns:
            Priority level
        """
        text_lower = text.lower()

        for priority, keywords in self.priority_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return priority

        return "medium"

    def refine_intent(self, intent: ResearchIntent, feedback: Dict) -> ResearchIntent:
        """Refine an existing intent based on feedback.

        Args:
            intent: Original research intent
            feedback: Dictionary containing refinement feedback

        Returns:
            Refined research intent
        """
        if "add_topics" in feedback:
            intent.topics.extend(feedback["add_topics"])

        if "remove_topics" in feedback:
            intent.topics = [t for t in intent.topics if t not in feedback["remove_topics"]]

        if "add_keywords" in feedback:
            intent.keywords.extend(feedback["add_keywords"])

        if "scope" in feedback:
            intent.scope = feedback["scope"]

        if "priority" in feedback:
            intent.priority = feedback["priority"]

        if "constraints" in feedback:
            intent.constraints.update(feedback["constraints"])

        return intent
