"""Orchestrator module for the tracer bullet pipeline."""

from .compiler import compile_expression
from .gatherer import fetch_web_content, parse_html_content
from .meta_auditor import detect_prompt_injection

def run_pipeline(url: str, expression: str, prompt: str):
    """
    Runs the complete tracer bullet pipeline.

    Args:
        url (str): The URL to fetch and parse.
        expression (str): The mathematical expression to compile and evaluate.
        prompt (str): The prompt to check for injection.

    Returns:
        dict: Results of the pipeline execution.
    """
    results = {}

    # Step 1: Web scraping
    try:
        html_content = fetch_web_content(url)
        structured_data = parse_html_content(html_content)
        results['web_scraping'] = structured_data
    except Exception as e:
        results['web_scraping_error'] = str(e)

    # Step 2: Compile and evaluate expression
    try:
        calculation_result = compile_expression(expression)
        results['calculation'] = calculation_result
    except Exception as e:
        results['calculation_error'] = str(e)

    # Step 3: Prompt injection detection
    if detect_prompt_injection(prompt):
        results['prompt_injection'] = "Detected"
    else:
        results['prompt_injection'] = "Safe"

    return results

if __name__ == "__main__":
    # Example usage
    url = "https://example.com"
    expression = "2 + 3 * (4 - 1)"
    prompt = "SELECT * FROM users WHERE username = 'admin';"

    pipeline_results = run_pipeline(url, expression, prompt)
    print(f"Pipeline results: {pipeline_results}")

# Note: This orchestrator demonstrates a simple end-to-end pipeline.
# In a production environment, consider adding logging, error handling,
# and integration with other systems as needed.
