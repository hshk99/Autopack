"""Tests for ParallelExecutor module."""

import pytest
import time
from autopack.research.gatherers.parallel_executor import ParallelExecutor


class TestParallelExecutor:
    """Test cases for ParallelExecutor."""

    def test_initialization(self):
        """Test parallel executor initialization."""
        executor = ParallelExecutor(max_workers=10)
        assert executor.max_workers == 10

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
        executor.execute_with_callback(
            maybe_fail,
            task_args,
            success_callback,
            error_callback
        )
        
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
