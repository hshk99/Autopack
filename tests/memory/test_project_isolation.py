"""Tests for IMP-MEM-015: Memory Service Project Namespace Isolation.

This module tests that all memory operations require a valid project_id
to prevent cross-project contamination in vector memory.
"""

from unittest.mock import MagicMock, patch

import pytest

from autopack.memory.memory_service import (
    MemoryService,
    ProjectNamespaceError,
    _validate_project_id,
)


class TestValidateProjectId:
    """Tests for the _validate_project_id helper function."""

    def test_valid_project_id_passes(self):
        """Valid project_id should pass validation."""
        # Should not raise
        _validate_project_id("my-project", "test_operation")
        _validate_project_id("project123", "test_operation")
        _validate_project_id("a", "test_operation")  # Single char is valid

    def test_empty_project_id_raises(self):
        """Empty string project_id should raise ProjectNamespaceError."""
        with pytest.raises(ProjectNamespaceError) as exc_info:
            _validate_project_id("", "test_operation")
        assert "project_id is required" in str(exc_info.value)
        assert "IMP-MEM-015" in str(exc_info.value)

    def test_none_project_id_raises(self):
        """None project_id should raise ProjectNamespaceError."""
        with pytest.raises(ProjectNamespaceError) as exc_info:
            _validate_project_id(None, "test_operation")  # type: ignore
        assert "project_id is required" in str(exc_info.value)

    def test_whitespace_only_project_id_raises(self):
        """Whitespace-only project_id should raise ProjectNamespaceError."""
        with pytest.raises(ProjectNamespaceError) as exc_info:
            _validate_project_id("   ", "test_operation")
        assert "project_id is required" in str(exc_info.value)

        with pytest.raises(ProjectNamespaceError):
            _validate_project_id("\t\n", "test_operation")

    def test_error_message_includes_operation_name(self):
        """Error message should include the operation name for debugging."""
        with pytest.raises(ProjectNamespaceError) as exc_info:
            _validate_project_id("", "search_code")
        assert "search_code" in str(exc_info.value)


class TestMemoryServiceProjectIsolation:
    """Tests for MemoryService methods requiring project_id."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService with mocked store."""
        with patch("autopack.memory.memory_service.FaissStore"):
            with patch("autopack.memory.memory_service.sync_embed_text") as mock_embed:
                mock_embed.return_value = [0.0] * 1536
                service = MemoryService(enabled=True, use_qdrant=False)
                service.store = MagicMock()
                yield service

    def test_search_code_requires_project_id(self, memory_service):
        """search_code should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.search_code("query", "")

        with pytest.raises(ProjectNamespaceError):
            memory_service.search_code("query", "   ")

    def test_search_summaries_requires_project_id(self, memory_service):
        """search_summaries should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.search_summaries("query", "")

    def test_search_errors_requires_project_id(self, memory_service):
        """search_errors should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.search_errors("query", "")

    def test_search_doctor_hints_requires_project_id(self, memory_service):
        """search_doctor_hints should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.search_doctor_hints("query", "")

    def test_search_sot_requires_project_id(self, memory_service):
        """search_sot should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.search_sot("query", "")

    def test_search_planning_requires_project_id(self, memory_service):
        """search_planning should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.search_planning("query", "")

    def test_latest_plan_change_requires_project_id(self, memory_service):
        """latest_plan_change should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.latest_plan_change("")

    def test_search_execution_feedback_requires_project_id(self, memory_service):
        """search_execution_feedback should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.search_execution_feedback("query", "")

    def test_index_file_requires_project_id(self, memory_service):
        """index_file should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.index_file("/path/to/file.py", "content", "")

    def test_write_phase_summary_requires_project_id(self, memory_service):
        """write_phase_summary should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.write_phase_summary(
                run_id="run-1",
                phase_id="phase-1",
                project_id="",
                summary="test summary",
                changes=["file.py"],
            )

    def test_write_error_requires_project_id(self, memory_service):
        """write_error should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.write_error(
                run_id="run-1",
                phase_id="phase-1",
                project_id="",
                error_text="Error message",
            )

    def test_write_doctor_hint_requires_project_id(self, memory_service):
        """write_doctor_hint should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.write_doctor_hint(
                run_id="run-1",
                phase_id="phase-1",
                project_id="",
                hint="Fix the bug",
            )

    def test_write_task_execution_feedback_requires_project_id(self, memory_service):
        """write_task_execution_feedback should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.write_task_execution_feedback(
                run_id="run-1",
                phase_id="phase-1",
                project_id="",
                success=True,
            )

    def test_write_planning_artifact_requires_project_id(self, memory_service):
        """write_planning_artifact should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.write_planning_artifact(
                path="plan.yaml",
                content="plan content",
                project_id="",
                version=1,
            )

    def test_write_plan_change_requires_project_id(self, memory_service):
        """write_plan_change should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.write_plan_change(
                summary="Changed the plan",
                rationale="Because",
                project_id="",
            )

    def test_write_decision_log_requires_project_id(self, memory_service):
        """write_decision_log should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.write_decision_log(
                trigger="error detected",
                choice="retry",
                rationale="might work",
                project_id="",
            )

    def test_retrieve_insights_requires_project_id(self, memory_service):
        """retrieve_insights should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.retrieve_insights(
                query="test query",
                project_id="",
            )

    def test_retrieve_context_requires_project_id(self, memory_service):
        """retrieve_context should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.retrieve_context("query", "")

    def test_retrieve_context_with_metadata_requires_project_id(self, memory_service):
        """retrieve_context_with_metadata should raise error for empty project_id."""
        with pytest.raises(ProjectNamespaceError):
            memory_service.retrieve_context_with_metadata("query", "")


class TestProjectIsolationFiltering:
    """Tests verifying that project_id is properly used in filters."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService with mocked store."""
        with patch("autopack.memory.memory_service.FaissStore"):
            with patch("autopack.memory.memory_service.sync_embed_text") as mock_embed:
                mock_embed.return_value = [0.0] * 1536
                service = MemoryService(enabled=True, use_qdrant=False)
                service.store = MagicMock()
                service.store.search.return_value = []
                yield service

    def test_search_code_filters_by_project_id(self, memory_service):
        """search_code should pass project_id in filter to store."""
        memory_service.search_code("query", "project-123")

        # Verify store.search was called with project_id filter
        call_args = memory_service.store.search.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("filter") or call_args[1].get("filter")
        assert filter_arg["project_id"] == "project-123"

    def test_search_summaries_filters_by_project_id(self, memory_service):
        """search_summaries should pass project_id in filter to store."""
        memory_service.search_summaries("query", "project-456")

        call_args = memory_service.store.search.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("filter") or call_args[1].get("filter")
        assert filter_arg["project_id"] == "project-456"

    def test_search_errors_filters_by_project_id(self, memory_service):
        """search_errors should pass project_id in filter to store."""
        memory_service.search_errors("query", "project-789")

        call_args = memory_service.store.search.call_args
        assert call_args is not None
        filter_arg = call_args.kwargs.get("filter") or call_args[1].get("filter")
        assert filter_arg["project_id"] == "project-789"


class TestProjectNamespaceErrorInheritance:
    """Tests for ProjectNamespaceError exception class."""

    def test_inherits_from_value_error(self):
        """ProjectNamespaceError should inherit from ValueError."""
        assert issubclass(ProjectNamespaceError, ValueError)

    def test_can_be_caught_as_value_error(self):
        """ProjectNamespaceError should be catchable as ValueError."""
        with pytest.raises(ValueError):
            raise ProjectNamespaceError("test error")

    def test_error_message_preserved(self):
        """ProjectNamespaceError should preserve error message."""
        error = ProjectNamespaceError("test message")
        assert str(error) == "test message"
