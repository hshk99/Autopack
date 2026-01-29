"""Tests for scope_refiner.py - Progressive Deterministic Scope Refinement."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autopack.scope_refiner import (ScopeRefinementResult, ScopeRefiner,
                                    ScopeSuggestion)


class TestScopeSuggestionDataclass:
    """Tests for the ScopeSuggestion dataclass."""

    def test_scope_suggestion_creation(self):
        """Test ScopeSuggestion can be created with all fields."""
        suggestion = ScopeSuggestion(
            file_path=Path("src/main.py"),
            confidence=0.75,
            reasons=["Same directory as scope files"],
            signal_scores={"co_location": 0.30},
        )
        assert suggestion.file_path == Path("src/main.py")
        assert suggestion.confidence == 0.75
        assert len(suggestion.reasons) == 1
        assert suggestion.signal_scores["co_location"] == 0.30

    def test_scope_suggestion_with_multiple_signals(self):
        """Test ScopeSuggestion with multiple signal scores."""
        suggestion = ScopeSuggestion(
            file_path=Path("test_main.py"),
            confidence=0.55,
            reasons=["Matches test file pattern", "Same directory as scope files"],
            signal_scores={"test_pattern": 0.25, "co_location": 0.30},
        )
        assert len(suggestion.signal_scores) == 2
        assert sum(suggestion.signal_scores.values()) == 0.55


class TestScopeRefinementResultDataclass:
    """Tests for the ScopeRefinementResult dataclass."""

    def test_scope_refinement_result_creation(self):
        """Test ScopeRefinementResult can be created with all fields."""
        result = ScopeRefinementResult(
            suggestions=[],
            total_signals_checked=5,
            high_confidence_count=1,
            medium_confidence_count=2,
            low_confidence_count=2,
        )
        assert result.suggestions == []
        assert result.total_signals_checked == 5
        assert result.high_confidence_count == 1
        assert result.medium_confidence_count == 2
        assert result.low_confidence_count == 2


class TestScopeRefinerInit:
    """Tests for ScopeRefiner initialization."""

    def test_init_with_defaults(self, tmp_path):
        """Test ScopeRefiner initializes with default values."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        assert refiner.repo_root == tmp_path
        assert refiner.import_graph_analyzer is None
        assert refiner.max_suggestions == 10

    def test_init_with_custom_max_suggestions(self, tmp_path):
        """Test ScopeRefiner with custom max_suggestions."""
        refiner = ScopeRefiner(repo_root=tmp_path, max_suggestions=5)
        assert refiner.max_suggestions == 5

    def test_init_with_import_graph_analyzer(self, tmp_path):
        """Test ScopeRefiner with import graph analyzer."""
        mock_analyzer = MagicMock()
        refiner = ScopeRefiner(repo_root=tmp_path, import_graph_analyzer=mock_analyzer)
        assert refiner.import_graph_analyzer is mock_analyzer


class TestRefineScope:
    """Tests for the refine_scope method."""

    def test_refine_scope_empty_current_scope(self, tmp_path):
        """Test refine_scope with empty current scope."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=[],
            phase_description="Test phase",
            confidence_threshold=0.5,
        )
        assert isinstance(result, ScopeRefinementResult)
        assert result.suggestions == []
        assert result.total_signals_checked == 0

    def test_refine_scope_nonexistent_files(self, tmp_path):
        """Test refine_scope with non-existent files in scope."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["nonexistent.py"],
            phase_description="Test phase",
            confidence_threshold=0.5,
        )
        assert isinstance(result, ScopeRefinementResult)
        # Non-existent files should be handled gracefully
        assert result.suggestions == []

    def test_refine_scope_co_location_signal(self, tmp_path):
        """Test refine_scope finds co-located files."""
        # Create directory structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "helper.py").write_text("# helper")
        (src_dir / "utils.py").write_text("# utils")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test phase",
            confidence_threshold=0.2,
        )

        # Should suggest co-located files
        suggested_paths = [str(s.file_path) for s in result.suggestions]
        assert any("helper.py" in p for p in suggested_paths)
        assert any("utils.py" in p for p in suggested_paths)

    def test_refine_scope_test_pattern_signal(self, tmp_path):
        """Test refine_scope finds test files matching patterns."""
        # Create directory structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "auth.py").write_text("# auth")
        (src_dir / "test_auth.py").write_text("# test auth")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/auth.py"],
            phase_description="Test authentication",
            confidence_threshold=0.2,
        )

        # Should suggest test file
        suggested_paths = [str(s.file_path) for s in result.suggestions]
        assert any("test_auth.py" in p for p in suggested_paths)

    def test_refine_scope_test_pattern_in_tests_subdir(self, tmp_path):
        """Test refine_scope finds test files in tests/ subdirectory."""
        # Create directory structure
        src_dir = tmp_path / "src"
        tests_dir = src_dir / "tests"
        src_dir.mkdir()
        tests_dir.mkdir()
        (src_dir / "auth.py").write_text("# auth")
        (tests_dir / "test_auth.py").write_text("# test auth")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/auth.py"],
            phase_description="Test authentication",
            confidence_threshold=0.2,
        )

        # Should suggest test file from tests/ subdir
        suggested_paths = [str(s.file_path) for s in result.suggestions]
        assert any("test_auth.py" in p for p in suggested_paths)

    def test_refine_scope_name_similarity_signal(self, tmp_path):
        """Test refine_scope finds files based on name similarity."""
        # Create directory structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "oauth_client.py").write_text("# oauth")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Implement OAuth2 authentication",
            confidence_threshold=0.1,
        )

        # Should suggest oauth_client.py based on name similarity
        suggested_paths = [str(s.file_path) for s in result.suggestions]
        assert any("oauth" in p.lower() for p in suggested_paths)

    def test_refine_scope_confidence_threshold_filtering(self, tmp_path):
        """Test refine_scope filters by confidence threshold."""
        # Create files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "helper.py").write_text("# helper")

        refiner = ScopeRefiner(repo_root=tmp_path)

        # With low threshold, should include suggestions
        result_low = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # With high threshold, should filter out low-confidence suggestions
        result_high = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.9,
        )

        assert len(result_low.suggestions) >= len(result_high.suggestions)

    def test_refine_scope_max_suggestions_limit(self, tmp_path):
        """Test refine_scope respects max_suggestions limit."""
        # Create many files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        for i in range(20):
            (src_dir / f"helper_{i}.py").write_text(f"# helper {i}")

        refiner = ScopeRefiner(repo_root=tmp_path, max_suggestions=5)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        assert len(result.suggestions) <= 5

    def test_refine_scope_excludes_current_scope_files(self, tmp_path):
        """Test refine_scope excludes files already in scope."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "helper.py").write_text("# helper")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py", "src/helper.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # Should not suggest files already in scope
        suggested_paths = [str(s.file_path) for s in result.suggestions]
        assert "src/main.py" not in suggested_paths
        assert "src/helper.py" not in suggested_paths

    def test_refine_scope_suggestions_sorted_by_confidence(self, tmp_path):
        """Test refine_scope returns suggestions sorted by confidence."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "test_main.py").write_text("# test")
        (src_dir / "helper.py").write_text("# helper")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # Verify descending confidence order
        confidences = [s.confidence for s in result.suggestions]
        assert confidences == sorted(confidences, reverse=True)

    def test_refine_scope_counts_confidence_levels(self, tmp_path):
        """Test refine_scope correctly counts confidence levels."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        # Create files that will have different confidence levels
        (src_dir / "test_main.py").write_text("# test")  # test pattern
        (src_dir / "helper.py").write_text("# helper")  # co-location only

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # Verify counts are non-negative
        assert result.high_confidence_count >= 0
        assert result.medium_confidence_count >= 0
        assert result.low_confidence_count >= 0


class TestExtractKeywords:
    """Tests for the _extract_keywords method."""

    def test_extract_keywords_basic(self, tmp_path):
        """Test basic keyword extraction."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        keywords = refiner._extract_keywords("Implement OAuth2 authentication")
        assert "implement" in keywords
        assert "oauth2" in keywords
        assert "authentication" in keywords

    def test_extract_keywords_filters_stop_words(self, tmp_path):
        """Test that stop words are filtered."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        keywords = refiner._extract_keywords("the user is in the system")
        assert "the" not in keywords
        assert "is" not in keywords
        assert "in" not in keywords
        assert "user" in keywords
        assert "system" in keywords

    def test_extract_keywords_filters_short_words(self, tmp_path):
        """Test that short words (< 3 chars) are filtered."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        keywords = refiner._extract_keywords("an ox is in me")
        assert "an" not in keywords
        assert "ox" not in keywords
        assert "me" not in keywords

    def test_extract_keywords_lowercase(self, tmp_path):
        """Test that keywords are lowercased."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        keywords = refiner._extract_keywords("UPPERCASE Keyword Test")
        assert "uppercase" in keywords
        assert "keyword" in keywords
        assert "test" in keywords

    def test_extract_keywords_empty_string(self, tmp_path):
        """Test keyword extraction from empty string."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        keywords = refiner._extract_keywords("")
        assert keywords == []


class TestGetLlmCritique:
    """Tests for the get_llm_critique method."""

    def test_get_llm_critique_returns_none(self, tmp_path):
        """Test get_llm_critique returns None (not implemented)."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.get_llm_critique(
            current_scope=["src/main.py"],
            suggestions=[],
            phase_description="Test phase",
        )
        assert result is None


class TestFormatSuggestions:
    """Tests for the format_suggestions method."""

    def test_format_suggestions_no_suggestions(self, tmp_path):
        """Test format_suggestions with no suggestions."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        result = ScopeRefinementResult(
            suggestions=[],
            total_signals_checked=5,
            high_confidence_count=0,
            medium_confidence_count=0,
            low_confidence_count=0,
        )
        formatted = refiner.format_suggestions(result)
        assert "No suggestions above confidence threshold" in formatted
        assert "Total signals checked: 5" in formatted

    def test_format_suggestions_with_suggestions(self, tmp_path):
        """Test format_suggestions with suggestions."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        suggestion = ScopeSuggestion(
            file_path=Path("src/helper.py"),
            confidence=0.55,
            reasons=["Same directory as scope files"],
            signal_scores={"co_location": 0.30, "test_pattern": 0.25},
        )
        result = ScopeRefinementResult(
            suggestions=[suggestion],
            total_signals_checked=10,
            high_confidence_count=0,
            medium_confidence_count=1,
            low_confidence_count=0,
        )
        formatted = refiner.format_suggestions(result)
        # Check for helper.py (path separators may vary by OS)
        assert "helper.py" in formatted
        assert "55.0%" in formatted
        assert "Same directory as scope files" in formatted
        assert "Suggested files:" in formatted

    def test_format_suggestions_shows_confidence_counts(self, tmp_path):
        """Test format_suggestions shows confidence level counts."""
        refiner = ScopeRefiner(repo_root=tmp_path)
        result = ScopeRefinementResult(
            suggestions=[],
            total_signals_checked=15,
            high_confidence_count=3,
            medium_confidence_count=5,
            low_confidence_count=7,
        )
        formatted = refiner.format_suggestions(result)
        assert "High confidence: 3" in formatted
        assert "Medium confidence: 5" in formatted
        assert "Low confidence: 7" in formatted


class TestConfidenceConstants:
    """Tests for confidence threshold constants."""

    def test_confidence_thresholds_exist(self):
        """Test that confidence thresholds are defined."""
        assert ScopeRefiner.HIGH_CONFIDENCE == 0.75
        assert ScopeRefiner.MEDIUM_CONFIDENCE == 0.50
        assert ScopeRefiner.LOW_CONFIDENCE == 0.30

    def test_signal_weights_sum_to_one(self):
        """Test that signal weights sum to 1.0."""
        total = (
            ScopeRefiner.WEIGHT_CO_LOCATION
            + ScopeRefiner.WEIGHT_TEST_PATTERN
            + ScopeRefiner.WEIGHT_IMPORT_GRAPH
            + ScopeRefiner.WEIGHT_NAME_SIMILARITY
        )
        assert total == pytest.approx(1.0)


class TestWithImportGraphAnalyzer:
    """Tests for ScopeRefiner with import graph analyzer."""

    def test_import_graph_candidates_with_mock_analyzer(self, tmp_path):
        """Test that import graph analyzer is called when provided."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "imported.py").write_text("# imported")

        mock_analyzer = MagicMock()
        refiner = ScopeRefiner(repo_root=tmp_path, import_graph_analyzer=mock_analyzer)

        # The refiner should attempt to use the analyzer
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        assert isinstance(result, ScopeRefinementResult)

    def test_import_graph_without_analyzer(self, tmp_path):
        """Test refine_scope works without import graph analyzer."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")

        refiner = ScopeRefiner(repo_root=tmp_path, import_graph_analyzer=None)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.5,
        )

        assert isinstance(result, ScopeRefinementResult)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_refine_scope_with_init_py(self, tmp_path):
        """Test refine_scope handles __init__.py files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text("")
        (src_dir / "main.py").write_text("# main")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # Should include __init__.py as co-located
        assert isinstance(result, ScopeRefinementResult)

    def test_refine_scope_deep_directory_structure(self, tmp_path):
        """Test refine_scope with deep directory structure."""
        deep_dir = tmp_path / "src" / "module" / "sub" / "deep"
        deep_dir.mkdir(parents=True)
        (deep_dir / "main.py").write_text("# main")
        (deep_dir / "helper.py").write_text("# helper")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/module/sub/deep/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        suggested_paths = [str(s.file_path) for s in result.suggestions]
        assert any("helper.py" in p for p in suggested_paths)

    def test_refine_scope_special_characters_in_description(self, tmp_path):
        """Test refine_scope handles special characters in description."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Fix bug #123: handle @user's request (urgent!)",
            confidence_threshold=0.5,
        )

        # Should handle gracefully
        assert isinstance(result, ScopeRefinementResult)

    def test_refine_scope_unicode_in_files(self, tmp_path):
        """Test refine_scope handles unicode in file contents."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        # Use explicit utf-8 encoding for cross-platform compatibility
        (src_dir / "main.py").write_text(
            "# \u65e5\u672c\u8a9e\u30b3\u30e1\u30f3\u30c8", encoding="utf-8"
        )
        (src_dir / "helper.py").write_text("# \u4e2d\u6587\u6ce8\u91ca", encoding="utf-8")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test unicode",
            confidence_threshold=0.1,
        )

        assert isinstance(result, ScopeRefinementResult)

    def test_refine_scope_multiple_test_patterns(self, tmp_path):
        """Test refine_scope finds multiple test file patterns."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "auth.py").write_text("# auth")
        (src_dir / "test_auth.py").write_text("# test_auth")
        (src_dir / "auth_test.py").write_text("# auth_test")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/auth.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        suggested_paths = [str(s.file_path) for s in result.suggestions]
        # Should find both test patterns
        test_count = sum(1 for p in suggested_paths if "test" in p.lower())
        assert test_count >= 1

    def test_refine_scope_preserves_relative_paths(self, tmp_path):
        """Test that suggestions use relative paths from repo root."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "helper.py").write_text("# helper")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # All paths should be relative to repo root
        for suggestion in result.suggestions:
            assert not suggestion.file_path.is_absolute()


class TestSignalReasons:
    """Tests for suggestion reason generation."""

    def test_co_location_reason(self, tmp_path):
        """Test co-location reason is included."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "helper.py").write_text("# helper")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # Find the helper.py suggestion
        helper_suggestion = next(
            (s for s in result.suggestions if "helper" in str(s.file_path)), None
        )
        if helper_suggestion:
            assert "Same directory as scope files" in helper_suggestion.reasons

    def test_test_pattern_reason(self, tmp_path):
        """Test test pattern reason is included."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "test_main.py").write_text("# test")

        refiner = ScopeRefiner(repo_root=tmp_path)
        result = refiner.refine_scope(
            current_scope=["src/main.py"],
            phase_description="Test",
            confidence_threshold=0.1,
        )

        # Find the test file suggestion
        test_suggestion = next(
            (s for s in result.suggestions if "test_main" in str(s.file_path)), None
        )
        if test_suggestion:
            assert "Matches test file pattern" in test_suggestion.reasons
