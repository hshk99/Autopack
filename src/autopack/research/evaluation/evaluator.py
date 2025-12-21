"""Evaluator module for the tracer bullet pipeline."""

from tracer_bullet.orchestrator import run_pipeline

def evaluate_pipeline(url: str, expression: str, prompt: str) -> dict:
    """
    Evaluates the tracer bullet pipeline with given inputs.

    Args:
        url (str): The URL to fetch and parse.
        expression (str): The mathematical expression to compile and evaluate.
        prompt (str): The prompt to check for injection.

    Returns:
        dict: Results of the pipeline execution.
    """
    return run_pipeline(url, expression, prompt)

if __name__ == "__main__":
    # Example evaluation
    url = "https://example.com"
    expression = "2 + 3 * (4 - 1)"
    prompt = "SELECT * FROM users WHERE username = 'admin';"

    evaluation_results = evaluate_pipeline(url, expression, prompt)
    print(f"Evaluation results: {evaluation_results}")

# Note: This evaluator is a simple wrapper around the orchestrator to demonstrate
# how the pipeline can be evaluated with different inputs. In a production environment,
# consider adding more sophisticated evaluation metrics and logging.
