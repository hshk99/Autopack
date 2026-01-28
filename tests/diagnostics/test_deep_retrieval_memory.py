"""Tests for DeepRetrieval memory integration (IMP-DIAG-001).

Tests cover:
- Memory service not configured (returns empty)
- Memory service not enabled (returns empty)
- No project_id in handoff_bundle (returns empty)
- Successful error search retrieval
- Successful code pattern search retrieval
- Budget limits are respected
- Exception handling
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from autopack.diagnostics.deep_retrieval import DeepRetrieval


class TestDeepRetrievalMemory:
    """Tests for DeepRetrieval._retrieve_memory_entries method."""

    @pytest.fixture
    def run_dir(self, tmp_path: Path) -> Path:
        """Create a temporary run directory."""
        run_dir = tmp_path / ".autonomous_runs" / "test-run"
        run_dir.mkdir(parents=True)
        return run_dir

    @pytest.fixture
    def repo_root(self, tmp_path: Path) -> Path:
        """Create a temporary repo root."""
        return tmp_path

    @pytest.fixture
    def mock_memory_service(self) -> Mock:
        """Create a mock memory service."""
        service = Mock()
        service.enabled = True
        service.search_errors = Mock(return_value=[])
        service.search_code = Mock(return_value=[])
        return service

    def test_memory_service_not_configured(self, run_dir: Path, repo_root: Path) -> None:
        """Test that empty list is returned when memory_service is None."""
        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=None)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert result == []

    def test_memory_service_not_enabled(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test that empty list is returned when memory_service is disabled."""
        mock_memory_service.enabled = False
        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert result == []
        mock_memory_service.search_errors.assert_not_called()

    def test_no_project_id_in_handoff(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test that empty list is returned when project_id is missing."""
        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "error_message": "Some error",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert result == []
        mock_memory_service.search_errors.assert_not_called()

    def test_successful_error_search(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test successful retrieval of error entries from memory."""
        mock_memory_service.search_errors.return_value = [
            {
                "id": "error-1",
                "score": 0.95,
                "payload": {"error_snippet": "Previous error: KeyError in module.py"},
            },
            {
                "id": "error-2",
                "score": 0.85,
                "payload": {"content": "Another error content"},
            },
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "KeyError: 'missing_key'",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert len(result) == 2
        assert result[0]["source"] == "memory:error"
        assert result[0]["content"] == "Previous error: KeyError in module.py"
        assert result[0]["relevance_score"] == 0.95
        assert result[0]["metadata"]["collection"] == "errors"
        assert result[0]["metadata"]["id"] == "error-1"

        assert result[1]["source"] == "memory:error"
        assert result[1]["content"] == "Another error content"
        assert result[1]["relevance_score"] == 0.85

    def test_successful_code_pattern_search(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test successful retrieval of code pattern entries from memory."""
        mock_memory_service.search_code.return_value = [
            {
                "id": "code-1",
                "score": 0.90,
                "payload": {"content": "def handle_error(): pass"},
            },
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "",
            "file_path": "src/module.py",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert len(result) == 1
        assert result[0]["source"] == "memory:pattern"
        assert result[0]["content"] == "def handle_error(): pass"
        assert result[0]["relevance_score"] == 0.90
        assert result[0]["metadata"]["collection"] == "code"

    def test_combined_error_and_pattern_search(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test retrieval of both error and code pattern entries."""
        mock_memory_service.search_errors.return_value = [
            {
                "id": "error-1",
                "score": 0.95,
                "payload": {"error_snippet": "Error content"},
            },
        ]
        mock_memory_service.search_code.return_value = [
            {
                "id": "code-1",
                "score": 0.80,
                "payload": {"content": "Code pattern"},
            },
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
            "file_path": "src/module.py",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert len(result) == 2
        # First should be error entry
        assert result[0]["source"] == "memory:error"
        # Second should be pattern entry
        assert result[1]["source"] == "memory:pattern"

    def test_respects_max_entries_limit(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test that MAX_MEMORY_ENTRIES limit is respected."""
        # Return more than MAX_MEMORY_ENTRIES (5)
        mock_memory_service.search_errors.return_value = [
            {
                "id": f"error-{i}",
                "score": 0.9 - i * 0.1,
                "payload": {"error_snippet": f"Error {i}"},
            }
            for i in range(10)
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert len(result) <= DeepRetrieval.MAX_MEMORY_ENTRIES

    def test_respects_size_budget(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test that MAX_MEMORY_ENTRIES_SIZE budget is respected."""
        # Each entry is 2KB, so only 2 should fit in 5KB budget
        large_content = "x" * 2048  # 2KB
        mock_memory_service.search_errors.return_value = [
            {
                "id": f"error-{i}",
                "score": 0.9,
                "payload": {"error_snippet": large_content},
            }
            for i in range(5)
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        total_size = sum(entry["size"] for entry in result)
        assert total_size <= DeepRetrieval.MAX_MEMORY_ENTRIES_SIZE

    def test_truncates_large_content(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test that large content is truncated to fit budget."""
        # Single entry larger than budget
        large_content = "x" * 10000  # 10KB, larger than 5KB budget
        mock_memory_service.search_errors.return_value = [
            {
                "id": "error-1",
                "score": 0.95,
                "payload": {"error_snippet": large_content},
            },
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert len(result) == 1
        assert result[0]["size"] <= DeepRetrieval.MAX_MEMORY_ENTRIES_SIZE

    def test_handles_search_errors_exception(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test graceful handling of search_errors exceptions."""
        mock_memory_service.search_errors.side_effect = Exception("Database error")
        mock_memory_service.search_code.return_value = [
            {
                "id": "code-1",
                "score": 0.80,
                "payload": {"content": "Code pattern"},
            },
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
            "file_path": "src/module.py",
        }

        # Should not raise, should continue with code search
        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        # Should still get code pattern results
        assert len(result) == 1
        assert result[0]["source"] == "memory:pattern"

    def test_handles_search_code_exception(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test graceful handling of search_code exceptions."""
        mock_memory_service.search_errors.return_value = [
            {
                "id": "error-1",
                "score": 0.95,
                "payload": {"error_snippet": "Error content"},
            },
        ]
        mock_memory_service.search_code.side_effect = Exception("Database error")

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
            "file_path": "src/module.py",
        }

        # Should not raise, should return error results
        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert len(result) == 1
        assert result[0]["source"] == "memory:error"

    def test_uses_root_cause_for_pattern_search(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test that root_cause is used for pattern search when file_path is empty."""
        mock_memory_service.search_code.return_value = [
            {
                "id": "code-1",
                "score": 0.85,
                "payload": {"content": "Pattern from root cause"},
            },
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "",
            "root_cause": "Missing dependency import",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        assert len(result) == 1
        mock_memory_service.search_code.assert_called_once()
        call_args = mock_memory_service.search_code.call_args
        assert "Missing dependency import" in call_args.kwargs.get(
            "query", call_args.args[0] if call_args.args else ""
        )

    def test_skips_empty_content(
        self, run_dir: Path, repo_root: Path, mock_memory_service: Mock
    ) -> None:
        """Test that entries with empty content are skipped."""
        mock_memory_service.search_errors.return_value = [
            {
                "id": "error-1",
                "score": 0.95,
                "payload": {"error_snippet": ""},  # Empty content
            },
            {
                "id": "error-2",
                "score": 0.90,
                "payload": {},  # No content at all
            },
            {
                "id": "error-3",
                "score": 0.85,
                "payload": {"error_snippet": "Valid content"},
            },
        ]

        retrieval = DeepRetrieval(run_dir, repo_root, memory_service=mock_memory_service)
        handoff_bundle = {
            "project_id": "test-project",
            "error_message": "Some error",
        }

        result = retrieval._retrieve_memory_entries("phase-1", handoff_bundle)

        # Only the entry with valid content should be included
        assert len(result) == 1
        assert result[0]["content"] == "Valid content"
