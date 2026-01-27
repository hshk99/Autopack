"""Tests for scoped context loader file caching (IMP-P03).

Tests that file content is cached with mtime-based invalidation
to reduce disk I/O during phase execution.
"""

import time
from unittest.mock import Mock

import pytest

from autopack.executor.scoped_context_loader import (
    ScopedContextLoader,
    _cached_read_file,
    clear_file_cache,
    get_file_cache_info,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset file cache before each test."""
    clear_file_cache()
    yield
    clear_file_cache()


@pytest.fixture
def mock_executor(tmp_path):
    """Create a mock executor with minimal configuration."""
    executor = Mock()
    executor.workspace = str(tmp_path)
    executor.run_id = "test-run-123"
    executor.run_type = "project_build"
    return executor


class TestFileCaching:
    """Tests for file content caching functionality."""

    def test_cache_hit_on_repeated_read(self, tmp_path):
        """File should be cached on first read, hit cache on second read."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # First read - cache miss
        mtime = test_file.stat().st_mtime
        content1 = _cached_read_file(str(test_file), mtime)

        # Second read with same mtime - cache hit
        content2 = _cached_read_file(str(test_file), mtime)

        assert content1 == content2 == "print('hello')"

        # Verify cache hit
        cache_info = get_file_cache_info()
        assert cache_info["hits"] == 1
        assert cache_info["misses"] == 1

    def test_cache_invalidation_on_file_change(self, tmp_path):
        """Cache should invalidate when file mtime changes."""
        test_file = tmp_path / "test.py"
        test_file.write_text("version 1")

        # First read
        mtime1 = test_file.stat().st_mtime
        content1 = _cached_read_file(str(test_file), mtime1)
        assert content1 == "version 1"

        # Modify file (ensure mtime changes)
        time.sleep(0.01)
        test_file.write_text("version 2")
        mtime2 = test_file.stat().st_mtime
        assert mtime2 != mtime1  # mtime changed

        # Second read with new mtime - cache miss (new key)
        content2 = _cached_read_file(str(test_file), mtime2)
        assert content2 == "version 2"

        # Should have 2 misses (2 different keys)
        cache_info = get_file_cache_info()
        assert cache_info["misses"] == 2
        assert cache_info["size"] == 2  # Both versions cached

    def test_cache_info_returns_correct_stats(self, tmp_path):
        """Cache info should return accurate statistics."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        mtime = test_file.stat().st_mtime

        # Initial state
        cache_info = get_file_cache_info()
        assert cache_info["hits"] == 0
        assert cache_info["misses"] == 0
        assert cache_info["hit_rate"] == 0.0

        # First read - miss
        _cached_read_file(str(test_file), mtime)
        cache_info = get_file_cache_info()
        assert cache_info["misses"] == 1
        assert cache_info["hit_rate"] == 0.0

        # Second read - hit
        _cached_read_file(str(test_file), mtime)
        cache_info = get_file_cache_info()
        assert cache_info["hits"] == 1
        assert cache_info["misses"] == 1
        assert cache_info["hit_rate"] == 0.5

        # Third read - another hit
        _cached_read_file(str(test_file), mtime)
        cache_info = get_file_cache_info()
        assert cache_info["hits"] == 2
        assert cache_info["misses"] == 1
        assert cache_info["hit_rate"] == pytest.approx(0.666, rel=0.01)

    def test_clear_cache_resets_statistics(self, tmp_path):
        """Clear cache should reset all statistics."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        mtime = test_file.stat().st_mtime

        # Generate some cache activity
        _cached_read_file(str(test_file), mtime)
        _cached_read_file(str(test_file), mtime)

        cache_info = get_file_cache_info()
        assert cache_info["hits"] > 0

        # Clear cache
        clear_file_cache()

        # Stats should be reset
        cache_info = get_file_cache_info()
        assert cache_info["hits"] == 0
        assert cache_info["misses"] == 0
        assert cache_info["size"] == 0

    def test_multiple_files_cached_independently(self, tmp_path):
        """Different files should be cached independently."""
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("content 1")
        file2.write_text("content 2")

        mtime1 = file1.stat().st_mtime
        mtime2 = file2.stat().st_mtime

        # Read both files
        content1 = _cached_read_file(str(file1), mtime1)
        content2 = _cached_read_file(str(file2), mtime2)

        assert content1 == "content 1"
        assert content2 == "content 2"

        # Both should be cached
        cache_info = get_file_cache_info()
        assert cache_info["size"] == 2

        # Read again - both should hit cache
        _cached_read_file(str(file1), mtime1)
        _cached_read_file(str(file2), mtime2)

        cache_info = get_file_cache_info()
        assert cache_info["hits"] == 2
        assert cache_info["misses"] == 2


class TestScopedContextLoaderCaching:
    """Tests for file caching within ScopedContextLoader."""

    def test_load_context_uses_cache(self, mock_executor, tmp_path):
        """load_context should use file cache for repeated file reads."""
        loader = ScopedContextLoader(mock_executor)

        # Create test files
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def main(): pass")

        scope_config = {
            "paths": ["src/main.py"],
            "read_only_context": [],
        }

        phase = {
            "description": "Test phase",
            "deliverables": [],
        }

        # First load - should miss cache
        clear_file_cache()
        result1 = loader.load_context(phase, scope_config)
        cache_info1 = get_file_cache_info()

        # Second load - should hit cache
        result2 = loader.load_context(phase, scope_config)
        cache_info2 = get_file_cache_info()

        # Both loads should return same content
        assert "src/main.py" in result1["existing_files"]
        assert "src/main.py" in result2["existing_files"]
        assert result1["existing_files"]["src/main.py"] == result2["existing_files"]["src/main.py"]

        # Cache hits should increase on second load
        assert cache_info2["hits"] > cache_info1["hits"]

    def test_load_context_with_read_only_files_cached(self, mock_executor, tmp_path):
        """Read-only context files should also be cached."""
        loader = ScopedContextLoader(mock_executor)

        # Create test files
        main_file = tmp_path / "src" / "main.py"
        utils_file = tmp_path / "src" / "utils.py"
        main_file.parent.mkdir(parents=True)
        main_file.write_text("def main(): pass")
        utils_file.write_text("def helper(): pass")

        scope_config = {
            "paths": ["src/main.py"],
            "read_only_context": ["src/utils.py"],
        }

        phase = {
            "description": "Test phase",
            "deliverables": [],
        }

        # First load
        clear_file_cache()
        loader.load_context(phase, scope_config)

        # Second load
        result2 = loader.load_context(phase, scope_config)

        # Both modifiable and read-only files should be cached
        cache_info = get_file_cache_info()
        assert cache_info["hits"] >= 2  # At least 2 files hit cache on second load
        assert "src/main.py" in result2["existing_files"]
        assert "src/utils.py" in result2["existing_files"]

    def test_cache_hit_rate_improves_across_phases(self, mock_executor, tmp_path):
        """Cache hit rate should improve when loading same files across phases."""
        loader = ScopedContextLoader(mock_executor)

        # Create common files
        for i in range(5):
            file_path = tmp_path / f"file{i}.py"
            file_path.write_text(f"# File {i}")

        scope_config = {
            "paths": [f"file{i}.py" for i in range(5)],
            "read_only_context": [],
        }

        phase = {
            "description": "Test phase",
            "deliverables": [],
        }

        # Clear cache and load first time
        clear_file_cache()
        loader.load_context(phase, scope_config)
        cache_info_first = get_file_cache_info()

        # Load again (simulating next phase)
        loader.load_context(phase, scope_config)
        cache_info_second = get_file_cache_info()

        # Hit rate should improve
        assert cache_info_second["hit_rate"] > cache_info_first["hit_rate"]
        assert cache_info_second["hits"] >= 5  # All 5 files should hit cache


class TestCacheInvalidationScenarios:
    """Tests for various cache invalidation scenarios."""

    def test_file_modification_invalidates_cache(self, tmp_path):
        """Modifying a file should invalidate its cache entry."""
        test_file = tmp_path / "test.py"
        test_file.write_text("original")

        # Read original
        mtime1 = test_file.stat().st_mtime
        content1 = _cached_read_file(str(test_file), mtime1)
        assert content1 == "original"

        # Modify file
        time.sleep(0.01)  # Ensure mtime changes
        test_file.write_text("modified")

        # Read with new mtime - should get new content
        mtime2 = test_file.stat().st_mtime
        content2 = _cached_read_file(str(test_file), mtime2)
        assert content2 == "modified"
        assert mtime2 != mtime1

    def test_cache_respects_maxsize(self, tmp_path):
        """Cache should respect maxsize=128 limit."""
        # The cache has maxsize=128, so let's verify it doesn't grow beyond that
        # Note: This test is informational - LRU cache handles this automatically

        files = []
        for i in range(150):  # Create more than maxsize
            file_path = tmp_path / f"file{i}.py"
            file_path.write_text(f"content {i}")
            files.append(file_path)

        # Read all files
        for file_path in files:
            mtime = file_path.stat().st_mtime
            _cached_read_file(str(file_path), mtime)

        # Cache size should not exceed maxsize
        cache_info = get_file_cache_info()
        assert cache_info["size"] <= cache_info["maxsize"]
        assert cache_info["maxsize"] == 128


class TestErrorHandling:
    """Tests for error handling in file caching."""

    def test_read_nonexistent_file_returns_empty(self, tmp_path):
        """Reading non-existent file should return empty string and log warning."""
        nonexistent = tmp_path / "missing.py"
        content = _cached_read_file(str(nonexistent), 0.0)
        assert content == ""

    def test_read_error_returns_empty(self, tmp_path):
        """Read errors should return empty string without crashing."""
        # Create a directory (not a file)
        dir_path = tmp_path / "directory"
        dir_path.mkdir()

        # Try to read it as a file - should fail gracefully
        content = _cached_read_file(str(dir_path), 0.0)
        assert content == ""
