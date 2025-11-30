"""Utility functions for Autopack framework."""

def format_token_count(token_count: int) -> str:
    """Format token count into a human-readable string.

    Args:
        token_count: The number of tokens as an integer.

    Returns:
        A formatted string representing the token count.
        - If token_count < 1000, returns "<token_count> tokens".
        - If 1000 <= token_count < 1,000,000, returns "<x.x>K tokens".
        - If token_count >= 1,000,000, returns "<x.x>M tokens".
    """
    if token_count < 1000:
        return f"{token_count} tokens"
    elif token_count < 1000000:
        return f"{token_count / 1000:.1f}K tokens"
    else:
        return f"{token_count / 1000000:.1f}M tokens"

# Example usage:
# print(format_token_count(1500))  # Output: "1.5K tokens"
