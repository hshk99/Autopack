"""Tests for embedding cache implementation."""

from autopack.file_hashing import compute_cache_key, compute_content_hash


class TestFileHashing:
    """Test suite for file hashing utilities."""

    def test_compute_content_hash_deterministic(self):
        """Test that hash computation is deterministic."""
        content = "def hello(): return 'world'"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_compute_content_hash_different_content(self):
        """Test that different content produces different hashes."""
        content1 = "def hello(): return 'world'"
        content2 = "def hello(): return 'universe'"

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 != hash2

    def test_compute_content_hash_handles_unicode(self):
        """Test that hash computation handles unicode correctly."""
        content = "def greet(): return '你好世界'"
        hash_result = compute_content_hash(content)

        assert isinstance(hash_result, str)
        assert len(hash_result) == 64

    def test_compute_cache_key_format(self):
        """Test that cache key has correct format."""
        path = "src/example.py"
        content = "def test(): pass"
        model = "text-embedding-3-small"

        key = compute_cache_key(path, content, model)

        # Should be in format: path|hash|model
        parts = key.split("|")
        assert len(parts) == 3
        assert parts[0] == path
        assert len(parts[1]) == 64  # SHA256 hash
        assert parts[2] == model

    def test_compute_cache_key_different_paths(self):
        """Test that different paths produce different cache keys."""
        content = "def test(): pass"

        key1 = compute_cache_key("src/a.py", content)
        key2 = compute_cache_key("src/b.py", content)

        assert key1 != key2

    def test_compute_cache_key_different_content(self):
        """Test that different content produces different cache keys."""
        path = "src/example.py"

        key1 = compute_cache_key(path, "content1")
        key2 = compute_cache_key(path, "content2")

        assert key1 != key2

    def test_compute_cache_key_different_models(self):
        """Test that different models produce different cache keys."""
        path = "src/example.py"
        content = "def test(): pass"

        key1 = compute_cache_key(path, content, "text-embedding-3-small")
        key2 = compute_cache_key(path, content, "text-embedding-3-large")

        assert key1 != key2

    def test_compute_cache_key_default_model(self):
        """Test that default model is used when not specified."""
        path = "src/example.py"
        content = "def test(): pass"

        key1 = compute_cache_key(path, content)
        key2 = compute_cache_key(path, content, "text-embedding-3-small")

        assert key1 == key2

    def test_compute_content_hash_empty_string(self):
        """Test that empty string produces valid hash."""
        hash_result = compute_content_hash("")
        assert isinstance(hash_result, str)
        assert len(hash_result) == 64

    def test_compute_content_hash_whitespace_sensitive(self):
        """Test that whitespace differences produce different hashes."""
        content1 = "def test(): pass"
        content2 = "def test():  pass"  # Extra space

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 != hash2

    def test_compute_content_hash_newline_sensitive(self):
        """Test that newline differences produce different hashes."""
        content1 = "line1\nline2"
        content2 = "line1\r\nline2"  # Different line ending

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 != hash2


class TestEmbeddingCachePerPhaseReset:
    """Test per-phase embedding cache reset (BUILD-145 P1 hardening)."""

    def test_per_phase_reset_counter(self):
        """Test that embedding cache counter resets per phase."""
        from autopack.context_budgeter import reset_embedding_cache

        # Reset should clear the counter
        reset_embedding_cache()
        # Import after reset to get current value
        from autopack import context_budgeter

        assert context_budgeter._PHASE_CALL_COUNT == 0

        # Simulate phase 1 making calls (we'll just increment directly for testing)
        context_budgeter._PHASE_CALL_COUNT = 10
        assert context_budgeter._PHASE_CALL_COUNT == 10

        # Reset for phase 2
        reset_embedding_cache()
        assert context_budgeter._PHASE_CALL_COUNT == 0

        # Simulate phase 2 making calls
        context_budgeter._PHASE_CALL_COUNT = 5
        assert context_budgeter._PHASE_CALL_COUNT == 5

    def test_per_phase_reset_cache(self):
        """Test that embedding cache respects persistence setting."""
        from autopack import context_budgeter
        from autopack.context_budgeter import (
            reset_embedding_cache,
            set_cache_persistence,
        )

        # Disable cross-phase persistence for this test (old behavior)
        set_cache_persistence(False)

        # Reset to start clean
        reset_embedding_cache()
        assert len(context_budgeter._EMBEDDING_CACHE) == 0

        # Add some entries (simulating cached embeddings)
        context_budgeter._EMBEDDING_CACHE["key1"] = [0.1, 0.2, 0.3]
        context_budgeter._EMBEDDING_CACHE["key2"] = [0.4, 0.5, 0.6]
        assert len(context_budgeter._EMBEDDING_CACHE) == 2

        # Reset for next phase
        reset_embedding_cache()
        assert len(context_budgeter._EMBEDDING_CACHE) == 0

        # Re-enable cross-phase persistence for other tests
        set_cache_persistence(True)
