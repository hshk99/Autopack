from concurrent.futures import ThreadPoolExecutor, as_completed

class ParallelExecutor:
    """Executes tasks in parallel using a thread pool."""

    def __init__(self, max_workers=5):
        self.max_workers = max_workers

    def execute(self, tasks):
        """Executes a list of tasks in parallel.

        Args:
            tasks (list): A list of callables to execute.

        Returns:
            list: Results of the executed tasks.
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
                    print(f"Task {task} generated an exception: {e}")
        return results

def sample_task():
    """Sample task function."""
    return "Task completed"

executor = ParallelExecutor()
executor.execute([sample_task for _ in range(10)])
