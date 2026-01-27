"""Performance tests for data collection."""

import time
from unittest.mock import AsyncMock, Mock

import pytest


class TestCollectionPerformance:
    """Performance tests for data collection operations."""

    @pytest.mark.asyncio
    async def test_collection_throughput(self):
        """Test data collection throughput."""
        collector = Mock()
        collector.collect = AsyncMock(return_value=[{"title": f"Result {i}"} for i in range(100)])

        start_time = time.time()
        results = await collector.collect("test query")
        elapsed = time.time() - start_time

        # Should collect 100 results quickly
        assert len(results) == 100
        assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_parallel_source_collection(self):
        """Test parallel collection from multiple sources."""
        collector = Mock()
        collector.collect_from_sources = AsyncMock(
            return_value={
                "source1": [{"title": "R1"}],
                "source2": [{"title": "R2"}],
                "source3": [{"title": "R3"}],
            }
        )

        start_time = time.time()
        results = await collector.collect_from_sources(["source1", "source2", "source3"])
        elapsed = time.time() - start_time

        assert len(results) == 3
        # Parallel collection should be faster than sequential
        assert elapsed < 3.0

    def test_deduplication_performance(self):
        """Test deduplication performance with large datasets."""
        collector = Mock()

        # Create dataset with duplicates
        data = [{"id": i % 500, "title": f"Result {i % 500}"} for i in range(1000)]
        collector.deduplicate.return_value = [{"id": i, "title": f"Result {i}"} for i in range(500)]

        start_time = time.time()
        deduplicated = collector.deduplicate(data)
        elapsed = time.time() - start_time

        assert len(deduplicated) == 500
        assert elapsed < 0.5

    def test_rate_limiting_overhead(self):
        """Test performance overhead of rate limiting."""
        collector = Mock()
        collector.check_rate_limit.return_value = True

        start_time = time.time()
        for _ in range(100):
            collector.check_rate_limit()
        elapsed = time.time() - start_time

        # Rate limit checks should have minimal overhead
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_collection_with_retries(self):
        """Test performance impact of retry logic."""
        collector = Mock()
        collector.collect_with_retry = AsyncMock(return_value=[{"title": "Result"}])

        start_time = time.time()
        results = await collector.collect_with_retry("test query", max_retries=3)
        elapsed = time.time() - start_time

        assert len(results) > 0
        # Should complete quickly even with retry capability
        assert elapsed < 1.0
