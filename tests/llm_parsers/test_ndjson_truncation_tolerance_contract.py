"""Contract tests for NDJSONResponseParser truncation tolerance.

This test suite validates the NDJSON parser contract with 10+ scenarios:
- Valid NDJSON parsing
- Truncated last line (incomplete JSON object)
- Missing newline at EOF
- Empty lines handling
- Format detection (structured_edit, unsupported_diff, json_array)
- Markdown fence removal
- Fallback format conversion

Each test is table-driven to ensure comprehensive coverage.
"""

import json

import pytest

from autopack.llm.parsers.anthropic.ndjson import NDJSONResponseParser


class TestNDJSONTruncationToleranceContract:
    """Contract tests for NDJSON parser truncation tolerance."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return NDJSONResponseParser()

    # Test 1: Valid NDJSON with meta line
    def test_valid_ndjson_with_meta(self, parser):
        """Test parsing valid NDJSON with meta line."""
        content = """{"type": "meta", "summary": "Create files", "total_operations": 2}
{"type": "create", "file_path": "src/foo.py", "content": "def foo():\\n    pass"}
{"type": "create", "file_path": "src/bar.py", "content": "def bar():\\n    pass"}"""
        result = parser.parse(content)
        assert result.success
        assert len(result.operations) == 2  # Meta is parsed but not included in operations
        assert not result.was_truncated
        assert result.lines_parsed == 3  # All 3 lines were parsed
        assert result.total_expected == 2

    # Test 2: Valid NDJSON without meta line
    def test_valid_ndjson_no_meta(self, parser):
        """Test parsing valid NDJSON without meta line."""
        content = """{"type": "create", "file_path": "src/foo.py", "content": "def foo():\\n    pass"}
{"type": "modify", "file_path": "src/bar.py", "operations": [{"type": "insert", "line": 10, "content": "new line"}]}"""
        result = parser.parse(content)
        assert result.success
        assert len(result.operations) == 2
        assert not result.was_truncated

    # Test 3: Truncated last line (incomplete JSON)
    @pytest.mark.parametrize(
        "truncated_content,expected_operations",
        [
            # Truncated in middle of line
            (
                '{"type": "create", "file_path": "a.py", "content": "x"}\n{"type": "create", "file_path": "b.py"',
                1,
            ),
            # Truncated after opening brace
            (
                '{"type": "create", "file_path": "a.py", "content": "x"}\n{"type":',
                1,
            ),
            # Truncated in content field
            (
                '{"type": "create", "file_path": "a.py", "content": "x"}\n{"type": "create", "file_path": "b.py", "content": "partial',
                1,
            ),
        ],
    )
    def test_truncated_last_line(self, parser, truncated_content, expected_operations):
        """Test that truncated last line is tolerated."""
        result = parser.parse(truncated_content)
        assert result.success
        assert len(result.operations) == expected_operations
        assert result.was_truncated  # Should detect truncation

    # Test 4: Missing newline at EOF
    def test_missing_newline_at_eof(self, parser):
        """Test handling of missing newline at EOF (but line is complete)."""
        content = '{"type": "create", "file_path": "a.py", "content": "x"}'
        result = parser.parse(content)
        # Single-line NDJSON is valid
        assert result.success
        assert len(result.operations) == 1

    # Test 5: Empty lines handling
    def test_empty_lines(self, parser):
        """Test that empty lines are tolerated."""
        content = """{"type": "create", "file_path": "a.py", "content": "x"}

{"type": "create", "file_path": "b.py", "content": "y"}

"""
        result = parser.parse(content)
        assert result.success
        assert len(result.operations) == 2

    # Test 6: Markdown fence removal
    @pytest.mark.parametrize(
        "fenced_content",
        [
            # JSON fence
            '```json\n{"type": "create", "file_path": "a.py", "content": "x"}\n```',
            # Plain fence
            '```\n{"type": "create", "file_path": "a.py", "content": "x"}\n```',
            # Fence with language
            '```ndjson\n{"type": "create", "file_path": "a.py", "content": "x"}\n```',
        ],
    )
    def test_markdown_fence_removal(self, parser, fenced_content):
        """Test that markdown fences are removed before parsing."""
        result = parser.parse(fenced_content)
        # After fence removal, single-line NDJSON should parse successfully
        assert result.success
        assert len(result.operations) == 1

    # Test 7: Structured edit format detection
    def test_structured_edit_detection(self, parser):
        """Test detection of structured edit format instead of NDJSON."""
        content = """{
    "summary": "Make changes",
    "operations": [
        {"type": "insert", "file_path": "a.py", "line": 10, "content": "new line"}
    ]
}"""
        result = parser.parse(content)
        assert not result.success
        assert result.fallback_format == "structured_edit"
        assert "structured_edit" in result.error.lower()

    # Test 8: Unsupported diff format detection
    def test_unsupported_diff_detection(self, parser):
        """Test detection of unsupported diff format (legacy diff removed)."""
        content = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
-old line
+new line"""
        result = parser.parse(content)
        assert not result.success
        assert result.fallback_format == "unsupported_diff"

    # Test 9: JSON array format conversion
    def test_json_array_conversion(self, parser):
        """Test conversion of JSON array to NDJSON."""
        content = """[
    {"type": "create", "file_path": "a.py", "content": "x"},
    {"type": "create", "file_path": "b.py", "content": "y"}
]"""
        result = parser.parse(content)
        # Should either convert successfully or detect as json_array format
        assert result.fallback_format == "json_array" or (
            result.success and len(result.operations) == 2
        )

    # Test 10: Single JSON operation
    def test_single_json_operation(self, parser):
        """Test single JSON operation (valid single-line NDJSON)."""
        content = '{"type": "create", "file_path": "a.py", "content": "x"}'
        result = parser.parse(content)
        # Single-line NDJSON is valid
        assert result.success
        assert len(result.operations) == 1

    # Test 11: Mixed valid and invalid lines
    def test_mixed_valid_invalid_lines(self, parser):
        """Test handling of mixed valid and invalid lines."""
        content = """{"type": "create", "file_path": "a.py", "content": "x"}
not valid json
{"type": "create", "file_path": "b.py", "content": "y"}"""
        result = parser.parse(content)
        # Should parse valid lines and skip invalid ones
        # Note: lines_failed counter is only incremented for JSON decode errors on lines starting with { or [
        # "not valid json" doesn't start with { or [ so it's just skipped
        assert result.lines_parsed >= 2
        assert len(result.operations) == 2

    # Test 12: Large number of operations
    def test_large_number_of_operations(self, parser):
        """Test parsing large number of NDJSON operations."""
        lines = [
            json.dumps({"type": "create", "file_path": f"file_{i}.py", "content": f"content_{i}"})
            for i in range(100)
        ]
        content = "\n".join(lines)
        result = parser.parse(content)
        assert result.success
        assert len(result.operations) == 100

    # Test 13: Operations with special characters
    def test_special_characters_in_content(self, parser):
        """Test handling of special characters in content."""
        content = json.dumps(
            {
                "type": "create",
                "file_path": "test.py",
                "content": 'def foo():\n    return "hello\\nworld"\n',
            }
        )
        result = parser.parse(content)
        # Single-line NDJSON with special characters
        assert result.success
        assert len(result.operations) == 1

    # Test 14: Empty content
    def test_empty_content(self, parser):
        """Test handling of empty content."""
        content = ""
        result = parser.parse(content)
        assert not result.success
        assert result.error is not None

    # Test 15: Whitespace-only content
    def test_whitespace_only(self, parser):
        """Test handling of whitespace-only content."""
        content = "   \n\n   \t\t\n"
        result = parser.parse(content)
        assert not result.success


class TestNDJSONFormatDetection:
    """Tests for NDJSON format detection helpers."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return NDJSONResponseParser()

    def test_detect_structured_edit_format(self, parser):
        """Test structured edit format detection."""
        content = '{"operations": [{"type": "insert"}], "summary": "test"}'
        detected = parser._detect_format(content)
        assert detected == "structured_edit"

    def test_detect_unsupported_diff_format(self, parser):
        """Test unsupported diff format detection (legacy diff removed)."""
        content = "diff --git a/file.py b/file.py"
        detected = parser._detect_format(content)
        assert detected == "unsupported_diff"

    def test_detect_json_array_format(self, parser):
        """Test JSON array format detection."""
        # Arrays with NDJSON-like operations are NOT flagged as different format
        # (they get converted to NDJSON later)
        content = '[{"type": "create"}, {"type": "modify"}]'
        detected = parser._detect_format(content)
        assert detected is None  # Treated as convertible to NDJSON

        # But arrays without type fields should be detected
        content_no_type = '[{"path": "a.py"}, {"path": "b.py"}]'
        detected2 = parser._detect_format(content_no_type)
        assert detected2 == "json_array"

    def test_detect_single_json_op(self, parser):
        """Test single JSON operation (valid single-line NDJSON)."""
        # Single-line NDJSON is NOT flagged as a different format
        content = '{"type": "create", "file_path": "test.py"}'
        detected = parser._detect_format(content)
        assert detected is None  # Single-line NDJSON is valid NDJSON

    def test_no_format_detected_ndjson(self, parser):
        """Test that valid NDJSON returns None (no format detected)."""
        content = '{"type": "create", "file_path": "a.py"}\n{"type": "modify", "file_path": "b.py"}'
        detected = parser._detect_format(content)
        assert detected is None


class TestNDJSONMarkdownSanitization:
    """Tests for markdown fence sanitization."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return NDJSONResponseParser()

    def test_remove_json_fence(self, parser):
        """Test removal of ```json fence."""
        content = "```json\nactual content\n```"
        result = parser._sanitize_markdown_fences(content)
        assert "```" not in result
        assert "actual content" in result

    def test_remove_plain_fence(self, parser):
        """Test removal of ``` fence."""
        content = "```\nactual content\n```"
        result = parser._sanitize_markdown_fences(content)
        assert "```" not in result

    def test_preserve_non_fence_content(self, parser):
        """Test that non-fence content is preserved."""
        content = "line1\nline2\nline3"
        result = parser._sanitize_markdown_fences(content)
        assert result == content

    def test_multiple_fences(self, parser):
        """Test handling of multiple fences."""
        content = "```json\ncontent1\n```\nsome text\n```\ncontent2\n```"
        result = parser._sanitize_markdown_fences(content)
        assert "```" not in result
        assert "content1" in result
        assert "content2" in result
