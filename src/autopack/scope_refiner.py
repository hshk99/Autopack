"""Progressive Deterministic Scope Refinement.

Iteratively improves scope using static signals before optional LLM critique.

Architecture:
- Iteration 1 (Deterministic): Use static signals
  - Co-location: Same directory as existing scope files
  - Test patterns: If scope has foo.py, suggest test_foo.py
  - Import graph: Use ImportGraphAnalyzer from existing codebase
  - Name similarity: Fuzzy match on file names
- Iteration 2 (Optional LLM Critique): Advisory only, never auto-add
- Confidence scoring: Each signal contributes to earned confidence
- Threshold-based suggestions: Only suggest files above confidence threshold

Usage:
    refiner = ScopeRefiner(
        repo_root=Path("."),
        import_graph_analyzer=analyzer
    )

    # Refine scope with deterministic signals
    suggestions = refiner.refine_scope(
        current_scope=["src/auth/login.py"],
        phase_description="Implement OAuth2 authentication",
        confidence_threshold=0.6
    )

    # Optional: Get LLM critique (advisory only)
    critique = refiner.get_llm_critique(
        current_scope=["src/auth/login.py"],
        suggestions=suggestions,
        phase_description="Implement OAuth2 authentication"
    )
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScopeSuggestion:
    """Suggested file to add to scope."""

    file_path: Path
    confidence: float
    reasons: List[str]
    signal_scores: Dict[str, float]


@dataclass
class ScopeRefinementResult:
    """Result of scope refinement."""

    suggestions: List[ScopeSuggestion]
    total_signals_checked: int
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int


class ScopeRefiner:
    """Progressive deterministic scope refinement."""

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.75
    MEDIUM_CONFIDENCE = 0.50
    LOW_CONFIDENCE = 0.30

    # Signal weights (must sum to 1.0)
    WEIGHT_CO_LOCATION = 0.30
    WEIGHT_TEST_PATTERN = 0.25
    WEIGHT_IMPORT_GRAPH = 0.30
    WEIGHT_NAME_SIMILARITY = 0.15

    # Test file patterns
    TEST_PATTERNS = [
        (r"^(.+)\.py$", r"test_\1.py"),
        (r"^(.+)\.py$", r"\1_test.py"),
        (r"^(.+)\.py$", r"tests/test_\1.py"),
        (r"^(.+)\.py$", r"tests/\1_test.py"),
    ]

    def __init__(
        self,
        repo_root: Path,
        import_graph_analyzer: Optional[object] = None,
        max_suggestions: int = 10,
    ):
        """Initialize scope refiner.

        Args:
            repo_root: Repository root path
            import_graph_analyzer: Optional ImportGraphAnalyzer instance
            max_suggestions: Maximum number of suggestions to return
        """
        self.repo_root = repo_root
        self.import_graph_analyzer = import_graph_analyzer
        self.max_suggestions = max_suggestions

    def refine_scope(
        self,
        current_scope: List[str],
        phase_description: str,
        confidence_threshold: float = 0.5,
    ) -> ScopeRefinementResult:
        """Refine scope using deterministic signals.

        Args:
            current_scope: Current scope file paths (relative to repo root)
            phase_description: Phase description for context
            confidence_threshold: Minimum confidence to include suggestion

        Returns:
            ScopeRefinementResult with suggestions
        """
        # Convert to Path objects
        scope_paths = [self.repo_root / p for p in current_scope]

        # Collect candidate files from all signals
        candidates: Dict[Path, Dict[str, float]] = {}

        # Signal 1: Co-location (same directory)
        self._add_co_location_candidates(scope_paths, candidates)

        # Signal 2: Test patterns
        self._add_test_pattern_candidates(scope_paths, candidates)

        # Signal 3: Import graph (if available)
        if self.import_graph_analyzer:
            self._add_import_graph_candidates(scope_paths, candidates)

        # Signal 4: Name similarity
        self._add_name_similarity_candidates(scope_paths, candidates, phase_description)

        # Compute confidence scores
        suggestions = self._compute_suggestions(candidates, scope_paths, confidence_threshold)

        # Count by confidence level
        high_count = sum(1 for s in suggestions if s.confidence >= self.HIGH_CONFIDENCE)
        medium_count = sum(
            1 for s in suggestions if self.MEDIUM_CONFIDENCE <= s.confidence < self.HIGH_CONFIDENCE
        )
        low_count = sum(
            1 for s in suggestions if self.LOW_CONFIDENCE <= s.confidence < self.MEDIUM_CONFIDENCE
        )

        return ScopeRefinementResult(
            suggestions=suggestions[: self.max_suggestions],
            total_signals_checked=len(candidates),
            high_confidence_count=high_count,
            medium_confidence_count=medium_count,
            low_confidence_count=low_count,
        )

    def _add_co_location_candidates(
        self,
        scope_paths: List[Path],
        candidates: Dict[Path, Dict[str, float]],
    ) -> None:
        """Add candidates from same directory as scope files.

        Args:
            scope_paths: Current scope paths
            candidates: Candidate dict to update
        """
        for scope_file in scope_paths:
            if not scope_file.exists():
                continue

            parent_dir = scope_file.parent
            if not parent_dir.exists():
                continue

            # Find all Python files in same directory
            for sibling in parent_dir.glob("*.py"):
                if sibling in scope_paths:
                    continue

                if sibling not in candidates:
                    candidates[sibling] = {}
                candidates[sibling]["co_location"] = self.WEIGHT_CO_LOCATION

    def _add_test_pattern_candidates(
        self,
        scope_paths: List[Path],
        candidates: Dict[Path, Dict[str, float]],
    ) -> None:
        """Add candidates matching test file patterns.

        Args:
            scope_paths: Current scope paths
            candidates: Candidate dict to update
        """
        for scope_file in scope_paths:
            if not scope_file.exists():
                continue

            # Try each test pattern
            for source_pattern, test_pattern in self.TEST_PATTERNS:
                match = re.match(source_pattern, scope_file.name)
                if not match:
                    continue

                # Generate test file name
                test_name = re.sub(source_pattern, test_pattern, scope_file.name)

                # Check if test file exists
                test_file = scope_file.parent / test_name
                if test_file.exists() and test_file not in scope_paths:
                    if test_file not in candidates:
                        candidates[test_file] = {}
                    candidates[test_file]["test_pattern"] = self.WEIGHT_TEST_PATTERN

                # Also check tests/ subdirectory
                tests_dir = scope_file.parent / "tests"
                if tests_dir.exists():
                    test_file = tests_dir / test_name
                    if test_file.exists() and test_file not in scope_paths:
                        if test_file not in candidates:
                            candidates[test_file] = {}
                        candidates[test_file]["test_pattern"] = self.WEIGHT_TEST_PATTERN

    def _add_import_graph_candidates(
        self,
        scope_paths: List[Path],
        candidates: Dict[Path, Dict[str, float]],
    ) -> None:
        """Add candidates from import graph analysis.

        Args:
            scope_paths: Current scope paths
            candidates: Candidate dict to update
        """
        if not self.import_graph_analyzer:
            return

        # Get imports for each scope file
        for scope_file in scope_paths:
            if not scope_file.exists():
                continue

            try:
                # Use import graph analyzer to find dependencies
                # This assumes the analyzer has a method to get imports
                # Adjust based on actual ImportGraphAnalyzer API
                imports = self._get_imports_for_file(scope_file)

                for imported_file in imports:
                    if imported_file in scope_paths:
                        continue

                    if imported_file not in candidates:
                        candidates[imported_file] = {}
                    candidates[imported_file]["import_graph"] = self.WEIGHT_IMPORT_GRAPH

            except Exception as e:
                logger.warning(f"Failed to analyze imports for {scope_file}: {e}")

    def _get_imports_for_file(self, file_path: Path) -> List[Path]:
        """Get imported files for a given file.

        Args:
            file_path: File to analyze

        Returns:
            List of imported file paths
        """
        # This is a placeholder - actual implementation depends on
        # ImportGraphAnalyzer API from Phase E2
        # For now, return empty list
        return []

    def _add_name_similarity_candidates(
        self,
        scope_paths: List[Path],
        candidates: Dict[Path, Dict[str, float]],
        phase_description: str,
    ) -> None:
        """Add candidates based on name similarity.

        Args:
            scope_paths: Current scope paths
            candidates: Candidate dict to update
            phase_description: Phase description for keyword extraction
        """
        # Extract keywords from phase description
        keywords = self._extract_keywords(phase_description)

        # Find all Python files in repo
        for py_file in self.repo_root.rglob("*.py"):
            if py_file in scope_paths:
                continue

            # Check if file name contains any keywords
            file_name_lower = py_file.stem.lower()
            matches = sum(1 for kw in keywords if kw in file_name_lower)

            if matches > 0:
                similarity_score = min(matches / len(keywords), 1.0) * self.WEIGHT_NAME_SIMILARITY

                if py_file not in candidates:
                    candidates[py_file] = {}
                candidates[py_file]["name_similarity"] = similarity_score

    def _extract_keywords(self, description: str) -> List[str]:
        """Extract keywords from phase description.

        Args:
            description: Phase description

        Returns:
            List of lowercase keywords
        """
        # Simple keyword extraction: split on whitespace and punctuation
        words = re.findall(r"\b\w+\b", description.lower())

        # Filter out common stop words
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
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "should",
            "could",
            "may",
            "might",
            "must",
            "can",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "they",
            "them",
            "their",
        }

        return [w for w in words if w not in stop_words and len(w) > 2]

    def _compute_suggestions(
        self,
        candidates: Dict[Path, Dict[str, float]],
        scope_paths: List[Path],
        confidence_threshold: float,
    ) -> List[ScopeSuggestion]:
        """Compute final suggestions with confidence scores.

        Args:
            candidates: Candidate files with signal scores
            scope_paths: Current scope paths
            confidence_threshold: Minimum confidence threshold

        Returns:
            List of ScopeSuggestion objects, sorted by confidence
        """
        suggestions = []

        for file_path, signal_scores in candidates.items():
            # Compute total confidence (sum of signal scores)
            confidence = sum(signal_scores.values())

            # Skip if below threshold
            if confidence < confidence_threshold:
                continue

            # Build reasons list
            reasons = []
            if "co_location" in signal_scores:
                reasons.append("Same directory as scope files")
            if "test_pattern" in signal_scores:
                reasons.append("Matches test file pattern")
            if "import_graph" in signal_scores:
                reasons.append("Imported by scope files")
            if "name_similarity" in signal_scores:
                reasons.append("Name similar to phase description")

            suggestions.append(
                ScopeSuggestion(
                    file_path=file_path.relative_to(self.repo_root),
                    confidence=confidence,
                    reasons=reasons,
                    signal_scores=signal_scores,
                )
            )

        # Sort by confidence (descending)
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        return suggestions

    def get_llm_critique(
        self,
        current_scope: List[str],
        suggestions: List[ScopeSuggestion],
        phase_description: str,
    ) -> Optional[str]:
        """Get optional LLM critique of scope (advisory only).

        This is Iteration 2 - LLM provides advisory feedback but never
        auto-adds files to scope. Human must review and approve.

        Args:
            current_scope: Current scope file paths
            suggestions: Deterministic suggestions from Iteration 1
            phase_description: Phase description

        Returns:
            LLM critique text (advisory only), or None if LLM unavailable
        """
        # Placeholder for future LLM integration
        # This would call an LLM service to provide advisory feedback
        # For now, return None to indicate LLM critique not implemented
        logger.info("[ScopeRefiner] LLM critique not yet implemented (advisory only)")
        return None

    def format_suggestions(self, result: ScopeRefinementResult) -> str:
        """Format suggestions for display.

        Args:
            result: Scope refinement result

        Returns:
            Formatted string
        """
        lines = [
            "Scope Refinement Suggestions:",
            f"Total signals checked: {result.total_signals_checked}",
            f"High confidence: {result.high_confidence_count}",
            f"Medium confidence: {result.medium_confidence_count}",
            f"Low confidence: {result.low_confidence_count}",
            "",
        ]

        if not result.suggestions:
            lines.append("No suggestions above confidence threshold.")
            return "\n".join(lines)

        lines.append("Suggested files:")
        for i, suggestion in enumerate(result.suggestions, 1):
            confidence_pct = suggestion.confidence * 100
            lines.append(f"\n{i}. {suggestion.file_path} (confidence: {confidence_pct:.1f}%)")
            lines.append(f"   Reasons: {', '.join(suggestion.reasons)}")
            lines.append(f"   Signal scores: {suggestion.signal_scores}")

        return "\n".join(lines)
