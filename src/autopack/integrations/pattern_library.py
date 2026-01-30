"""Pattern Library for cross-project learning.

Extracts and stores reusable patterns from build history
for application to new projects.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReusablePattern:
    """A reusable pattern extracted from build history."""

    pattern_id: str
    name: str
    category: str
    description: str
    success_rate: float = 0.0
    times_applied: int = 0
    context_requirements: List[str] = field(default_factory=list)
    code_template: Optional[str] = None
    extracted_from: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)


class PatternLibrary:
    """Stores and retrieves reusable patterns."""

    # Pattern categories for classification
    CATEGORY_AUTH = "authentication"
    CATEGORY_API = "api_integration"
    CATEGORY_DATABASE = "database"
    CATEGORY_TESTING = "testing"
    CATEGORY_DEPLOYMENT = "deployment"
    CATEGORY_ERROR_HANDLING = "error_handling"
    CATEGORY_GENERAL = "general"

    # Keywords for pattern detection
    PATTERN_KEYWORDS = {
        CATEGORY_AUTH: ["auth", "jwt", "token", "login", "oauth", "session", "password"],
        CATEGORY_API: ["api", "endpoint", "rest", "graphql", "webhook", "request"],
        CATEGORY_DATABASE: ["database", "db", "migration", "schema", "sql", "query"],
        CATEGORY_TESTING: ["test", "pytest", "unittest", "coverage", "mock", "fixture"],
        CATEGORY_DEPLOYMENT: [
            "deploy",
            "ci/cd",
            "docker",
            "kubernetes",
            "pipeline",
            "release",
        ],
        CATEGORY_ERROR_HANDLING: ["error", "exception", "retry", "fallback", "recovery"],
    }

    def __init__(self) -> None:
        self._patterns: Dict[str, ReusablePattern] = {}

    def _generate_pattern_id(self, name: str, category: str) -> str:
        """Generate a unique pattern ID."""
        content = f"{name}:{category}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def _classify_category(self, text: str) -> str:
        """Classify text into a pattern category based on keywords."""
        text_lower = text.lower()
        category_scores: Dict[str, int] = {}

        for category, keywords in self.PATTERN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                category_scores[category] = score

        if category_scores:
            return max(category_scores, key=category_scores.get)  # type: ignore[arg-type]
        return self.CATEGORY_GENERAL

    def extract_patterns_from_history(self, history_data: Dict[str, Any]) -> List[ReusablePattern]:
        """Extract patterns from build history.

        Analyzes build history data to identify successful patterns that can
        be reused in new projects. Patterns are extracted based on:
        - Successful phase completions
        - Recurring solutions to similar problems
        - Best practices identified across multiple phases

        Args:
            history_data: Dictionary containing build history with 'phases' key

        Returns:
            List of ReusablePattern objects extracted from the history
        """
        patterns: List[ReusablePattern] = []
        phases = history_data.get("phases", [])

        if not phases:
            logger.debug("No phases found in history data")
            return patterns

        # Group phases by category
        category_phases: Dict[str, List[Dict[str, Any]]] = {}
        for phase in phases:
            category = phase.get("category", "unknown")
            if category not in category_phases:
                category_phases[category] = []
            category_phases[category].append(phase)

        # Extract patterns from successful phases
        for category, cat_phases in category_phases.items():
            successful = [
                p
                for p in cat_phases
                if p.get("status") in ["SUCCESS", "success", "completed", "COMPLETED"]
            ]
            failed = [
                p for p in cat_phases if p.get("status") in ["FAILED", "failed", "error", "ERROR"]
            ]

            if not successful:
                continue

            # Calculate success rate
            total = len(cat_phases)
            success_rate = len(successful) / total if total > 0 else 0.0

            # Extract common elements from successful phases
            success_contents = [p.get("content", "") for p in successful]
            common_elements = self._extract_common_elements(success_contents)

            # Classify the pattern category based on content
            combined_content = " ".join(success_contents[:3])
            pattern_category = self._classify_category(combined_content)

            # Create pattern
            pattern_name = f"{category}_success_pattern"
            pattern_id = self._generate_pattern_id(pattern_name, pattern_category)

            pattern = ReusablePattern(
                pattern_id=pattern_id,
                name=pattern_name,
                category=pattern_category,
                description=f"Successful pattern for {category} tasks",
                success_rate=success_rate,
                times_applied=len(successful),
                context_requirements=common_elements.get("requirements", []),
                code_template=common_elements.get("template"),
                extracted_from=[
                    p.get("title", f"Phase {p.get('number', '?')}") for p in successful[:5]
                ],
            )

            patterns.append(pattern)
            self._patterns[pattern_id] = pattern

            # Extract failure avoidance patterns
            if failed:
                failure_contents = [p.get("content", "") for p in failed]
                failure_elements = self._extract_failure_patterns(failure_contents)

                if failure_elements:
                    avoidance_name = f"{category}_failure_avoidance"
                    avoidance_id = self._generate_pattern_id(avoidance_name, pattern_category)

                    avoidance_pattern = ReusablePattern(
                        pattern_id=avoidance_id,
                        name=avoidance_name,
                        category=pattern_category,
                        description=f"Avoid common failures in {category} tasks: {', '.join(failure_elements[:3])}",
                        success_rate=0.0,
                        times_applied=len(failed),
                        context_requirements=failure_elements,
                        extracted_from=[
                            p.get("title", f"Phase {p.get('number', '?')}") for p in failed[:5]
                        ],
                    )
                    patterns.append(avoidance_pattern)
                    self._patterns[avoidance_id] = avoidance_pattern

        # Extract cross-cutting patterns (best practices, lessons learned)
        cross_cutting = self._extract_cross_cutting_patterns(phases)
        patterns.extend(cross_cutting)

        logger.info(f"Extracted {len(patterns)} patterns from build history")
        return patterns

    def _extract_common_elements(self, contents: List[str]) -> Dict[str, Any]:
        """Extract common elements from successful phase contents."""
        result: Dict[str, Any] = {"requirements": [], "template": None}

        if not contents:
            return result

        # Extract common keywords and phrases
        all_words: Dict[str, int] = {}
        for content in contents:
            words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", content.lower())
            for word in words:
                if len(word) > 3:
                    all_words[word] = all_words.get(word, 0) + 1

        # Find words that appear in majority of contents
        threshold = len(contents) * 0.5
        common_words = [word for word, count in all_words.items() if count >= threshold]

        # Identify requirements from common words
        requirement_keywords = ["requires", "needs", "must", "should", "install", "setup"]
        for content in contents:
            for keyword in requirement_keywords:
                pattern = rf"{keyword}\s+[^.]+\."
                matches = re.findall(pattern, content.lower())
                result["requirements"].extend(matches[:2])

        result["requirements"] = list(set(result["requirements"]))[:5]

        # Look for code snippets
        code_pattern = r"```[\w]*\n(.*?)```"
        for content in contents:
            matches = re.findall(code_pattern, content, re.DOTALL)
            if matches:
                result["template"] = matches[0][:500]
                break

        return result

    def _extract_failure_patterns(self, contents: List[str]) -> List[str]:
        """Extract common failure reasons from failed phase contents."""
        failure_indicators = []

        failure_keywords = [
            "failed",
            "error",
            "issue",
            "problem",
            "conflict",
            "missing",
            "timeout",
            "exception",
        ]

        for content in contents:
            content_lower = content.lower()
            for keyword in failure_keywords:
                # Find sentences containing failure keywords
                pattern = rf"[^.]*{keyword}[^.]*\."
                matches = re.findall(pattern, content_lower)
                for match in matches[:2]:
                    if len(match) > 10 and len(match) < 200:
                        failure_indicators.append(match.strip())

        # Deduplicate and return top items
        return list(set(failure_indicators))[:5]

    def _extract_cross_cutting_patterns(
        self, phases: List[Dict[str, Any]]
    ) -> List[ReusablePattern]:
        """Extract cross-cutting patterns (best practices, lessons learned)."""
        patterns: List[ReusablePattern] = []

        all_lessons: List[str] = []
        all_best_practices: List[str] = []

        for phase in phases:
            content = phase.get("content", "")

            # Extract lessons learned
            lessons_match = re.findall(r"Lessons Learned:\n(.+?)(?=\n\n|##|$)", content, re.DOTALL)
            for lessons in lessons_match:
                for line in lessons.split("\n"):
                    if line.strip().startswith("-"):
                        all_lessons.append(line.strip()[1:].strip())

            # Extract best practices
            practices_match = re.findall(r"Best Practices:\n(.+?)(?=\n\n|##|$)", content, re.DOTALL)
            for practices in practices_match:
                for line in practices.split("\n"):
                    if line.strip().startswith("-"):
                        all_best_practices.append(line.strip()[1:].strip())

        # Create lessons learned pattern
        if all_lessons:
            unique_lessons = list(set(all_lessons))[:10]
            lesson_id = self._generate_pattern_id("lessons_learned", "general")
            lesson_pattern = ReusablePattern(
                pattern_id=lesson_id,
                name="lessons_learned",
                category=self.CATEGORY_GENERAL,
                description="Lessons learned across all phases",
                success_rate=1.0,
                times_applied=len(unique_lessons),
                context_requirements=unique_lessons,
            )
            patterns.append(lesson_pattern)
            self._patterns[lesson_id] = lesson_pattern

        # Create best practices pattern
        if all_best_practices:
            unique_practices = list(set(all_best_practices))[:10]
            practice_id = self._generate_pattern_id("best_practices", "general")
            practice_pattern = ReusablePattern(
                pattern_id=practice_id,
                name="best_practices",
                category=self.CATEGORY_GENERAL,
                description="Best practices identified across phases",
                success_rate=1.0,
                times_applied=len(unique_practices),
                context_requirements=unique_practices,
            )
            patterns.append(practice_pattern)
            self._patterns[practice_id] = practice_pattern

        return patterns

    def find_applicable_patterns(self, project_context: Dict[str, Any]) -> List[ReusablePattern]:
        """Find patterns applicable to a project context.

        Matches stored patterns against the given project context to find
        relevant patterns that can be applied.

        Args:
            project_context: Dictionary containing project information:
                - category: Task category (optional)
                - description: Task description (optional)
                - tech_stack: List of technologies (optional)
                - requirements: List of requirements (optional)

        Returns:
            List of applicable ReusablePattern objects, sorted by relevance
        """
        if not self._patterns:
            logger.debug("No patterns in library")
            return []

        applicable: List[tuple[float, ReusablePattern]] = []
        context_category = project_context.get("category", "")
        context_description = project_context.get("description", "")
        context_tech_stack = project_context.get("tech_stack", [])
        context_requirements = project_context.get("requirements", [])

        # Combine all context text for matching
        context_text = " ".join(
            [
                context_category,
                context_description,
                " ".join(context_tech_stack),
                " ".join(context_requirements),
            ]
        ).lower()

        for pattern in self._patterns.values():
            score = self._calculate_pattern_relevance(pattern, context_text, project_context)
            if score > 0:
                applicable.append((score, pattern))

        # Sort by score descending
        applicable.sort(key=lambda x: x[0], reverse=True)

        return [pattern for _, pattern in applicable]

    def _calculate_pattern_relevance(
        self,
        pattern: ReusablePattern,
        context_text: str,
        project_context: Dict[str, Any],
    ) -> float:
        """Calculate relevance score for a pattern given context."""
        score = 0.0

        # Category match
        pattern_category = pattern.category.lower()
        classified_category = self._classify_category(context_text)
        if pattern_category == classified_category:
            score += 0.4

        # Keyword matching from pattern description
        pattern_keywords = set(
            re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", pattern.description.lower())
        )
        context_keywords = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", context_text))

        matching_keywords = pattern_keywords & context_keywords
        if pattern_keywords:
            keyword_score = len(matching_keywords) / len(pattern_keywords)
            score += keyword_score * 0.3

        # Success rate bonus
        if pattern.success_rate > 0.7:
            score += 0.2

        # Times applied bonus (proven patterns)
        if pattern.times_applied >= 3:
            score += 0.1

        return score

    def add_pattern(self, pattern: ReusablePattern) -> None:
        """Add a pattern to the library.

        Args:
            pattern: Pattern to add
        """
        self._patterns[pattern.pattern_id] = pattern
        logger.debug(f"Added pattern: {pattern.name} ({pattern.pattern_id})")

    def get_pattern(self, pattern_id: str) -> Optional[ReusablePattern]:
        """Get a pattern by ID.

        Args:
            pattern_id: Pattern ID to look up

        Returns:
            Pattern if found, None otherwise
        """
        return self._patterns.get(pattern_id)

    def get_all_patterns(self) -> List[ReusablePattern]:
        """Get all patterns in the library.

        Returns:
            List of all patterns
        """
        return list(self._patterns.values())

    def get_patterns_by_category(self, category: str) -> List[ReusablePattern]:
        """Get patterns by category.

        Args:
            category: Category to filter by

        Returns:
            List of patterns in the category
        """
        return [p for p in self._patterns.values() if p.category == category]

    def record_pattern_application(self, pattern_id: str, success: bool) -> None:
        """Record that a pattern was applied.

        Updates the pattern's times_applied and success_rate.

        Args:
            pattern_id: ID of the pattern that was applied
            success: Whether the application was successful
        """
        pattern = self._patterns.get(pattern_id)
        if not pattern:
            logger.warning(f"Pattern not found: {pattern_id}")
            return

        old_times = pattern.times_applied
        old_rate = pattern.success_rate

        pattern.times_applied += 1
        if success:
            # Recalculate success rate
            successful_count = int(old_rate * old_times) + 1
            pattern.success_rate = successful_count / pattern.times_applied
        else:
            successful_count = int(old_rate * old_times)
            pattern.success_rate = successful_count / pattern.times_applied

        pattern.last_updated = datetime.now()
        logger.debug(
            f"Pattern {pattern_id} applied: success={success}, "
            f"new_rate={pattern.success_rate:.2f}"
        )
