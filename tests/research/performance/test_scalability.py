"""Scalability tests for research system."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class TestScalability:
    """Scalability test suite for research system."""

    def test_linear_scaling_sessions(self):
        """Test that session creation scales linearly."""
        from autopack.research.session_manager import SessionManager

        manager = SessionManager()

        # Test with different loads
        loads = [10, 50, 100, 200]
        times = []

        for load in loads:
            start = time.time()
            for i in range(load):
                manager.create_session(query=f"test {i}")
            elapsed = time.time() - start
            times.append(elapsed)
            print(f"Load {load}: {elapsed:.3f}s")

        # Check that scaling is roughly linear (within 2x tolerance)
        ratio_1 = times[1] / times[0]
        ratio_2 = times[2] / times[1]

        assert ratio_1 < 10  # Should not degrade significantly
        assert ratio_2 < 5

    def test_concurrent_load_handling(self):
        """Test handling of high concurrent load."""
        from autopack.research.session_manager import SessionManager

        manager = SessionManager()

        def create_and_process(index):
            session_id = manager.create_session(query=f"concurrent {index}")
            session = manager.get_session(session_id)
            return session is not None

        # Test with increasing concurrency
        for workers in [5, 10, 20]:
            start = time.time()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(create_and_process, i) for i in range(100)]
                results = [f.result() for f in as_completed(futures)]
            elapsed = time.time() - start

            assert all(results)
            print(f"Workers {workers}: {elapsed:.3f}s for 100 operations")

    def test_data_volume_scaling(self):
        """Test handling of increasing data volumes."""
        from autopack.research.analyzer import Analyzer

        analyzer = Analyzer()

        # Test with increasing data sizes
        sizes = [10, 50, 100, 200]
        times = []

        for size in sizes:
            data = [{"title": f"Article {i}", "content": f"Content {i}" * 100} for i in range(size)]

            start = time.time()
            analyzer.analyze(data)
            elapsed = time.time() - start
            times.append(elapsed)
            print(f"Data size {size}: {elapsed:.3f}s")

        # Should scale sub-quadratically
        ratio = times[-1] / times[0]
        size_ratio = sizes[-1] / sizes[0]

        assert ratio < size_ratio * 2  # Should not be worse than 2x linear

    def test_sustained_load(self):
        """Test system under sustained load."""
        from autopack.research.query_processor import QueryProcessor
        from autopack.research.session_manager import SessionManager

        manager = SessionManager()
        processor = QueryProcessor()

        duration = 5  # seconds
        start_time = time.time()
        operations = 0

        while time.time() - start_time < duration:
            manager.create_session(query=f"sustained {operations}")
            processor.process(f"sustained {operations}")
            operations += 1

        ops_per_second = operations / duration

        # Should maintain at least 10 ops/second under sustained load
        assert ops_per_second > 10
        print(f"Sustained throughput: {ops_per_second:.2f} ops/second")

    def test_resource_cleanup(self):
        """Test that resources are properly cleaned up at scale."""
        from autopack.research.session_manager import SessionManager

        manager = SessionManager()

        # Create many sessions
        session_ids = []
        for i in range(500):
            session_id = manager.create_session(query=f"cleanup test {i}")
            session_ids.append(session_id)

        # Delete half of them
        for session_id in session_ids[:250]:
            manager.delete_session(session_id)

        # Verify cleanup
        remaining = manager.list_sessions()
        assert len(remaining) <= 250

        # System should still be responsive
        start = time.time()
        new_session = manager.create_session(query="post-cleanup test")
        elapsed = time.time() - start

        assert new_session is not None
        assert elapsed < 0.1  # Should be fast
