import pytest
from src.autopack.research.gatherers.parallel_executor import ParallelExecutor

def test_parallel_executor_success():
    executor = ParallelExecutor(max_workers=2)

    def task():
        return "Task completed"

    results = executor.execute([task, task])
    assert results == ["Task completed", "Task completed"]

def test_parallel_executor_with_exceptions():
    executor = ParallelExecutor(max_workers=2)

    def successful_task():
        return "Success"

    def failing_task():
        raise ValueError("Failure")

    results = executor.execute([successful_task, failing_task])
    assert "Success" in results

def test_parallel_executor_partial_failure():
    executor = ParallelExecutor(max_workers=2)
    attempts = 0

    def partially_failing_task():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Failure")
        return "Recovered"

    results = executor.execute([partially_failing_task, partially_failing_task])
    assert results == ["Recovered", "Recovered"]
