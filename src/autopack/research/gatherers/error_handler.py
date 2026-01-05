class ErrorHandler:
    """Handles errors for gatherers with retry logic and logging."""

    def __init__(self, max_retries=3):
        self.max_retries = max_retries

    def handle_error(self, func, *args, **kwargs):
        """Executes a function with error handling and retries.

        Args:
            func (callable): The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function if successful, None otherwise.
        """
        retries = 0
        while retries < self.max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                retries += 1
                print(f"Error occurred: {e}. Retrying {retries}/{self.max_retries}...")
        print("Max retries reached. Operation failed.")
        return None


error_handler = ErrorHandler()
