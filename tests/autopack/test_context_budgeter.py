"""Tests for context_budgeter with embedding cache."""

from unittest.mock import patch

from autopack.context_budgeter import (_lexical_score, get_embedding_stats,
                                       reset_embedding_cache,
                                       select_files_for_context,
                                       set_cache_persistence)


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
        """Test that reset_embedding_cache respects persistence setting."""
        # Disable cross-phase persistence for this test (old behavior)
        set_cache_persistence(False)

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
        assert stats_before["persist_cache"] is False

        # Reset
        reset_embedding_cache()

        stats_after = get_embedding_stats()
        assert stats_after["cache_size"] == 0
        assert stats_after["call_count"] == 0

        # Re-enable cross-phase persistence for other tests
        set_cache_persistence(True)

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


class TestCacheThreadSafety:
    """Test suite for thread-safe cache operations.

    These tests verify that the TOCTOU fix is working correctly by testing
    concurrent cache operations don't cause race conditions.
    """

    def setup_method(self):
        """Reset cache before each test."""
        set_cache_persistence(True)
        reset_embedding_cache()

    def teardown_method(self):
        """Cleanup after each test."""
        set_cache_persistence(True)
        reset_embedding_cache()

    def test_concurrent_cache_clear_no_race(self):
        """Test that concurrent cache clear operations don't cause race conditions.

        This validates the TOCTOU fix: the lock is held across both check and clear.
        """
        import threading

        from autopack import context_budgeter

        # Disable persistence so clear actually clears the cache
        set_cache_persistence(False)

        # Manually populate cache to test clearing
        with context_budgeter._CACHE_LOCK:
            for i in range(100):
                context_budgeter._EMBEDDING_CACHE[f"key_{i}"] = [0.1] * 1536

        stats = get_embedding_stats()
        assert stats["cache_size"] == 100

        errors = []
        clear_count = [0]

        def clear_cache():
            try:
                for _ in range(10):
                    reset_embedding_cache()
                    clear_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Start multiple threads trying to clear cache concurrently
        threads = [threading.Thread(target=clear_cache) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Errors during concurrent clear: {errors}"
        # Cache should be empty after all clears
        stats = get_embedding_stats()
        assert stats["cache_size"] == 0

    def test_concurrent_read_clear_no_race(self):
        """Test that concurrent read and clear operations don't cause race conditions."""
        import threading

        from autopack import context_budgeter

        # Disable persistence so clear actually clears the cache
        set_cache_persistence(False)

        # Populate cache
        with context_budgeter._CACHE_LOCK:
            for i in range(50):
                context_budgeter._EMBEDDING_CACHE[f"key_{i}"] = [0.1] * 1536

        errors = []
        read_results = []

        def read_stats():
            try:
                for _ in range(20):
                    stats = get_embedding_stats()
                    read_results.append(stats["cache_size"])
            except Exception as e:
                errors.append(e)

        def clear_cache():
            try:
                for _ in range(5):
                    reset_embedding_cache()
                    # Re-populate for more iterations
                    with context_budgeter._CACHE_LOCK:
                        for i in range(10):
                            context_budgeter._EMBEDDING_CACHE[f"new_{i}"] = [0.2] * 1536
            except Exception as e:
                errors.append(e)

        # Start reader and clearer threads
        readers = [threading.Thread(target=read_stats) for _ in range(3)]
        clearers = [threading.Thread(target=clear_cache) for _ in range(2)]

        all_threads = readers + clearers
        for t in all_threads:
            t.start()
        for t in all_threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Errors during concurrent read/clear: {errors}"
        # All read results should be valid integers >= 0
        assert all(isinstance(r, int) and r >= 0 for r in read_results)

    def test_concurrent_persistence_toggle_no_race(self):
        """Test that concurrent persistence toggle and clear don't cause issues."""
        import threading

        from autopack import context_budgeter

        # Populate cache
        with context_budgeter._CACHE_LOCK:
            for i in range(30):
                context_budgeter._EMBEDDING_CACHE[f"key_{i}"] = [0.1] * 1536

        errors = []

        def toggle_persistence():
            try:
                for i in range(20):
                    set_cache_persistence(i % 2 == 0)
            except Exception as e:
                errors.append(e)

        def clear_cache():
            try:
                for _ in range(10):
                    reset_embedding_cache()
            except Exception as e:
                errors.append(e)

        # Start toggler and clearer threads
        togglers = [threading.Thread(target=toggle_persistence) for _ in range(2)]
        clearers = [threading.Thread(target=clear_cache) for _ in range(2)]

        all_threads = togglers + clearers
        for t in all_threads:
            t.start()
        for t in all_threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Errors during concurrent toggle/clear: {errors}"

    def test_cache_state_consistency_under_load(self):
        """Test cache state remains consistent under concurrent access."""
        import threading

        from autopack import context_budgeter

        set_cache_persistence(True)  # Keep cache between resets
        reset_embedding_cache()

        errors = []
        inconsistencies = []

        def writer():
            try:
                for i in range(50):
                    with context_budgeter._CACHE_LOCK:
                        key = f"thread_{threading.current_thread().name}_{i}"
                        context_budgeter._EMBEDDING_CACHE[key] = [float(i)] * 1536
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    stats = get_embedding_stats()
                    # Cache size should never be negative
                    if stats["cache_size"] < 0:
                        inconsistencies.append(f"Negative cache size: {stats['cache_size']}")
            except Exception as e:
                errors.append(e)

        def resetter():
            try:
                for _ in range(10):
                    reset_embedding_cache()
            except Exception as e:
                errors.append(e)

        writers = [threading.Thread(target=writer, name=f"writer_{i}") for i in range(3)]
        readers = [threading.Thread(target=reader, name=f"reader_{i}") for i in range(3)]
        resetters = [threading.Thread(target=resetter, name=f"resetter_{i}") for i in range(2)]

        all_threads = writers + readers + resetters
        for t in all_threads:
            t.start()
        for t in all_threads:
            t.join()

        assert len(errors) == 0, f"Errors during load test: {errors}"
        assert len(inconsistencies) == 0, f"Inconsistencies found: {inconsistencies}"
