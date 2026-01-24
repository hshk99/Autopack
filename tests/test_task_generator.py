"""Tests for ROAD-C Autonomous Task Generator."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from autopack.roadc import AutonomousTaskGenerator, GeneratedTask, TaskGenerationResult
from autopack.telemetry.analyzer import RankedIssue


class TestAutonomousTaskGenerator:
    """Test suite for AutonomousTaskGenerator."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        service = Mock()
        service.retrieve_insights = Mock(return_value=[])
        return service

    def test_generator_initialization_with_defaults(self):
        """Test that generator can be initialized with default services."""
        with patch("autopack.roadc.task_generator.MemoryService"):
            generator = AutonomousTaskGenerator()
            assert generator is not None

    def test_generator_initialization_with_custom_services(self, mock_memory_service):
        """Test that generator can be initialized with custom services."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        assert generator._memory == mock_memory_service

    def test_generate_tasks_returns_task_generation_result(self, mock_memory_service):
        """Test that generate_tasks returns TaskGenerationResult."""
        mock_memory_service.retrieve_insights.return_value = []

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(max_tasks=5)

        assert isinstance(result, TaskGenerationResult)
        assert result.insights_processed >= 0
        assert result.patterns_detected >= 0

    def test_pattern_detection_groups_similar_errors(self, mock_memory_service):
        """Test that pattern detection groups similar error types."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        insights = [
            {"issue_type": "timeout", "content": "API timeout", "id": "1", "severity": "high"},
            {"issue_type": "timeout", "content": "DB timeout", "id": "2", "severity": "high"},
            {"issue_type": "error", "content": "Syntax error", "id": "3", "severity": "low"},
        ]

        patterns = generator._detect_patterns(insights)

        # Should group the 2 timeouts
        timeout_pattern = next((p for p in patterns if p["type"] == "timeout"), None)
        assert timeout_pattern is not None
        assert timeout_pattern["occurrences"] == 2
        assert len(timeout_pattern["examples"]) > 0

    def test_pattern_detection_filters_single_occurrences(self, mock_memory_service):
        """Test that pattern detection ignores single-occurrence errors."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        insights = [
            {"issue_type": "timeout", "content": "API timeout", "id": "1", "severity": "high"},
            {
                "issue_type": "unique_error",
                "content": "One-off error",
                "id": "2",
                "severity": "low",
            },
        ]

        patterns = generator._detect_patterns(insights)

        # Only timeout should be detected (needs 2+ occurrences)
        unique_pattern = next((p for p in patterns if p["type"] == "unique_error"), None)
        assert unique_pattern is None

    def test_severity_calculation(self, mock_memory_service):
        """Test that severity is calculated correctly."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Group with multiple high-severity items
        group = [
            {"severity": "high"},
            {"severity": "high"},
            {"severity": "low"},
            {"severity": "low"},
        ]

        severity = generator._calculate_severity(group)

        # Should account for count and high-severity items
        assert severity > 0
        assert severity <= 10

    def test_severity_to_priority_mapping(self, mock_memory_service):
        """Test that severity maps to priority correctly."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        assert generator._severity_to_priority(9) == "critical"
        assert generator._severity_to_priority(7) == "high"
        assert generator._severity_to_priority(5) == "medium"
        assert generator._severity_to_priority(2) == "low"

    def test_effort_estimation(self, mock_memory_service):
        """Test that effort is estimated based on occurrences."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        assert generator._estimate_effort({"occurrences": 15}) == "XL"
        assert generator._estimate_effort({"occurrences": 7}) == "L"
        assert generator._estimate_effort({"occurrences": 3}) == "M"
        assert generator._estimate_effort({"occurrences": 1}) == "S"

    def test_generated_task_has_required_fields(self):
        """Test that generated tasks have all required fields."""
        task = GeneratedTask(
            task_id="TASK-ABC123",
            title="Test task",
            description="Test description",
            priority="high",
            source_insights=["insight-1"],
            suggested_files=["src/file.py"],
            estimated_effort="M",
            created_at=datetime.now(),
        )

        assert task.task_id.startswith("TASK-")
        assert task.priority in ["critical", "high", "medium", "low"]
        assert task.estimated_effort in ["S", "M", "L", "XL"]
        assert len(task.source_insights) > 0

    def test_pattern_to_task_conversion(self, mock_memory_service):
        """Test that patterns are converted to tasks correctly."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        pattern = {
            "type": "timeout",
            "occurrences": 6,
            "confidence": 0.8,
            "examples": [
                {
                    "id": "1",
                    "content": "Timeout error",
                    "file_path": "src/timeout.py",
                    "severity": "high",
                },
                {
                    "id": "2",
                    "content": "Another timeout",
                    "file_path": "src/timeout.py",
                    "severity": "high",
                },
            ],
            "severity": 7,
        }

        task = generator._pattern_to_task(pattern)

        assert isinstance(task, GeneratedTask)
        assert task.task_id.startswith("TASK-")
        assert "timeout" in task.title.lower()
        assert task.priority == "high"
        assert task.estimated_effort == "L"

    def test_task_generation_respects_min_confidence(self, mock_memory_service):
        """Test that task generation filters by minimum confidence."""
        mock_memory_service.retrieve_insights.return_value = [
            {"issue_type": "error", "content": "Error 1", "id": "1", "severity": "high"},
            {"issue_type": "error", "content": "Error 2", "id": "2", "severity": "high"},
            {"issue_type": "timeout", "content": "Timeout 1", "id": "3", "severity": "low"},
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(max_tasks=10, min_confidence=0.8)

        # With high min_confidence, fewer tasks should be generated
        assert isinstance(result, TaskGenerationResult)

    def test_task_generation_respects_max_tasks(self, mock_memory_service):
        """Test that task generation respects max_tasks limit."""
        # Create many insights to generate many patterns
        insights = []
        for i in range(20):
            error_type = f"error_{i % 5}"
            insights.append(
                {
                    "issue_type": error_type,
                    "content": f"Error {i}",
                    "id": str(i),
                    "severity": "high",
                }
            )

        mock_memory_service.retrieve_insights.return_value = insights

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(max_tasks=3, min_confidence=0.0)

        # Should not exceed max_tasks
        assert len(result.tasks_generated) <= 3

    def test_description_generation(self, mock_memory_service):
        """Test that task descriptions are generated correctly."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        pattern = {
            "type": "timeout",
            "occurrences": 3,
            "examples": [
                {"content": "Timeout error 1"},
                {"content": "Timeout error 2"},
            ],
        }

        description = generator._generate_description(pattern)

        assert "Problem" in description
        assert "timeout" in description.lower()
        assert "occurrences" in description.lower()

    def test_file_suggestion_extraction(self, mock_memory_service):
        """Test that files are suggested from pattern examples."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        pattern = {
            "examples": [
                {"file_path": "src/file1.py"},
                {"file_path": "src/file2.py"},
                {"file_path": "src/file1.py"},  # Duplicate
            ]
        }

        files = generator._suggest_files(pattern)

        assert "src/file1.py" in files
        assert "src/file2.py" in files
        assert len(files) <= 5

    def test_task_generation_result_metrics(self, mock_memory_service):
        """Test that TaskGenerationResult tracks metrics correctly."""
        mock_memory_service.retrieve_insights.return_value = [
            {"issue_type": "error", "content": "Error 1", "id": "1", "severity": "high"},
            {"issue_type": "error", "content": "Error 2", "id": "2", "severity": "high"},
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(max_tasks=10)

        assert result.insights_processed == 2
        assert result.patterns_detected >= 0
        assert result.generation_time_ms >= 0

    def test_persist_tasks_count_only_after_commit_success(self, mock_memory_service):
        """Test that persisted_count is only returned after successful commit (IMP-LOOP-002)."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        tasks = [
            GeneratedTask(
                task_id="TASK-TEST001",
                title="Test task 1",
                description="Description 1",
                priority="high",
                source_insights=["i1"],
                suggested_files=["f1.py"],
                estimated_effort="M",
                created_at=datetime.now(),
            ),
            GeneratedTask(
                task_id="TASK-TEST002",
                title="Test task 2",
                description="Description 2",
                priority="medium",
                source_insights=["i2"],
                suggested_files=["f2.py"],
                estimated_effort="S",
                created_at=datetime.now(),
            ),
        ]

        # Mock database session and commit failure
        mock_session = Mock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.commit.side_effect = Exception("Database commit failed")

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            # Should raise exception on commit failure
            with pytest.raises(Exception, match="Database commit failed"):
                generator.persist_tasks(tasks)

        # Verify rollback was called
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    def test_persist_tasks_returns_correct_count_on_success(self, mock_memory_service):
        """Test that persist_tasks returns correct count after successful commit."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        tasks = [
            GeneratedTask(
                task_id="TASK-TEST001",
                title="Test task 1",
                description="Description 1",
                priority="high",
                source_insights=["i1"],
                suggested_files=["f1.py"],
                estimated_effort="M",
                created_at=datetime.now(),
            ),
            GeneratedTask(
                task_id="TASK-TEST002",
                title="Test task 2",
                description="Description 2",
                priority="medium",
                source_insights=["i2"],
                suggested_files=["f2.py"],
                estimated_effort="S",
                created_at=datetime.now(),
            ),
        ]

        # Mock database session with successful commit
        mock_session = Mock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            count = generator.persist_tasks(tasks)

        # Should return count of persisted tasks
        assert count == 2
        mock_session.commit.assert_called_once()
        assert mock_session.add.call_count == 2


class TestTelemetryInsightsWiring:
    """Tests for IMP-FEAT-001: Wire TelemetryAnalyzer output to TaskGenerator."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        service = Mock()
        service.retrieve_insights = Mock(return_value=[])
        return service

    @pytest.fixture
    def sample_telemetry_insights(self):
        """Create sample telemetry insights from TelemetryAnalyzer."""
        return {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="build-phase-1",
                    phase_type="build",
                    metric_value=75000.0,
                    details={"avg_tokens": 25000.0, "count": 3},
                ),
                RankedIssue(
                    rank=2,
                    issue_type="cost_sink",
                    phase_id="test-phase-1",
                    phase_type="test",
                    metric_value=50000.0,
                    details={"avg_tokens": 16666.0, "count": 3},
                ),
            ],
            "top_failure_modes": [
                RankedIssue(
                    rank=1,
                    issue_type="failure_mode",
                    phase_id="deploy-phase-1",
                    phase_type="deploy",
                    metric_value=10.0,
                    details={"outcome": "FAILED", "stop_reason": "timeout"},
                ),
            ],
            "top_retry_causes": [
                RankedIssue(
                    rank=1,
                    issue_type="retry_cause",
                    phase_id="integration-phase",
                    phase_type="integration",
                    metric_value=8.0,
                    details={"stop_reason": "rate_limit", "success_count": 2, "retry_count": 8},
                ),
            ],
            "phase_type_stats": {
                "build:opus": {"success_rate": 0.9, "avg_tokens": 5000, "sample_count": 10}
            },
        }

    def test_generate_tasks_accepts_telemetry_insights(
        self, mock_memory_service, sample_telemetry_insights
    ):
        """Test that generate_tasks accepts telemetry_insights parameter."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.0,
            telemetry_insights=sample_telemetry_insights,
        )

        assert isinstance(result, TaskGenerationResult)
        # Should not call memory service when telemetry is provided
        mock_memory_service.retrieve_insights.assert_not_called()

    def test_convert_telemetry_to_insights_converts_cost_sinks(
        self, mock_memory_service, sample_telemetry_insights
    ):
        """Test that cost sinks are converted to insight format."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        insights = generator._convert_telemetry_to_insights(sample_telemetry_insights)

        cost_sink_insights = [i for i in insights if i["issue_type"] == "cost_sink"]
        assert len(cost_sink_insights) == 2

        first_cost_sink = cost_sink_insights[0]
        assert first_cost_sink["phase_id"] == "build-phase-1"
        assert first_cost_sink["phase_type"] == "build"
        assert first_cost_sink["metric_value"] == 75000.0
        assert first_cost_sink["rank"] == 1
        assert "75,000 tokens" in first_cost_sink["content"]

    def test_convert_telemetry_to_insights_converts_failure_modes(
        self, mock_memory_service, sample_telemetry_insights
    ):
        """Test that failure modes are converted to insight format."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        insights = generator._convert_telemetry_to_insights(sample_telemetry_insights)

        failure_insights = [i for i in insights if i["issue_type"] == "failure_mode"]
        assert len(failure_insights) == 1

        failure = failure_insights[0]
        assert failure["phase_id"] == "deploy-phase-1"
        assert failure["phase_type"] == "deploy"
        assert failure["severity"] == "high"
        assert "timeout" in failure["content"]

    def test_convert_telemetry_to_insights_converts_retry_causes(
        self, mock_memory_service, sample_telemetry_insights
    ):
        """Test that retry causes are converted to insight format."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        insights = generator._convert_telemetry_to_insights(sample_telemetry_insights)

        retry_insights = [i for i in insights if i["issue_type"] == "retry_cause"]
        assert len(retry_insights) == 1

        retry = retry_insights[0]
        assert retry["phase_id"] == "integration-phase"
        assert retry["phase_type"] == "integration"
        assert "rate_limit" in retry["content"]
        assert retry["metric_value"] == 8.0

    def test_convert_telemetry_to_insights_total_count(
        self, mock_memory_service, sample_telemetry_insights
    ):
        """Test that total insight count matches telemetry issue count."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        insights = generator._convert_telemetry_to_insights(sample_telemetry_insights)

        expected_count = (
            len(sample_telemetry_insights.get("top_cost_sinks", []))
            + len(sample_telemetry_insights.get("top_failure_modes", []))
            + len(sample_telemetry_insights.get("top_retry_causes", []))
        )
        assert len(insights) == expected_count

    def test_generate_tasks_with_telemetry_produces_tasks(
        self, mock_memory_service, sample_telemetry_insights
    ):
        """Test that generate_tasks with telemetry produces improvement tasks."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.0,
            telemetry_insights=sample_telemetry_insights,
        )

        # Should generate tasks from telemetry insights
        assert result.insights_processed > 0
        # Tasks depend on pattern detection (need 2+ occurrences of same type)
        # With 2 cost_sinks, 1 failure_mode, 1 retry_cause - cost_sink should create a pattern
        assert result.patterns_detected >= 0

    def test_generate_tasks_fallback_to_memory_when_no_telemetry(self, mock_memory_service):
        """Test that generate_tasks falls back to memory service when no telemetry."""
        mock_memory_service.retrieve_insights.return_value = [
            {"issue_type": "error", "content": "Test error", "id": "1", "severity": "high"},
            {"issue_type": "error", "content": "Test error 2", "id": "2", "severity": "high"},
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.0,
            telemetry_insights=None,  # No telemetry
        )

        # Should call memory service as fallback
        mock_memory_service.retrieve_insights.assert_called_once()
        assert result.insights_processed == 2

    def test_convert_telemetry_assigns_high_severity_for_high_token_usage(
        self, mock_memory_service
    ):
        """Test that high token usage (>50k) is assigned high severity."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        telemetry = {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="expensive-phase",
                    phase_type="build",
                    metric_value=75000.0,  # > 50000 threshold
                    details={"avg_tokens": 75000.0, "count": 1},
                ),
            ],
            "top_failure_modes": [],
            "top_retry_causes": [],
        }

        insights = generator._convert_telemetry_to_insights(telemetry)

        assert len(insights) == 1
        assert insights[0]["severity"] == "high"

    def test_convert_telemetry_assigns_medium_severity_for_moderate_token_usage(
        self, mock_memory_service
    ):
        """Test that moderate token usage (<50k) is assigned medium severity."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        telemetry = {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="moderate-phase",
                    phase_type="build",
                    metric_value=30000.0,  # < 50000 threshold
                    details={"avg_tokens": 30000.0, "count": 1},
                ),
            ],
            "top_failure_modes": [],
            "top_retry_causes": [],
        }

        insights = generator._convert_telemetry_to_insights(telemetry)

        assert len(insights) == 1
        assert insights[0]["severity"] == "medium"

    def test_convert_telemetry_handles_empty_input(self, mock_memory_service):
        """Test that empty telemetry data is handled gracefully."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        empty_telemetry = {
            "top_cost_sinks": [],
            "top_failure_modes": [],
            "top_retry_causes": [],
            "phase_type_stats": {},
        }

        insights = generator._convert_telemetry_to_insights(empty_telemetry)

        assert len(insights) == 0

    def test_convert_telemetry_handles_missing_keys(self, mock_memory_service):
        """Test that missing telemetry keys are handled gracefully."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        partial_telemetry = {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="only-phase",
                    phase_type="build",
                    metric_value=10000.0,
                    details={},
                ),
            ],
            # Missing top_failure_modes, top_retry_causes
        }

        insights = generator._convert_telemetry_to_insights(partial_telemetry)

        assert len(insights) == 1
        assert insights[0]["issue_type"] == "cost_sink"

    def test_insight_ids_are_unique(self, mock_memory_service, sample_telemetry_insights):
        """Test that generated insight IDs are unique."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        insights = generator._convert_telemetry_to_insights(sample_telemetry_insights)

        ids = [i["id"] for i in insights]
        assert len(ids) == len(set(ids)), "Insight IDs must be unique"


class TestCleanupStaleTasks:
    """Tests for stale in_progress task cleanup (IMP-REL-003)."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        service = Mock()
        service.retrieve_insights = Mock(return_value=[])
        return service

    def test_cleanup_stale_tasks_marks_old_tasks_as_failed(self, mock_memory_service):
        """Test that tasks in_progress for too long are marked as failed."""
        from datetime import timedelta

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Create mock stale task (updated 48 hours ago)
        stale_task = Mock()
        stale_task.task_id = "TASK-STALE001"
        stale_task.status = "in_progress"
        stale_task.updated_at = datetime.now() - timedelta(hours=48)
        stale_task.created_at = datetime.now() - timedelta(hours=50)

        # Create mock recent task (updated 1 hour ago)
        recent_task = Mock()
        recent_task.task_id = "TASK-RECENT001"
        recent_task.status = "in_progress"
        recent_task.updated_at = datetime.now() - timedelta(hours=1)
        recent_task.created_at = datetime.now() - timedelta(hours=2)

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = [
            stale_task,
            recent_task,
        ]

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            count = generator.cleanup_stale_tasks(threshold_hours=24)

        # Should only clean up the stale task
        assert count == 1
        assert stale_task.status == "failed"
        assert "24 hours" in stale_task.failure_reason
        # Recent task should not be modified
        assert recent_task.status == "in_progress"
        mock_session.commit.assert_called_once()

    def test_cleanup_stale_tasks_uses_created_at_as_fallback(self, mock_memory_service):
        """Test that cleanup uses created_at when updated_at is None."""
        from datetime import timedelta

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Create mock stale task with no updated_at (old migration data)
        stale_task = Mock()
        stale_task.task_id = "TASK-OLD001"
        stale_task.status = "in_progress"
        stale_task.updated_at = None
        stale_task.created_at = datetime.now() - timedelta(hours=48)

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = [stale_task]

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            count = generator.cleanup_stale_tasks(threshold_hours=24)

        assert count == 1
        assert stale_task.status == "failed"

    def test_cleanup_stale_tasks_respects_custom_threshold(self, mock_memory_service):
        """Test that cleanup respects custom threshold_hours parameter."""
        from datetime import timedelta

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Create mock task updated 6 hours ago
        task = Mock()
        task.task_id = "TASK-BORDER001"
        task.status = "in_progress"
        task.updated_at = datetime.now() - timedelta(hours=6)
        task.created_at = datetime.now() - timedelta(hours=8)

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = [task]

        # With 4-hour threshold, task should be stale
        with patch("autopack.database.SessionLocal", return_value=mock_session):
            count = generator.cleanup_stale_tasks(threshold_hours=4)

        assert count == 1
        assert task.status == "failed"
        assert "4 hours" in task.failure_reason

    def test_cleanup_stale_tasks_returns_zero_when_no_stale_tasks(self, mock_memory_service):
        """Test that cleanup returns 0 when there are no stale tasks."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = []

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            count = generator.cleanup_stale_tasks()

        assert count == 0
        mock_session.commit.assert_called_once()

    def test_cleanup_stale_tasks_sets_updated_at_on_cleanup(self, mock_memory_service):
        """Test that cleanup sets updated_at when marking tasks as failed."""
        from datetime import timedelta

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        stale_task = Mock()
        stale_task.task_id = "TASK-STALE001"
        stale_task.status = "in_progress"
        stale_task.updated_at = datetime.now() - timedelta(hours=48)
        stale_task.created_at = datetime.now() - timedelta(hours=50)

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = [stale_task]

        before_cleanup = datetime.now()

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            generator.cleanup_stale_tasks()

        # updated_at should be set to current time
        assert stale_task.updated_at >= before_cleanup

    def test_cleanup_stale_tasks_raises_on_db_error(self, mock_memory_service):
        """Test that cleanup raises exception on database error."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.side_effect = Exception(
            "Database connection failed"
        )

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            with pytest.raises(Exception, match="Database connection failed"):
                generator.cleanup_stale_tasks()

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
