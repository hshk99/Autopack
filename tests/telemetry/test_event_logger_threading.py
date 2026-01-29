"""Thread safety tests for event logger."""

import json
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from telemetry.event_logger import EventLogger, get_logger


class TestEventLoggerThreadSafety:
    """Tests for EventLogger thread safety."""

    def test_concurrent_log_writes_no_corruption(self):
        """Test that concurrent log writes don't corrupt data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(log_dir=tmpdir)
            num_threads = 10
            logs_per_thread = 50

            def write_logs(thread_id: int) -> int:
                """Write multiple log entries from a single thread."""
                for i in range(logs_per_thread):
                    logger.log(
                        event_type="concurrent_test",
                        data={"thread_id": thread_id, "sequence": i},
                        slot=thread_id,
                    )
                return thread_id

            # Run concurrent writes
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(write_logs, i) for i in range(num_threads)]
                for future in as_completed(futures):
                    future.result()  # Ensure no exceptions

            # Verify all entries are valid JSON and present
            with open(logger.current_log) as f:
                lines = f.readlines()

            assert len(lines) == num_threads * logs_per_thread

            # Each line should be valid JSON
            for line in lines:
                event = json.loads(line)
                assert event["type"] == "concurrent_test"
                assert "thread_id" in event["data"]
                assert "sequence" in event["data"]

    def test_concurrent_log_writes_all_data_preserved(self):
        """Test that all data from concurrent writes is preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(log_dir=tmpdir)
            num_threads = 5
            logs_per_thread = 20

            def write_logs(thread_id: int) -> None:
                for i in range(logs_per_thread):
                    logger.log(
                        event_type="data_integrity",
                        data={"thread_id": thread_id, "value": thread_id * 1000 + i},
                    )

            threads = []
            for i in range(num_threads):
                t = threading.Thread(target=write_logs, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Read and verify all entries
            with open(logger.current_log) as f:
                lines = f.readlines()

            events = [json.loads(line) for line in lines]
            values = {e["data"]["value"] for e in events}

            # All expected values should be present
            expected_values = {
                i * 1000 + j for i in range(num_threads) for j in range(logs_per_thread)
            }
            assert values == expected_values


class TestGetLoggerThreadSafety:
    """Tests for get_logger() thread safety."""

    def test_concurrent_get_logger_returns_same_instance(self):
        """Test that concurrent get_logger calls return the same instance."""
        import telemetry.event_logger as module

        with tempfile.TemporaryDirectory() as tmpdir:
            # Reset global logger
            module._default_logger = None

            instances = []
            lock = threading.Lock()

            def get_instance() -> None:
                # Call without log_dir to get cached instance
                instance = get_logger()
                with lock:
                    instances.append(instance)

            # First call to initialize with log_dir
            first = get_logger(log_dir=tmpdir)

            # Concurrent calls without log_dir should all return the same instance
            threads = []
            for _ in range(20):
                t = threading.Thread(target=get_instance)
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # All instances should be the same
            for instance in instances:
                assert instance is first

    def test_singleton_initialization_race_condition(self):
        """Test that singleton initialization handles race conditions."""
        import telemetry.event_logger as module

        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            os.environ["AUTOPACK_LOG_DIR"] = tmpdir
            instances = []
            lock = threading.Lock()
            barrier = threading.Barrier(10)

            def get_instance_with_barrier() -> None:
                """Try to get logger simultaneously with other threads."""
                barrier.wait()  # Synchronize all threads to start together
                # Call without log_dir to test singleton behavior
                instance = get_logger()
                with lock:
                    instances.append(instance)

            # Reset for each test run
            module._default_logger = None

            threads = []
            for _ in range(10):
                t = threading.Thread(target=get_instance_with_barrier)
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # All instances should be identical (same object)
            first = instances[0]
            for instance in instances:
                assert instance is first

    def test_write_lock_attribute_exists(self):
        """Test that EventLogger has a write lock attribute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(log_dir=tmpdir)
            assert hasattr(logger, "_write_lock")
            assert isinstance(logger._write_lock, type(threading.Lock()))
