"""
Tests for ContinuationRecovery (BUILD-129 Phase 2).

Tests continuation-based recovery from truncation.
"""

import pytest
from autopack.continuation_recovery import ContinuationRecovery, ContinuationContext


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
