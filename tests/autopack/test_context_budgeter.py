"""Tests for context_budgeter with embedding cache."""

from unittest.mock import patch
from autopack.context_budgeter import (
    select_files_for_context,
    reset_embedding_cache,
    get_embedding_stats,
    _lexical_score,
)


class TestContextBudgeter:
    """Test suite for context budgeter functionality."""

    def setup_method(self):
        """Reset cache before each test."""
        reset_embedding_cache()

    def test_lexical_fallback_when_embeddings_disabled(self):
        """Test that lexical ranking is used when embeddings are disabled."""
        files = {
            "src/auth.py": "def authenticate(user): pass",
            "src/db.py": "def connect(): pass",
            "src/user.py": "class User: pass",
        }

        result = select_files_for_context(
            files=files,
            scope_metadata=None,
            deliverables=None,
            query="authentication user login",
            budget_tokens=1000,
            semantic=False,
        )

        assert result.mode == "lexical"
        assert "src/auth.py" in result.kept
        assert "src/user.py" in result.kept

    def test_lexical_score_path_boost(self):
        """Test that path matches get higher scores than content matches."""
        score_path = _lexical_score("auth", "src/auth.py", "def connect(): pass")
        score_content = _lexical_score("auth", "src/db.py", "def authenticate(): pass")

        # Path match should score higher due to 3x weight
        assert score_path > score_content

    @patch("autopack.context_budgeter.semantic_embeddings_enabled")
    @patch("autopack.context_budgeter.sync_embed_texts")
    def test_cache_hit_no_api_call(self, mock_embed, mock_enabled):
        """Test that cache hits don't trigger API calls."""
        mock_enabled.return_value = True
        mock_embed.return_value = [
            [0.1] * 1536,  # query
            [0.2] * 1536,  # file1
            [0.3] * 1536,  # file2
        ]

        files = {
            "src/a.py": "content a",
            "src/b.py": "content b",
        }

        # First call - should hit API
        result1 = select_files_for_context(
            files=files,
            scope_metadata=None,
            deliverables=None,
            query="test query",
            budget_tokens=1000,
            semantic=True,
        )

        assert result1.mode == "semantic"
        assert mock_embed.call_count == 1

        # Second call with same files - should use cache
        result2 = select_files_for_context(
            files=files,
            scope_metadata=None,
            deliverables=None,
            query="test query",
            budget_tokens=1000,
            semantic=True,
        )

        assert result2.mode == "semantic"
        assert mock_embed.call_count == 2  # One more for query only

        stats = get_embedding_stats()
        assert stats["cache_size"] > 0
        assert stats["call_count"] == 2

    @patch("autopack.context_budgeter.semantic_embeddings_enabled")
    @patch("autopack.context_budgeter.sync_embed_texts")
    def test_cache_miss_triggers_api_call(self, mock_embed, mock_enabled):
        """Test that cache misses trigger API calls."""
        mock_enabled.return_value = True
        mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]

        files1 = {"src/a.py": "content a"}
        files2 = {"src/b.py": "content b"}  # Different file

        # First call
        select_files_for_context(
            files=files1,
            scope_metadata=None,
            deliverables=None,
            query="test",
            budget_tokens=1000,
            semantic=True,
        )

        assert mock_embed.call_count == 1

        # Second call with different file - cache miss
        select_files_for_context(
            files=files2,
            scope_metadata=None,
            deliverables=None,
            query="test",
            budget_tokens=1000,
            semantic=True,
        )

        assert mock_embed.call_count == 2  # Additional call for cache miss

    @patch("autopack.context_budgeter.semantic_embeddings_enabled")
    @patch("autopack.context_budgeter.sync_embed_texts")
    @patch("autopack.context_budgeter._get_embedding_call_cap")
    def test_cap_exceeded_falls_back_to_lexical(self, mock_cap, mock_embed, mock_enabled):
        """Test that exceeding call cap falls back to lexical ranking."""
        mock_enabled.return_value = True
        mock_cap.return_value = 0  # Set cap to 0

        files = {f"src/file{i}.py": f"content {i}" for i in range(10)}

        result = select_files_for_context(
            files=files,
            scope_metadata=None,
            deliverables=None,
            query="test",
            budget_tokens=10000,
            semantic=True,
        )

        # Should fall back to lexical due to cap
        assert result.mode == "lexical"
        assert mock_embed.call_count == 0

    @patch("autopack.context_budgeter.semantic_embeddings_enabled")
    @patch("autopack.context_budgeter.sync_embed_texts")
    def test_hash_invalidation_on_content_change(self, mock_embed, mock_enabled):
        """Test that changing file content invalidates cache."""
        mock_enabled.return_value = True
        mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]

        # First call with original content
        files1 = {"src/a.py": "original content"}
        select_files_for_context(
            files=files1,
            scope_metadata=None,
            deliverables=None,
            query="test",
            budget_tokens=1000,
            semantic=True,
        )

        assert mock_embed.call_count == 1

        # Second call with modified content - should trigger new API call
        files2 = {"src/a.py": "modified content"}
        select_files_for_context(
            files=files2,
            scope_metadata=None,
            deliverables=None,
            query="test",
            budget_tokens=1000,
            semantic=True,
        )

        assert mock_embed.call_count == 2  # Cache invalidated, new call made

    @patch("autopack.context_budgeter.semantic_embeddings_enabled")
    @patch("autopack.context_budgeter.sync_embed_texts")
    def test_deliverables_always_included(self, mock_embed, mock_enabled):
        """Test that deliverable files are always included regardless of ranking."""
        mock_enabled.return_value = True
        mock_embed.return_value = [
            [0.1] * 1536,  # query
            [0.9] * 1536,  # high relevance
            [0.1] * 1536,  # low relevance (deliverable)
        ]

        files = {
            "src/relevant.py": "x" * 100,
            "src/deliverable.py": "x" * 100,
        }

        result = select_files_for_context(
            files=files,
            scope_metadata=None,
            deliverables=["src/deliverable.py"],
            query="test",
            budget_tokens=150,  # Only enough for one file
            semantic=True,
        )

        # Deliverable should be included even with low relevance
        assert "src/deliverable.py" in result.kept

    def test_reset_cache_clears_state(self):
        """Test that reset_embedding_cache clears all state."""
        # Populate cache
        with patch("autopack.context_budgeter.semantic_embeddings_enabled", return_value=True):
            with patch(
                "autopack.context_budgeter.sync_embed_texts",
                return_value=[[0.1] * 1536, [0.2] * 1536],
            ):
                select_files_for_context(
                    files={"src/a.py": "content"},
                    scope_metadata=None,
                    deliverables=None,
                    query="test",
                    budget_tokens=1000,
                    semantic=True,
                )

        stats_before = get_embedding_stats()
        assert stats_before["cache_size"] > 0
        assert stats_before["call_count"] > 0

        # Reset
        reset_embedding_cache()

        stats_after = get_embedding_stats()
        assert stats_after["cache_size"] == 0
        assert stats_after["call_count"] == 0

    @patch("autopack.context_budgeter.semantic_embeddings_enabled")
    @patch("autopack.context_budgeter.sync_embed_texts")
    def test_api_failure_falls_back_to_lexical(self, mock_embed, mock_enabled):
        """Test that API failures gracefully fall back to lexical ranking."""
        mock_enabled.return_value = True
        mock_embed.side_effect = Exception("API error")

        files = {"src/a.py": "content"}

        result = select_files_for_context(
            files=files,
            scope_metadata=None,
            deliverables=None,
            query="test",
            budget_tokens=1000,
            semantic=True,
        )

        # Should fall back to lexical on API failure
        assert result.mode == "lexical"
        assert "src/a.py" in result.kept
