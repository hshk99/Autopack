"""Contract tests for llm/parsers.py module.

These tests verify the parser's public API and behavior.
"""

from __future__ import annotations


class TestJSONRepair:
    """Tests for JSONRepair utilities."""

    def test_escape_newlines_in_strings(self):
        """Escapes bare newlines inside JSON strings."""
        from autopack.llm.parsers import JSONRepair

        # String with embedded newline
        raw = '{"content": "line1\nline2"}'
        repaired = JSONRepair.escape_newlines_in_strings(raw)
        assert repaired == '{"content": "line1\\nline2"}'

    def test_escape_newlines_preserves_escaped_newlines(self):
        """Preserves already-escaped newlines."""
        from autopack.llm.parsers import JSONRepair

        raw = '{"content": "line1\\nline2"}'
        repaired = JSONRepair.escape_newlines_in_strings(raw)
        assert repaired == '{"content": "line1\\nline2"}'

    def test_escape_newlines_outside_strings(self):
        """Does not escape newlines outside strings."""
        from autopack.llm.parsers import JSONRepair

        raw = '{\n  "key": "value"\n}'
        repaired = JSONRepair.escape_newlines_in_strings(raw)
        assert repaired == '{\n  "key": "value"\n}'

    def test_balance_brackets_complete_json(self):
        """Does nothing to complete JSON."""
        from autopack.llm.parsers import JSONRepair

        raw = '{"files": []}'
        result = JSONRepair.balance_brackets(raw)
        assert result == raw

    def test_balance_brackets_missing_closing(self):
        """Adds missing closing brackets."""
        from autopack.llm.parsers import JSONRepair

        raw = '{"files": ['
        result = JSONRepair.balance_brackets(raw)
        assert result == '{"files": []}' or result.endswith("]}")

    def test_balance_brackets_nested(self):
        """Handles nested structures."""
        from autopack.llm.parsers import JSONRepair

        raw = '{"outer": {"inner": ["item"'
        result = JSONRepair.balance_brackets(raw)
        assert result.count("]") >= 1
        assert result.count("}") >= 2

    def test_extract_code_fence_json(self):
        """Extracts JSON from code fence."""
        from autopack.llm.parsers import JSONRepair

        raw = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        result = JSONRepair.extract_code_fence(raw, "```json")
        assert result == '{"key": "value"}'

    def test_extract_code_fence_not_found(self):
        """Returns None when fence not found."""
        from autopack.llm.parsers import JSONRepair

        raw = '{"key": "value"}'
        result = JSONRepair.extract_code_fence(raw, "```json")
        assert result is None

    def test_extract_first_json_object(self):
        """Extracts first JSON object from text."""
        from autopack.llm.parsers import JSONRepair

        raw = 'Here is the result: {"key": "value"} and more'
        result = JSONRepair.extract_first_json_object(raw)
        assert result == '{"key": "value"}'

    def test_extract_first_json_object_nested(self):
        """Handles nested objects."""
        from autopack.llm.parsers import JSONRepair

        raw = '{"outer": {"inner": "value"}}'
        result = JSONRepair.extract_first_json_object(raw)
        assert result == raw


class TestDiffExtractor:
    """Tests for DiffExtractor utilities."""

    def test_extract_simple_diff(self):
        """Extracts simple git diff."""
        from autopack.llm.parsers import DiffExtractor

        raw = """Here's the change:

diff --git a/test.py b/test.py
index abc123..def456 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def hello():
     pass
+    print("hello")

Done!"""

        result = DiffExtractor.extract_diff_from_text(raw)
        assert "diff --git" in result
        assert "+    print" in result
        assert "Done!" not in result

    def test_extract_diff_no_diff(self):
        """Returns empty string when no diff present."""
        from autopack.llm.parsers import DiffExtractor

        raw = "Just some regular text without a diff"
        result = DiffExtractor.extract_diff_from_text(raw)
        assert result == ""

    def test_extract_multiple_diffs(self):
        """Extracts multiple file diffs."""
        from autopack.llm.parsers import DiffExtractor

        raw = """diff --git a/file1.py b/file1.py
--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,2 @@
+new line

diff --git a/file2.py b/file2.py
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,2 @@
+another new line"""

        result = DiffExtractor.extract_diff_from_text(raw)
        assert "file1.py" in result
        assert "file2.py" in result


class TestParseResult:
    """Tests for ParseResult dataclass."""

    def test_successful_result(self):
        """ParseResult stores successful parse data."""
        from autopack.llm.parsers import ParseResult

        result = ParseResult(
            success=True,
            data={"files": []},
            format_type="full_file",
        )
        assert result.success is True
        assert result.data == {"files": []}
        assert result.error is None

    def test_failed_result(self):
        """ParseResult stores error information."""
        from autopack.llm.parsers import ParseResult

        result = ParseResult(
            success=False,
            error="Parse error",
            format_type="json",
        )
        assert result.success is False
        assert result.error == "Parse error"
        assert result.data is None


class TestResponseParser:
    """Tests for ResponseParser class."""

    def test_parse_json_valid(self):
        """Parses valid JSON."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        result = parser.parse_json('{"key": "value"}')

        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.was_repaired is False

    def test_parse_json_with_code_fence(self):
        """Parses JSON inside code fence."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '```json\n{"key": "value"}\n```'
        result = parser.parse_json(raw)

        assert result.success is True
        assert result.data == {"key": "value"}

    def test_parse_json_with_repair(self):
        """Parses JSON with newline repair."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"content": "line1\nline2"}'
        result = parser.parse_json(raw)

        assert result.success is True
        assert result.data["content"] == "line1\nline2"
        assert result.was_repaired is True

    def test_parse_json_detects_diff(self):
        """Detects git diff format and returns error."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1 +1,2 @@
+new line"""

        result = parser.parse_json(raw)
        assert result.success is False
        assert result.format_type == "diff"

    def test_parse_full_file_output_valid(self):
        """Parses valid full-file output."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"summary": "test", "files": [{"path": "test.py", "mode": "create", "new_content": "# test"}]}'
        result = parser.parse_full_file_output(raw)

        assert result.success is True
        assert len(result.data["files"]) == 1
        assert result.format_type == "full_file"

    def test_parse_full_file_output_missing_files(self):
        """Returns error when files array missing."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"summary": "test"}'
        result = parser.parse_full_file_output(raw)

        assert result.success is False
        assert "files" in result.error.lower()

    def test_parse_structured_edit_output_valid(self):
        """Parses valid structured edit output."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"summary": "test", "operations": [{"type": "insert", "file_path": "test.py", "line": 1, "content": "new"}]}'
        result = parser.parse_structured_edit_output(raw)

        assert result.success is True
        assert len(result.data["operations"]) == 1
        assert result.format_type == "structured_edit"

    def test_parse_structured_edit_output_missing_operations(self):
        """Returns error when operations array missing."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"summary": "test"}'
        result = parser.parse_structured_edit_output(raw)

        assert result.success is False
        assert "operations" in result.error.lower()

    def test_parse_diff_output_raw(self):
        """Parses raw diff output."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = """diff --git a/test.py b/test.py
index abc..def 100644
--- a/test.py
+++ b/test.py
@@ -1 +1,2 @@
 existing
+new line"""

        result = parser.parse_diff_output(raw)
        assert result.success is True
        assert "diff --git" in result.data["patch_content"]

    def test_parse_diff_output_json_wrapped(self):
        """Parses diff wrapped in JSON."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"patch_content": "diff --git a/test.py b/test.py\\n+new"}'
        result = parser.parse_diff_output(raw)

        assert result.success is True
        assert "diff --git" in result.data["patch_content"]

    def test_detect_format_full_file(self):
        """Detects full-file format."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"summary": "test", "files": []}'
        assert parser.detect_format(raw) == "full_file"

    def test_detect_format_structured_edit(self):
        """Detects structured edit format."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = '{"summary": "test", "operations": []}'
        assert parser.detect_format(raw) == "structured_edit"

    def test_detect_format_diff(self):
        """Detects diff format."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = """diff --git a/test.py b/test.py
+new line"""
        assert parser.detect_format(raw) == "diff"

    def test_detect_format_unknown(self):
        """Returns unknown for unrecognized format."""
        from autopack.llm.parsers import ResponseParser

        parser = ResponseParser()
        raw = "Just some plain text"
        assert parser.detect_format(raw) == "unknown"


class TestNDJSONOperation:
    """Tests for NDJSONOperation dataclass."""

    def test_operation_attributes(self):
        """NDJSONOperation stores operation data."""
        from autopack.llm.parsers import NDJSONOperation

        op = NDJSONOperation(
            op_type="create",
            file_path="test.py",
            content="# test",
            raw_line='{"type": "create"}',
        )
        assert op.op_type == "create"
        assert op.file_path == "test.py"
        assert op.content == "# test"


class TestNDJSONParseResult:
    """Tests for NDJSONParseResult dataclass."""

    def test_successful_parse(self):
        """NDJSONParseResult stores successful parse data."""
        from autopack.llm.parsers import NDJSONParseResult, NDJSONOperation

        result = NDJSONParseResult(
            success=True,
            operations=[NDJSONOperation(op_type="create", file_path="test.py")],
            lines_parsed=2,
        )
        assert result.success is True
        assert len(result.operations) == 1
        assert result.lines_parsed == 2


class TestNDJSONParser:
    """Tests for NDJSONParser class."""

    def test_parse_single_operation(self):
        """Parses single NDJSON line."""
        from autopack.llm.parsers import NDJSONParser

        parser = NDJSONParser()
        raw = '{"type": "create", "file_path": "test.py", "content": "# test"}'
        result = parser.parse(raw)

        assert result.success is True
        assert len(result.operations) == 1
        assert result.operations[0].op_type == "create"
        assert result.operations[0].file_path == "test.py"

    def test_parse_multiple_operations(self):
        """Parses multiple NDJSON lines."""
        from autopack.llm.parsers import NDJSONParser

        parser = NDJSONParser()
        raw = """{"type": "meta", "summary": "test", "total_operations": 2}
{"type": "create", "file_path": "file1.py", "content": "# 1"}
{"type": "create", "file_path": "file2.py", "content": "# 2"}"""

        result = parser.parse(raw)

        assert result.success is True
        assert len(result.operations) == 2
        assert result.total_expected == 2
        assert result.meta is not None

    def test_parse_with_meta_line(self):
        """Parses meta line correctly."""
        from autopack.llm.parsers import NDJSONParser

        parser = NDJSONParser()
        raw = '{"type": "meta", "summary": "Adding tests", "total_operations": 3}'
        result = parser.parse(raw)

        assert result.meta is not None
        assert result.meta["summary"] == "Adding tests"
        assert result.total_expected == 3

    def test_parse_strips_markdown_fences(self):
        """Strips markdown fences from NDJSON."""
        from autopack.llm.parsers import NDJSONParser

        parser = NDJSONParser()
        raw = """```
{"type": "create", "file_path": "test.py", "content": "# test"}
```"""

        result = parser.parse(raw)
        assert result.success is True
        assert len(result.operations) == 1

    def test_parse_detects_truncation(self):
        """Detects truncation from meta line."""
        from autopack.llm.parsers import NDJSONParser

        parser = NDJSONParser()
        raw = """{"type": "meta", "summary": "test", "total_operations": 5}
{"type": "create", "file_path": "file1.py", "content": "# 1"}
{"type": "create", "file_path": "file2.py", "content": "# 2"}"""

        result = parser.parse(raw)

        assert result.was_truncated is True
        assert result.total_expected == 5
        assert len(result.operations) == 2

    def test_parse_handles_invalid_lines(self):
        """Handles invalid JSON lines gracefully."""
        from autopack.llm.parsers import NDJSONParser

        parser = NDJSONParser()
        raw = """{"type": "create", "file_path": "test.py", "content": "# test"}
not valid json
{"type": "create", "file_path": "test2.py", "content": "# test2"}"""

        result = parser.parse(raw)

        assert result.success is True
        assert len(result.operations) == 2
        assert result.lines_failed == 1

    def test_format_for_prompt(self):
        """Generates prompt instructions."""
        from autopack.llm.parsers import NDJSONParser

        parser = NDJSONParser()
        result = parser.format_for_prompt(
            deliverables=["src/test.py"],
            summary="Add test file",
        )

        assert "NDJSON" in result or "ndjson" in result.lower()
        assert "src/test.py" in result
        assert "Add test file" in result
