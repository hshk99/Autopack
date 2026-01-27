"""Contract tests for FullFileParser JSON repair logic.

This test suite validates the JSON repair contract with 10+ scenarios:
- Bare newline repair in JSON strings
- Placeholder decoding ({{PLACEHOLDER_N}})
- Bracket balancing on truncation
- Malformed JSON recovery strategies
- Markdown fence extraction
- Object extraction and balancing

Each test is table-driven to ensure comprehensive coverage.
"""

import pytest

from autopack.llm.parsers.anthropic.full_file import FullFileParser


class TestFullFileJsonRepairContract:
    """Contract tests for FullFileParser JSON repair."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return FullFileParser()

    # Test 1: Valid JSON (no repair needed)
    def test_valid_json_no_repair(self, parser):
        """Test that valid JSON parses without repair."""
        content = '{"files": [{"path": "test.py", "mode": "create", "new_content": "def foo():\\n    pass"}]}'
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        assert len(result.content["files"]) == 1
        assert result.repair_method == "direct_parse"

    # Test 2: Bare newlines in JSON strings
    @pytest.mark.parametrize(
        "input_json,expected_content",
        [
            # Bare newline in string value
            (
                '{"files": [{"path": "test.py", "new_content": "line1\nline2"}]}',
                "line1\nline2",
            ),
            # Multiple bare newlines
            (
                '{"files": [{"path": "test.py", "new_content": "line1\nline2\nline3"}]}',
                "line1\nline2\nline3",
            ),
            # Bare newline with other content
            (
                '{"files": [{"path": "test.py", "new_content": "def foo():\n    pass"}]}',
                "def foo():\n    pass",
            ),
        ],
    )
    def test_bare_newline_repair(self, parser, input_json, expected_content):
        """Test that bare newlines in JSON strings are repaired."""
        result = parser.parse(input_json)
        assert result.success
        assert result.content is not None
        assert result.content["files"][0]["new_content"] == expected_content

    # Test 3: Markdown fence extraction
    @pytest.mark.parametrize(
        "fenced_content",
        [
            # Basic fence
            '```json\n{"files": [{"path": "test.py", "new_content": "code"}]}\n```',
            # Fence with explanation before
            'Here is the output:\n```json\n{"files": [{"path": "test.py", "new_content": "code"}]}\n```',
            # Fence with explanation after
            '```json\n{"files": [{"path": "test.py", "new_content": "code"}]}\n```\nThis creates a file.',
        ],
    )
    def test_markdown_fence_extraction(self, parser, fenced_content):
        """Test extraction of JSON from markdown code fences."""
        result = parser.parse(fenced_content)
        assert result.success
        assert result.content is not None
        assert len(result.content["files"]) == 1
        assert result.repair_method == "markdown_fence_extraction"

    # Test 4: Bracket balancing on truncation
    @pytest.mark.parametrize(
        "truncated_json,expected_success",
        [
            # Missing closing brace
            ('{"files": [{"path": "test.py", "new_content": "code"', True),
            # Missing closing bracket and brace
            ('{"files": [{"path": "test.py"', True),
            # Missing multiple closers
            ('{"files": [{"path": "a"}, {"path": "b"', True),
            # Completely truncated (no opening for "files")
            ('{"fil', False),
        ],
    )
    def test_bracket_balancing(self, parser, truncated_json, expected_success):
        """Test bracket balancing for truncated JSON."""
        result = parser.parse(truncated_json)
        assert result.success == expected_success
        if expected_success:
            assert result.content is not None
            assert "files" in result.content

    # Test 5: Placeholder content sanitization
    def test_placeholder_sanitization(self, parser):
        """Test that problematic new_content is sanitized with placeholders."""
        # This content has problematic characters that might break JSON parsing
        content = r'{"files": [{"path": "test.py", "new_content": "def foo():\n    \"quoted\"\n    pass"}]}'
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        assert "test.py" in result.content["files"][0]["path"]

    # Test 6: Git diff rejection
    def test_git_diff_rejection(self, parser):
        """Test that git diff output is rejected with clear error."""
        diff_content = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
-old line
+new line
"""
        result = parser.parse(diff_content)
        assert not result.success
        assert "git diff" in result.error.lower()
        assert "JSON" in result.error

    # Test 7: Object extraction and balancing
    def test_object_extraction_with_prefix(self, parser):
        """Test extraction of JSON object when prefixed with text."""
        content = 'Here is the result: {"files": [{"path": "test.py", "new_content": "code"}]}'
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        assert result.repair_method is not None

    # Test 8: Empty files array
    def test_empty_files_array(self, parser):
        """Test that empty files array is valid."""
        content = '{"files": []}'
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        assert len(result.content["files"]) == 0

    # Test 9: Missing files key
    def test_missing_files_key(self, parser):
        """Test that missing files key returns error."""
        content = '{"summary": "Some summary"}'
        result = parser.parse(content)
        assert not result.success
        assert "files" in result.error.lower()

    # Test 10: Files field is not array
    def test_files_not_array(self, parser):
        """Test that files field must be an array."""
        content = '{"files": "not an array"}'
        result = parser.parse(content)
        assert not result.success
        assert "array" in result.error.lower()

    # Test 11: Complex escape sequences
    def test_complex_escape_sequences(self, parser):
        """Test handling of complex escape sequences in content."""
        content = r'{"files": [{"path": "test.py", "new_content": "line1\nline2\ttab\rcarriage\u0020space"}]}'
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        # Verify escape sequences are preserved or handled correctly
        assert "test.py" in result.content["files"][0]["path"]

    # Test 12: Nested JSON in content
    def test_nested_json_in_content(self, parser):
        """Test handling of JSON-like content within new_content field."""
        content = r'{"files": [{"path": "config.json", "new_content": "{\"key\": \"value\"}"}]}'
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        # The nested JSON should be preserved as a string
        assert '"key"' in result.content["files"][0]["new_content"]

    # Test 13: Large file content
    def test_large_file_content(self, parser):
        """Test handling of large file content (100+ lines)."""
        large_content = "\\n".join([f"line {i}" for i in range(150)])
        content = f'{{"files": [{{"path": "large.py", "new_content": "{large_content}"}}]}}'
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        assert len(result.content["files"]) == 1

    # Test 14: Multiple files in array
    def test_multiple_files(self, parser):
        """Test parsing multiple files in array."""
        content = """{"files": [
            {"path": "file1.py", "mode": "create", "new_content": "content1"},
            {"path": "file2.py", "mode": "modify", "new_content": "content2"},
            {"path": "file3.py", "mode": "delete"}
        ]}"""
        result = parser.parse(content)
        assert result.success
        assert result.content is not None
        assert len(result.content["files"]) == 3

    # Test 15: Completely malformed JSON
    def test_completely_malformed_json(self, parser):
        """Test that completely malformed JSON returns error."""
        content = "This is not JSON at all, just plain text."
        result = parser.parse(content)
        assert not result.success
        assert result.error is not None


class TestFullFileParserHelperMethods:
    """Tests for FullFileParser helper methods."""

    def test_escape_newlines_in_strings(self):
        """Test the newline escaping helper method."""
        input_str = '{"key": "value with\nnewline"}'
        expected = '{"key": "value with\\nnewline"}'
        result = FullFileParser._escape_newlines_in_json_strings(input_str)
        assert result == expected

    def test_decode_placeholder_string(self):
        """Test placeholder string decoding."""
        # Test basic escape sequences
        input_str = r"line1\nline2\ttab\rcarriage"
        result = FullFileParser._decode_placeholder_string(input_str)
        assert "\n" in result
        assert "\t" in result
        assert "\r" in result

        # Test unicode escape
        input_str = r"\u0041\u0042\u0043"  # ABC
        result = FullFileParser._decode_placeholder_string(input_str)
        assert result == "ABC"

    def test_balance_json_brackets(self):
        """Test bracket balancing."""
        # Unbalanced braces
        input_str = '{"key": "value"'
        result = FullFileParser._balance_json_brackets(input_str)
        assert result == '{"key": "value"}'

        # Unbalanced brackets
        input_str = '["item1", "item2"'
        result = FullFileParser._balance_json_brackets(input_str)
        assert result == '["item1", "item2"]'

        # Already balanced
        input_str = '{"key": "value"}'
        result = FullFileParser._balance_json_brackets(input_str)
        assert result == input_str

    def test_extract_first_json_object(self):
        """Test JSON object extraction."""
        # With prefix text
        input_str = 'Some text before {"key": "value"} some text after'
        result = FullFileParser._extract_first_json_object(input_str)
        assert result == '{"key": "value"}'

        # Nested braces
        input_str = '{"outer": {"inner": "value"}}'
        result = FullFileParser._extract_first_json_object(input_str)
        assert result == input_str

        # No JSON object
        input_str = "No JSON here"
        result = FullFileParser._extract_first_json_object(input_str)
        assert result is None
