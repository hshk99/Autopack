"""Parallel Executor Module

This module provides functionality to execute tasks in parallel.
"""

import concurrent.futures
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ParallelExecutor:
    """Executes tasks in parallel using a thread pool."""

    def __init__(self, max_workers: int = 5):
        """Initialize parallel executor.

        Args:
            max_workers: Maximum number of worker threads
        """
        self.max_workers = max_workers
        logger.info(f"ParallelExecutor initialized with {max_workers} workers")

    def execute_tasks(
        self,
        func: Callable[..., Any],
        task_args: List[Tuple[Any, ...]],
        task_kwargs: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Any]:
        """Execute multiple tasks in parallel.

        Args:
            func: Function to execute for each task
            task_args: List of argument tuples, one per task
            task_kwargs: Optional list of keyword argument dicts, one per task

        Returns:
            List of results from each task execution
        """
        if task_kwargs is None:
            task_kwargs = [{}] * len(task_args)

        if len(task_args) != len(task_kwargs):
            raise ValueError("task_args and task_kwargs must have the same length")

        results = []
        failed_tasks = []

        logger.info(f"Executing {len(task_args)} tasks in parallel with {self.max_workers} workers")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(func, *args, **kwargs): i
                for i, (args, kwargs) in enumerate(zip(task_args, task_kwargs))
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    results.append((index, result))
                    logger.debug(f"Task {index} completed successfully")
                except Exception as e:
                    logger.error(f"Task {index} failed: {str(e)}")
                    failed_tasks.append((index, e))
                    results.append((index, None))

        # Sort results by original index to maintain order
        results.sort(key=lambda x: x[0])

        if failed_tasks:
            logger.warning(f"{len(failed_tasks)} tasks failed out of {len(task_args)}")
        else:
            logger.info(f"All {len(task_args)} tasks completed successfully")

        return [result for _, result in results]

    def execute_with_callback(
        self,
        func: Callable[..., Any],
        task_args: List[Tuple[Any, ...]],
        callback: Callable[[int, Any], None],
        error_callback: Optional[Callable[[int, Exception], None]] = None,
    ) -> None:
        """Execute tasks in parallel with callbacks for each completion.

        Args:
            func: Function to execute for each task
            task_args: List of argument tuples, one per task
            callback: Function called with (index, result) when a task succeeds
            error_callback: Optional function called with (index, exception) when a task fails
        """
        logger.info(f"Executing {len(task_args)} tasks with callbacks")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_index = {executor.submit(func, *args): i for i, args in enumerate(task_args)}

            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    callback(index, result)
                except Exception as e:
                    logger.error(f"Task {index} failed: {str(e)}")
                    if error_callback:
                        error_callback(index, e)
