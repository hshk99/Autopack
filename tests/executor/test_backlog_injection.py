"""Tests for IMP-LOOP-001: Backlog Injection Verification.

This module tests the injection verification functionality added to
BacklogMaintenance to ensure generated tasks properly appear in the
execution queue after injection.
"""

from __future__ import annotations

from typing import List
from unittest.mock import Mock, patch

import pytest

from autopack.executor.backlog_maintenance import BacklogMaintenance, InjectionResult, TaskCandidate


class TestInjectionVerification:
    """Tests for injection verification in BacklogMaintenance."""

    @pytest.fixture
    def mock_executor_with_queue(self):
        """Create a mock executor with an active phase queue."""
        executor = Mock()
        executor.run_id = "test-run-injection"
        executor.workspace = "/tmp/test"

        autonomous_loop = Mock()
        autonomous_loop._current_run_phases = []
        executor.autonomous_loop = autonomous_loop

        return executor

    @pytest.fixture
    def mock_executor_no_queue(self):
        """Create a mock executor without an active queue."""
        executor = Mock()
        executor.run_id = "test-run-no-queue"
        executor.workspace = "/tmp/test"
        executor.autonomous_loop = None
        return executor

    @pytest.fixture
    def backlog_maintenance(self, mock_executor_with_queue) -> BacklogMaintenance:
        """Create BacklogMaintenance with mock executor."""
        return BacklogMaintenance(mock_executor_with_queue)

    def test_inject_tasks_returns_injection_result(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test inject_tasks returns InjectionResult."""
        candidates = [TaskCandidate(task_id="IMP-001", title="Test task")]

        result = backlog_maintenance.inject_tasks(candidates)

        assert isinstance(result, InjectionResult)

    def test_inject_empty_list_returns_verified_result(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test injecting empty list returns verified result."""
        result = backlog_maintenance.inject_tasks([])

        assert result.verified is True
        assert result.success_count == 0
        assert result.failure_count == 0

    def test_inject_tasks_populates_injected_ids(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test successful injection populates injected_ids."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task 1"),
            TaskCandidate(task_id="IMP-002", title="Task 2"),
        ]

        result = backlog_maintenance.inject_tasks(candidates)

        assert "IMP-001" in result.injected_ids
        assert "IMP-002" in result.injected_ids

    def test_inject_tasks_verifies_queue_presence(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test verification checks queue presence."""
        candidates = [TaskCandidate(task_id="IMP-001", title="Test task")]

        result = backlog_maintenance.inject_tasks(candidates)

        # Should be verified since task was added to queue
        assert result.verified is True
        assert len(result.verification_errors) == 0

    def test_queue_contains_finds_injected_task(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test queue_contains returns True for injected tasks."""
        candidates = [TaskCandidate(task_id="IMP-001", title="Test task")]

        backlog_maintenance.inject_tasks(candidates)

        assert backlog_maintenance.queue_contains("IMP-001") is True

    def test_queue_contains_returns_false_for_missing_task(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test queue_contains returns False for non-existent tasks."""
        assert backlog_maintenance.queue_contains("NONEXISTENT") is False

    def test_inject_without_queue_fails(self, mock_executor_no_queue) -> None:
        """Test injection fails gracefully when no queue available."""
        bm = BacklogMaintenance(mock_executor_no_queue)
        candidates = [TaskCandidate(task_id="IMP-001", title="Test task")]

        result = bm.inject_tasks(candidates)

        # When no queue is available, injection succeeds but verification fails
        # because queue_contains returns False
        assert result.failure_count > 0 or not result.verified

    def test_inject_validates_before_injection(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test validation runs before injection."""
        candidates = [
            TaskCandidate(task_id="", title="Invalid"),  # Should be filtered
            TaskCandidate(task_id="IMP-001", title="Valid"),
        ]

        result = backlog_maintenance.inject_tasks(candidates)

        # Only valid task should be in injected_ids
        assert "IMP-001" in result.injected_ids
        assert result.success_count == 1

    def test_inject_callback_invoked(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test on_injection callback is invoked."""
        callback_calls: List[str] = []

        def callback(task_id: str) -> None:
            callback_calls.append(task_id)

        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task 1"),
            TaskCandidate(task_id="IMP-002", title="Task 2"),
        ]

        backlog_maintenance.inject_tasks(candidates, on_injection=callback)

        assert len(callback_calls) == 2
        assert "IMP-001" in callback_calls
        assert "IMP-002" in callback_calls


class TestValidateInjectionCandidates:
    """Tests for _validate_injection_candidates method."""

    @pytest.fixture
    def backlog_maintenance(self):
        """Create BacklogMaintenance with mock executor."""
        executor = Mock()
        executor.autonomous_loop = Mock()
        executor.autonomous_loop._current_run_phases = []
        return BacklogMaintenance(executor)

    def test_filters_empty_task_id(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test tasks with empty task_id are filtered."""
        candidates = [
            TaskCandidate(task_id="", title="No ID"),
            TaskCandidate(task_id="IMP-001", title="Has ID"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 1
        assert validated[0].task_id == "IMP-001"

    def test_filters_empty_title(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test tasks with empty title are filtered."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title=""),
            TaskCandidate(task_id="IMP-002", title="Has title"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 1
        assert validated[0].task_id == "IMP-002"

    def test_filters_duplicate_task_ids(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test duplicate task_ids are filtered."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="First"),
            TaskCandidate(task_id="IMP-001", title="Duplicate"),
            TaskCandidate(task_id="IMP-002", title="Second"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        task_ids = [t.task_id for t in validated]
        assert len(task_ids) == 2
        assert task_ids.count("IMP-001") == 1

    def test_normalizes_invalid_priority(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test invalid priorities are normalized to medium."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task", priority="invalid"),
            TaskCandidate(task_id="IMP-002", title="Task", priority="URGENT"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        for task in validated:
            assert task.priority == "medium"

    def test_preserves_valid_priorities(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test valid priorities are preserved."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task", priority="critical"),
            TaskCandidate(task_id="IMP-002", title="Task", priority="high"),
            TaskCandidate(task_id="IMP-003", title="Task", priority="medium"),
            TaskCandidate(task_id="IMP-004", title="Task", priority="low"),
        ]

        validated = backlog_maintenance._validate_injection_candidates(candidates)

        assert len(validated) == 4
        priorities = {t.task_id: t.priority for t in validated}
        assert priorities["IMP-001"] == "critical"
        assert priorities["IMP-002"] == "high"
        assert priorities["IMP-003"] == "medium"
        assert priorities["IMP-004"] == "low"

    def test_empty_list_returns_empty(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test empty list returns empty list."""
        validated = backlog_maintenance._validate_injection_candidates([])
        assert validated == []


class TestPerformInjection:
    """Tests for _perform_injection method."""

    @pytest.fixture
    def mock_executor_with_queue(self):
        """Create mock executor with queue."""
        executor = Mock()
        executor.autonomous_loop = Mock()
        executor.autonomous_loop._current_run_phases = []
        return executor

    @pytest.fixture
    def backlog_maintenance(self, mock_executor_with_queue) -> BacklogMaintenance:
        """Create BacklogMaintenance with mock executor."""
        return BacklogMaintenance(mock_executor_with_queue)

    def test_adds_tasks_to_phase_list(
        self, backlog_maintenance: BacklogMaintenance, mock_executor_with_queue
    ) -> None:
        """Test tasks are added to _current_run_phases."""
        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task 1"),
            TaskCandidate(task_id="IMP-002", title="Task 2"),
        ]

        backlog_maintenance._perform_injection(candidates)

        phases = mock_executor_with_queue.autonomous_loop._current_run_phases
        assert len(phases) == 2
        phase_ids = [p["phase_id"] for p in phases]
        assert "IMP-001" in phase_ids
        assert "IMP-002" in phase_ids

    def test_returns_result_with_injected_ids(
        self, backlog_maintenance: BacklogMaintenance
    ) -> None:
        """Test returns result with injected_ids."""
        candidates = [TaskCandidate(task_id="IMP-001", title="Task")]

        result = backlog_maintenance._perform_injection(candidates)

        assert "IMP-001" in result.injected_ids

    def test_invokes_callback_for_each_task(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test callback is invoked for each injected task."""
        callback_calls: List[str] = []

        candidates = [
            TaskCandidate(task_id="IMP-001", title="Task 1"),
            TaskCandidate(task_id="IMP-002", title="Task 2"),
        ]

        backlog_maintenance._perform_injection(
            candidates, on_injection=lambda x: callback_calls.append(x)
        )

        assert callback_calls == ["IMP-001", "IMP-002"]


class TestTaskToPhaseSpec:
    """Tests for _task_to_phase_spec conversion."""

    @pytest.fixture
    def backlog_maintenance(self):
        """Create BacklogMaintenance with mock executor."""
        executor = Mock()
        return BacklogMaintenance(executor)

    def test_converts_basic_task(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test basic task conversion."""
        candidate = TaskCandidate(task_id="IMP-001", title="Test task")

        spec = backlog_maintenance._task_to_phase_spec(candidate)

        assert spec["phase_id"] == "IMP-001"
        assert spec["description"] == "Test task"
        assert spec["status"] == "QUEUED"

    def test_includes_priority(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test priority is included in spec."""
        candidate = TaskCandidate(task_id="IMP-001", title="Task", priority="high")

        spec = backlog_maintenance._task_to_phase_spec(candidate)

        assert spec["priority"] == "high"
        assert spec["priority_order"] == 1

    def test_priority_order_mapping(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test priority to order mapping."""
        mapping = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }

        for priority, expected_order in mapping.items():
            candidate = TaskCandidate(task_id="IMP-001", title="Task", priority=priority)
            spec = backlog_maintenance._task_to_phase_spec(candidate)
            assert spec["priority_order"] == expected_order

    def test_includes_source(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test source is included in spec."""
        candidate = TaskCandidate(
            task_id="IMP-001",
            title="Task",
            source="telemetry_insights",
        )

        spec = backlog_maintenance._task_to_phase_spec(candidate)

        assert spec["source"] == "telemetry_insights"

    def test_includes_metadata(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test metadata is included in spec."""
        candidate = TaskCandidate(
            task_id="IMP-001",
            title="Task",
            metadata={"scope": {"paths": ["src/"]}},
        )

        spec = backlog_maintenance._task_to_phase_spec(candidate)

        assert spec["metadata"]["generated_task"] is True
        assert spec["metadata"]["injection_source"] == "backlog_maintenance"
        assert spec["scope"] == {"paths": ["src/"]}


class TestVerifyInjection:
    """Tests for _verify_injection method."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor with queue."""
        executor = Mock()
        executor.autonomous_loop = Mock()
        executor.autonomous_loop._current_run_phases = []
        return executor

    @pytest.fixture
    def backlog_maintenance(self, mock_executor) -> BacklogMaintenance:
        """Create BacklogMaintenance with mock executor."""
        return BacklogMaintenance(mock_executor)

    def test_empty_injection_is_verified(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test empty injection result is verified."""
        result = InjectionResult()

        backlog_maintenance._verify_injection(result)

        assert result.verified is True

    def test_all_tasks_found_is_verified(
        self, backlog_maintenance: BacklogMaintenance, mock_executor
    ) -> None:
        """Test verification passes when all tasks found."""
        # Add tasks to queue
        mock_executor.autonomous_loop._current_run_phases = [
            {"phase_id": "IMP-001"},
            {"phase_id": "IMP-002"},
        ]

        result = InjectionResult(injected_ids=["IMP-001", "IMP-002"])

        backlog_maintenance._verify_injection(result)

        assert result.verified is True
        assert len(result.verification_errors) == 0

    def test_missing_tasks_not_verified(
        self, backlog_maintenance: BacklogMaintenance, mock_executor
    ) -> None:
        """Test verification fails when tasks missing."""
        # Only add one task to queue
        mock_executor.autonomous_loop._current_run_phases = [
            {"phase_id": "IMP-001"},
        ]

        result = InjectionResult(injected_ids=["IMP-001", "IMP-002"])

        backlog_maintenance._verify_injection(result)

        assert result.verified is False
        assert len(result.verification_errors) == 1
        assert "IMP-002" in result.verification_errors[0]


class TestQueueStatus:
    """Tests for get_queue_status method."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor with queue."""
        executor = Mock()
        executor.autonomous_loop = Mock()
        executor.autonomous_loop._current_run_phases = []
        return executor

    @pytest.fixture
    def backlog_maintenance(self, mock_executor) -> BacklogMaintenance:
        """Create BacklogMaintenance with mock executor."""
        return BacklogMaintenance(mock_executor)

    def test_empty_queue_status(self, backlog_maintenance: BacklogMaintenance) -> None:
        """Test status of empty queue."""
        status = backlog_maintenance.get_queue_status()

        assert status["total_phases"] == 0
        assert status["queued_count"] == 0
        assert status["in_progress_count"] == 0
        assert status["completed_count"] == 0
        assert status["generated_task_count"] == 0

    def test_queue_with_mixed_statuses(
        self, backlog_maintenance: BacklogMaintenance, mock_executor
    ) -> None:
        """Test status with mixed phase statuses."""
        mock_executor.autonomous_loop._current_run_phases = [
            {"phase_id": "p1", "status": "QUEUED"},
            {"phase_id": "p2", "status": "QUEUED"},
            {"phase_id": "p3", "status": "IN_PROGRESS"},
            {"phase_id": "p4", "status": "COMPLETED"},
            {"phase_id": "p5", "status": "DONE"},
        ]

        status = backlog_maintenance.get_queue_status()

        assert status["total_phases"] == 5
        assert status["queued_count"] == 2
        assert status["in_progress_count"] == 1
        assert status["completed_count"] == 2

    def test_generated_task_count(
        self, backlog_maintenance: BacklogMaintenance, mock_executor
    ) -> None:
        """Test counting generated tasks."""
        mock_executor.autonomous_loop._current_run_phases = [
            {"phase_id": "p1", "status": "QUEUED", "metadata": {"generated_task": True}},
            {"phase_id": "p2", "status": "QUEUED", "metadata": {}},
            {"phase_id": "p3", "status": "QUEUED", "metadata": {"generated_task": True}},
        ]

        status = backlog_maintenance.get_queue_status()

        assert status["generated_task_count"] == 2

    def test_no_autonomous_loop_returns_zeros(self) -> None:
        """Test status when no autonomous_loop available."""
        executor = Mock()
        executor.autonomous_loop = None
        bm = BacklogMaintenance(executor)

        status = bm.get_queue_status()

        assert status["total_phases"] == 0


class TestAutonomousLoopInjectionVerification:
    """Tests for injection verification in AutonomousLoop."""

    def test_inject_generated_tasks_verifies_presence(self) -> None:
        """Test _inject_generated_tasks_into_backlog verifies task presence."""
        # This test verifies the verification logic added to autonomous_loop.py
        from autopack.executor.autonomous_loop import AutonomousLoop

        # Create minimal mock executor
        executor = Mock()
        executor.run_id = "test-run"
        executor.workspace = "/tmp"
        executor.memory_service = None
        executor.db_session = Mock()
        executor.api_client = Mock()
        executor._intention_wiring = None

        loop = AutonomousLoop(executor)

        # Mock _fetch_generated_tasks to return some tasks
        with patch.object(
            loop,
            "_fetch_generated_tasks",
            return_value=[
                {"phase_id": "IMP-GEN-001", "status": "QUEUED"},
                {"phase_id": "IMP-GEN-002", "status": "QUEUED"},
            ],
        ):
            run_data = {"phases": []}

            result = loop._inject_generated_tasks_into_backlog(run_data)

            # Verify tasks were injected
            assert len(result["phases"]) == 2
            phase_ids = [p["phase_id"] for p in result["phases"]]
            assert "IMP-GEN-001" in phase_ids
            assert "IMP-GEN-002" in phase_ids

    def test_queue_contains_method_in_autonomous_loop(self) -> None:
        """Test queue_contains method in AutonomousLoop."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        executor = Mock()
        executor.run_id = "test"
        executor.workspace = "/tmp"
        executor.memory_service = None
        executor.db_session = Mock()
        executor.api_client = Mock()
        executor._intention_wiring = None

        loop = AutonomousLoop(executor)
        loop._current_run_phases = [
            {"phase_id": "IMP-001"},
            {"phase_id": "IMP-002"},
        ]

        assert loop.queue_contains("IMP-001") is True
        assert loop.queue_contains("IMP-002") is True
        assert loop.queue_contains("IMP-003") is False

    def test_get_queued_task_ids_method(self) -> None:
        """Test get_queued_task_ids returns only QUEUED phase IDs."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        executor = Mock()
        executor.run_id = "test"
        executor.workspace = "/tmp"
        executor.memory_service = None
        executor.db_session = Mock()
        executor.api_client = Mock()
        executor._intention_wiring = None

        loop = AutonomousLoop(executor)
        loop._current_run_phases = [
            {"phase_id": "IMP-001", "status": "QUEUED"},
            {"phase_id": "IMP-002", "status": "IN_PROGRESS"},
            {"phase_id": "IMP-003", "status": "QUEUED"},
            {"phase_id": "IMP-004", "status": "COMPLETED"},
        ]

        queued_ids = loop.get_queued_task_ids()

        assert len(queued_ids) == 2
        assert "IMP-001" in queued_ids
        assert "IMP-003" in queued_ids
        assert "IMP-002" not in queued_ids
        assert "IMP-004" not in queued_ids

    def test_get_injection_stats_method(self) -> None:
        """Test get_injection_stats returns correct counts."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        executor = Mock()
        executor.run_id = "test"
        executor.workspace = "/tmp"
        executor.memory_service = None
        executor.db_session = Mock()
        executor.api_client = Mock()
        executor._intention_wiring = None

        loop = AutonomousLoop(executor)
        loop._current_run_phases = [
            {"phase_id": "IMP-001", "status": "QUEUED", "metadata": {"generated_task": True}},
            {"phase_id": "IMP-002", "status": "QUEUED", "metadata": {}},
            {"phase_id": "IMP-003", "status": "COMPLETED", "metadata": {"generated_task": True}},
        ]

        stats = loop.get_injection_stats()

        assert stats["total_phases"] == 3
        assert stats["queued_count"] == 2
        assert stats["generated_task_count"] == 2
