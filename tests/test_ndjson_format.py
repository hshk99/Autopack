"""
Tests for NDJSON Format (BUILD-129 Phase 3).

Tests truncation-tolerant NDJSON parsing and application.
"""

import pytest

from autopack.ndjson_format import (
    NDJSONParser,
    NDJSONApplier,
    NDJSONOperation,
    NDJSONParseResult,
    detect_ndjson_format,
)


class TestNDJSONOperation:
    """Test NDJSONOperation dataclass."""

    def test_create_operation_to_dict(self):
        """Test create operation serialization."""
        op = NDJSONOperation(
            op_type="create",
            file_path="src/foo.py",
            content="def foo():\n    pass",
            operations=None,
            metadata=None,
        )

        result = op.to_dict()

        assert result["type"] == "create"
        assert result["file_path"] == "src/foo.py"
        assert result["content"] == "def foo():\n    pass"
        assert "operations" not in result  # None fields excluded

    def test_modify_operation_to_dict(self):
        """Test modify operation serialization."""
        op = NDJSONOperation(
            op_type="modify",
            file_path="src/bar.py",
            content=None,
            operations=[{"type": "append", "content": "\nprint('hi')"}],
            metadata=None,
        )

        result = op.to_dict()

        assert result["type"] == "modify"
        assert result["file_path"] == "src/bar.py"
        assert len(result["operations"]) == 1
        assert "content" not in result


class TestNDJSONParser:
    """Test NDJSON parsing."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return NDJSONParser()

    def test_parse_simple_ndjson(self, parser):
        """Test parsing simple NDJSON with meta + operations."""
        output = """{\"type\": \"meta\", \"summary\": \"Add user service\", \"total_operations\": 2}
{\"type\": \"create\", \"file_path\": \"src/user.py\", \"content\": \"class User:\\n    pass\"}
{\"type\": \"create\", \"file_path\": \"tests/test_user.py\", \"content\": \"def test_user():\\n    assert True\"}"""

        result = parser.parse(output)

        assert isinstance(result, NDJSONParseResult)
        assert result.total_expected == 2
        assert len(result.operations) == 2
        assert not result.was_truncated
        assert result.lines_parsed == 3
        assert result.lines_failed == 0

    def test_parse_without_meta(self, parser):
        """Test parsing NDJSON without meta line."""
        output = """{\"type\": \"create\", \"file_path\": \"src/foo.py\", \"content\": \"pass\"}
{\"type\": \"modify\", \"file_path\": \"src/bar.py\", \"operations\": [{\"type\": \"append\", \"content\": \"new\"}]}"""

        result = parser.parse(output)

        assert result.total_expected is None  # No meta line
        assert len(result.operations) == 2
        assert not result.was_truncated

    def test_parse_truncated_last_line(self, parser):
        """Test parsing NDJSON with truncated last line."""
        output = """{\"type\": \"meta\", \"summary\": \"Test\", \"total_operations\": 3}
{\"type\": \"create\", \"file_path\": \"src/a.py\", \"content\": \"pass\"}
{\"type\": \"create\", \"file_path\": \"src/b.py\", \"content\": \"pass\"}
{\"type\": \"create\", \"file_path\": \"src/c.py\", \"content\": \"pa"""  # Truncated mid-string

        result = parser.parse(output)

        assert result.was_truncated is True
        assert result.total_expected == 3
        assert len(result.operations) == 2  # Only first 2 complete
        assert result.lines_failed == 1

    def test_parse_empty_lines(self, parser):
        """Test parsing NDJSON with empty lines (should be skipped)."""
        output = """{\"type\": \"create\", \"file_path\": \"src/foo.py\", \"content\": \"pass\"}

{\"type\": \"create\", \"file_path\": \"src/bar.py\", \"content\": \"pass\"}
"""

        result = parser.parse(output)

        assert len(result.operations) == 2
        assert not result.was_truncated

    def test_parse_create_operation(self, parser):
        """Test parsing create operation."""
        output = '{"type": "create", "file_path": "src/module.py", "content": "def hello():\\n    return 42"}'

        result = parser.parse(output)

        assert len(result.operations) == 1
        op = result.operations[0]
        assert op.op_type == "create"
        assert op.file_path == "src/module.py"
        assert "def hello():" in op.content

    def test_parse_modify_operation(self, parser):
        """Test parsing modify operation."""
        output = '{"type": "modify", "file_path": "src/existing.py", "operations": [{"type": "append", "content": "\\nprint(\'added\')"}]}'

        result = parser.parse(output)

        assert len(result.operations) == 1
        op = result.operations[0]
        assert op.op_type == "modify"
        assert op.file_path == "src/existing.py"
        assert len(op.operations) == 1
        assert op.operations[0]["type"] == "append"

    def test_parse_delete_operation(self, parser):
        """Test parsing delete operation."""
        output = '{"type": "delete", "file_path": "src/old.py"}'

        result = parser.parse(output)

        assert len(result.operations) == 1
        op = result.operations[0]
        assert op.op_type == "delete"
        assert op.file_path == "src/old.py"

    def test_parse_malformed_mid_output(self, parser):
        """Test parsing with malformed JSON in middle (unexpected)."""
        output = """{\"type\": \"create\", \"file_path\": \"src/a.py\", \"content\": \"pass\"}
{invalid json line}
{\"type\": \"create\", \"file_path\": \"src/b.py\", \"content\": \"pass\"}"""

        result = parser.parse(output)

        # Should log error but continue parsing
        assert len(result.operations) == 2  # First and last lines valid
        assert result.lines_failed == 1

    def test_parse_files_wrapper_schema_multiline(self, parser):
        """Test recovery of alternate {"files":[...]} schema (pretty-printed multi-line JSON)."""
        output = """{
  "files": [
    {"path": "docs/a.md", "mode": "create", "new_content": "hello"},
    {"path": "docs/b.md", "mode": "create", "new_content": "world"}
  ]
}"""
        result = parser.parse(output)
        assert len(result.operations) == 2
        assert {op.file_path for op in result.operations} == {"docs/a.md", "docs/b.md"}
        assert all(op.op_type == "create" for op in result.operations)

    def test_parse_files_wrapper_truncated_outer_recovers_inner(self, parser):
        """Recover file objects even when the outer {"files":[...]} wrapper is truncated/incomplete."""
        output = """{
  "files": [
    {"path": "docs/a.md", "mode": "create", "new_content": "hello"},
    {"path": "docs/b.md", "mode": "create", "new_content": "world"}"""
        result = parser.parse(output)
        assert len(result.operations) == 2
        assert {op.file_path for op in result.operations} == {"docs/a.md", "docs/b.md"}

    def test_format_for_prompt(self, parser):
        """Test generating NDJSON format instruction."""
        deliverables = ["src/user.py", "src/auth.py", "tests/test_user.py"]
        summary = "Add user authentication"

        prompt = parser.format_for_prompt(deliverables, summary)

        assert "NDJSON" in prompt
        assert 'total_operations": 3' in prompt
        assert "one complete JSON object per line" in prompt
        assert "NO line breaks within JSON objects" in prompt


class TestNDJSONApplier:
    """Test NDJSON application."""

    @pytest.fixture
    def applier(self, tmp_path):
        """Create applier with temp workspace."""
        return NDJSONApplier(workspace=tmp_path)

    def test_apply_create_operation(self, applier, tmp_path):
        """Test applying create operation."""
        op = NDJSONOperation(
            op_type="create",
            file_path="src/module.py",
            content="def foo():\n    return 42",
            operations=None,
            metadata=None,
        )

        result = applier.apply([op])

        assert len(result["applied"]) == 1
        assert "src/module.py" in result["applied"]
        assert len(result["failed"]) == 0

        # Verify file created
        created_file = tmp_path / "src" / "module.py"
        assert created_file.exists()
        assert "def foo():" in created_file.read_text()

    def test_apply_multiple_creates(self, applier, tmp_path):
        """Test applying multiple create operations."""
        ops = [
            NDJSONOperation("create", "src/a.py", "# A", None, None),
            NDJSONOperation("create", "src/b.py", "# B", None, None),
            NDJSONOperation("create", "tests/test_a.py", "# Test A", None, None),
        ]

        result = applier.apply(ops)

        assert len(result["applied"]) == 3
        assert len(result["failed"]) == 0

        # Verify all files created
        assert (tmp_path / "src" / "a.py").exists()
        assert (tmp_path / "src" / "b.py").exists()
        assert (tmp_path / "tests" / "test_a.py").exists()

    def test_apply_modify_append(self, applier, tmp_path):
        """Test applying modify operation with append."""
        # Create initial file
        test_file = tmp_path / "src" / "module.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Initial content\n")

        op = NDJSONOperation(
            op_type="modify",
            file_path="src/module.py",
            content=None,
            operations=[{"type": "append", "content": "\n# Appended content"}],
            metadata=None,
        )

        result = applier.apply([op])

        assert len(result["applied"]) == 1
        assert len(result["failed"]) == 0

        # Verify content modified
        modified_content = test_file.read_text()
        assert "# Initial content" in modified_content
        assert "# Appended content" in modified_content

    def test_apply_modify_insert_after(self, applier, tmp_path):
        """Test applying modify operation with insert_after."""
        # Create initial file
        test_file = tmp_path / "src" / "module.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("import os\n\ndef foo():\n    pass")

        op = NDJSONOperation(
            op_type="modify",
            file_path="src/module.py",
            content=None,
            operations=[{"type": "insert_after", "anchor": "import os", "content": "import sys"}],
            metadata=None,
        )

        result = applier.apply([op])

        assert len(result["applied"]) == 1

        # Verify insertion
        modified_content = test_file.read_text()
        lines = modified_content.split("\n")
        assert lines[0] == "import os"
        assert lines[1] == "import sys"

    def test_apply_modify_replace(self, applier, tmp_path):
        """Test applying modify operation with replace."""
        # Create initial file
        test_file = tmp_path / "src" / "module.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("OLD_VALUE = 42")

        op = NDJSONOperation(
            op_type="modify",
            file_path="src/module.py",
            content=None,
            operations=[
                {"type": "replace", "old_text": "OLD_VALUE = 42", "new_text": "NEW_VALUE = 100"}
            ],
            metadata=None,
        )

        result = applier.apply([op])

        assert len(result["applied"]) == 1

        # Verify replacement
        modified_content = test_file.read_text()
        assert "NEW_VALUE = 100" in modified_content
        assert "OLD_VALUE" not in modified_content

    def test_apply_delete_operation(self, applier, tmp_path):
        """Test applying delete operation."""
        # Create file to delete
        test_file = tmp_path / "src" / "old.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Old file")

        op = NDJSONOperation(
            op_type="delete", file_path="src/old.py", content=None, operations=None, metadata=None
        )

        result = applier.apply([op])

        assert len(result["applied"]) == 1

        # Verify file deleted
        assert not test_file.exists()

    def test_apply_handles_errors_gracefully(self, applier, tmp_path):
        """Test that errors in one operation don't stop others."""
        ops = [
            NDJSONOperation("create", "src/a.py", "# A", None, None),
            NDJSONOperation(
                "modify", "src/nonexistent.py", None, [{"type": "append", "content": "x"}], None
            ),  # Will fail
            NDJSONOperation("create", "src/b.py", "# B", None, None),
        ]

        result = applier.apply(ops)

        assert len(result["applied"]) == 2  # First and last succeeded
        assert len(result["failed"]) == 1  # Middle failed
        assert result["failed"][0]["file_path"] == "src/nonexistent.py"

        # Verify successful files created
        assert (tmp_path / "src" / "a.py").exists()
        assert (tmp_path / "src" / "b.py").exists()

    def test_apply_create_with_nested_directories(self, applier, tmp_path):
        """Test creating file in nested directory structure."""
        op = NDJSONOperation(
            op_type="create",
            file_path="src/services/auth/user_service.py",
            content="# User service",
            operations=None,
            metadata=None,
        )

        result = applier.apply([op])

        assert len(result["applied"]) == 1

        # Verify nested directory created
        created_file = tmp_path / "src" / "services" / "auth" / "user_service.py"
        assert created_file.exists()
        assert created_file.parent.exists()


class TestNDJSONDetection:
    """Test NDJSON format detection."""

    def test_detect_valid_ndjson(self):
        """Test detecting valid NDJSON format."""
        output = """{\"type\": \"meta\", \"summary\": \"Test\"}
{\"type\": \"create\", \"file_path\": \"src/foo.py\", \"content\": \"pass\"}"""

        assert detect_ndjson_format(output) is True

    def test_detect_ndjson_without_meta(self):
        """Test detecting NDJSON without meta line."""
        output = """{\"type\": \"create\", \"file_path\": \"src/foo.py\", \"content\": \"pass\"}
{\"type\": \"modify\", \"file_path\": \"src/bar.py\", \"operations\": []}"""

        assert detect_ndjson_format(output) is True

    def test_detect_non_ndjson_single_json(self):
        """Test that single JSON object is NOT NDJSON."""
        output = '{"operations": [{"type": "create", "file_path": "foo.py"}]}'

        assert detect_ndjson_format(output) is False

    def test_detect_non_ndjson_diff_format(self):
        """Test that diff format is NOT NDJSON."""
        output = """diff --git a/src/foo.py b/src/foo.py
new file mode 100644
--- /dev/null
+++ b/src/foo.py"""

        assert detect_ndjson_format(output) is False

    def test_detect_non_ndjson_plain_text(self):
        """Test that plain text is NOT NDJSON."""
        output = "This is just some plain text output"

        assert detect_ndjson_format(output) is False


class TestNDJSONIntegration:
    """Integration tests for NDJSON format."""

    def test_full_workflow_parse_and_apply(self, tmp_path):
        """Test complete workflow: parse NDJSON → apply operations."""
        parser = NDJSONParser()
        applier = NDJSONApplier(workspace=tmp_path)

        # Simulate LLM output
        llm_output = """{\"type\": \"meta\", \"summary\": \"Add user service\", \"total_operations\": 3}
{\"type\": \"create\", \"file_path\": \"src/user_service.py\", \"content\": \"class UserService:\\n    def __init__(self):\\n        self.users = []\\n\\n    def add_user(self, name):\\n        self.users.append(name)\"}
{\"type\": \"create\", \"file_path\": \"tests/test_user_service.py\", \"content\": \"import pytest\\nfrom src.user_service import UserService\\n\\ndef test_add_user():\\n    service = UserService()\\n    service.add_user('Alice')\\n    assert 'Alice' in service.users\"}
{\"type\": \"create\", \"file_path\": \"README.md\", \"content\": \"# User Service\\n\\nA simple user management service.\"}"""

        # Parse
        parse_result = parser.parse(llm_output)

        assert parse_result.total_expected == 3
        assert len(parse_result.operations) == 3
        assert not parse_result.was_truncated

        # Apply
        apply_result = applier.apply(parse_result.operations)

        assert len(apply_result["applied"]) == 3
        assert len(apply_result["failed"]) == 0

        # Verify files
        assert (tmp_path / "src" / "user_service.py").exists()
        assert (tmp_path / "tests" / "test_user_service.py").exists()
        assert (tmp_path / "README.md").exists()

        # Verify content
        user_service_content = (tmp_path / "src" / "user_service.py").read_text()
        assert "class UserService:" in user_service_content
        assert "def add_user" in user_service_content

    def test_truncation_recovery_workflow(self, tmp_path):
        """Test workflow with truncation - partial operations still applied."""
        parser = NDJSONParser()
        applier = NDJSONApplier(workspace=tmp_path)

        # Simulate truncated LLM output (truncates mid-3rd operation)
        truncated_output = """{\"type\": \"meta\", \"summary\": \"Test\", \"total_operations\": 4}
{\"type\": \"create\", \"file_path\": \"src/a.py\", \"content\": \"# File A\"}
{\"type\": \"create\", \"file_path\": \"src/b.py\", \"content\": \"# File B\"}
{\"type\": \"create\", \"file_path\": \"src/c.py\", \"content\": \"# File C incomplete"""

        # Parse (should detect truncation)
        parse_result = parser.parse(truncated_output)

        assert parse_result.was_truncated is True
        assert parse_result.total_expected == 4
        assert len(parse_result.operations) == 2  # Only first 2 complete

        # Apply (should succeed for complete operations)
        apply_result = applier.apply(parse_result.operations)

        assert len(apply_result["applied"]) == 2
        assert len(apply_result["failed"]) == 0

        # Verify partial success
        assert (tmp_path / "src" / "a.py").exists()
        assert (tmp_path / "src" / "b.py").exists()
        assert not (tmp_path / "src" / "c.py").exists()  # Truncated, not created

        # Key benefit: 2/4 operations succeeded despite truncation
        # In monolithic JSON, ALL operations would be lost
