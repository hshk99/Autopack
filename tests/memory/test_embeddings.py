"""Tests for embedding generation utilities.

Tests cover:
- Local deterministic embedding (SHA256-based)
- OpenAI fallback logic
- Text truncation
- Batch embedding
- Async embedding wrapper
- Usage recording
- IMP-PERF-005: Embedding result caching
"""

import asyncio
from unittest.mock import MagicMock, patch

from autopack.memory.embeddings import (
    EMBEDDING_SIZE,
    MAX_EMBEDDING_CHARS,
    _local_embed,
    _record_embedding_usage,
    async_embed_text,
    clear_embedding_cache,
    get_embedding_cache_stats,
    semantic_embeddings_enabled,
    sync_embed_text,
    sync_embed_texts,
)


class TestLocalEmbed:
    """Tests for the local deterministic embedding function."""

    def test_local_embed_deterministic_same_input(self):
        """Test that same input always produces same output."""
        text = "hello world"
        result1 = _local_embed(text)
        result2 = _local_embed(text)
        assert result1 == result2

    def test_local_embed_different_inputs_different_outputs(self):
        """Test that different inputs produce different outputs."""
        result1 = _local_embed("hello")
        result2 = _local_embed("world")
        assert result1 != result2

    def test_local_embed_default_size(self):
        """Test that default embedding size is EMBEDDING_SIZE (1536)."""
        result = _local_embed("test text")
        assert len(result) == EMBEDDING_SIZE
        assert len(result) == 1536

    def test_local_embed_custom_size(self):
        """Test that custom size parameter works."""
        result = _local_embed("test text", size=256)
        assert len(result) == 256

    def test_local_embed_empty_string(self):
        """Test handling of empty string."""
        result = _local_embed("")
        assert len(result) == EMBEDDING_SIZE
        # Empty string should still be deterministic
        assert result == _local_embed("")

    def test_local_embed_none_input(self):
        """Test handling of None input (converts to empty string)."""
        result = _local_embed(None)
        assert len(result) == EMBEDDING_SIZE
        # None should be treated as empty string
        assert result == _local_embed("")

    def test_local_embed_returns_floats(self):
        """Test that all values are floats."""
        result = _local_embed("test")
        assert all(isinstance(v, float) for v in result)

    def test_local_embed_values_in_range(self):
        """Test that values are roughly normalized (-0.5 to 0.5)."""
        result = _local_embed("test text for range check")
        assert all(-0.5 <= v <= 0.5 for v in result)

    def test_local_embed_unicode_handling(self):
        """Test handling of unicode characters."""
        result = _local_embed("Hello \u4e16\u754c \U0001f600")
        assert len(result) == EMBEDDING_SIZE
        # Should be deterministic
        assert result == _local_embed("Hello \u4e16\u754c \U0001f600")

    def test_local_embed_long_text(self):
        """Test handling of long text input."""
        long_text = "a" * 100000
        result = _local_embed(long_text)
        assert len(result) == EMBEDDING_SIZE

    def test_local_embed_whitespace_variations(self):
        """Test that different whitespace produces different embeddings."""
        result1 = _local_embed("hello world")
        result2 = _local_embed("hello  world")
        result3 = _local_embed("hello\nworld")
        assert result1 != result2
        assert result1 != result3
        assert result2 != result3

    def test_local_embed_case_sensitive(self):
        """Test that embeddings are case-sensitive."""
        result1 = _local_embed("Hello")
        result2 = _local_embed("hello")
        assert result1 != result2


class TestSyncEmbedText:
    """Tests for synchronous text embedding."""

    def setup_method(self):
        """Clear embedding cache before each test to ensure isolation."""
        clear_embedding_cache()

    def teardown_method(self):
        """Clear embedding cache after each test."""
        clear_embedding_cache()

    def test_sync_embed_text_returns_correct_size(self):
        """Test that sync_embed_text returns correct size vector."""
        result = sync_embed_text("test text")
        assert len(result) == EMBEDDING_SIZE

    def test_sync_embed_text_truncates_long_text(self, caplog):
        """Test that text longer than MAX_EMBEDDING_CHARS is truncated."""
        import logging

        caplog.set_level(logging.WARNING)
        long_text = "a" * (MAX_EMBEDDING_CHARS + 1000)
        result = sync_embed_text(long_text)
        assert len(result) == EMBEDDING_SIZE
        assert "truncated" in caplog.text.lower()

    def test_sync_embed_text_no_truncation_for_short_text(self, caplog):
        """Test that short text is not truncated."""
        import logging

        caplog.set_level(logging.WARNING)
        short_text = "short text"
        sync_embed_text(short_text)
        assert "truncated" not in caplog.text.lower()

    def test_sync_embed_text_empty_string(self):
        """Test handling of empty string."""
        result = sync_embed_text("")
        assert len(result) == EMBEDDING_SIZE

    def test_sync_embed_text_returns_list(self):
        """Test that result is a list of floats."""
        result = sync_embed_text("test")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    @patch("autopack.memory.embeddings._USE_OPENAI", False)
    @patch("autopack.memory.embeddings._openai_client", None)
    def test_sync_embed_text_uses_local_when_openai_disabled(self):
        """Test that local embedding is used when OpenAI is disabled."""
        text = "test text"
        result = sync_embed_text(text)
        expected = _local_embed(text)
        assert result == expected

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    def test_sync_embed_text_falls_back_on_openai_error(self):
        """Test fallback to local embedding when OpenAI fails."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API Error")

        with patch("autopack.memory.embeddings._openai_client", mock_client):
            text = "test text"
            result = sync_embed_text(text)
            expected = _local_embed(text)
            assert result == expected

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    def test_sync_embed_text_uses_openai_when_available(self):
        """Test that OpenAI embedding is used when available."""
        mock_embedding = [0.1] * EMBEDDING_SIZE
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_response.usage = MagicMock(total_tokens=10)

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("autopack.memory.embeddings._openai_client", mock_client):
            result = sync_embed_text("test text")
            assert result == mock_embedding
            mock_client.embeddings.create.assert_called_once()

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    def test_sync_embed_text_passes_model_parameter(self):
        """Test that model parameter is passed to OpenAI."""
        mock_embedding = [0.1] * EMBEDDING_SIZE
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_response.usage = MagicMock(total_tokens=10)

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("autopack.memory.embeddings._openai_client", mock_client):
            sync_embed_text("test", model="text-embedding-ada-002")
            mock_client.embeddings.create.assert_called_with(
                input="test", model="text-embedding-ada-002"
            )


class TestSyncEmbedTexts:
    """Tests for batch text embedding."""

    def setup_method(self):
        """Clear embedding cache before each test to ensure isolation."""
        clear_embedding_cache()

    def teardown_method(self):
        """Clear embedding cache after each test."""
        clear_embedding_cache()

    def test_sync_embed_texts_returns_correct_count(self):
        """Test that batch embedding returns correct number of vectors."""
        texts = ["hello", "world", "test"]
        results = sync_embed_texts(texts)
        assert len(results) == 3

    def test_sync_embed_texts_each_correct_size(self):
        """Test that each vector has correct size."""
        texts = ["hello", "world"]
        results = sync_embed_texts(texts)
        for result in results:
            assert len(result) == EMBEDDING_SIZE

    def test_sync_embed_texts_empty_list(self):
        """Test handling of empty list."""
        results = sync_embed_texts([])
        assert results == []

    def test_sync_embed_texts_truncates_long_items(self):
        """Test that long texts in batch are truncated."""
        long_text = "a" * (MAX_EMBEDDING_CHARS + 1000)
        texts = ["short", long_text]
        results = sync_embed_texts(texts)
        assert len(results) == 2
        # Both should have valid embeddings
        assert len(results[0]) == EMBEDDING_SIZE
        assert len(results[1]) == EMBEDDING_SIZE

    def test_sync_embed_texts_handles_none_items(self):
        """Test handling of None items in batch."""
        texts = ["hello", None, "world"]
        results = sync_embed_texts(texts)
        assert len(results) == 3
        # None should be treated as empty string
        assert results[1] == _local_embed("")

    def test_sync_embed_texts_handles_empty_strings(self):
        """Test handling of empty strings in batch."""
        texts = ["hello", "", "world"]
        results = sync_embed_texts(texts)
        assert len(results) == 3
        assert results[1] == _local_embed("")

    @patch("autopack.memory.embeddings._USE_OPENAI", False)
    @patch("autopack.memory.embeddings._openai_client", None)
    def test_sync_embed_texts_uses_local_per_item(self):
        """Test that local embedding is applied to each item."""
        texts = ["hello", "world"]
        results = sync_embed_texts(texts)
        assert results[0] == _local_embed("hello")
        assert results[1] == _local_embed("world")

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    def test_sync_embed_texts_falls_back_on_openai_error(self):
        """Test fallback to local embedding when OpenAI batch fails."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("Batch API Error")

        with patch("autopack.memory.embeddings._openai_client", mock_client):
            texts = ["hello", "world"]
            results = sync_embed_texts(texts)
            assert results[0] == _local_embed("hello")
            assert results[1] == _local_embed("world")

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    def test_sync_embed_texts_uses_openai_batch(self):
        """Test that OpenAI batch embedding is used when available."""
        mock_embeddings = [[0.1] * EMBEDDING_SIZE, [0.2] * EMBEDDING_SIZE]
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=mock_embeddings[0]),
            MagicMock(embedding=mock_embeddings[1]),
        ]
        mock_response.usage = MagicMock(total_tokens=20)

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("autopack.memory.embeddings._openai_client", mock_client):
            results = sync_embed_texts(["hello", "world"])
            assert results == mock_embeddings


class TestAsyncEmbedText:
    """Tests for asynchronous text embedding."""

    def setup_method(self):
        """Clear embedding cache before each test to ensure isolation."""
        clear_embedding_cache()

    def teardown_method(self):
        """Clear embedding cache after each test."""
        clear_embedding_cache()

    def test_async_embed_text_returns_correct_size(self):
        """Test that async embedding returns correct size."""
        result = asyncio.run(async_embed_text("test text"))
        assert len(result) == EMBEDDING_SIZE

    def test_async_embed_text_matches_sync(self):
        """Test that async returns same result as sync."""
        text = "hello world"
        async_result = asyncio.run(async_embed_text(text))
        sync_result = sync_embed_text(text)
        assert async_result == sync_result

    def test_async_embed_text_empty_string(self):
        """Test async handling of empty string."""
        result = asyncio.run(async_embed_text(""))
        assert len(result) == EMBEDDING_SIZE

    def test_async_embed_text_passes_parameters(self):
        """Test that parameters are passed through to sync function."""
        with patch("autopack.memory.embeddings.sync_embed_text") as mock_sync:
            mock_sync.return_value = [0.1] * EMBEDDING_SIZE
            asyncio.run(
                async_embed_text(
                    "test", model="custom-model", db="fake_db", run_id="run1", phase_id="phase1"
                )
            )
            mock_sync.assert_called_once_with("test", "custom-model", "fake_db", "run1", "phase1")


class TestRecordEmbeddingUsage:
    """Tests for embedding usage recording."""

    def test_record_usage_noop_when_db_none(self):
        """Test that recording is skipped when db is None."""
        mock_response = MagicMock()
        mock_response.usage = MagicMock(total_tokens=100)
        # Should not raise any errors
        _record_embedding_usage(mock_response, "model", None, None, None)

    def test_record_usage_handles_missing_usage_attr(self, caplog):
        """Test handling when response has no usage attribute."""
        import logging

        caplog.set_level(logging.DEBUG)
        mock_response = MagicMock(spec=[])  # No usage attribute
        mock_db = MagicMock()
        _record_embedding_usage(mock_response, "model", mock_db, None, None)
        assert "No usage data" in caplog.text

    def test_record_usage_handles_none_usage(self, caplog):
        """Test handling when usage is None."""
        import logging

        caplog.set_level(logging.DEBUG)
        mock_response = MagicMock()
        mock_response.usage = None
        mock_db = MagicMock()
        _record_embedding_usage(mock_response, "model", mock_db, None, None)
        assert "No usage data" in caplog.text

    def test_record_usage_handles_zero_tokens(self, caplog):
        """Test handling when total_tokens is zero."""
        import logging

        caplog.set_level(logging.DEBUG)
        mock_response = MagicMock()
        mock_response.usage = MagicMock(total_tokens=0)
        mock_db = MagicMock()
        _record_embedding_usage(mock_response, "model", mock_db, None, None)
        assert "No total_tokens" in caplog.text

    def test_record_usage_handles_none_total_tokens(self, caplog):
        """Test handling when total_tokens is None."""
        import logging

        caplog.set_level(logging.DEBUG)
        mock_response = MagicMock()
        mock_response.usage = MagicMock(total_tokens=None)
        mock_db = MagicMock()
        _record_embedding_usage(mock_response, "model", mock_db, None, None)
        assert "No total_tokens" in caplog.text

    def test_record_usage_calls_record_function(self):
        """Test that usage recording function is called with correct args."""
        mock_response = MagicMock()
        mock_response.usage = MagicMock(total_tokens=100)
        mock_db = MagicMock()

        with patch("autopack.service.usage_recording.record_usage_total_only") as mock_record:
            with patch("autopack.usage_recorder.EMBEDDING_ROLE", "embedding"):
                _record_embedding_usage(mock_response, "test-model", mock_db, "run123", "phase456")
                mock_record.assert_called_once_with(
                    db=mock_db,
                    provider="openai",
                    model="test-model",
                    role="embedding",
                    total_tokens=100,
                    run_id="run123",
                    phase_id="phase456",
                )

    def test_record_usage_graceful_on_recording_failure(self, caplog):
        """Test graceful handling when recording fails."""
        import logging

        caplog.set_level(logging.WARNING)
        mock_response = MagicMock()
        mock_response.usage = MagicMock(total_tokens=100)
        mock_db = MagicMock()

        with patch(
            "autopack.service.usage_recording.record_usage_total_only",
            side_effect=Exception("Recording failed"),
        ):
            # Should not raise
            _record_embedding_usage(mock_response, "model", mock_db, None, None)
            assert "Failed to record embedding usage" in caplog.text


class TestSemanticEmbeddingsEnabled:
    """Tests for semantic_embeddings_enabled function."""

    @patch("autopack.memory.embeddings._USE_OPENAI", False)
    @patch("autopack.memory.embeddings._openai_client", None)
    def test_returns_false_when_openai_disabled(self):
        """Test returns False when OpenAI is not enabled."""
        assert semantic_embeddings_enabled() is False

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    @patch("autopack.memory.embeddings._openai_client", None)
    def test_returns_false_when_client_none(self):
        """Test returns False when client is None."""
        assert semantic_embeddings_enabled() is False

    @patch("autopack.memory.embeddings._USE_OPENAI", False)
    def test_returns_false_when_use_openai_false(self):
        """Test returns False when _USE_OPENAI is False."""
        with patch("autopack.memory.embeddings._openai_client", MagicMock()):
            assert semantic_embeddings_enabled() is False

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    def test_returns_true_when_both_set(self):
        """Test returns True when both USE_OPENAI and client are set."""
        with patch("autopack.memory.embeddings._openai_client", MagicMock()):
            assert semantic_embeddings_enabled() is True


class TestConstants:
    """Tests for module constants."""

    def test_max_embedding_chars_value(self):
        """Test MAX_EMBEDDING_CHARS has expected value."""
        assert MAX_EMBEDDING_CHARS == 30000

    def test_embedding_size_value(self):
        """Test EMBEDDING_SIZE has expected value."""
        assert EMBEDDING_SIZE == 1536


class TestEmbeddingCache:
    """Tests for IMP-PERF-005: Embedding result caching."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_embedding_cache()

    def teardown_method(self):
        """Clear cache after each test."""
        clear_embedding_cache()

    def test_cache_hit_on_repeated_query(self):
        """Test that repeated queries return cached results."""
        text = "test text for caching"

        # First call - cache miss
        result1 = sync_embed_text(text)
        stats1 = get_embedding_cache_stats()
        assert stats1["misses"] == 1
        assert stats1["hits"] == 0

        # Second call - cache hit
        result2 = sync_embed_text(text)
        stats2 = get_embedding_cache_stats()
        assert stats2["misses"] == 1
        assert stats2["hits"] == 1

        # Results should be identical
        assert result1 == result2

    def test_different_texts_cached_separately(self):
        """Test that different texts have separate cache entries."""
        result1 = sync_embed_text("hello")
        result2 = sync_embed_text("world")

        stats = get_embedding_cache_stats()
        assert stats["size"] == 2
        assert stats["misses"] == 2

        # Results should be different
        assert result1 != result2

    def test_cache_respects_model_parameter(self):
        """Test that different models have separate cache entries."""
        text = "same text"

        # Different models should create different cache entries
        sync_embed_text(text, model="model-a")
        sync_embed_text(text, model="model-b")

        stats = get_embedding_cache_stats()
        assert stats["size"] == 2
        assert stats["misses"] == 2

    def test_clear_embedding_cache_function(self):
        """Test that cache can be cleared."""
        # Populate cache
        sync_embed_text("text1")
        sync_embed_text("text2")

        stats_before = get_embedding_cache_stats()
        assert stats_before["size"] == 2

        # Clear cache
        clear_embedding_cache()

        stats_after = get_embedding_cache_stats()
        assert stats_after["size"] == 0
        assert stats_after["hits"] == 0
        assert stats_after["misses"] == 0

    def test_cache_stats_hit_rate(self):
        """Test that hit rate is calculated correctly."""
        # 1 miss
        sync_embed_text("unique text")

        # 3 hits
        sync_embed_text("unique text")
        sync_embed_text("unique text")
        sync_embed_text("unique text")

        stats = get_embedding_cache_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.75  # 3 / 4

    def test_cache_returns_list_not_tuple(self):
        """Test that cached results are returned as lists for API compatibility."""
        text = "test for type check"

        result = sync_embed_text(text)
        assert isinstance(result, list)

        # Second call from cache should also return list
        cached_result = sync_embed_text(text)
        assert isinstance(cached_result, list)

    @patch("autopack.memory.embeddings._USE_OPENAI", True)
    def test_cache_prevents_redundant_api_calls(self):
        """Test that cache hits prevent API calls."""
        mock_embedding = [0.1] * EMBEDDING_SIZE
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_response.usage = MagicMock(total_tokens=10)

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("autopack.memory.embeddings._openai_client", mock_client):
            # First call - API should be called
            sync_embed_text("test text")
            assert mock_client.embeddings.create.call_count == 1

            # Second call - should use cache, no additional API call
            sync_embed_text("test text")
            assert mock_client.embeddings.create.call_count == 1

            stats = get_embedding_cache_stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 1

    def test_cache_handles_truncated_text(self):
        """Test that truncated text is cached correctly."""
        # Create text longer than MAX_EMBEDDING_CHARS
        long_text = "a" * (MAX_EMBEDDING_CHARS + 1000)

        # First call - will truncate and cache
        result1 = sync_embed_text(long_text)

        # Second call with same text - should hit cache
        result2 = sync_embed_text(long_text)

        stats = get_embedding_cache_stats()
        assert stats["hits"] == 1
        assert result1 == result2

    def test_cache_maxsize_enforcement(self):
        """Test that cache respects maxsize limit."""
        from autopack.memory.embeddings import _EMBEDDING_CACHE_MAXSIZE, get_embedding_cache_stats

        # Fill cache beyond maxsize
        for i in range(_EMBEDDING_CACHE_MAXSIZE + 100):
            sync_embed_text(f"unique text {i}")

        stats = get_embedding_cache_stats()
        # Cache should not exceed maxsize
        assert stats["size"] <= _EMBEDDING_CACHE_MAXSIZE
