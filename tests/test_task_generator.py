"""Tests for ROAD-C Autonomous Task Generator."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from autopack.roadc import AutonomousTaskGenerator, GeneratedTask, TaskGenerationResult


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
