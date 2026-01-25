"""Unit tests for task execution feedback functionality.

IMP-LOOP-005: Tests for task execution feedback capture and memory storage
to enable learning from past executions and context improvement.
"""

import time
from unittest.mock import MagicMock, patch


class TestWriteTaskExecutionFeedback:
    """Tests for MemoryService.write_task_execution_feedback method."""

    def test_write_success_feedback(self):
        """Test writing successful execution feedback."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.store = MagicMock()
            service.store.upsert = MagicMock(return_value=1)

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                result = service.write_task_execution_feedback(
                    run_id="test-run-1",
                    phase_id="phase-001",
                    project_id="test-project",
                    success=True,
                    phase_type="build",
                    execution_time_seconds=45.5,
                )

        assert result.startswith("exec_feedback:test-run-1:phase-001:")
        service.store.upsert.assert_called_once()
        call_args = service.store.upsert.call_args
        points = call_args[0][1]
        assert len(points) == 1
        payload = points[0]["payload"]
        assert payload["success"] is True
        assert payload["phase_type"] == "build"
        assert payload["execution_time_seconds"] == 45.5
        assert payload["type"] == "execution_feedback"
        assert payload["task_type"] == "execution_feedback"

    def test_write_failure_feedback(self):
        """Test writing failed execution feedback with error message."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.store = MagicMock()
            service.store.upsert = MagicMock(return_value=1)

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                result = service.write_task_execution_feedback(
                    run_id="test-run-1",
                    phase_id="phase-002",
                    project_id="test-project",
                    success=False,
                    phase_type="test",
                    execution_time_seconds=120.0,
                    error_message="Test failed: assertion error in test_foo",
                )

        assert result.startswith("exec_feedback:test-run-1:phase-002:")
        service.store.upsert.assert_called_once()
        call_args = service.store.upsert.call_args
        payload = call_args[0][1][0]["payload"]
        assert payload["success"] is False
        assert payload["error_message"] == "Test failed: assertion error in test_foo"

    def test_write_feedback_with_learnings(self):
        """Test writing feedback with learnings list."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.store = MagicMock()
            service.store.upsert = MagicMock(return_value=1)

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                learnings = [
                    "Caching improved performance",
                    "Parallel execution helped",
                    "Consider breaking into smaller phases",
                ]
                result = service.write_task_execution_feedback(
                    run_id="test-run-1",
                    phase_id="phase-003",
                    project_id="test-project",
                    success=True,
                    learnings=learnings,
                )

        assert result.startswith("exec_feedback:")
        call_args = service.store.upsert.call_args
        payload = call_args[0][1][0]["payload"]
        assert payload["learnings"] == learnings

    def test_write_feedback_disabled_returns_empty(self):
        """Test that writing feedback when disabled returns empty string."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = False

            result = service.write_task_execution_feedback(
                run_id="test-run-1",
                phase_id="phase-001",
                project_id="test-project",
                success=True,
            )

        assert result == ""

    def test_write_feedback_truncates_long_error_message(self):
        """Test that long error messages are truncated."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.store = MagicMock()
            service.store.upsert = MagicMock(return_value=1)

            long_error = "x" * 5000

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                service.write_task_execution_feedback(
                    run_id="test-run-1",
                    phase_id="phase-001",
                    project_id="test-project",
                    success=False,
                    error_message=long_error,
                )

        call_args = service.store.upsert.call_args
        payload = call_args[0][1][0]["payload"]
        # Error message should be truncated to 2000 chars
        assert len(payload["error_message"]) == 2000

    def test_write_feedback_with_context_summary(self):
        """Test writing feedback with context summary."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.store = MagicMock()
            service.store.upsert = MagicMock(return_value=1)

            context = (
                "Previous errors: TypeError in module X\nSuccessful strategies: retry with backoff"
            )

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                service.write_task_execution_feedback(
                    run_id="test-run-1",
                    phase_id="phase-001",
                    project_id="test-project",
                    success=True,
                    context_summary=context,
                )

        call_args = service.store.upsert.call_args
        payload = call_args[0][1][0]["payload"]
        assert payload["context_summary"] == context

    def test_write_feedback_with_tokens_used(self):
        """Test writing feedback with tokens used metric."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.store = MagicMock()
            service.store.upsert = MagicMock(return_value=1)

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                service.write_task_execution_feedback(
                    run_id="test-run-1",
                    phase_id="phase-001",
                    project_id="test-project",
                    success=True,
                    tokens_used=50000,
                )

        call_args = service.store.upsert.call_args
        payload = call_args[0][1][0]["payload"]
        assert payload["tokens_used"] == 50000


class TestSearchExecutionFeedback:
    """Tests for MemoryService.search_execution_feedback method."""

    def test_search_feedback_basic(self):
        """Test basic search for execution feedback."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.top_k = 5
            service.store = MagicMock()

            mock_results = [
                {
                    "id": "exec_feedback:run1:phase1:123",
                    "score": 0.9,
                    "payload": {
                        "success": True,
                        "phase_type": "build",
                        "type": "execution_feedback",
                    },
                }
            ]
            service.store.search = MagicMock(return_value=mock_results)

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                results = service.search_execution_feedback(
                    query="build phase",
                    project_id="test-project",
                )

        assert len(results) == 1
        assert results[0]["payload"]["success"] is True

    def test_search_feedback_success_only(self):
        """Test searching for only successful execution feedback."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.top_k = 5
            service.store = MagicMock()
            service.store.search = MagicMock(return_value=[])

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                service.search_execution_feedback(
                    query="build phase",
                    project_id="test-project",
                    success_only=True,
                )

        call_args = service.store.search.call_args
        filter_dict = call_args[1]["filter"]
        assert filter_dict["success"] is True

    def test_search_feedback_failures_only(self):
        """Test searching for only failed execution feedback."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.top_k = 5
            service.store = MagicMock()
            service.store.search = MagicMock(return_value=[])

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                service.search_execution_feedback(
                    query="failed test",
                    project_id="test-project",
                    success_only=False,
                )

        call_args = service.store.search.call_args
        filter_dict = call_args[1]["filter"]
        assert filter_dict["success"] is False

    def test_search_feedback_by_phase_type(self):
        """Test searching for execution feedback by phase type."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = True
            service.top_k = 5
            service.store = MagicMock()
            service.store.search = MagicMock(return_value=[])

            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 1536,
            ):
                service.search_execution_feedback(
                    query="deployment",
                    project_id="test-project",
                    phase_type="deploy",
                )

        call_args = service.store.search.call_args
        filter_dict = call_args[1]["filter"]
        assert filter_dict["phase_type"] == "deploy"

    def test_search_feedback_disabled_returns_empty(self):
        """Test that search returns empty when disabled."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService()
            service.enabled = False

            results = service.search_execution_feedback(
                query="build phase",
                project_id="test-project",
            )

        assert results == []


class TestAutonomousLoopExecutionFeedback:
    """Tests for execution feedback recording in AutonomousLoop."""

    @patch("autopack.executor.autonomous_loop.settings")
    def test_record_execution_feedback_success(self, mock_settings):
        """Test recording feedback for successful execution."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run-123"
        mock_executor._get_project_slug = MagicMock(return_value="test-project")
        mock_executor._run_tokens_used = 10000
        mock_memory_service = MagicMock()
        mock_executor.memory_service = mock_memory_service

        loop = AutonomousLoop(mock_executor)

        phase = {"phase_id": "phase-001", "phase_type": "build"}
        start_time = time.time() - 30  # 30 seconds ago

        loop._record_execution_feedback(
            phase=phase,
            success=True,
            status="DONE_SUCCESS",
            execution_start_time=start_time,
        )

        mock_memory_service.write_task_execution_feedback.assert_called_once()
        call_kwargs = mock_memory_service.write_task_execution_feedback.call_args[1]
        assert call_kwargs["run_id"] == "test-run-123"
        assert call_kwargs["phase_id"] == "phase-001"
        assert call_kwargs["success"] is True
        assert call_kwargs["phase_type"] == "build"
        assert call_kwargs["execution_time_seconds"] >= 29  # Approximately 30 seconds

    @patch("autopack.executor.autonomous_loop.settings")
    def test_record_execution_feedback_failure(self, mock_settings):
        """Test recording feedback for failed execution."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run-456"
        mock_executor._get_project_slug = MagicMock(return_value="test-project")
        mock_executor._run_tokens_used = 5000
        mock_memory_service = MagicMock()
        mock_executor.memory_service = mock_memory_service

        loop = AutonomousLoop(mock_executor)

        phase = {"phase_id": "phase-002", "phase_type": "test"}
        start_time = time.time() - 60  # 60 seconds ago

        loop._record_execution_feedback(
            phase=phase,
            success=False,
            status="DONE_FAILURE",
            execution_start_time=start_time,
        )

        mock_memory_service.write_task_execution_feedback.assert_called_once()
        call_kwargs = mock_memory_service.write_task_execution_feedback.call_args[1]
        assert call_kwargs["success"] is False
        assert "DONE_FAILURE" in call_kwargs["error_message"]

    @patch("autopack.executor.autonomous_loop.settings")
    def test_record_execution_feedback_with_memory_context(self, mock_settings):
        """Test recording feedback includes memory context summary."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run-789"
        mock_executor._get_project_slug = MagicMock(return_value="test-project")
        mock_executor._run_tokens_used = 15000
        mock_memory_service = MagicMock()
        mock_executor.memory_service = mock_memory_service

        loop = AutonomousLoop(mock_executor)

        phase = {"phase_id": "phase-003", "phase_type": "build"}
        memory_context = "## Past Errors\n- TypeError in module X\n\n## Strategies\n- Use retry"

        loop._record_execution_feedback(
            phase=phase,
            success=True,
            status="DONE_SUCCESS",
            execution_start_time=time.time(),
            memory_context=memory_context,
        )

        call_kwargs = mock_memory_service.write_task_execution_feedback.call_args[1]
        assert call_kwargs["context_summary"] is not None
        assert "Past Errors" in call_kwargs["context_summary"]

    @patch("autopack.executor.autonomous_loop.settings")
    def test_record_execution_feedback_no_memory_service(self, mock_settings):
        """Test that feedback recording gracefully handles missing memory service."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        mock_executor.memory_service = None  # No memory service

        loop = AutonomousLoop(mock_executor)

        phase = {"phase_id": "phase-001", "phase_type": "build"}

        # Should not raise an exception
        loop._record_execution_feedback(
            phase=phase,
            success=True,
            status="DONE_SUCCESS",
            execution_start_time=time.time(),
        )

    @patch("autopack.executor.autonomous_loop.settings")
    def test_record_execution_feedback_handles_exceptions(self, mock_settings):
        """Test that feedback recording handles exceptions gracefully."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"
        mock_executor._get_project_slug = MagicMock(return_value="test-project")
        mock_memory_service = MagicMock()
        mock_memory_service.write_task_execution_feedback = MagicMock(
            side_effect=Exception("Memory service error")
        )
        mock_executor.memory_service = mock_memory_service

        loop = AutonomousLoop(mock_executor)

        phase = {"phase_id": "phase-001", "phase_type": "build"}

        # Should not raise an exception
        loop._record_execution_feedback(
            phase=phase,
            success=True,
            status="DONE_SUCCESS",
            execution_start_time=time.time(),
        )

    @patch("autopack.executor.autonomous_loop.settings")
    def test_learnings_extracted_for_success(self, mock_settings):
        """Test that learnings are extracted for successful execution."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"
        mock_executor._get_project_slug = MagicMock(return_value="test-project")
        mock_executor._run_tokens_used = 1000
        mock_memory_service = MagicMock()
        mock_executor.memory_service = mock_memory_service

        loop = AutonomousLoop(mock_executor)

        phase = {"phase_id": "phase-001", "phase_type": "build"}

        loop._record_execution_feedback(
            phase=phase,
            success=True,
            status="DONE_SUCCESS",
            execution_start_time=time.time() - 15,  # 15 seconds ago - fast execution
        )

        call_kwargs = mock_memory_service.write_task_execution_feedback.call_args[1]
        learnings = call_kwargs["learnings"]
        assert any("completed successfully" in item for item in learnings)
        assert any("Fast execution" in item for item in learnings)

    @patch("autopack.executor.autonomous_loop.settings")
    def test_learnings_extracted_for_timeout(self, mock_settings):
        """Test that learnings are extracted for timeout failure."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"
        mock_executor._get_project_slug = MagicMock(return_value="test-project")
        mock_executor._run_tokens_used = 1000
        mock_memory_service = MagicMock()
        mock_executor.memory_service = mock_memory_service

        loop = AutonomousLoop(mock_executor)

        phase = {"phase_id": "phase-001", "phase_type": "build"}

        loop._record_execution_feedback(
            phase=phase,
            success=False,
            status="TIMEOUT_EXCEEDED",
            execution_start_time=time.time(),
        )

        call_kwargs = mock_memory_service.write_task_execution_feedback.call_args[1]
        learnings = call_kwargs["learnings"]
        assert any("Timeout" in item for item in learnings)


class TestExecutionFeedbackIntegration:
    """Integration tests for execution feedback in the loop."""

    @patch("autopack.executor.autonomous_loop.settings")
    @patch("autopack.executor.autonomous_loop.time")
    def test_feedback_recorded_after_phase_execution(self, mock_time, mock_settings):
        """Test that feedback is recorded after execute_phase call."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        # Setup settings
        mock_settings.circuit_breaker_enabled = False
        mock_settings.context_ceiling_tokens = 50000

        # Setup time mock
        mock_time.time.return_value = 1000.0
        mock_time.sleep = MagicMock()

        # Create mock executor
        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"
        mock_executor._get_project_slug = MagicMock(return_value="test-project")
        mock_executor._run_tokens_used = 5000
        mock_memory_service = MagicMock()
        mock_executor.memory_service = mock_memory_service

        loop = AutonomousLoop(mock_executor)

        # Manually call _record_execution_feedback as it would be called in the loop
        phase = {"phase_id": "phase-001", "phase_type": "build", "description": "Build app"}

        loop._record_execution_feedback(
            phase=phase,
            success=True,
            status="DONE_SUCCESS",
            execution_start_time=950.0,  # 50 seconds ago
        )

        # Verify feedback was recorded
        mock_memory_service.write_task_execution_feedback.assert_called_once()
        call_kwargs = mock_memory_service.write_task_execution_feedback.call_args[1]

        assert call_kwargs["run_id"] == "test-run"
        assert call_kwargs["phase_id"] == "phase-001"
        assert call_kwargs["project_id"] == "test-project"
        assert call_kwargs["success"] is True
        assert call_kwargs["phase_type"] == "build"
        assert call_kwargs["execution_time_seconds"] == 50.0
