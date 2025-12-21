"""Meta-auditor module for the tracer bullet pipeline."""

import re

def detect_prompt_injection(prompt: str) -> bool:
    """
    Detects potential prompt injection in a given prompt.

    Args:
        prompt (str): The prompt to analyze.

    Returns:
        bool: True if prompt injection is detected, False otherwise.
    """
    # Simple heuristic to detect suspicious patterns
    injection_patterns = [
        r"(?i)delete\s+from",  # SQL injection pattern
        r"(?i)drop\s+table",  # SQL injection pattern
        r"(?i)shutdown",  # Command injection pattern
        r"(?i)exec\s+",  # Command execution pattern
    ]

    for pattern in injection_patterns:
        if re.search(pattern, prompt):
            return True
    return False

if __name__ == "__main__":
    # Example usage
    prompts = [
        "SELECT * FROM users WHERE username = 'admin';",
        "DROP TABLE students;",
        "echo 'Hello, world!'",
        "Normal prompt without injection."
    ]

    for prompt in prompts:
        if detect_prompt_injection(prompt):
            print(f"Injection detected in prompt: {prompt}")
        else:
            print(f"Prompt is safe: {prompt}")

# Note: This is a basic implementation for demonstration purposes.
# In a production environment, consider using more sophisticated methods
# for detecting and preventing prompt injection.
