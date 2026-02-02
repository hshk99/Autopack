#!/usr/bin/env python3
"""Benchmark script for research cache optimization.

Measures performance improvements from LRU eviction and compression.
"""

import time
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from unittest.mock import MagicMock
from autopack.research.orchestrator import ResearchCache
from autopack.research.cache_optimizer import OptimizedResearchCache
from autopack.research.models.bootstrap_session import BootstrapSession


def create_mock_session(size_bytes: int = 50000) -> BootstrapSession:
    """Create a mock BootstrapSession with specified data size.

    Args:
        size_bytes: Approximate size of the session in bytes

    Returns:
        Mock BootstrapSession
    """
    session = MagicMock(spec=BootstrapSession)
    session.id = f"session_{time.time()}"

    # Create large data attributes to simulate real sessions
    session.large_data = "x" * size_bytes
    session.results = {"data": list(range(size_bytes // 4))}

    return session


def benchmark_lru_eviction():
    """Benchmark LRU eviction behavior."""
    print("\n" + "=" * 70)
    print("BENCHMARK 1: LRU Eviction Performance")
    print("=" * 70)

    max_size = 100
    num_requests = 500

    # Test basic cache (unbounded)
    print("\nTest Setup:")
    print(f"  - Max cache size: {max_size}")
    print(f"  - Number of requests: {num_requests}")

    # Basic cache - no eviction
    print("\nBasic Cache (no eviction):")
    basic_cache = ResearchCache(ttl_hours=24)

    start_time = time.time()
    for i in range(num_requests):
        session = create_mock_session()
        basic_cache.set(f"hash_{i % (num_requests)}", session)

    basic_time = time.time() - start_time
    basic_size = len(basic_cache._cache)

    print(f"  - Time: {basic_time:.4f} seconds")
    print(f"  - Final cache size: {basic_size} entries (unbounded)")
    print("  - Memory impact: HIGH (no eviction)")

    # Optimized cache with LRU
    print("\nOptimized Cache (LRU eviction):")
    opt_cache = OptimizedResearchCache(
        ttl_hours=24,
        max_size=max_size,
        enable_compression=False,
    )

    start_time = time.time()
    for i in range(num_requests):
        session = create_mock_session()
        opt_cache.set(f"hash_{i % (num_requests)}", session)

    opt_time = time.time() - start_time
    opt_size = opt_cache.get_size()
    stats = opt_cache.get_stats()

    print(f"  - Time: {opt_time:.4f} seconds")
    print(f"  - Final cache size: {opt_size} entries (bounded to {max_size})")
    print(f"  - Evictions: {stats['evictions']}")
    print("  - Memory impact: LOW (bounded cache)")
    print(f"  - Performance ratio: {basic_time / opt_time:.2f}x")


def benchmark_cache_hit_rates():
    """Benchmark cache hit rates."""
    print("\n" + "=" * 70)
    print("BENCHMARK 2: Cache Hit Rate Performance")
    print("=" * 70)

    cache_size = 100
    num_requests = 1000
    locality = 0.8  # 80% of requests hit top 20% of entries

    print("\nTest Setup:")
    print(f"  - Cache size: {cache_size}")
    print(f"  - Number of requests: {num_requests}")
    print(f"  - Locality: {locality * 100}% of requests to {int(cache_size * 0.2)} popular entries")

    opt_cache = OptimizedResearchCache(
        ttl_hours=24,
        max_size=cache_size,
        enable_compression=False,
    )

    # Populate cache
    print("\nPopulating cache...")
    for i in range(cache_size):
        session = create_mock_session()
        opt_cache.set(f"hash_{i}", session)

    # Perform requests with locality
    print("Running requests...")
    start_time = time.time()
    popular_hashes = [f"hash_{i}" for i in range(int(cache_size * 0.2))]
    uncommon_hashes = [f"hash_{i}" for i in range(int(cache_size * 0.2), cache_size)]

    request_count = 0
    for i in range(num_requests):
        if (i % 100) < (locality * 100):
            # Likely to hit (use popular entries)
            hash_key = popular_hashes[i % len(popular_hashes)]
        else:
            # Less likely to hit (use uncommon entries)
            hash_key = uncommon_hashes[(i // 100) % len(uncommon_hashes)]

        opt_cache.get(hash_key)
        request_count += 1

    elapsed = time.time() - start_time

    stats = opt_cache.get_stats()
    print("\nResults:")
    print(f"  - Total requests: {request_count}")
    print(f"  - Cache hits: {stats['hits']}")
    print(f"  - Cache misses: {stats['misses']}")
    print(f"  - Hit rate: {stats['hit_rate_percent']:.2f}%")
    print(f"  - Time per request: {(elapsed / request_count) * 1000:.3f} ms")
    print(f"  - Throughput: {request_count / elapsed:.0f} requests/sec")


def benchmark_compression():
    """Benchmark compression effectiveness."""
    print("\n" + "=" * 70)
    print("BENCHMARK 3: Compression Effectiveness")
    print("=" * 70)

    cache_size = 50
    session_size = 500000  # 500KB sessions

    print("\nTest Setup:")
    print(f"  - Cache size: {cache_size}")
    print(f"  - Session size: {session_size / 1024:.0f} KB")

    # Without compression
    print("\nWithout Compression:")
    cache_no_compress = OptimizedResearchCache(
        ttl_hours=24,
        max_size=cache_size,
        enable_compression=False,
    )

    start_time = time.time()
    for i in range(cache_size):
        session = create_mock_session(size_bytes=session_size)
        cache_no_compress.set(f"hash_{i}", session)

    time_no_compress = time.time() - start_time
    cache_no_compress.get_stats()

    print(f"  - Time to populate: {time_no_compress:.4f} seconds")
    print(f"  - Cache size: {cache_size} entries")

    # With compression
    print("\nWith Compression:")
    cache_compress = OptimizedResearchCache(
        ttl_hours=24,
        max_size=cache_size,
        enable_compression=True,
        compression_threshold=10000,  # 10KB threshold
    )

    start_time = time.time()
    for i in range(cache_size):
        session = create_mock_session(size_bytes=session_size)
        cache_compress.set(f"hash_{i}", session)

    time_compress = time.time() - start_time
    stats_compress = cache_compress.get_stats()

    print(f"  - Time to populate: {time_compress:.4f} seconds")
    print(f"  - Compressions performed: {stats_compress['compressions']}")
    print(
        f"  - Total bytes saved: {stats_compress['total_bytes_saved_by_compression'] / (1024*1024):.2f} MB"
    )

    if stats_compress["compressions"] > 0:
        avg_saved = (
            stats_compress["total_bytes_saved_by_compression"] / stats_compress["compressions"]
        )
        print(f"  - Average bytes saved per entry: {avg_saved / 1024:.1f} KB")

    print("\nCompression Overhead:")
    print(f"  - Extra time for compression: {(time_compress - time_no_compress) * 1000:.2f} ms")


def benchmark_memory_usage():
    """Benchmark memory usage improvements."""
    print("\n" + "=" * 70)
    print("BENCHMARK 4: Memory Usage Analysis")
    print("=" * 70)

    cache_size = 50
    session_sizes = [50000, 100000, 500000, 1000000]

    print("\nTest Setup:")
    print(f"  - Cache size: {cache_size}")
    print("  - Testing various session sizes")

    results = []

    for session_size in session_sizes:
        cache = OptimizedResearchCache(
            ttl_hours=24,
            max_size=cache_size,
            enable_compression=True,
            compression_threshold=50000,
        )

        for i in range(cache_size):
            session = create_mock_session(size_bytes=session_size)
            cache.set(f"hash_{i}", session)

        cache.get_stats()

        # Calculate approximate memory usage
        total_stored = 0
        compressed = 0
        for entry in cache._cache.values():
            total_stored += entry.get_size()
            if entry.is_compressed:
                compressed += 1

        avg_entry_size = total_stored / cache_size if cache_size > 0 else 0

        result = {
            "session_size": session_size,
            "num_entries": cache_size,
            "avg_stored_size": int(avg_entry_size),
            "total_size": total_stored,
            "compressed_entries": compressed,
            "compression_ratio": (compressed / cache_size * 100) if cache_size > 0 else 0,
        }
        results.append(result)

        print(f"\nSession size: {session_size / 1024:.0f} KB")
        print(f"  - Compressed entries: {compressed}/{cache_size}")
        print(f"  - Compression ratio: {result['compression_ratio']:.1f}%")
        print(f"  - Avg stored size: {avg_entry_size / 1024:.1f} KB")
        print(f"  - Total cache size: {total_stored / (1024*1024):.2f} MB")

    return results


def benchmark_scalability():
    """Benchmark scalability with varying cache sizes."""
    print("\n" + "=" * 70)
    print("BENCHMARK 5: Scalability Analysis")
    print("=" * 70)

    cache_sizes = [10, 50, 100, 500]
    requests_per_cache = 100

    print("\nTest Setup:")
    print("  - Testing caches of various sizes")
    print(f"  - Requests per cache: {requests_per_cache}")

    results = []

    for cache_size in cache_sizes:
        cache = OptimizedResearchCache(
            ttl_hours=24,
            max_size=cache_size,
            enable_compression=False,
        )

        # Populate
        for i in range(cache_size):
            session = create_mock_session()
            cache.set(f"hash_{i}", session)

        # Measure request performance
        start_time = time.time()
        for i in range(requests_per_cache):
            hash_key = f"hash_{i % cache_size}"
            cache.get(hash_key)

        elapsed = time.time() - start_time

        result = {
            "cache_size": cache_size,
            "requests": requests_per_cache,
            "total_time": elapsed,
            "time_per_request": (elapsed / requests_per_cache) * 1000,
        }
        results.append(result)

        print(f"\nCache size: {cache_size}")
        print(f"  - Requests: {requests_per_cache}")
        print(f"  - Total time: {elapsed:.6f} seconds")
        print(f"  - Time per request: {result['time_per_request']:.4f} ms")

    return results


def main():
    """Run all benchmarks."""
    print("\n" + "=" * 70)
    print("RESEARCH CACHE OPTIMIZATION BENCHMARKS")
    print("=" * 70)

    try:
        benchmark_lru_eviction()
        benchmark_cache_hit_rates()
        benchmark_compression()
        benchmark_memory_usage()
        benchmark_scalability()

        print("\n" + "=" * 70)
        print("BENCHMARK SUMMARY")
        print("=" * 70)
        print("\nKey Improvements:")
        print("1. LRU Eviction: Bounded memory usage prevents unbounded growth")
        print("2. Hit Rate: Efficient access patterns leverage locality")
        print("3. Compression: Reduces memory footprint for large sessions")
        print("4. Scalability: O(1) access patterns maintain performance at scale")
        print("\nFor detailed metrics, use cache.get_stats() and CacheOptimizer.analyze_cache()")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\nError running benchmarks: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
