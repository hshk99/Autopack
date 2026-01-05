"""Tests for backlog maintenance system.

Verifies the backlog maintenance helpers work correctly:
- Parsing backlog markdown files
- Converting items to phases
- Git checkpoint operations
- Patch stats parsing
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from autopack.backlog_maintenance import (
    BacklogItem,
    parse_backlog_markdown,
    backlog_items_to_phases,
    write_plan,
    create_git_checkpoint,
    revert_to_checkpoint,
    parse_patch_stats,
)


class TestBacklogItemParsing:
    """Tests for parsing backlog markdown files."""

    def test_parse_empty_file(self, tmp_path: Path):
        """Empty file returns empty list."""
        backlog_file = tmp_path / "backlog.md"
        backlog_file.write_text("")

        items = parse_backlog_markdown(backlog_file)
        assert items == []

    def test_parse_single_item(self, tmp_path: Path):
        """Single bullet item is parsed correctly."""
        backlog_file = tmp_path / "backlog.md"
        backlog_file.write_text("- Fix the login bug\n  This is a critical issue.\n")

        items = parse_backlog_markdown(backlog_file)
        assert len(items) == 1
        assert items[0].title == "Fix the login bug"
        assert "critical issue" in items[0].summary

    def test_parse_multiple_items(self, tmp_path: Path):
        """Multiple bullet items are parsed correctly."""
        content = """- First item
  Description of first item.
- Second item
  Description of second item.
- Third item
  Description of third item.
"""
        backlog_file = tmp_path / "backlog.md"
        backlog_file.write_text(content)

        items = parse_backlog_markdown(backlog_file)
        assert len(items) == 3
        assert items[0].title == "First item"
        assert items[1].title == "Second item"
        assert items[2].title == "Third item"

    def test_parse_respects_max_items(self, tmp_path: Path):
        """max_items parameter limits returned items."""
        content = "\n".join([f"- Item {i}" for i in range(20)])
        backlog_file = tmp_path / "backlog.md"
        backlog_file.write_text(content)

        items = parse_backlog_markdown(backlog_file, max_items=5)
        assert len(items) == 5

    def test_parse_file_not_found(self, tmp_path: Path):
        """FileNotFoundError raised for missing file."""
        backlog_file = tmp_path / "nonexistent.md"

        with pytest.raises(FileNotFoundError):
            parse_backlog_markdown(backlog_file)

    def test_parse_generates_unique_ids(self, tmp_path: Path):
        """Each item gets a unique ID based on title."""
        content = "- Fix bug A\n- Fix bug B\n- Fix bug C\n"
        backlog_file = tmp_path / "backlog.md"
        backlog_file.write_text(content)

        items = parse_backlog_markdown(backlog_file)
        ids = [item.id for item in items]
        assert len(ids) == len(set(ids))  # All unique

    def test_parse_handles_unicode(self, tmp_path: Path):
        """Unicode characters in backlog are handled."""
        content = "- Fix the café menu 🍕\n  Handle émojis and accénts.\n"
        backlog_file = tmp_path / "backlog.md"
        backlog_file.write_text(content, encoding="utf-8")

        items = parse_backlog_markdown(backlog_file)
        assert len(items) == 1
        assert "café" in items[0].title


class TestBacklogItemsToPhases:
    """Tests for converting backlog items to phase specs."""

    def test_empty_items_returns_empty_phases(self):
        """Empty item list returns empty phases."""
        result = backlog_items_to_phases([])
        assert result == {"phases": []}

    def test_single_item_creates_phase(self):
        """Single item creates a valid phase spec."""
        items = [
            BacklogItem(
                id="backlog-test",
                title="Test item",
                summary="Test summary",
            )
        ]

        result = backlog_items_to_phases(items)
        assert len(result["phases"]) == 1

        phase = result["phases"][0]
        assert phase["id"] == "backlog-test"
        assert phase["description"] == "Test item"
        assert phase["task_category"] == "maintenance"
        assert phase["complexity"] == "low"

    def test_default_allowed_paths_applied(self):
        """Default allowed paths are added to phases."""
        items = [BacklogItem(id="test", title="Test", summary="")]

        result = backlog_items_to_phases(items, default_allowed_paths=["src/", "tests/"])

        phase = result["phases"][0]
        assert "src/" in phase["scope"]["paths"]
        assert "tests/" in phase["scope"]["paths"]

    def test_item_allowed_paths_preserved(self):
        """Item-specific allowed paths are preserved."""
        items = [BacklogItem(id="test", title="Test", summary="", allowed_paths=["custom/path/"])]

        result = backlog_items_to_phases(items)
        phase = result["phases"][0]
        assert "custom/path/" in phase["scope"]["paths"]

    def test_budgets_applied(self):
        """Custom budgets are applied to phases."""
        items = [BacklogItem(id="test", title="Test", summary="")]

        result = backlog_items_to_phases(items, max_commands=50, max_seconds=1200)

        phase = result["phases"][0]
        assert phase["budgets"]["max_commands"] == 50
        assert phase["budgets"]["max_seconds"] == 1200

    def test_metadata_includes_backlog_info(self):
        """Phase metadata includes backlog summary and mode."""
        items = [BacklogItem(id="test", title="Test", summary="Detailed summary here")]

        result = backlog_items_to_phases(items)
        phase = result["phases"][0]

        assert phase["metadata"]["backlog_summary"] == "Detailed summary here"
        assert phase["metadata"]["mode"] == "backlog_maintenance"


class TestWritePlan:
    """Tests for writing plan files."""

    def test_write_plan_creates_file(self, tmp_path: Path):
        """Plan is written to specified path."""
        plan = {"phases": [{"id": "test", "description": "Test"}]}
        out_path = tmp_path / "subdir" / "plan.json"

        result = write_plan(plan, out_path)

        assert result == out_path
        assert out_path.exists()

    def test_write_plan_creates_parent_dirs(self, tmp_path: Path):
        """Parent directories are created if needed."""
        plan = {"phases": []}
        out_path = tmp_path / "deep" / "nested" / "plan.json"

        write_plan(plan, out_path)

        assert out_path.exists()

    def test_write_plan_valid_json(self, tmp_path: Path):
        """Written file contains valid JSON."""
        plan = {"phases": [{"id": "test", "key": "value"}]}
        out_path = tmp_path / "plan.json"

        write_plan(plan, out_path)

        loaded = json.loads(out_path.read_text())
        assert loaded == plan


class TestGitCheckpoint:
    """Tests for git checkpoint operations."""

    @patch("autopack.backlog_maintenance.subprocess.run")
    def test_create_checkpoint_success(self, mock_run):
        """Successful checkpoint returns commit hash."""
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123def456\n")

        success, result = create_git_checkpoint(Path("/repo"))

        assert success is True
        assert result == "abc123def456"

    @patch("autopack.backlog_maintenance.subprocess.run")
    def test_create_checkpoint_failure(self, mock_run):
        """Failed checkpoint returns error message."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "git", stderr="nothing to commit")

        success, result = create_git_checkpoint(Path("/repo"))

        assert success is False
        assert "nothing to commit" in result or result is not None

    @patch("autopack.backlog_maintenance.subprocess.run")
    def test_revert_to_checkpoint_success(self, mock_run):
        """Successful revert returns True."""
        mock_run.return_value = MagicMock(returncode=0)

        success, error = revert_to_checkpoint(Path("/repo"), "abc123")

        assert success is True
        assert error is None

    @patch("autopack.backlog_maintenance.subprocess.run")
    def test_revert_to_checkpoint_failure(self, mock_run):
        """Failed revert returns error message."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "git", stderr="invalid commit")

        success, error = revert_to_checkpoint(Path("/repo"), "invalid")

        assert success is False
        assert error is not None


class TestParsePatchStats:
    """Tests for parsing patch statistics."""

    def test_empty_patch(self):
        """Empty patch returns zero stats."""
        stats = parse_patch_stats("")

        assert stats.files_changed == []
        assert stats.lines_added == 0
        assert stats.lines_deleted == 0

    def test_simple_patch(self):
        """Simple patch stats are computed correctly."""
        patch = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
 line1
+added line
 line2
-removed line
 line3
"""
        stats = parse_patch_stats(patch)

        assert "file.py" in stats.files_changed
        assert stats.lines_added == 1
        assert stats.lines_deleted == 1

    def test_multiple_files_patch(self):
        """Multi-file patch counts all files."""
        patch = """--- a/file1.py
+++ b/file1.py
@@ -1 +1 @@
-old
+new
--- a/file2.py
+++ b/file2.py
@@ -1 +1 @@
-old2
+new2
"""
        stats = parse_patch_stats(patch)

        assert len(stats.files_changed) == 2
        assert "file1.py" in stats.files_changed
        assert "file2.py" in stats.files_changed

    def test_addition_only_patch(self):
        """Addition-only patch counts correctly."""
        patch = "+++ b/new.py\n+line1\n+line2\n+line3\n"
        stats = parse_patch_stats(patch)

        assert stats.lines_added == 3
        assert stats.lines_deleted == 0

    def test_deletion_only_patch(self):
        """Deletion-only patch counts correctly."""
        patch = "--- a/old.py\n-line1\n-line2\n"
        stats = parse_patch_stats(patch)

        assert stats.lines_added == 0
        assert stats.lines_deleted == 2


class TestBacklogItemDataclass:
    """Tests for BacklogItem dataclass."""

    def test_default_allowed_paths(self):
        """Default allowed_paths is empty list."""
        item = BacklogItem(id="test", title="Test", summary="Summary")
        assert item.allowed_paths == []

    def test_custom_allowed_paths(self):
        """Custom allowed_paths is preserved."""
        item = BacklogItem(
            id="test", title="Test", summary="Summary", allowed_paths=["src/", "lib/"]
        )
        assert item.allowed_paths == ["src/", "lib/"]


class TestIntegration:
    """Integration tests for backlog maintenance workflow."""

    def test_full_workflow(self, tmp_path: Path):
        """Test complete workflow: parse -> convert -> write."""
        # Create backlog file
        backlog_content = """# Backlog

- Fix authentication timeout
  Users report session expiring too quickly.
  Need to increase timeout value.

- Add rate limiting
  Prevent API abuse by implementing rate limits.
"""
        backlog_file = tmp_path / "backlog.md"
        backlog_file.write_text(backlog_content)
