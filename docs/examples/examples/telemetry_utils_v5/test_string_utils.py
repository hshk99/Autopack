"""Pytest tests for string_utils module.

This module contains comprehensive tests for all string utility functions
including capitalize_words, reverse_string, snake_to_camel, and truncate.
"""

from examples.telemetry_utils_v5.string_utils import (
    capitalize_words,
    reverse_string,
    snake_to_camel,
    truncate,
)


class TestCapitalizeWords:
    """Tests for capitalize_words function."""
    
    def test_capitalize_basic(self):
        """Test basic word capitalization."""
        assert capitalize_words("hello world") == "Hello World"
    
    def test_capitalize_multiple_words(self):
        """Test capitalization with multiple words."""
        assert capitalize_words("the quick brown fox") == "The Quick Brown Fox"
    
    def test_capitalize_empty_string(self):
        """Test capitalization with empty string."""
        assert capitalize_words("") == ""
    
    def test_capitalize_single_word(self):
        """Test capitalization with single word."""
        assert capitalize_words("python") == "Python"
    
    def test_capitalize_already_capitalized(self):
        """Test capitalization with already capitalized text."""
        assert capitalize_words("Hello World") == "Hello World"


class TestReverseString:
    """Tests for reverse_string function."""
    
    def test_reverse_basic(self):
        """Test basic string reversal."""
        assert reverse_string("hello") == "olleh"
    
    def test_reverse_with_spaces(self):
        """Test reversal with spaces."""
        assert reverse_string("hello world") == "dlrow olleh"
    
    def test_reverse_empty_string(self):
        """Test reversal with empty string."""
        assert reverse_string("") == ""
    
    def test_reverse_single_char(self):
        """Test reversal with single character."""
        assert reverse_string("a") == "a"
    
    def test_reverse_palindrome(self):
        """Test reversal with palindrome."""
        assert reverse_string("racecar") == "racecar"


class TestSnakeToCamel:
    """Tests for snake_to_camel function."""
    
    def test_snake_to_camel_basic(self):
        """Test basic snake_case to camelCase conversion."""
        assert snake_to_camel("hello_world") == "helloWorld"
    
    def test_snake_to_camel_pascal_case(self):
        """Test snake_case to PascalCase conversion."""
        assert snake_to_camel("hello_world", upper_first=True) == "HelloWorld"
    
    def test_snake_to_camel_multiple_underscores(self):
        """Test conversion with multiple underscores."""
        assert snake_to_camel("my_variable_name") == "myVariableName"
    
    def test_snake_to_camel_empty_string(self):
        """Test conversion with empty string."""
        assert snake_to_camel("") == ""
    
    def test_snake_to_camel_no_underscores(self):
        """Test conversion with no underscores."""
        assert snake_to_camel("hello") == "hello"
        assert snake_to_camel("hello", upper_first=True) == "Hello"


class TestTruncate:
    """Tests for truncate function."""
    
    def test_truncate_basic(self):
        """Test basic truncation."""
        assert truncate("Hello, World!", 10) == "Hello, ..."
    
    def test_truncate_no_truncation_needed(self):
        """Test when string is shorter than max_length."""
        assert truncate("Short", 10) == "Short"
    
    def test_truncate_custom_suffix(self):
        """Test truncation with custom suffix."""
        assert truncate("This is a long string", 15, suffix="…") == "This is a lon…"
    
    def test_truncate_exact_length(self):
        """Test when string is exactly max_length."""
        assert truncate("Hello", 5) == "Hello"
    
    def test_truncate_suffix_longer_than_max(self):
        """Test when suffix is longer than max_length."""
        result = truncate("Hello, World!", 2, suffix="...")
        assert result == ".."
        assert len(result) == 2
