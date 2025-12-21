"""Parallel Executor Module

This module provides functionality to execute tasks in parallel.
"""

import concurrent.futures
import logging

logger = logging.getLogger(__name__)

class ParallelExecutor:
    """Executes tasks in parallel using a thread pool."""

    def __init__(self, max_workers=5):
        self.max_workers = max_workers

    def execute(self, tasks):
        """Executes a list of tasks in parallel.

        Args:
            tasks (list): A list of callables representing the tasks to execute.

        Returns:
            list: A list of results from the executed tasks.
        """
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {executor.submit(task): task for task in tasks}
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Task {task} generated an exception: {e}")
        return results

    def execute_with_callback(self, tasks, callback):
        """Executes tasks in parallel and applies a callback to each result.

        Args:
            tasks (list): A list of callables representing the tasks to execute.
            callback (callable): A function to apply to each result.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {executor.submit(task): task for task in tasks}
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    callback(result)
                except Exception as e:
                    logger.error(f"Task {task} generated an exception: {e}")
