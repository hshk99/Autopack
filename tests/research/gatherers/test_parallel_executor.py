"""Tests for ParallelExecutor module."""

import time

import pytest

from autopack.research.gatherers.parallel_executor import (
    BatchConfig,
    BatchResult,
    ParallelExecutor,
    TaskResult,
)
from autopack.research.gatherers.rate_limiter import RateLimiter


class TestParallelExecutor:
    """Test cases for ParallelExecutor."""

    def test_initialization(self):
        """Test parallel executor initialization."""
        executor = ParallelExecutor(max_workers=10)
        assert executor.max_workers == 10

    def test_initialization_with_batch_config(self):
        """Test initialization with custom batch config."""
        config = BatchConfig(batch_size=5, inter_batch_delay_seconds=2.0)
        executor = ParallelExecutor(max_workers=10, batch_config=config)
        assert executor.max_workers == 10
        assert executor.batch_config.batch_size == 5
        assert executor.batch_config.inter_batch_delay_seconds == 2.0

    def test_execute_tasks_success(self):
        """Test successful execution of multiple tasks."""
        executor = ParallelExecutor(max_workers=3)

        def square(x):
            return x * x

        task_args = [(2,), (3,), (4,), (5,)]
        results = executor.execute_tasks(square, task_args)

        assert results == [4, 9, 16, 25]

    def test_execute_tasks_with_kwargs(self):
        """Test execution with keyword arguments."""
        executor = ParallelExecutor(max_workers=2)

        def add(a, b, c=0):
            return a + b + c

        task_args = [(1, 2), (3, 4)]
        task_kwargs = [{"c": 10}, {"c": 20}]
        results = executor.execute_tasks(add, task_args, task_kwargs)

        assert results == [13, 27]

    def test_execute_tasks_with_failures(self):
        """Test execution with some failing tasks."""
        executor = ParallelExecutor(max_workers=2)

        def maybe_fail(x):
            if x == 3:
                raise ValueError("Failed on 3")
            return x * 2

        task_args = [(1,), (2,), (3,), (4,)]
        results = executor.execute_tasks(maybe_fail, task_args)

        # Failed task should return None
        assert results == [2, 4, None, 8]

    def test_execute_tasks_maintains_order(self):
        """Test that results maintain the order of input tasks."""
        executor = ParallelExecutor(max_workers=3)

        def slow_func(x, delay):
            time.sleep(delay)
            return x

        # Tasks with different delays - later tasks finish first
        task_args = [(1, 0.3), (2, 0.1), (3, 0.2)]
        results = executor.execute_tasks(slow_func, task_args)

        # Results should still be in original order
        assert results == [1, 2, 3]

    def test_execute_with_callback_success(self):
        """Test execution with success callbacks."""
        executor = ParallelExecutor(max_workers=2)

        def square(x):
            return x * x

        results = []

        def callback(index, result):
            results.append((index, result))

        task_args = [(2,), (3,), (4,)]
        executor.execute_with_callback(square, task_args, callback)

        # Sort by index to ensure consistent order
        results.sort(key=lambda x: x[0])
        assert results == [(0, 4), (1, 9), (2, 16)]

    def test_execute_with_callback_errors(self):
        """Test execution with error callbacks."""
        executor = ParallelExecutor(max_workers=2)

        def maybe_fail(x):
            if x == 3:
                raise ValueError("Failed on 3")
            return x * 2

        successes = []
        errors = []

        def success_callback(index, result):
            successes.append((index, result))

        def error_callback(index, exception):
            errors.append((index, str(exception)))

        task_args = [(1,), (2,), (3,), (4,)]
        executor.execute_with_callback(maybe_fail, task_args, success_callback, error_callback)

        # Sort for consistent order
        successes.sort(key=lambda x: x[0])
        errors.sort(key=lambda x: x[0])

        assert len(successes) == 3
        assert len(errors) == 1
        assert errors[0][0] == 2  # Index of failed task

    def test_execute_tasks_empty_list(self):
        """Test execution with empty task list."""
        executor = ParallelExecutor(max_workers=2)

        def dummy(x):
            return x

        results = executor.execute_tasks(dummy, [])
        assert results == []

    def test_execute_tasks_single_task(self):
        """Test execution with a single task."""
        executor = ParallelExecutor(max_workers=2)

        def square(x):
            return x * x

        results = executor.execute_tasks(square, [(5,)])
        assert results == [25]

    def test_max_workers_limit(self):
        """Test that max_workers limits concurrent execution."""
        executor = ParallelExecutor(max_workers=2)

        active_count = [0]
        max_active = [0]

        def track_concurrency(x):
            active_count[0] += 1
            max_active[0] = max(max_active[0], active_count[0])
            time.sleep(0.1)
            active_count[0] -= 1
            return x

        task_args = [(i,) for i in range(10)]
        executor.execute_tasks(track_concurrency, task_args)

        # Max active should not exceed max_workers
        assert max_active[0] <= 2

    def test_kwargs_length_mismatch(self):
        """Test that mismatched args and kwargs lengths raise an error."""
        executor = ParallelExecutor(max_workers=2)

        def dummy(x, y=0):
            return x + y

        task_args = [(1,), (2,), (3,)]
        task_kwargs = [{"y": 1}, {"y": 2}]  # Wrong length

        with pytest.raises(ValueError):
            executor.execute_tasks(dummy, task_args, task_kwargs)


class TestBatchedExecution:
    """Test cases for batched execution."""

    def test_execute_batched_basic(self):
        """Test basic batched execution."""
        config = BatchConfig(batch_size=2, inter_batch_delay_seconds=0.0)
        executor = ParallelExecutor(max_workers=2, batch_config=config)

        def square(x):
            return x * x

        task_args = [(1,), (2,), (3,), (4,), (5,)]
        batch_results = executor.execute_batched(square, task_args)

        # Should have 3 batches: [1,2], [3,4], [5]
        assert len(batch_results) == 3
        assert batch_results[0].batch_index == 0
        assert batch_results[1].batch_index == 1
        assert batch_results[2].batch_index == 2

        # All tasks should succeed
        total_success = sum(br.success_count for br in batch_results)
        assert total_success == 5

    def test_execute_batched_flat(self):
        """Test batched execution with flat results."""
        config = BatchConfig(batch_size=2, inter_batch_delay_seconds=0.0)
        executor = ParallelExecutor(max_workers=2, batch_config=config)

        def square(x):
            return x * x

        task_args = [(1,), (2,), (3,), (4,)]
        results = executor.execute_batched_flat(square, task_args)

        assert results == [1, 4, 9, 16]

    def test_execute_batched_with_failures(self):
        """Test batched execution handles failures correctly."""
        config = BatchConfig(batch_size=2, inter_batch_delay_seconds=0.0)
        executor = ParallelExecutor(max_workers=2, batch_config=config)

        def maybe_fail(x):
            if x == 3:
                raise ValueError("Failed on 3")
            return x * 2

        task_args = [(1,), (2,), (3,), (4,)]
        results = executor.execute_batched_flat(maybe_fail, task_args)

        # Failed task at index 2 should be None
        assert results == [2, 4, None, 8]

    def test_execute_batched_inter_batch_delay(self):
        """Test that inter-batch delay is applied."""
        config = BatchConfig(batch_size=2, inter_batch_delay_seconds=0.1)
        executor = ParallelExecutor(max_workers=2, batch_config=config)

        def identity(x):
            return x

        task_args = [(i,) for i in range(6)]  # 3 batches

        start_time = time.time()
        executor.execute_batched(identity, task_args)
        elapsed = time.time() - start_time

        # Should have at least 2 delays (between batches 0-1 and 1-2)
        assert elapsed >= 0.2

    def test_execute_batched_empty_list(self):
        """Test batched execution with empty list."""
        executor = ParallelExecutor(max_workers=2)

        def dummy(x):
            return x

        results = executor.execute_batched(dummy, [])
        assert results == []

    def test_batch_result_properties(self):
        """Test BatchResult computed properties."""
        result = BatchResult(
            batch_index=0,
            task_results=[
                TaskResult(index=0, success=True, result=1),
                TaskResult(index=1, success=True, result=2),
                TaskResult(index=2, success=False, error=ValueError("test")),
            ],
            start_time=100.0,
            end_time=105.0,
        )

        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.duration_seconds == 5.0


class TestRateLimitedExecution:
    """Test cases for rate-limited execution."""

    def test_execute_rate_limited_basic(self):
        """Test basic rate-limited execution."""
        rate_limiter = RateLimiter(max_requests_per_hour=100)
        executor = ParallelExecutor(max_workers=2)

        def square(x):
            return x * x

        task_args = [(1,), (2,), (3,)]
        results = executor.execute_rate_limited(square, task_args, rate_limiter=rate_limiter)

        assert results == [1, 4, 9]

    def test_execute_rate_limited_with_batch_config(self):
        """Test rate-limited execution using batch config's rate limiter."""
        rate_limiter = RateLimiter(max_requests_per_hour=100)
        config = BatchConfig(rate_limiter=rate_limiter)
        executor = ParallelExecutor(max_workers=2, batch_config=config)

        def square(x):
            return x * x

        task_args = [(1,), (2,), (3,)]
        results = executor.execute_rate_limited(square, task_args)

        assert results == [1, 4, 9]

    def test_execute_rate_limited_empty_list(self):
        """Test rate-limited execution with empty list."""
        rate_limiter = RateLimiter(max_requests_per_hour=100)
        executor = ParallelExecutor(max_workers=2)

        def dummy(x):
            return x

        results = executor.execute_rate_limited(dummy, [], rate_limiter=rate_limiter)
        assert results == []

    def test_execute_rate_limited_kwargs_mismatch(self):
        """Test that kwargs mismatch raises error."""
        rate_limiter = RateLimiter(max_requests_per_hour=100)
        executor = ParallelExecutor(max_workers=2)

        def dummy(x, y=0):
            return x + y

        task_args = [(1,), (2,), (3,)]
        task_kwargs = [{"y": 1}]  # Wrong length

        with pytest.raises(ValueError):
            executor.execute_rate_limited(
                dummy, task_args, task_kwargs=task_kwargs, rate_limiter=rate_limiter
            )


class TestTaskResult:
    """Test cases for TaskResult dataclass."""

    def test_task_result_success(self):
        """Test TaskResult for successful task."""
        result = TaskResult(index=0, success=True, result=42)
        assert result.index == 0
        assert result.success is True
        assert result.result == 42
        assert result.error is None
        assert result.retries == 0

    def test_task_result_failure(self):
        """Test TaskResult for failed task."""
        error = ValueError("test error")
        result = TaskResult(index=1, success=False, error=error, retries=2)
        assert result.index == 1
        assert result.success is False
        assert result.result is None
        assert result.error == error
        assert result.retries == 2


class TestBatchConfig:
    """Test cases for BatchConfig dataclass."""

    def test_batch_config_defaults(self):
        """Test BatchConfig default values."""
        config = BatchConfig()
        assert config.batch_size == 3
        assert config.inter_batch_delay_seconds == 1.0
        assert config.rate_limiter is None
        assert config.max_retries_per_task == 2

    def test_batch_config_custom(self):
        """Test BatchConfig with custom values."""
        rate_limiter = RateLimiter(max_requests_per_hour=50)
        config = BatchConfig(
            batch_size=5,
            inter_batch_delay_seconds=2.5,
            rate_limiter=rate_limiter,
            max_retries_per_task=3,
        )
        assert config.batch_size == 5
        assert config.inter_batch_delay_seconds == 2.5
        assert config.rate_limiter == rate_limiter
        assert config.max_retries_per_task == 3


class TestLegacyExecuteMethod:
    """Test cases for the legacy execute() method (backward compatibility)."""

    def test_execute_legacy_interface(self):
        """Test the original execute() method with callables."""
        executor = ParallelExecutor(max_workers=3)

        def task():
            return "done"

        tasks = [task for _ in range(5)]
        results = executor.execute(tasks)

        assert len(results) == 5
        assert all(r == "done" for r in results)

    def test_execute_legacy_with_failures(self):
        """Test legacy execute handles failures."""
        executor = ParallelExecutor(max_workers=2)

        call_count = [0]

        def maybe_fail():
            call_count[0] += 1
            if call_count[0] == 2:
                raise ValueError("Failed")
            return call_count[0]

        tasks = [maybe_fail for _ in range(3)]
        results = executor.execute(tasks)

        # Should have results, but one less due to failure
        assert len(results) == 2
