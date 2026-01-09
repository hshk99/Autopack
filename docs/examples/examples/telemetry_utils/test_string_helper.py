"""Comprehensive tests for string_helper module.

This module provides comprehensive test coverage for the string_helper module,
including tests for capitalize_words and reverse_string functions.
"""

from examples.telemetry_utils.string_helper import capitalize_words, reverse_string


class TestCapitalizeWords:
    """Test suite for capitalize_words function."""

    def test_capitalize_simple_words(self, simple_strings):
        """Test capitalizing simple whitespace-separated words."""
        assert capitalize_words("hello world") == "Hello World"
        assert capitalize_words("python programming") == "Python Programming"
        assert capitalize_words("the quick brown fox") == "The Quick Brown Fox"

    def test_capitalize_empty_string(self):
        """Test capitalizing an empty string."""
        assert capitalize_words("") == ""

    def test_capitalize_single_word(self):
        """Test capitalizing a single word."""
        assert capitalize_words("hello") == "Hello"
        assert capitalize_words("WORLD") == "World"
        assert capitalize_words("PyThOn") == "Python"

    def test_capitalize_with_custom_delimiter(self, delimiter_strings):
        """Test capitalizing with custom delimiter."""
        assert capitalize_words("hello-world", delimiter="-") == "Hello-World"
        assert capitalize_words("python-programming-language", delimiter="-") == "Python-Programming-Language"
        assert capitalize_words("one_two_three", delimiter="_") == "One_Two_Three"

    def test_capitalize_with_multiple_spaces(self):
        """Test capitalizing with multiple consecutive spaces."""
        result = capitalize_words("hello  world")
        assert "Hello" in result
        assert "World" in result

    def test_capitalize_with_numbers(self):
        """Test capitalizing strings containing numbers."""
        assert capitalize_words("test 123 case") == "Test 123 Case"
        assert capitalize_words("python3 rocks") == "Python3 Rocks"

    def test_capitalize_with_special_chars(self):
        """Test capitalizing strings with special characters."""
        result = capitalize_words("hello, world!")
        assert "Hello" in result
        assert "World" in result

    def test_capitalize_already_capitalized(self):
        """Test capitalizing already capitalized strings."""
        assert capitalize_words("Hello World") == "Hello World"
        assert capitalize_words("HELLO WORLD") == "Hello World"

    def test_capitalize_mixed_case(self):
        """Test capitalizing mixed case strings."""
        assert capitalize_words("hElLo WoRlD") == "Hello World"
        assert capitalize_words("pYtHoN") == "Python"

    def test_capitalize_with_none_delimiter(self):
        """Test that None delimiter uses default whitespace splitting."""
        assert capitalize_words("hello world", delimiter=None) == "Hello World"

    def test_capitalize_delimiter_not_in_string(self):
        """Test capitalizing when delimiter is not present in string."""
        assert capitalize_words("hello world", delimiter="-") == "Hello world"

    def test_capitalize_single_char_words(self):
        """Test capitalizing single character words."""
        assert capitalize_words("a b c") == "A B C"
        assert capitalize_words("i am a developer") == "I Am A Developer"


class TestReverseString:
    """Test suite for reverse_string function."""

    def test_reverse_simple_string(self, simple_strings):
        """Test reversing simple strings."""
        assert reverse_string("hello") == "olleh"
        assert reverse_string("world") == "dlrow"
        assert reverse_string("python") == "nohtyp"

    def test_reverse_empty_string(self):
        """Test reversing an empty string."""
        assert reverse_string("") == ""

    def test_reverse_single_char(self):
        """Test reversing a single character."""
        assert reverse_string("a") == "a"
        assert reverse_string("Z") == "Z"
        assert reverse_string("5") == "5"

    def test_reverse_palindrome(self, palindrome_strings):
        """Test reversing palindromes (should equal original)."""
        assert reverse_string("racecar") == "racecar"
        assert reverse_string("level") == "level"
        assert reverse_string("noon") == "noon"
        assert reverse_string("radar") == "radar"

    def test_reverse_with_spaces(self):
        """Test reversing strings with spaces."""
        assert reverse_string("hello world") == "dlrow olleh"
        assert reverse_string("a b c") == "c b a"

    def test_reverse_with_numbers(self):
        """Test reversing strings with numbers."""
        assert reverse_string("abc123") == "321cba"
        assert reverse_string("12345") == "54321"

    def test_reverse_with_special_chars(self):
        """Test reversing strings with special characters."""
        assert reverse_string("hello!") == "!olleh"
        assert reverse_string("a-b-c") == "c-b-a"
        assert reverse_string("test@123") == "321@tset"

    def test_reverse_mixed_case(self):
        """Test reversing mixed case strings."""
        assert reverse_string("HeLLo") == "oLLeH"
        assert reverse_string("PyThOn") == "nOhTyP"

    def test_reverse_unicode(self):
        """Test reversing unicode strings."""
        assert reverse_string("café") == "éfac"
        assert reverse_string("hello🌍") == "🌍olleh"

    def test_reverse_twice_returns_original(self):
        """Test that reversing twice returns the original string."""
        original = "hello world"
        assert reverse_string(reverse_string(original)) == original
        
        original = "test123"
        assert reverse_string(reverse_string(original)) == original

    def test_reverse_long_string(self, long_string):
        """Test reversing a long string."""
        reversed_str = reverse_string(long_string)
        assert len(reversed_str) == len(long_string)
        assert reversed_str == long_string[::-1]


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_capitalize_then_reverse(self):
        """Test capitalizing then reversing a string."""
        text = "hello world"
        capitalized = capitalize_words(text)
        reversed_text = reverse_string(capitalized)
        assert reversed_text == "dlroW olleH"

    def test_reverse_then_capitalize(self):
        """Test reversing then capitalizing a string."""
        text = "hello world"
        reversed_text = reverse_string(text)
        capitalized = capitalize_words(reversed_text)
        assert capitalized == "Dlrow Olleh"

    def test_multiple_operations(self):
        """Test multiple operations in sequence."""
        text = "python programming"
        # Capitalize
        result = capitalize_words(text)
        assert result == "Python Programming"
        # Reverse
        result = reverse_string(result)
        assert result == "gnimmargorP nohtyP"
        # Reverse back
        result = reverse_string(result)
        assert result == "Python Programming"

    def test_delimiter_operations(self):
        """Test operations with custom delimiters."""
        text = "hello-world-test"
        capitalized = capitalize_words(text, delimiter="-")
        assert capitalized == "Hello-World-Test"
        reversed_text = reverse_string(capitalized)
        assert reversed_text == "tseT-dlroW-olleH"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_whitespace_only(self):
        """Test strings with only whitespace."""
        assert capitalize_words("   ") == "   "
        assert reverse_string("   ") == "   "

    def test_newlines_and_tabs(self):
        """Test strings with newlines and tabs."""
        text_with_newline = "hello\nworld"
        assert reverse_string(text_with_newline) == "dlrow\nolleh"
        
        text_with_tab = "hello\tworld"
        capitalized = capitalize_words(text_with_tab)
        assert "Hello" in capitalized
        assert "World" in capitalized

    def test_very_long_delimiter(self):
        """Test with a very long delimiter."""
        text = "hello---world"
        result = capitalize_words(text, delimiter="---")
        assert result == "Hello---World"

    def test_delimiter_at_boundaries(self):
        """Test delimiter at start and end of string."""
        text = "-hello-world-"
        result = capitalize_words(text, delimiter="-")
        assert result.startswith("-")
        assert result.endswith("-")

    def test_consecutive_delimiters(self):
        """Test consecutive delimiters."""
        text = "hello--world"
        result = capitalize_words(text, delimiter="-")
        # Should have empty string between delimiters
        assert "--" in result

    def test_empty_delimiter(self):
        """Test with empty string as delimiter."""
        # Empty delimiter should split into individual characters
        text = "hello"
        result = capitalize_words(text, delimiter="")
        # Each character should be capitalized and joined
        assert len(result) == len(text)
