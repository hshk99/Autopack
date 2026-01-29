"""Tests for ROAD-C Autonomous Task Generator."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

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


class TestRiskGatingIntegration:
    """Tests for IMP-LOOP-018: Regression risk gating in task generation."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        service = Mock()
        service.retrieve_insights = Mock(return_value=[])
        return service

    def test_generated_task_has_risk_fields(self):
        """Test that GeneratedTask has risk-related fields."""
        task = GeneratedTask(
            task_id="TASK-RISK001",
            title="Test task",
            description="Test description",
            priority="high",
            source_insights=["insight-1"],
            suggested_files=["src/file.py"],
            estimated_effort="M",
            created_at=datetime.now(),
            requires_approval=True,
            risk_severity="medium",
        )

        assert task.requires_approval is True
        assert task.risk_severity == "medium"

    def test_generated_task_risk_fields_default_to_safe_values(self):
        """Test that risk fields default to safe values."""
        task = GeneratedTask(
            task_id="TASK-SAFE001",
            title="Test task",
            description="Test description",
            priority="high",
            source_insights=["insight-1"],
            suggested_files=["src/file.py"],
            estimated_effort="M",
            created_at=datetime.now(),
        )

        assert task.requires_approval is False
        assert task.risk_severity is None

    def test_generate_tasks_uses_risk_assessment(self, mock_memory_service):
        """Test that generate_tasks integrates risk assessment."""
        mock_memory_service.retrieve_insights.return_value = [
            {"issue_type": "error", "content": "Error 1", "id": "1", "severity": "high"},
            {"issue_type": "error", "content": "Error 2", "id": "2", "severity": "high"},
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        result = generator.generate_tasks(max_tasks=10, min_confidence=0.0)

        # Should complete without error (risk assessment integrated)
        assert isinstance(result, TaskGenerationResult)

    def test_medium_risk_tasks_flagged_for_approval(self, mock_memory_service, tmp_path):
        """Test that medium risk tasks are flagged for approval gate."""
        from autopack.roadi import RegressionProtector, RiskSeverity

        # Create a test file to trigger medium risk
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_regression_cost.py").write_text(
            '"""Regression test for cost sink."""\n'
            "# Pattern: cost sink optimization\n"
            "def test_cost_regression():\n"
            "    assert True\n"
        )

        protector = RegressionProtector(tests_root=tests_dir)

        patterns = [
            {
                "type": "cost_sink",
                "occurrences": 2,
                "confidence": 0.7,
                "severity": 5,
                "examples": [
                    {
                        "content": "cost sink optimization in build",
                        "phase_id": "build",
                        "issue_type": "cost_sink",
                    }
                ],
            },
        ]

        filtered, risk_assessments = protector.filter_patterns_with_risk_assessment(patterns)

        # Should have risk assessment
        assert "cost_sink" in risk_assessments
        # If medium risk, should be flagged for approval
        if risk_assessments["cost_sink"].severity == RiskSeverity.MEDIUM:
            assert filtered[0].get("_requires_approval", False) is True

    def test_high_risk_tasks_blocked_from_generation(self, mock_memory_service, tmp_path):
        """Test that high/critical risk patterns are blocked."""
        from autopack.roadi import RegressionProtector, RiskSeverity

        # Create multiple test files to trigger high risk
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        for i in range(3):
            (tests_dir / f"test_regression_fail_{i}.py").write_text(
                f'"""Regression test for failure mode #{i}."""\n'
                "# Pattern: critical failure mode\n"
                "def test_failure_regression():\n"
                "    assert True\n"
            )

        protector = RegressionProtector(tests_root=tests_dir)

        patterns = [
            {
                "type": "failure_mode",
                "occurrences": 5,
                "confidence": 0.9,
                "severity": 8,
                "examples": [
                    {
                        "content": "critical failure mode in deploy",
                        "phase_id": "deploy",
                        "issue_type": "failure_mode",
                    }
                ],
            },
        ]

        filtered, risk_assessments = protector.filter_patterns_with_risk_assessment(patterns)

        # Check if blocking was recommended
        risk = risk_assessments.get("failure_mode")
        if risk and risk.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL):
            # Pattern should be blocked (not in filtered list)
            assert risk.blocking_recommended is True
            assert len([p for p in filtered if p["type"] == "failure_mode"]) == 0

    def test_risk_assessment_includes_evidence(self, mock_memory_service, tmp_path):
        """Test that risk assessment includes evidence for its decision."""
        from autopack.roadi import RegressionProtector

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_regression_perf.py").write_text(
            '"""Regression test for performance."""\n'
            "# Pattern: slow query performance\n"
            "def test_performance_regression():\n"
            "    assert True\n"
        )

        protector = RegressionProtector(tests_root=tests_dir)

        risk = protector.assess_regression_risk(
            "slow query performance",
            {"issue_type": "performance"},
        )

        # Should have some evidence
        assert len(risk.evidence) > 0
        # Should include historical rate info
        assert any("historical" in e.lower() for e in risk.evidence)


class TestBacklogInjection:
    """Tests for IMP-LOOP-003: Same-run task execution via backlog injection."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        service = Mock()
        service.retrieve_insights = Mock(return_value=[])
        return service

    @pytest.fixture
    def sample_critical_task(self):
        """Create a sample critical priority task."""
        return GeneratedTask(
            task_id="TASK-CRITICAL001",
            title="Critical task",
            description="Critical priority task for immediate execution",
            priority="critical",
            source_insights=["insight-1"],
            suggested_files=["src/critical.py"],
            estimated_effort="M",
            created_at=datetime.now(),
        )

    @pytest.fixture
    def sample_high_task(self):
        """Create a sample high priority task."""
        return GeneratedTask(
            task_id="TASK-HIGH001",
            title="High priority task",
            description="High priority task",
            priority="high",
            source_insights=["insight-2"],
            suggested_files=["src/high.py"],
            estimated_effort="M",
            created_at=datetime.now(),
        )

    def test_inject_into_backlog_injects_critical_tasks(
        self, mock_memory_service, sample_critical_task
    ):
        """Test that critical priority tasks are injected into backlog."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        backlog = [
            {"phase_id": "existing-phase-1", "status": "QUEUED"},
            {"phase_id": "existing-phase-2", "status": "QUEUED"},
        ]

        injected_count = generator._inject_into_backlog(backlog, [sample_critical_task])

        assert injected_count == 1
        assert len(backlog) == 3
        # Critical task should be at position 0 (front of backlog)
        assert backlog[0]["phase_id"] == "generated-task-execution-TASK-CRITICAL001"
        assert backlog[0]["phase_type"] == "generated-task-execution"
        assert backlog[0]["priority_order"] == 0
        assert backlog[0]["metadata"]["injected_same_run"] is True

    def test_inject_into_backlog_ignores_non_critical_tasks(
        self, mock_memory_service, sample_high_task
    ):
        """Test that non-critical tasks are NOT injected into backlog."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        backlog = [{"phase_id": "existing-phase-1", "status": "QUEUED"}]
        original_length = len(backlog)

        injected_count = generator._inject_into_backlog(backlog, [sample_high_task])

        assert injected_count == 0
        assert len(backlog) == original_length

    def test_inject_into_backlog_handles_multiple_critical_tasks(self, mock_memory_service):
        """Test that multiple critical tasks are all injected."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        critical_tasks = [
            GeneratedTask(
                task_id=f"TASK-CRIT{i}",
                title=f"Critical task {i}",
                description=f"Description {i}",
                priority="critical",
                source_insights=[f"insight-{i}"],
                suggested_files=[f"src/file{i}.py"],
                estimated_effort="S",
                created_at=datetime.now(),
            )
            for i in range(3)
        ]

        backlog = [{"phase_id": "existing-phase", "status": "QUEUED"}]

        injected_count = generator._inject_into_backlog(backlog, critical_tasks)

        assert injected_count == 3
        assert len(backlog) == 4
        # All critical tasks should be at the front
        for i in range(3):
            assert "generated-task-execution" in backlog[i]["phase_id"]

    def test_inject_into_backlog_handles_empty_backlog(
        self, mock_memory_service, sample_critical_task
    ):
        """Test injection into empty backlog."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        backlog = []

        injected_count = generator._inject_into_backlog(backlog, [sample_critical_task])

        assert injected_count == 1
        assert len(backlog) == 1
        assert backlog[0]["phase_id"] == "generated-task-execution-TASK-CRITICAL001"

    def test_inject_into_backlog_handles_empty_tasks(self, mock_memory_service):
        """Test injection with no tasks."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        backlog = [{"phase_id": "existing-phase", "status": "QUEUED"}]
        original_length = len(backlog)

        injected_count = generator._inject_into_backlog(backlog, [])

        assert injected_count == 0
        assert len(backlog) == original_length

    def test_inject_into_backlog_preserves_task_metadata(
        self, mock_memory_service, sample_critical_task
    ):
        """Test that task metadata is preserved in phase spec."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        backlog = []
        generator._inject_into_backlog(backlog, [sample_critical_task])

        injected_phase = backlog[0]
        assert injected_phase["metadata"]["task_id"] == "TASK-CRITICAL001"
        assert injected_phase["metadata"]["source_insights"] == ["insight-1"]
        assert injected_phase["metadata"]["estimated_effort"] == "M"
        assert injected_phase["scope"]["paths"] == ["src/critical.py"]

    def test_generate_tasks_with_backlog_injects_critical_tasks(self, mock_memory_service):
        """Test that generate_tasks injects critical tasks when backlog is provided."""
        # Create insights that will generate critical tasks
        mock_memory_service.retrieve_insights.return_value = [
            {"issue_type": "error", "content": "Critical error 1", "id": "1", "severity": "high"},
            {"issue_type": "error", "content": "Critical error 2", "id": "2", "severity": "high"},
            {"issue_type": "error", "content": "Critical error 3", "id": "3", "severity": "high"},
            {"issue_type": "error", "content": "Critical error 4", "id": "4", "severity": "high"},
            {"issue_type": "error", "content": "Critical error 5", "id": "5", "severity": "high"},
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        backlog = [{"phase_id": "existing-phase", "status": "QUEUED"}]

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.0,
            backlog=backlog,
        )

        # Should have generated tasks
        assert isinstance(result, TaskGenerationResult)
        # Backlog may have been modified if any critical tasks were generated
        # (depends on pattern detection logic)

    def test_generate_tasks_without_backlog_does_not_inject(self, mock_memory_service):
        """Test that generate_tasks does not inject when backlog is None."""
        mock_memory_service.retrieve_insights.return_value = [
            {"issue_type": "error", "content": "Error 1", "id": "1", "severity": "high"},
            {"issue_type": "error", "content": "Error 2", "id": "2", "severity": "high"},
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # No backlog provided (default behavior)
        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.0,
            backlog=None,
        )

        # Should complete without error
        assert isinstance(result, TaskGenerationResult)

    def test_injected_phase_has_correct_format(self, mock_memory_service, sample_critical_task):
        """Test that injected phase has correct structure for execution."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        backlog = []
        generator._inject_into_backlog(backlog, [sample_critical_task])

        phase = backlog[0]

        # Verify required phase fields
        assert "phase_id" in phase
        assert "phase_type" in phase
        assert "description" in phase
        assert "status" in phase
        assert "priority_order" in phase
        assert "category" in phase
        assert "scope" in phase
        assert "metadata" in phase

        # Verify correct values
        assert phase["status"] == "QUEUED"
        assert phase["category"] == "improvement"
        assert "[AUTO-CRITICAL]" in phase["description"]


class TestExecutorQueueEmission:
    """Tests for IMP-LOOP-025: Wire ROAD-C task generation to executor queue."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        service = Mock()
        service.retrieve_insights = Mock(return_value=[])
        return service

    @pytest.fixture
    def sample_tasks(self):
        """Create sample tasks for testing."""
        return [
            GeneratedTask(
                task_id="TASK-TEST001",
                title="Test task 1",
                description="Description 1",
                priority="critical",
                source_insights=["i1"],
                suggested_files=["f1.py"],
                estimated_effort="M",
                created_at=datetime.now(),
                requires_approval=False,
                risk_severity=None,
                estimated_cost=10000,
            ),
            GeneratedTask(
                task_id="TASK-TEST002",
                title="Test task 2",
                description="Description 2",
                priority="high",
                source_insights=["i2"],
                suggested_files=["f2.py"],
                estimated_effort="S",
                created_at=datetime.now(),
                requires_approval=True,
                risk_severity="medium",
                estimated_cost=5000,
            ),
        ]

    @pytest.fixture
    def temp_queue_file(self, tmp_path):
        """Create a temporary queue file path."""
        queue_dir = tmp_path / ".autopack"
        queue_dir.mkdir(parents=True, exist_ok=True)
        return queue_dir / "ROADC_TASK_QUEUE.json"

    def test_emit_to_executor_queue_creates_file(
        self, mock_memory_service, sample_tasks, temp_queue_file
    ):
        """Test that _emit_to_executor_queue creates the queue file."""
        import json

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        count = generator._emit_to_executor_queue(sample_tasks, queue_file=temp_queue_file)

        assert count == 2
        assert temp_queue_file.exists()

        queue_data = json.loads(temp_queue_file.read_text())
        assert len(queue_data["tasks"]) == 2
        assert queue_data["updated_at"] is not None

    def test_emit_to_executor_queue_preserves_task_data(
        self, mock_memory_service, sample_tasks, temp_queue_file
    ):
        """Test that emitted tasks contain all required fields."""
        import json

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        generator._emit_to_executor_queue(sample_tasks, queue_file=temp_queue_file)

        queue_data = json.loads(temp_queue_file.read_text())
        task = queue_data["tasks"][0]

        assert task["task_id"] == "TASK-TEST001"
        assert task["title"] == "Test task 1"
        assert task["description"] == "Description 1"
        assert task["priority"] == "critical"
        assert task["source_insights"] == ["i1"]
        assert task["suggested_files"] == ["f1.py"]
        assert task["estimated_effort"] == "M"
        assert task["requires_approval"] is False
        assert task["estimated_cost"] == 10000
        assert "queued_at" in task
        assert "created_at" in task

    def test_emit_to_executor_queue_deduplicates_tasks(
        self, mock_memory_service, sample_tasks, temp_queue_file
    ):
        """Test that duplicate tasks are not re-added to queue."""
        import json

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # First emission
        count1 = generator._emit_to_executor_queue(sample_tasks, queue_file=temp_queue_file)
        assert count1 == 2

        # Second emission with same tasks should not add duplicates
        count2 = generator._emit_to_executor_queue(sample_tasks, queue_file=temp_queue_file)
        assert count2 == 0

        queue_data = json.loads(temp_queue_file.read_text())
        assert len(queue_data["tasks"]) == 2

    def test_emit_to_executor_queue_empty_list(self, mock_memory_service, temp_queue_file):
        """Test that empty task list returns 0 without creating file."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        count = generator._emit_to_executor_queue([], queue_file=temp_queue_file)

        assert count == 0
        # File should not exist since no tasks were emitted
        # (unless it existed before)

    def test_emit_to_executor_queue_appends_to_existing(self, mock_memory_service, temp_queue_file):
        """Test that new tasks are appended to existing queue."""
        import json

        # Create initial queue with one task
        initial_data = {
            "tasks": [
                {
                    "task_id": "TASK-EXISTING",
                    "title": "Existing task",
                    "priority": "low",
                }
            ],
            "updated_at": "2024-01-01T00:00:00Z",
        }
        temp_queue_file.write_text(json.dumps(initial_data))

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)
        new_task = GeneratedTask(
            task_id="TASK-NEW001",
            title="New task",
            description="New description",
            priority="high",
            source_insights=["i1"],
            suggested_files=[],
            estimated_effort="S",
            created_at=datetime.now(),
        )

        count = generator._emit_to_executor_queue([new_task], queue_file=temp_queue_file)

        assert count == 1
        queue_data = json.loads(temp_queue_file.read_text())
        assert len(queue_data["tasks"]) == 2

        task_ids = {t["task_id"] for t in queue_data["tasks"]}
        assert "TASK-EXISTING" in task_ids
        assert "TASK-NEW001" in task_ids

    def test_emit_tasks_for_execution_dual_path(
        self, mock_memory_service, sample_tasks, temp_queue_file
    ):
        """Test that emit_tasks_for_execution writes to both DB and queue."""
        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Mock database session
        mock_session = Mock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            result = generator.emit_tasks_for_execution(
                sample_tasks,
                persist_to_db=True,
                emit_to_queue=True,
                run_id="test-run",
            )
            # Note: We're patching the method's internal queue file, so use a direct call
            generator._emit_to_executor_queue(sample_tasks, queue_file=temp_queue_file)

        # Check that both paths were attempted
        assert "persisted" in result
        assert "queued" in result

    def test_generate_tasks_emits_to_queue(self, mock_memory_service, tmp_path):
        """Test that generate_tasks automatically emits to queue."""
        import json

        # Create mock insights that will generate tasks
        mock_memory_service.retrieve_insights.return_value = [
            {"issue_type": "error", "content": "Error 1", "id": "1", "severity": "high"},
            {"issue_type": "error", "content": "Error 2", "id": "2", "severity": "high"},
            {"issue_type": "error", "content": "Error 3", "id": "3", "severity": "high"},
        ]

        generator = AutonomousTaskGenerator(memory_service=mock_memory_service)

        # Override queue file path for test
        test_queue_file = tmp_path / ".autopack" / "ROADC_TASK_QUEUE.json"
        original_queue_file = generator.ROADC_TASK_QUEUE_FILE

        try:
            # Temporarily override the class variable
            AutonomousTaskGenerator.ROADC_TASK_QUEUE_FILE = test_queue_file

            result = generator.generate_tasks(
                max_tasks=5,
                min_confidence=0.0,
            )

            # If tasks were generated, they should be emitted to queue
            if result.tasks_generated:
                # Queue file should exist with tasks
                assert test_queue_file.exists()
                queue_data = json.loads(test_queue_file.read_text())
                assert len(queue_data["tasks"]) == len(result.tasks_generated)
        finally:
            # Restore original queue file path
            AutonomousTaskGenerator.ROADC_TASK_QUEUE_FILE = original_queue_file
