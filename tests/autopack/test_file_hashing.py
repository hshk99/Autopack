"""Tests for file hashing and LRU caching.

Tests the compute_file_hash_with_cache function to ensure:
1. Cache hits work correctly (same mtime returns cached result)
2. Cache misses force re-computation (different mtime)
3. Cache invalidation on file modification
4. Cache statistics are tracked correctly
"""

import time

import pytest

from autopack.file_hashing import (
    clear_file_hash_cache,
    compute_file_hash_cached,
    compute_file_hash_with_cache,
)


class TestFileHashCaching:
    """Tests for file hashing with LRU cache."""

    def test_compute_file_hash_with_cache_basic(self, tmp_path):
        """Test basic file hashing."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        hash_value = compute_file_hash_with_cache(str(file_path))

        assert hash_value
        assert len(hash_value) == 64  # SHA256 hex digest is 64 characters
        assert hash_value.isalnum()

    def test_file_hash_cache_hit(self, tmp_path):
        """Test cache hit: same mtime returns cached result without re-reading."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        clear_file_hash_cache()

        # First call - cache miss
        hash1 = compute_file_hash_with_cache(str(file_path))
        cache_info_after_first = compute_file_hash_cached.cache_info()

        # Second call immediately - cache hit (same mtime, no file modification)
        hash2 = compute_file_hash_with_cache(str(file_path))
        cache_info_after_second = compute_file_hash_cached.cache_info()

        # Verify hashes match
        assert hash1 == hash2

        # Verify cache hit occurred
        assert cache_info_after_first.hits == 0
        assert cache_info_after_first.misses == 1
        assert cache_info_after_second.hits == 1
        assert cache_info_after_second.misses == 1

    def test_file_hash_cache_invalidation_on_modification(self, tmp_path):
        """Test cache invalidation when file is modified."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("original content")

        clear_file_hash_cache()

        # First call - cache miss
        hash1 = compute_file_hash_with_cache(str(file_path))

        # Modify file (changes mtime)
        # Use time.sleep to ensure mtime changes (file systems may have 1s resolution)
        time.sleep(0.01)
        file_path.write_text("modified content")

        # Second call - cache miss (different mtime)
        hash2 = compute_file_hash_with_cache(str(file_path))
        cache_info = compute_file_hash_cached.cache_info()

        # Verify hashes differ
        assert hash1 != hash2

        # Verify cache misses (both calls were misses due to different mtime keys)
        assert cache_info.misses == 2
        assert cache_info.hits == 0

    def test_file_hash_cache_size(self, tmp_path):
        """Test that cache has maxsize=512."""
        clear_file_hash_cache()

        # Create many test files
        files = []
        for i in range(20):
            file_path = tmp_path / f"test_{i}.txt"
            file_path.write_text(f"content {i}")
            files.append(str(file_path))

        # Hash all files
        for file_path in files:
            compute_file_hash_with_cache(file_path)

        cache_info = compute_file_hash_cached.cache_info()
        assert cache_info.maxsize == 512

    def test_file_hash_multiple_hashes_different_files(self, tmp_path):
        """Test that different files produce different hashes."""
        file1 = tmp_path / "test1.txt"
        file2 = tmp_path / "test2.txt"

        file1.write_text("content1")
        file2.write_text("content2")

        clear_file_hash_cache()

        hash1 = compute_file_hash_with_cache(str(file1))
        hash2 = compute_file_hash_with_cache(str(file2))

        assert hash1 != hash2

    def test_file_hash_same_content_same_hash(self, tmp_path):
        """Test that same content produces same hash."""
        file1 = tmp_path / "test1.txt"
        file2 = tmp_path / "test2.txt"

        file1.write_text("same content")
        file2.write_text("same content")

        clear_file_hash_cache()

        hash1 = compute_file_hash_with_cache(str(file1))
        hash2 = compute_file_hash_with_cache(str(file2))

        # Both files have same content, so same hash
        assert hash1 == hash2

    def test_file_hash_empty_file(self, tmp_path):
        """Test hashing of empty file."""
        file_path = tmp_path / "empty.txt"
        file_path.write_text("")

        clear_file_hash_cache()

        hash_value = compute_file_hash_with_cache(str(file_path))

        assert hash_value
        assert len(hash_value) == 64

    def test_file_hash_binary_file(self, tmp_path):
        """Test hashing of binary file."""
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(b"\x00\x01\x02\x03\x04")

        clear_file_hash_cache()

        hash_value = compute_file_hash_with_cache(str(file_path))

        assert hash_value
        assert len(hash_value) == 64

    def test_file_hash_nonexistent_file(self, tmp_path):
        """Test hashing of non-existent file."""
        file_path = tmp_path / "nonexistent.txt"

        clear_file_hash_cache()

        # Should raise OSError since file doesn't exist
        with pytest.raises(OSError):
            compute_file_hash_with_cache(str(file_path))

    def test_clear_file_hash_cache(self, tmp_path):
        """Test cache clearing."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        clear_file_hash_cache()
        compute_file_hash_with_cache(str(file_path))

        cache_info_before = compute_file_hash_cached.cache_info()
        assert cache_info_before.currsize > 0

        clear_file_hash_cache()

        cache_info_after = compute_file_hash_cached.cache_info()
        assert cache_info_after.currsize == 0

    def test_file_hash_large_file(self, tmp_path):
        """Test hashing of large file."""
        file_path = tmp_path / "large.txt"
        # Create a 10MB file
        with open(file_path, "wb") as f:
            f.write(b"x" * (10 * 1024 * 1024))

        clear_file_hash_cache()

        hash_value = compute_file_hash_with_cache(str(file_path))

        assert hash_value
        assert len(hash_value) == 64

    def test_file_hash_unicode_content(self, tmp_path):
        """Test hashing of file with unicode content."""
        file_path = tmp_path / "unicode.txt"
        file_path.write_text("Hello 世界 🌍", encoding="utf-8")

        clear_file_hash_cache()

        hash_value = compute_file_hash_with_cache(str(file_path))

        assert hash_value
        assert len(hash_value) == 64

    def test_file_hash_cache_efficiency_benchmark(self, tmp_path):
        """Benchmark cache efficiency: measure cache hits in typical scenario."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("benchmark content")

        clear_file_hash_cache()

        # Simulate typical usage: same file hashed multiple times in a phase
        for _ in range(10):
            compute_file_hash_with_cache(str(file_path))

        cache_info = compute_file_hash_cached.cache_info()

        # First call is a miss, remaining 9 are hits
        assert cache_info.hits == 9
        assert cache_info.misses == 1
        hit_rate = cache_info.hits / (cache_info.hits + cache_info.misses)
        assert hit_rate == 0.9  # 90% hit rate in this scenario

    def test_file_hash_deterministic(self, tmp_path):
        """Test that hashing is deterministic."""
        file_path = tmp_path / "test.txt"
        content = "deterministic content"
        file_path.write_text(content)

        clear_file_hash_cache()

        hashes = []
        for _ in range(5):
            hash_value = compute_file_hash_with_cache(str(file_path))
            hashes.append(hash_value)

        # All hashes should be identical
        assert all(h == hashes[0] for h in hashes)
