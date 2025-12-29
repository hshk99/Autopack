"""String utility functions for text manipulation.

This module provides common string manipulation utilities including:
- capitalize_words: Capitalize the first letter of each word
- reverse_string: Reverse a string
- snake_to_camel: Convert snake_case to camelCase
- truncate: Truncate a string to a maximum length with ellipsis
"""

from typing import Optional


def capitalize_words(text: str) -> str:
    """Capitalize the first letter of each word in the text.
    
    Args:
        text: The input string to capitalize
        
    Returns:
        String with each word capitalized
        
    Examples:
        >>> capitalize_words("hello world")
        'Hello World'
        >>> capitalize_words("the quick brown fox")
        'The Quick Brown Fox'
    """
    if not text:
        return text
    return ' '.join(word.capitalize() for word in text.split())


def reverse_string(text: str) -> str:
    """Reverse the characters in a string.
    
    Args:
        text: The input string to reverse
        
    Returns:
        The reversed string
        
    Examples:
        >>> reverse_string("hello")
        'olleh'
        >>> reverse_string("Python")
        'nohtyP'
    """
    return text[::-1]


def snake_to_camel(snake_str: str, upper_first: bool = False) -> str:
    """Convert snake_case string to camelCase.
    
    Args:
        snake_str: The snake_case string to convert
        upper_first: If True, capitalize the first letter (PascalCase)
        
    Returns:
        The camelCase (or PascalCase) string
        
    Examples:
        >>> snake_to_camel("hello_world")
        'helloWorld'
        >>> snake_to_camel("hello_world", upper_first=True)
        'HelloWorld'
        >>> snake_to_camel("my_variable_name")
        'myVariableName'
    """
    if not snake_str:
        return snake_str
    
    components = snake_str.split('_')
    if not components:
        return snake_str
    
    if upper_first:
        return ''.join(word.capitalize() for word in components)
    else:
        return components[0] + ''.join(word.capitalize() for word in components[1:])


def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate a string to a maximum length, adding a suffix if truncated.
    
    Args:
        text: The input string to truncate
        max_length: Maximum length of the output string (including suffix)
        suffix: String to append when truncating (default: "...")
        
    Returns:
        The truncated string with suffix, or original if shorter than max_length
        
    Examples:
        >>> truncate("Hello, World!", 10)
        'Hello, ...'
        >>> truncate("Short", 10)
        'Short'
        >>> truncate("This is a long string", 15, suffix="…")
        'This is a lon…'
    """
    if len(text) <= max_length:
        return text
    
    if max_length <= len(suffix):
        return suffix[:max_length]
    
    truncate_at = max_length - len(suffix)
    return text[:truncate_at] + suffix
