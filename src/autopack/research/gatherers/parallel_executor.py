"""Parallel executor with smart batching and rate-limited execution.

This module provides:
- Smart batching: Groups tasks into batches for wave-based execution
- Rate-limited parallel execution: Integrates with RateLimiter to respect API limits
- Configurable concurrency: Control max workers and batch sizes
- Error handling: Graceful handling of task failures with callbacks

IMP-RESEARCH-003: Implements optimized parallelization for research agents
that previously ran 8 discovery agents in sequence due to API rate limits.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .rate_limiter import RateLimiter, RetryBudgetExhausted

logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """Configuration for smart batching execution.

    Attributes:
        batch_size: Number of tasks per batch (default: 3)
        inter_batch_delay_seconds: Delay between batches for rate limiting (default: 1.0)
        rate_limiter: Optional RateLimiter instance for API rate limiting
        max_retries_per_task: Maximum retries for failed tasks (default: 2)
    """

    batch_size: int = 3
    inter_batch_delay_seconds: float = 1.0
    rate_limiter: Optional[RateLimiter] = None
    max_retries_per_task: int = 2


@dataclass
class TaskResult:
    """Result of a single task execution.

    Attributes:
        index: Original index of the task
        success: Whether the task succeeded
        result: Result value if successful
        error: Exception if failed
        retries: Number of retries attempted
    """

    index: int
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    retries: int = 0


@dataclass
class BatchResult:
    """Result of a batch execution.

    Attributes:
        batch_index: Index of the batch
        task_results: Results for each task in the batch
        start_time: When the batch started
        end_time: When the batch completed
    """

    batch_index: int
    task_results: List[TaskResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_seconds(self) -> float:
        """Get batch execution duration."""
        return self.end_time - self.start_time

    @property
    def success_count(self) -> int:
        """Count of successful tasks in batch."""
        return sum(1 for r in self.task_results if r.success)

    @property
    def failure_count(self) -> int:
        """Count of failed tasks in batch."""
        return sum(1 for r in self.task_results if not r.success)


class ParallelExecutor:
    """Executes tasks in parallel with smart batching and rate limiting.

    This executor provides optimized parallel execution for research agents
    that need to respect API rate limits while maximizing throughput.

    Features:
    - Thread pool based parallel execution
    - Smart batching: Groups tasks into waves to prevent rate limit hits
    - Rate-limited execution: Integrates with RateLimiter for API compliance
    - Configurable concurrency and batch sizes
    - Error handling with optional callbacks

    Example usage:
        # Basic usage
        executor = ParallelExecutor(max_workers=5)
        results = executor.execute_tasks(my_func, [(arg1,), (arg2,), (arg3,)])

        # With rate limiting
        batch_config = BatchConfig(
            batch_size=3,
            inter_batch_delay_seconds=2.0,
            rate_limiter=RateLimiter(max_requests_per_hour=100)
        )
        executor = ParallelExecutor(max_workers=3, batch_config=batch_config)
        results = executor.execute_batched(my_func, [(arg1,), (arg2,), ...])
    """

    def __init__(
        self,
        max_workers: int = 5,
        batch_config: Optional[BatchConfig] = None,
    ):
        """Initialize parallel executor.

        Args:
            max_workers: Maximum number of concurrent workers (threads)
            batch_config: Optional configuration for batched execution
        """
        self.max_workers = max_workers
        self.batch_config = batch_config or BatchConfig()

        logger.debug(
            f"[ParallelExecutor] Initialized with max_workers={max_workers}, "
            f"batch_size={self.batch_config.batch_size}"
        )

    def execute(self, tasks: List[Callable]) -> List[Any]:
        """Execute a list of callables in parallel.

        This is the original simple interface for backward compatibility.

        Args:
            tasks: A list of callables (no-argument functions) to execute

        Returns:
            List of results from executed tasks
        """
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {executor.submit(task): task for task in tasks}
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.warning(f"Task {task} generated an exception: {e}")
        return results

    def execute_tasks(
        self,
        func: Callable,
        task_args: List[Tuple],
        task_kwargs: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Any]:
        """Execute a function with multiple argument sets in parallel.

        Results are returned in the same order as input arguments,
        regardless of execution order.

        Args:
            func: The function to execute for each task
            task_args: List of argument tuples, one per task
            task_kwargs: Optional list of keyword argument dicts, one per task

        Returns:
            List of results in the same order as task_args.
            Failed tasks return None.

        Raises:
            ValueError: If task_kwargs provided but length doesn't match task_args
        """
        if not task_args:
            return []

        if task_kwargs is not None and len(task_kwargs) != len(task_args):
            raise ValueError(
                f"task_kwargs length ({len(task_kwargs)}) must match "
                f"task_args length ({len(task_args)})"
            )

        # Initialize results with None (preserves order)
        results: List[Any] = [None] * len(task_args)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks with their indices
            future_to_index: Dict[Any, int] = {}
            for i, args in enumerate(task_args):
                kwargs = task_kwargs[i] if task_kwargs else {}
                future = executor.submit(func, *args, **kwargs)
                future_to_index[future] = i

            # Collect results as they complete
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    logger.warning(f"[ParallelExecutor] Task at index {index} failed: {e}")
                    results[index] = None

        return results

    def execute_with_callback(
        self,
        func: Callable,
        task_args: List[Tuple],
        success_callback: Callable[[int, Any], None],
        error_callback: Optional[Callable[[int, Exception], None]] = None,
        task_kwargs: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Execute tasks with callbacks for success/failure notification.

        This method doesn't return results directly; instead it invokes
        callbacks as tasks complete.

        Args:
            func: The function to execute for each task
            task_args: List of argument tuples, one per task
            success_callback: Called with (index, result) on success
            error_callback: Optional callback with (index, exception) on failure
            task_kwargs: Optional list of keyword argument dicts
        """
        if not task_args:
            return

        if task_kwargs is not None and len(task_kwargs) != len(task_args):
            raise ValueError(
                f"task_kwargs length ({len(task_kwargs)}) must match "
                f"task_args length ({len(task_args)})"
            )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_index: Dict[Any, int] = {}
            for i, args in enumerate(task_args):
                kwargs = task_kwargs[i] if task_kwargs else {}
                future = executor.submit(func, *args, **kwargs)
                future_to_index[future] = i

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    success_callback(index, result)
                except Exception as e:
                    logger.warning(f"[ParallelExecutor] Task at index {index} failed: {e}")
                    if error_callback:
                        error_callback(index, e)

    def execute_batched(
        self,
        func: Callable,
        task_args: List[Tuple],
        task_kwargs: Optional[List[Dict[str, Any]]] = None,
        batch_config: Optional[BatchConfig] = None,
    ) -> List[BatchResult]:
        """Execute tasks in smart batches with rate limiting.

        This method groups tasks into batches and executes them with
        configurable delays between batches to respect API rate limits.

        Args:
            func: The function to execute for each task
            task_args: List of argument tuples, one per task
            task_kwargs: Optional list of keyword argument dicts
            batch_config: Override default batch configuration

        Returns:
            List of BatchResult objects, one per batch
        """
        if not task_args:
            return []

        config = batch_config or self.batch_config

        # Create batches
        batches = self._create_batches(task_args, task_kwargs, config.batch_size)

        logger.info(
            f"[ParallelExecutor] Executing {len(task_args)} tasks in "
            f"{len(batches)} batches (batch_size={config.batch_size})"
        )

        batch_results: List[BatchResult] = []

        for batch_idx, (batch_args, batch_kwargs) in enumerate(batches):
            batch_result = self._execute_batch(
                func=func,
                batch_args=batch_args,
                batch_kwargs=batch_kwargs,
                batch_index=batch_idx,
                config=config,
            )
            batch_results.append(batch_result)

            logger.debug(
                f"[ParallelExecutor] Batch {batch_idx + 1}/{len(batches)} completed: "
                f"{batch_result.success_count} succeeded, {batch_result.failure_count} failed, "
                f"duration={batch_result.duration_seconds:.2f}s"
            )

            # Apply inter-batch delay (except for last batch)
            if batch_idx < len(batches) - 1:
                self._apply_rate_limit_delay(config)

        total_success = sum(br.success_count for br in batch_results)
        total_failure = sum(br.failure_count for br in batch_results)
        logger.info(
            f"[ParallelExecutor] All batches completed: "
            f"{total_success} succeeded, {total_failure} failed"
        )

        return batch_results

    def execute_batched_flat(
        self,
        func: Callable,
        task_args: List[Tuple],
        task_kwargs: Optional[List[Dict[str, Any]]] = None,
        batch_config: Optional[BatchConfig] = None,
    ) -> List[Any]:
        """Execute tasks in batches and return flat results list.

        Convenience method that wraps execute_batched and flattens results
        into a simple list in original order.

        Args:
            func: The function to execute for each task
            task_args: List of argument tuples, one per task
            task_kwargs: Optional list of keyword argument dicts
            batch_config: Override default batch configuration

        Returns:
            List of results in original order (None for failed tasks)
        """
        batch_results = self.execute_batched(func, task_args, task_kwargs, batch_config)

        # Flatten results maintaining original order
        results: List[Any] = [None] * len(task_args)
        for batch_result in batch_results:
            for task_result in batch_result.task_results:
                if task_result.success:
                    results[task_result.index] = task_result.result

        return results

    def execute_rate_limited(
        self,
        func: Callable,
        task_args: List[Tuple],
        task_kwargs: Optional[List[Dict[str, Any]]] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> List[Any]:
        """Execute tasks with rate limiting (acquires slot before each task).

        This method checks the rate limiter before each task execution,
        blocking if necessary to stay within rate limits.

        Args:
            func: The function to execute for each task
            task_args: List of argument tuples, one per task
            task_kwargs: Optional list of keyword argument dicts
            rate_limiter: RateLimiter instance (uses batch_config's if not provided)

        Returns:
            List of results in original order (None for failed tasks)

        Raises:
            RetryBudgetExhausted: If rate limit errors exhaust retry budget
        """
        if not task_args:
            return []

        limiter = rate_limiter or self.batch_config.rate_limiter

        if task_kwargs is not None and len(task_kwargs) != len(task_args):
            raise ValueError(
                f"task_kwargs length ({len(task_kwargs)}) must match "
                f"task_args length ({len(task_args)})"
            )

        results: List[Any] = [None] * len(task_args)

        def rate_limited_task(index: int, args: Tuple, kwargs: Dict) -> Tuple[int, Any]:
            """Wrapper that acquires rate limit slot before execution."""
            if limiter:
                limiter.acquire(block=True)

            try:
                result = func(*args, **kwargs)
                if limiter:
                    limiter.record_success()
                return (index, result)
            except Exception as e:
                # Check if it's a rate limit error (429-like)
                if limiter and _is_rate_limit_error(e):
                    limiter.handle_rate_limit_error(wait=True)
                raise

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i, args in enumerate(task_args):
                kwargs = task_kwargs[i] if task_kwargs else {}
                future = executor.submit(rate_limited_task, i, args, kwargs)
                futures.append(future)

            for future in as_completed(futures):
                try:
                    index, result = future.result()
                    results[index] = result
                except RetryBudgetExhausted:
                    logger.error("[ParallelExecutor] Retry budget exhausted, stopping execution")
                    raise
                except Exception as e:
                    logger.warning(f"[ParallelExecutor] Task failed: {e}")

        return results

    def _create_batches(
        self,
        task_args: List[Tuple],
        task_kwargs: Optional[List[Dict[str, Any]]],
        batch_size: int,
    ) -> List[Tuple[List[Tuple[int, Tuple]], List[Optional[Dict[str, Any]]]]]:
        """Create batches from task arguments.

        Args:
            task_args: List of argument tuples
            task_kwargs: Optional list of keyword argument dicts
            batch_size: Size of each batch

        Returns:
            List of (batch_args, batch_kwargs) tuples where batch_args
            contains (original_index, args) pairs
        """
        batches = []
        for i in range(0, len(task_args), batch_size):
            batch_end = min(i + batch_size, len(task_args))

            # Include original indices with args
            batch_args = [(j, task_args[j]) for j in range(i, batch_end)]
            batch_kwargs = [task_kwargs[j] for j in range(i, batch_end)] if task_kwargs else None

            batches.append((batch_args, batch_kwargs))

        return batches

    def _execute_batch(
        self,
        func: Callable,
        batch_args: List[Tuple[int, Tuple]],
        batch_kwargs: Optional[List[Dict[str, Any]]],
        batch_index: int,
        config: BatchConfig,
    ) -> BatchResult:
        """Execute a single batch of tasks.

        Args:
            func: Function to execute
            batch_args: List of (original_index, args) tuples
            batch_kwargs: Optional keyword arguments
            batch_index: Index of this batch
            config: Batch configuration

        Returns:
            BatchResult with all task results
        """
        start_time = time.time()
        task_results: List[TaskResult] = []

        # Acquire rate limit slots for all tasks in batch if limiter configured
        if config.rate_limiter:
            for _ in batch_args:
                config.rate_limiter.acquire(block=True)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_data: Dict[Any, Tuple[int, int]] = {}  # future -> (batch_idx, orig_idx)

            for batch_idx, (orig_index, args) in enumerate(batch_args):
                kwargs = batch_kwargs[batch_idx] if batch_kwargs else {}
                future = executor.submit(func, *args, **kwargs)
                future_to_data[future] = (batch_idx, orig_index)

            for future in as_completed(future_to_data):
                batch_idx, orig_index = future_to_data[future]
                try:
                    result = future.result()
                    if config.rate_limiter:
                        config.rate_limiter.record_success()
                    task_results.append(
                        TaskResult(
                            index=orig_index,
                            success=True,
                            result=result,
                        )
                    )
                except Exception as e:
                    logger.warning(
                        f"[ParallelExecutor] Task {orig_index} in batch {batch_index} failed: {e}"
                    )
                    task_results.append(
                        TaskResult(
                            index=orig_index,
                            success=False,
                            error=e,
                        )
                    )

        end_time = time.time()

        return BatchResult(
            batch_index=batch_index,
            task_results=task_results,
            start_time=start_time,
            end_time=end_time,
        )

    def _apply_rate_limit_delay(self, config: BatchConfig) -> None:
        """Apply delay between batches for rate limiting.

        Args:
            config: Batch configuration with delay settings
        """
        delay = config.inter_batch_delay_seconds

        if config.rate_limiter:
            # Check remaining capacity and adjust delay if needed
            remaining = config.rate_limiter.get_remaining_requests()
            if remaining < config.batch_size:
                # Increase delay when running low on capacity
                delay = max(delay, config.inter_batch_delay_seconds * 2)
                logger.info(
                    f"[ParallelExecutor] Low rate limit capacity ({remaining}), "
                    f"increasing delay to {delay:.1f}s"
                )

        if delay > 0:
            logger.debug(f"[ParallelExecutor] Inter-batch delay: {delay:.1f}s")
            time.sleep(delay)


def _is_rate_limit_error(error: Exception) -> bool:
    """Check if an exception represents a rate limit error.

    Args:
        error: The exception to check

    Returns:
        True if this appears to be a rate limit (429) error
    """
    error_str = str(error).lower()
    return any(
        indicator in error_str
        for indicator in ["429", "rate limit", "too many requests", "throttl"]
    )


def sample_task():
    """Sample task function for testing."""
    return "Task completed"


# Only run example when executed directly
if __name__ == "__main__":
    executor = ParallelExecutor()
    results = executor.execute([sample_task for _ in range(10)])
    print(f"Results: {results}")
