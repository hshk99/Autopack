"""String utility functions for text manipulation.

This module provides common string manipulation utilities including
capitalization and reversal operations.
"""

from typing import Optional


def capitalize_words(text: str, delimiter: Optional[str] = None) -> str:
    """Capitalize the first letter of each word in a string.
    
    Args:
        text: The input string to capitalize
        delimiter: Optional delimiter to split words. If None, splits on whitespace.
    
    Returns:
        A new string with each word capitalized
    
    Examples:
        >>> capitalize_words("hello world")
        'Hello World'
        >>> capitalize_words("hello-world", delimiter="-")
        'Hello-World'
        >>> capitalize_words("")
        ''
    """
    if not text:
        return text
    
    if delimiter is None:
        # Use built-in title() for whitespace-delimited words
        return text.title()
    else:
        # Split by custom delimiter, capitalize each part, rejoin
        parts = text.split(delimiter)
        capitalized_parts = [part.capitalize() for part in parts]
        return delimiter.join(capitalized_parts)


def reverse_string(text: str) -> str:
    """Reverse a string.
    
    Args:
        text: The input string to reverse
    
    Returns:
        A new string with characters in reverse order
    
    Examples:
        >>> reverse_string("hello")
        'olleh'
        >>> reverse_string("racecar")
        'racecar'
        >>> reverse_string("")
        ''
        >>> reverse_string("a")
        'a'
    """
    return text[::-1]


if __name__ == "__main__":
    # Simple demonstration
    print("String Utilities Demo")
    print("=" * 40)
    
    # Test capitalize_words
    test_strings = [
        "hello world",
        "python programming",
        "the quick brown fox",
        "hello-world-example"
    ]
    
    print("\nCapitalize Words:")
    for s in test_strings[:-1]:
        result = capitalize_words(s)
        print(f"  '{s}' -> '{result}'")
    
    # Test with delimiter
    s = test_strings[-1]
    result = capitalize_words(s, delimiter="-")
    print(f"  '{s}' (delimiter='-') -> '{result}'")
    
    # Test reverse_string
    print("\nReverse String:")
    for s in test_strings:
        result = reverse_string(s)
        print(f"  '{s}' -> '{result}'")
