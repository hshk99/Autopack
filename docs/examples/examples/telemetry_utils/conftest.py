"""Pytest configuration and fixtures for telemetry_utils tests.

This module provides shared fixtures and configuration for all test modules
in the telemetry_utils package.
"""

import pytest
from typing import List


@pytest.fixture
def simple_strings() -> List[str]:
    """Provide a list of simple test strings.
    
    Returns:
        A list of simple strings for testing
    """
    return [
        "hello world",
        "python programming",
        "the quick brown fox",
        "test case",
        "simple string"
    ]


@pytest.fixture
def delimiter_strings() -> List[str]:
    """Provide a list of strings with various delimiters.
    
    Returns:
        A list of strings containing different delimiters
    """
    return [
        "hello-world",
        "python_programming",
        "test|case|example",
        "one,two,three",
        "a:b:c:d"
    ]


@pytest.fixture
def palindrome_strings() -> List[str]:
    """Provide a list of palindrome strings.
    
    Returns:
        A list of palindrome strings
    """
    return [
        "racecar",
        "level",
        "noon",
        "radar",
        "civic",
        "madam",
        "refer"
    ]


@pytest.fixture
def long_string() -> str:
    """Provide a long string for performance testing.
    
    Returns:
        A long string for testing
    """
    return "a" * 1000 + "b" * 1000 + "c" * 1000


@pytest.fixture
def empty_string() -> str:
    """Provide an empty string.
    
    Returns:
        An empty string
    """
    return ""


@pytest.fixture
def special_char_strings() -> List[str]:
    """Provide strings with special characters.
    
    Returns:
        A list of strings containing special characters
    """
    return [
        "hello, world!",
        "test@example.com",
        "price: $19.99",
        "100% complete",
        "question?",
        "exclamation!",
        "#hashtag"
    ]


@pytest.fixture
def numeric_strings() -> List[str]:
    """Provide strings with numbers.
    
    Returns:
        A list of strings containing numbers
    """
    return [
        "test123",
        "abc123def",
        "12345",
        "version 2.0",
        "python3"
    ]


@pytest.fixture
def mixed_case_strings() -> List[str]:
    """Provide strings with mixed case.
    
    Returns:
        A list of mixed case strings
    """
    return [
        "HeLLo WoRLd",
        "PyThOn",
        "TeSt CaSe",
        "MiXeD",
        "CamelCase"
    ]


@pytest.fixture
def unicode_strings() -> List[str]:
    """Provide strings with unicode characters.
    
    Returns:
        A list of strings containing unicode characters
    """
    return [
        "café",
        "naïve",
        "résumé",
        "hello🌍",
        "test™",
        "©2024"
    ]


@pytest.fixture
def whitespace_strings() -> List[str]:
    """Provide strings with various whitespace.
    
    Returns:
        A list of strings with different whitespace patterns
    """
    return [
        "  hello  ",
        "\thello\tworld\t",
        "hello\nworld",
        "test  multiple  spaces",
        "   "
    ]


@pytest.fixture(autouse=True)
def reset_test_state():
    """Reset any test state before each test.
    
    This fixture runs automatically before each test to ensure
    a clean state.
    """
    # Setup: runs before each test
    yield
    # Teardown: runs after each test
    # Add any cleanup code here if needed
    pass


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers.
    
    Args:
        config: Pytest configuration object
    """
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically.
    
    Args:
        config: Pytest configuration object
        items: List of collected test items
    """
    for item in items:
        # Add 'unit' marker to all tests by default
        if "integration" not in item.keywords:
            item.add_marker(pytest.mark.unit)
