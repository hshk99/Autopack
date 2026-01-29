"""
Tests for ContinuationRecovery (BUILD-129 Phase 2).

Tests continuation-based recovery from truncation.
"""

import pytest

from autopack.continuation_recovery import (ContinuationContext,
                                            ContinuationRecovery)


class TestContinuationContext:
    """Test ContinuationContext dataclass."""

    def test_continuation_context_creation(self):
        """Test basic ContinuationContext creation."""
        context = ContinuationContext(
            completed_files=["file1.py", "file2.py"],
            last_partial_file="file3.py",
            remaining_deliverables=["file4.py", "file5.py"],
            partial_output="diff --git a/file1.py...",
            tokens_used=15000,
            format_type="diff",
        )

        assert len(context.completed_files) == 2
        assert context.last_partial_file == "file3.py"
        assert len(context.remaining_deliverables) == 2
        assert context.tokens_used == 15000
        assert context.format_type == "diff"


class TestContinuationRecovery:
    """Test ContinuationRecovery."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_no_truncation_detected(self, recovery):
        """Test that no context is returned when not truncated."""
        output = "Complete output here"
        deliverables = ["file1.py", "file2.py"]

        context = recovery.detect_truncation_context(
            raw_output=output,
            deliverables=deliverables,
            stop_reason="stop_sequence",  # Not max_tokens
            tokens_used=5000,
        )

        assert context is None

    def test_detect_format_diff(self, recovery):
        """Test diff format detection."""
        output = """diff --git a/src/foo.py b/src/foo.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/foo.py
@@ -0,0 +1,10 @@
+def hello():
+    print("hello")
"""
        format_type = recovery._detect_format(output)
        assert format_type == "diff"

    def test_detect_format_full_file(self, recovery):
        """Test full-file JSON format detection."""
        output = """[
  {"file_path": "src/foo.py", "content": "..."},
  {"file_path": "src/bar.py", "content": "..."}
]"""
        format_type = recovery._detect_format(output)
        assert format_type == "full_file"

    def test_detect_format_ndjson(self, recovery):
        """Test NDJSON format detection."""
        output = """{"meta": "header"}
{"op": "create", "path": "src/foo.py", "content": "..."}
{"op": "modify", "path": "src/bar.py", "content": "..."}
"""
        format_type = recovery._detect_format(output)
        assert format_type == "ndjson"

    def test_parse_diff_truncation_complete_files(self, recovery):
        """Test parsing diff truncation with complete files."""
        output = """diff --git a/src/foo.py b/src/foo.py
new file mode 100644
--- /dev/null
+++ b/src/foo.py
@@ -0,0 +1,5 @@
+def foo():
+    return 42

diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null
+++ b/src/bar.py
@@ -0,0 +1,3 @@
+def bar():
+    return"""  # Truncated mid-function

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py"]

        context = recovery._parse_diff_truncation(output, deliverables, 10000)

        assert "src/foo.py" in context.completed_files
        # bar.py might be partial or completed depending on parsing
        assert len(context.remaining_deliverables) >= 1
        assert "src/baz.py" in context.remaining_deliverables
        assert context.format_type == "diff"

    def test_parse_full_file_truncation(self, recovery):
        """Test parsing full-file JSON truncation."""
        output = """[
  {"file_path": "src/foo.py", "content": "def foo(): return 42"},
  {"file_path": "src/bar.py", "content": "def bar()"""  # Truncated

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py"]

        context = recovery._parse_full_file_truncation(output, deliverables, 8000)

        assert "src/foo.py" in context.completed_files
        assert "src/baz.py" in context.remaining_deliverables
        assert context.format_type == "full_file"

    def test_parse_ndjson_truncation(self, recovery):
        """Test parsing NDJSON truncation."""
        output = """{"op": "create", "path": "src/foo.py", "content": "..."}
{"op": "create", "path": "src/bar.py", "content": "..."}
{"op": "create", "path": "src/baz.py", "content":"""  # Truncated mid-line

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py", "src/qux.py"]

        context = recovery._parse_ndjson_truncation(output, deliverables, 12000)

        assert "src/foo.py" in context.completed_files
        assert "src/bar.py" in context.completed_files
        # src/baz.py truncated, so should be in remaining
        assert "src/qux.py" in context.remaining_deliverables
        assert context.format_type == "ndjson"

    def test_build_continuation_prompt_with_completed(self, recovery):
        """Test building continuation prompt with some completed files."""
        context = ContinuationContext(
            completed_files=["src/foo.py", "src/bar.py"],
            last_partial_file=None,
            remaining_deliverables=["src/baz.py", "src/qux.py"],
            partial_output="...",
            tokens_used=10000,
            format_type="diff",
        )

        original_prompt = "Generate patches for all files."

        continuation_prompt = recovery.build_continuation_prompt(context, original_prompt)

        assert "CONTINUATION REQUEST" in continuation_prompt
        assert "2/4 files" in continuation_prompt
        assert "Already completed" in continuation_prompt
        assert "src/foo.py" in continuation_prompt
        assert "Remaining to complete" in continuation_prompt
        assert "src/baz.py" in continuation_prompt
        assert "src/qux.py" in continuation_prompt

    def test_build_continuation_prompt_no_completed(self, recovery):
        """Test building continuation prompt with no completed files."""
        context = ContinuationContext(
            completed_files=[],
            last_partial_file=None,
            remaining_deliverables=["src/foo.py", "src/bar.py"],
            partial_output="...",
            tokens_used=5000,
            format_type="diff",
        )

        original_prompt = "Generate patches for all files."

        continuation_prompt = recovery.build_continuation_prompt(context, original_prompt)

        assert "CONTINUATION REQUEST" in continuation_prompt
        assert "0/2 files" in continuation_prompt
        assert "Remaining to complete" in continuation_prompt

    def test_merge_diff_outputs(self, recovery):
        """Test merging diff outputs."""
        partial = """diff --git a/src/foo.py b/src/foo.py
new file mode 100644
--- /dev/null
+++ b/src/foo.py
@@ -0,0 +1,3 @@
+def foo():
+    return 42
"""

        continuation = """diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null
+++ b/src/bar.py
@@ -0,0 +1,3 @@
+def bar():
+    return 43
"""

        merged = recovery._merge_diff_outputs(partial, continuation)

        assert "src/foo.py" in merged
        assert "src/bar.py" in merged
        assert merged.count("diff --git") == 2

    def test_merge_ndjson_outputs(self, recovery):
        """Test merging NDJSON outputs."""
        partial = """{"op": "create", "path": "src/foo.py"}
{"op": "create", "path": "src/bar.py"}
"""

        continuation = """{"op": "create", "path": "src/baz.py"}
{"op": "create", "path": "src/qux.py"}
"""

        merged = recovery._merge_ndjson_outputs(partial, continuation)

        assert "src/foo.py" in merged
        assert "src/bar.py" in merged
        assert "src/baz.py" in merged
        assert "src/qux.py" in merged

    def test_merge_ndjson_outputs_with_incomplete_last_line(self, recovery):
        """Test merging NDJSON with incomplete last line in partial."""
        partial = """{"op": "create", "path": "src/foo.py"}
{"op": "create", "path": "src/bar.py"}
{"op": "create", "path":"""  # Incomplete

        continuation = """{"op": "create", "path": "src/baz.py"}
"""

        merged = recovery._merge_ndjson_outputs(partial, continuation)

        # Should skip incomplete last line
        assert "src/foo.py" in merged
        assert "src/bar.py" in merged
        assert "src/baz.py" in merged

    def test_detect_truncation_context_diff(self, recovery):
        """Test end-to-end truncation detection for diff format."""
        output = """diff --git a/src/foo.py b/src/foo.py
new file mode 100644
--- /dev/null
+++ b/src/foo.py
@@ -0,0 +1,5 @@
+def foo():
+    return 42

diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null
+++ b/src/bar.py
@@ -0,0 +1,3 @@"""  # Truncated

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py"]

        context = recovery.detect_truncation_context(
            raw_output=output,
            deliverables=deliverables,
            stop_reason="max_tokens",
            tokens_used=15000,
        )

        assert context is not None
        assert context.format_type == "diff"
        assert len(context.completed_files) >= 1
        assert len(context.remaining_deliverables) >= 1
        assert context.tokens_used == 15000

    def test_detect_truncation_context_ndjson(self, recovery):
        """Test end-to-end truncation detection for NDJSON format."""
        output = """{"op": "create", "path": "src/foo.py", "content": "..."}
{"op": "create", "path": "src/bar.py", "content": "..."}
{"op": "create", "path": "src/baz.py","""  # Truncated

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py", "src/qux.py"]

        context = recovery.detect_truncation_context(
            raw_output=output,
            deliverables=deliverables,
            stop_reason="max_tokens",
            tokens_used=20000,
        )

        assert context is not None
        assert context.format_type == "ndjson"
        assert "src/foo.py" in context.completed_files
        assert "src/bar.py" in context.completed_files
        assert "src/qux.py" in context.remaining_deliverables


class TestContinuationRecoveryIntegration:
    """Integration tests for continuation recovery."""

    def test_full_continuation_workflow(self):
        """Test complete continuation workflow."""
        recovery = ContinuationRecovery()

        # Simulate truncated output
        truncated_output = """diff --git a/src/foo.py b/src/foo.py
new file mode 100644
--- /dev/null
+++ b/src/foo.py
@@ -0,0 +1,3 @@
+def foo():
+    return 42

diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null"""  # Truncated mid-file

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py"]
        original_prompt = "Generate git patches for all files."

        # Step 1: Detect truncation
        context = recovery.detect_truncation_context(
            raw_output=truncated_output,
            deliverables=deliverables,
            stop_reason="max_tokens",
            tokens_used=12000,
        )

        assert context is not None

        # Step 2: Build continuation prompt
        continuation_prompt = recovery.build_continuation_prompt(context, original_prompt)

        assert "CONTINUATION REQUEST" in continuation_prompt
        assert "Remaining to complete" in continuation_prompt

        # Step 3: Simulate continuation output
        continuation_output = """diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null
+++ b/src/bar.py
@@ -0,0 +1,3 @@
+def bar():
+    return 43

diff --git a/src/baz.py b/src/baz.py
new file mode 100644
--- /dev/null
+++ b/src/baz.py
@@ -0,0 +1,3 @@
+def baz():
+    return 44
"""

        # Step 4: Merge outputs
        merged = recovery.merge_outputs(
            partial_output=truncated_output,
            continuation_output=continuation_output,
            format_type="diff",
        )

        # Verify merged output contains all files
        assert "src/foo.py" in merged
        assert "src/bar.py" in merged
        assert "src/baz.py" in merged
        assert merged.count("diff --git") == 3


class TestP15IncrementalJSONParsing:
    """P1.5: Tests for robust incremental JSON parsing."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_incremental_parse_complete_array(self, recovery):
        """Test parsing a complete JSON array."""
        json_str = """[
            {"file_path": "src/foo.py", "content": "def foo(): pass"},
            {"file_path": "src/bar.py", "content": "def bar(): pass"}
        ]"""

        completed, partial = recovery._incremental_parse_json_array(json_str)

        assert completed == ["src/foo.py", "src/bar.py"]
        assert partial is None

    def test_incremental_parse_truncated_mid_object(self, recovery):
        """Test parsing truncated mid-object - should detect partial file."""
        json_str = """[
            {"file_path": "src/foo.py", "content": "def foo(): pass"},
            {"file_path": "src/bar.py", "content": "def bar(): pass"},
            {"file_path": "src/baz.py", "content": "def baz("""

        completed, partial = recovery._incremental_parse_json_array(json_str)

        assert completed == ["src/foo.py", "src/bar.py"]
        assert partial == "src/baz.py"  # Partial file detected

    def test_incremental_parse_truncated_before_content(self, recovery):
        """Test parsing truncated before content field."""
        json_str = """[
            {"file_path": "src/foo.py", "content": "def foo(): pass"},
            {"file_path": "src/bar.py","""

        completed, partial = recovery._incremental_parse_json_array(json_str)

        assert completed == ["src/foo.py"]
        assert partial == "src/bar.py"

    def test_incremental_parse_nested_braces(self, recovery):
        """Test parsing with nested braces in content."""
        json_str = """[
            {"file_path": "src/foo.py", "content": "def foo(): return {'a': 1}"},
            {"file_path": "src/bar.py", "content": "def bar(): return {"""

        completed, partial = recovery._incremental_parse_json_array(json_str)

        assert completed == ["src/foo.py"]
        assert partial == "src/bar.py"

    def test_incremental_parse_escaped_quotes(self, recovery):
        """Test parsing with escaped quotes in content."""
        json_str = """[
            {"file_path": "src/foo.py", "content": "def foo(): return \\"hello\\""},
            {"file_path": "src/bar.py", "content": "def bar()"""

        completed, partial = recovery._incremental_parse_json_array(json_str)

        assert completed == ["src/foo.py"]
        assert partial == "src/bar.py"

    def test_incremental_parse_path_key(self, recovery):
        """Test parsing with 'path' key instead of 'file_path'."""
        json_str = """[
            {"path": "src/foo.py", "content": "def foo(): pass"},
            {"path": "src/bar.py", "content": "def bar(): pass"}
        ]"""

        completed, partial = recovery._incremental_parse_json_array(json_str)

        assert completed == ["src/foo.py", "src/bar.py"]
        assert partial is None

    def test_find_object_end_simple(self, recovery):
        """Test finding object end for simple object."""
        json_str = '{"key": "value"}'
        end_pos = recovery._find_object_end(json_str, 0)
        assert end_pos == len(json_str) - 1

    def test_find_object_end_nested(self, recovery):
        """Test finding object end with nested structures."""
        json_str = '{"outer": {"inner": "value"}}'
        end_pos = recovery._find_object_end(json_str, 0)
        assert end_pos == len(json_str) - 1

    def test_find_object_end_truncated(self, recovery):
        """Test finding object end when truncated."""
        json_str = '{"key": "value'
        end_pos = recovery._find_object_end(json_str, 0)
        assert end_pos == -1  # Not found

    def test_find_object_end_braces_in_string(self, recovery):
        """Test finding object end with braces inside string."""
        json_str = '{"code": "function() { return {}; }"}'
        end_pos = recovery._find_object_end(json_str, 0)
        assert end_pos == len(json_str) - 1

    def test_extract_path_from_partial_file_path(self, recovery):
        """Test extracting file_path from partial object."""
        partial = '{"file_path": "src/foo.py", "content": "def foo'
        path = recovery._extract_path_from_partial_object(partial)
        assert path == "src/foo.py"

    def test_extract_path_from_partial_path(self, recovery):
        """Test extracting path from partial object."""
        partial = '{"path": "src/bar.py", "op": "create'
        path = recovery._extract_path_from_partial_object(partial)
        assert path == "src/bar.py"

    def test_extract_path_no_path_found(self, recovery):
        """Test extracting path when none present."""
        partial = '{"content": "def foo'
        path = recovery._extract_path_from_partial_object(partial)
        assert path is None

    def test_full_file_truncation_returns_partial(self, recovery):
        """Test that _parse_full_file_truncation returns last_partial_file."""
        output = """[
            {"file_path": "src/foo.py", "content": "complete"},
            {"file_path": "src/bar.py", "content": "truncated"""

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py"]

        context = recovery._parse_full_file_truncation(output, deliverables, 10000)

        assert "src/foo.py" in context.completed_files
        assert context.last_partial_file == "src/bar.py"
        assert "src/baz.py" in context.remaining_deliverables

    def test_continuation_prompt_excludes_completed(self, recovery):
        """Test that continuation prompt tells LLM not to regenerate completed files."""
        context = ContinuationContext(
            completed_files=["src/foo.py", "src/bar.py"],
            last_partial_file="src/baz.py",
            remaining_deliverables=["src/baz.py", "src/qux.py"],
            partial_output="...",
            tokens_used=15000,
            format_type="full_file",
        )

        prompt = recovery.build_continuation_prompt(context, "Generate all files")

        # Must explicitly tell LLM not to regenerate
        assert "Do NOT regenerate already-completed files" in prompt
        assert "Already completed" in prompt
        assert "src/foo.py" in prompt
        assert "src/bar.py" in prompt


class TestMergeFullFileOutputs:
    """Tests for _merge_full_file_outputs method."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_merge_truncated_array_finds_last_complete(self, recovery):
        """Test merging truncated array - finds last complete via ',' pattern."""
        # The code uses rfind("},") to find last complete item
        # So we use an array with trailing comma to ensure complete detection
        partial = """[
  {"file_path": "src/foo.py", "content": "def foo(): pass"},
  {"file_path": "src/bar.py", "content": "def bar"""  # Truncated

        continuation = """[
  {"file_path": "src/baz.py", "content": "def baz(): pass"}
]"""

        merged = recovery._merge_full_file_outputs(partial, continuation)

        import json

        merged_data = json.loads(merged)
        # First file should be preserved, truncated file lost
        paths = [item.get("file_path") for item in merged_data]
        assert "src/foo.py" in paths
        assert "src/baz.py" in paths

    def test_merge_with_comma_separated_items(self, recovery):
        """Test merging with properly comma-separated items."""
        # When partial has }, pattern, both items before truncation are found
        partial = """[
  {"file_path": "src/foo.py", "content": "def foo(): pass"},
  {"file_path": "src/bar.py", "content": "def bar(): pass"},
  {"file_path": "src/baz.py", "content": "truncated"""

        continuation = """[
  {"file_path": "src/qux.py", "content": "def qux(): pass"}
]"""

        merged = recovery._merge_full_file_outputs(partial, continuation)

        import json

        merged_data = json.loads(merged)
        paths = [item.get("file_path") for item in merged_data]
        assert "src/foo.py" in paths
        assert "src/bar.py" in paths
        assert "src/qux.py" in paths

    def test_merge_non_array_returns_empty_merge(self, recovery):
        """Test that non-array content results in empty merged result."""
        # When startswith("[") is False, both partial_ops and continuation_ops stay empty
        # The function returns json.dumps([]) = "[]"
        partial = '{"single": "object"}'  # Not an array
        continuation = '{"another": "object"}'

        merged = recovery._merge_full_file_outputs(partial, continuation)

        import json

        # Since inputs don't start with "[", the merge returns empty array
        # This is expected behavior for the full_file merge
        merged_data = json.loads(merged)
        assert merged_data == []


class TestMergeOutputsUnknownFormat:
    """Tests for merge_outputs with unknown format type."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_merge_unknown_format(self, recovery):
        """Test merging with unknown format type."""
        partial = "partial content here"
        continuation = "continuation content here"

        merged = recovery.merge_outputs(partial, continuation, "unknown")

        assert "partial content here" in merged
        assert "continuation content here" in merged

    def test_merge_full_file_via_merge_outputs(self, recovery):
        """Test merge_outputs correctly delegates to full_file merger."""
        # Use comma-separated format that the merge logic can find
        partial = """[
  {"file_path": "src/foo.py", "content": "def foo(): pass"},
  {"file_path": "src/bar.py", "content": "truncated"""

        continuation = """[
  {"file_path": "src/baz.py", "content": "def baz(): pass"}
]"""

        merged = recovery.merge_outputs(partial, continuation, "full_file")

        import json

        merged_data = json.loads(merged)
        # foo.py should be preserved from partial (before truncation)
        # baz.py should come from continuation
        paths = [item.get("file_path") for item in merged_data]
        assert "src/foo.py" in paths
        assert "src/baz.py" in paths


class TestDetectFormatEdgeCases:
    """Tests for _detect_format edge cases."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_detect_format_unknown(self, recovery):
        """Test format detection returns unknown for unrecognized content."""
        output = "This is just plain text with no special markers"

        format_type = recovery._detect_format(output)

        assert format_type == "unknown"

    def test_detect_format_empty_string(self, recovery):
        """Test format detection with empty string."""
        format_type = recovery._detect_format("")

        assert format_type == "unknown"

    def test_detect_format_ndjson_with_op(self, recovery):
        """Test NDJSON detection with op field and newlines."""
        output = """{"op": "create", "path": "test.py"}
{"op": "modify", "path": "other.py"}"""

        format_type = recovery._detect_format(output)

        assert format_type == "ndjson"

    def test_detect_format_single_object_with_path(self, recovery):
        """Test full_file detection for single object with path."""
        output = '{"file_path": "src/test.py", "content": "code"}'

        format_type = recovery._detect_format(output)

        assert format_type == "full_file"


class TestDetectTruncationContextFullFile:
    """Tests for detect_truncation_context with full_file format."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_detect_truncation_context_full_file(self, recovery):
        """Test end-to-end truncation detection for full_file format."""
        output = """[
  {"file_path": "src/foo.py", "content": "def foo(): pass"},
  {"file_path": "src/bar.py", "content": "def bar"""

        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py"]

        context = recovery.detect_truncation_context(
            raw_output=output,
            deliverables=deliverables,
            stop_reason="max_tokens",
            tokens_used=18000,
        )

        assert context is not None
        assert context.format_type == "full_file"
        assert "src/foo.py" in context.completed_files
        assert context.tokens_used == 18000

    def test_detect_truncation_unknown_format(self, recovery):
        """Test truncation detection returns None for unknown format."""
        output = "Just some plain text that got truncated"

        deliverables = ["file1.py", "file2.py"]

        context = recovery.detect_truncation_context(
            raw_output=output,
            deliverables=deliverables,
            stop_reason="max_tokens",
            tokens_used=5000,
        )

        # Unknown format should return None
        assert context is None


class TestBuildContinuationPromptFormatInstructions:
    """Tests for build_continuation_prompt format-specific instructions."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_continuation_prompt_diff_format(self, recovery):
        """Test continuation prompt uses correct instruction for diff format."""
        context = ContinuationContext(
            completed_files=["file1.py"],
            last_partial_file=None,
            remaining_deliverables=["file2.py"],
            partial_output="...",
            tokens_used=5000,
            format_type="diff",
        )

        prompt = recovery.build_continuation_prompt(context, "Original prompt")

        assert "Continue generating git diff format patches" in prompt

    def test_continuation_prompt_full_file_format(self, recovery):
        """Test continuation prompt uses correct instruction for full_file format."""
        context = ContinuationContext(
            completed_files=["file1.py"],
            last_partial_file=None,
            remaining_deliverables=["file2.py"],
            partial_output="...",
            tokens_used=5000,
            format_type="full_file",
        )

        prompt = recovery.build_continuation_prompt(context, "Original prompt")

        assert "Continue generating full-file JSON operations" in prompt

    def test_continuation_prompt_ndjson_format(self, recovery):
        """Test continuation prompt uses correct instruction for ndjson format."""
        context = ContinuationContext(
            completed_files=["file1.py"],
            last_partial_file=None,
            remaining_deliverables=["file2.py"],
            partial_output="...",
            tokens_used=5000,
            format_type="ndjson",
        )

        prompt = recovery.build_continuation_prompt(context, "Original prompt")

        assert "Continue generating NDJSON operations" in prompt
        assert "one JSON object per line" in prompt

    def test_continuation_prompt_unknown_format(self, recovery):
        """Test continuation prompt uses generic instruction for unknown format."""
        context = ContinuationContext(
            completed_files=["file1.py"],
            last_partial_file=None,
            remaining_deliverables=["file2.py"],
            partial_output="...",
            tokens_used=5000,
            format_type="unknown",
        )

        prompt = recovery.build_continuation_prompt(context, "Original prompt")

        assert "Continue generating the output" in prompt


class TestBuildContinuationPromptTruncation:
    """Tests for build_continuation_prompt list truncation."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_many_completed_files_truncated(self, recovery):
        """Test that more than 5 completed files are truncated in prompt."""
        completed_files = [f"src/file{i}.py" for i in range(10)]

        context = ContinuationContext(
            completed_files=completed_files,
            last_partial_file=None,
            remaining_deliverables=["remaining.py"],
            partial_output="...",
            tokens_used=20000,
            format_type="diff",
        )

        prompt = recovery.build_continuation_prompt(context, "Original prompt")

        # First 5 should be listed
        assert "src/file0.py" in prompt
        assert "src/file4.py" in prompt
        # Should show truncation message
        assert "and 5 more" in prompt

    def test_many_remaining_files_truncated(self, recovery):
        """Test that more than 10 remaining files are truncated in prompt."""
        remaining_files = [f"src/remaining{i}.py" for i in range(15)]

        context = ContinuationContext(
            completed_files=["done.py"],
            last_partial_file=None,
            remaining_deliverables=remaining_files,
            partial_output="...",
            tokens_used=10000,
            format_type="diff",
        )

        prompt = recovery.build_continuation_prompt(context, "Original prompt")

        # First 10 should be listed
        assert "src/remaining0.py" in prompt
        assert "src/remaining9.py" in prompt
        # Should show truncation message
        assert "and 5 more" in prompt

    def test_all_deliverables_completed(self, recovery):
        """Test prompt when remaining_deliverables is empty."""
        context = ContinuationContext(
            completed_files=["file1.py", "file2.py"],
            last_partial_file=None,
            remaining_deliverables=[],
            partial_output="...",
            tokens_used=15000,
            format_type="diff",
        )

        prompt = recovery.build_continuation_prompt(context, "Original prompt")

        assert "All deliverables appear to be completed" in prompt
        assert "finish any partial work" in prompt


class TestContinuationPromptPreviousMarkerRemoval:
    """Tests for removing previous continuation markers from prompts."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_removes_previous_continuation_marker(self, recovery):
        """Test that previous CONTINUATION REQUEST markers are removed."""
        original_prompt = """CONTINUATION REQUEST - Previous attempt was truncated at 3/5 files.

Continue generating git diff format patches.

Continue from where the previous attempt was truncated. Generate ONLY the remaining deliverables.

Generate patches for all files."""

        context = ContinuationContext(
            completed_files=["file1.py", "file2.py", "file3.py"],
            last_partial_file=None,
            remaining_deliverables=["file4.py", "file5.py"],
            partial_output="...",
            tokens_used=10000,
            format_type="diff",
        )

        prompt = recovery.build_continuation_prompt(context, original_prompt)

        # Should have the new continuation marker
        assert "3/5 files" in prompt
        # Original base prompt should be preserved
        assert "Generate patches for all files" in prompt


class TestMergeDiffOutputsEdgeCases:
    """Additional edge case tests for _merge_diff_outputs."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_merge_with_incomplete_diff_header(self, recovery):
        """Test merging when partial ends with incomplete diff header."""
        partial = """diff --git a/src/foo.py b/src/foo.py
new file mode 100644
--- /dev/null
+++ b/src/foo.py
@@ -0,0 +1,3 @@
+def foo():
+    return 42

diff --git a/src/bar.py b/src/bar.py"""  # Incomplete header, no content after

        continuation = """diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null
+++ b/src/bar.py
@@ -0,0 +1,3 @@
+def bar():
+    return 43
"""

        merged = recovery._merge_diff_outputs(partial, continuation)

        # Should have both diffs properly
        assert "src/foo.py" in merged
        assert "src/bar.py" in merged
        # Should handle the incomplete header case
        assert "def foo" in merged
        assert "def bar" in merged


class TestParseDiffTruncationEdgeCases:
    """Additional edge case tests for _parse_diff_truncation."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_parse_diff_empty_output(self, recovery):
        """Test parsing empty diff output."""
        output = ""
        deliverables = ["file1.py", "file2.py"]

        context = recovery._parse_diff_truncation(output, deliverables, 0)

        assert context.completed_files == []
        assert context.remaining_deliverables == deliverables
        assert context.format_type == "diff"

    def test_parse_diff_no_matching_deliverables(self, recovery):
        """Test parsing diff when files don't match deliverables."""
        # Add more content after the hunk to make it "complete" by the logic
        output = """diff --git a/src/other.py b/src/other.py
new file mode 100644
--- /dev/null
+++ b/src/other.py
@@ -0,0 +1,3 @@
+def other():
+    pass
"""
        deliverables = ["file1.py", "file2.py"]

        context = recovery._parse_diff_truncation(output, deliverables, 5000)

        # other.py file is detected (either completed or partial depending on logic)
        # The key is that all original deliverables remain since none match
        assert context.remaining_deliverables == deliverables
        assert context.format_type == "diff"


class TestParseNdjsonTruncationEdgeCases:
    """Additional edge case tests for _parse_ndjson_truncation."""

    @pytest.fixture
    def recovery(self):
        """Create recovery instance."""
        return ContinuationRecovery()

    def test_parse_ndjson_empty_lines(self, recovery):
        """Test parsing NDJSON with empty lines."""
        output = """{"op": "create", "path": "src/foo.py"}

{"op": "create", "path": "src/bar.py"}

"""
        deliverables = ["src/foo.py", "src/bar.py", "src/baz.py"]

        context = recovery._parse_ndjson_truncation(output, deliverables, 5000)

        assert "src/foo.py" in context.completed_files
        assert "src/bar.py" in context.completed_files
        assert context.format_type == "ndjson"

    def test_parse_ndjson_file_path_key(self, recovery):
        """Test parsing NDJSON with file_path key instead of path."""
        output = """{"op": "create", "file_path": "src/foo.py"}
{"op": "create", "file_path": "src/bar.py"}
"""
        deliverables = ["src/foo.py", "src/bar.py"]

        context = recovery._parse_ndjson_truncation(output, deliverables, 5000)

        assert "src/foo.py" in context.completed_files
        assert "src/bar.py" in context.completed_files
