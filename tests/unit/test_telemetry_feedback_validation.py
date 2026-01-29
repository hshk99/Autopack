"""Unit tests for telemetry-to-memory feedback validation.

IMP-LOOP-002: Tests validation checks for telemetry data before memory storage.
"""

from unittest.mock import MagicMock, patch

import pytest

from autopack.memory.memory_service import (TelemetryFeedbackValidationError,
                                            TelemetryFeedbackValidator)


class TestTelemetryFeedbackValidator:
    """Tests for TelemetryFeedbackValidator class."""

    def test_validate_valid_insight(self):
        """Test validation passes for a valid insight."""
        insight = {
            "insight_type": "cost_sink",
            "description": "High token usage in build phase",
            "phase_id": "phase-001",
            "run_id": "run-001",
            "suggested_action": "Consider reducing context size",
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is True
        assert errors == []

    def test_validate_missing_required_field_insight_type(self):
        """Test validation fails when insight_type is missing."""
        insight = {
            "description": "Some description",
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is False
        assert any("insight_type" in e for e in errors)

    def test_validate_missing_required_field_description(self):
        """Test validation fails when description is missing."""
        insight = {
            "insight_type": "cost_sink",
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is False
        assert any("description" in e for e in errors)

    def test_validate_none_required_field(self):
        """Test validation fails when required field is None."""
        insight = {
            "insight_type": None,
            "description": "Some description",
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is False
        assert any("None" in e for e in errors)

    def test_validate_invalid_insight_type_type(self):
        """Test validation fails when insight_type is not a string."""
        insight = {
            "insight_type": 123,
            "description": "Some description",
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is False
        assert any("string" in e for e in errors)

    def test_validate_unknown_insight_type_warns(self):
        """Test validation warns but passes for unknown insight type."""
        insight = {
            "insight_type": "custom_type",
            "description": "Some description",
        }
        with patch("autopack.memory.memory_service.logger") as mock_logger:
            is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
            # Should pass validation (with warning)
            assert is_valid is True
            assert errors == []
            # Should log warning about unknown type
            mock_logger.warning.assert_called()

    def test_validate_description_too_long(self):
        """Test validation fails when description exceeds max length."""
        insight = {
            "insight_type": "cost_sink",
            "description": "x" * 15000,  # Exceeds MAX_DESCRIPTION_LENGTH
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is False
        assert any("max length" in e for e in errors)

    def test_validate_suggested_action_too_long(self):
        """Test validation fails when suggested_action exceeds max length."""
        insight = {
            "insight_type": "cost_sink",
            "description": "Valid description",
            "suggested_action": "x" * 6000,  # Exceeds MAX_SUGGESTED_ACTION_LENGTH
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is False
        assert any("suggested_action" in e and "max length" in e for e in errors)

    def test_validate_invalid_optional_field_type(self):
        """Test validation fails when optional string field is not a string."""
        insight = {
            "insight_type": "cost_sink",
            "description": "Valid description",
            "phase_id": 123,  # Should be string
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
        assert is_valid is False
        assert any("phase_id" in e for e in errors)

    def test_validate_non_dict_insight(self):
        """Test validation fails for non-dict insight."""
        is_valid, errors = TelemetryFeedbackValidator.validate_insight("not a dict")
        assert is_valid is False
        assert any("dict" in e for e in errors)

    def test_validate_strict_mode_raises_exception(self):
        """Test strict mode raises exception on validation failure."""
        insight = {
            "description": "Missing insight_type",
        }
        with pytest.raises(TelemetryFeedbackValidationError) as exc_info:
            TelemetryFeedbackValidator.validate_insight(insight, strict=True)
        assert "insight_type" in str(exc_info.value)

    def test_validate_strict_mode_passes_valid(self):
        """Test strict mode passes for valid insight."""
        insight = {
            "insight_type": "failure_mode",
            "description": "Valid description",
        }
        is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight, strict=True)
        assert is_valid is True
        assert errors == []


class TestTelemetryFeedbackValidatorSanitize:
    """Tests for TelemetryFeedbackValidator.sanitize_insight method."""

    def test_sanitize_valid_insight_unchanged(self):
        """Test sanitize returns valid insight unchanged."""
        insight = {
            "insight_type": "cost_sink",
            "description": "Valid description",
        }
        result = TelemetryFeedbackValidator.sanitize_insight(insight)
        assert result["insight_type"] == "cost_sink"
        assert result["description"] == "Valid description"

    def test_sanitize_missing_insight_type(self):
        """Test sanitize adds default insight_type."""
        insight = {
            "description": "Some description",
        }
        result = TelemetryFeedbackValidator.sanitize_insight(insight)
        assert result["insight_type"] == "unknown"

    def test_sanitize_none_insight_type(self):
        """Test sanitize replaces None insight_type."""
        insight = {
            "insight_type": None,
            "description": "Some description",
        }
        result = TelemetryFeedbackValidator.sanitize_insight(insight)
        assert result["insight_type"] == "unknown"

    def test_sanitize_missing_description(self):
        """Test sanitize adds empty description."""
        insight = {
            "insight_type": "cost_sink",
        }
        result = TelemetryFeedbackValidator.sanitize_insight(insight)
        assert result["description"] == ""

    def test_sanitize_truncates_long_description(self):
        """Test sanitize truncates long description."""
        long_desc = "x" * 15000
        insight = {
            "insight_type": "cost_sink",
            "description": long_desc,
        }
        result = TelemetryFeedbackValidator.sanitize_insight(insight)
        assert len(result["description"]) <= TelemetryFeedbackValidator.MAX_DESCRIPTION_LENGTH
        assert result["description"].endswith("...")

    def test_sanitize_truncates_long_suggested_action(self):
        """Test sanitize truncates long suggested_action."""
        long_action = "x" * 6000
        insight = {
            "insight_type": "cost_sink",
            "description": "Valid",
            "suggested_action": long_action,
        }
        result = TelemetryFeedbackValidator.sanitize_insight(insight)
        assert (
            len(result["suggested_action"])
            <= TelemetryFeedbackValidator.MAX_SUGGESTED_ACTION_LENGTH
        )
        assert result["suggested_action"].endswith("...")

    def test_sanitize_non_dict_converts_to_dict(self):
        """Test sanitize converts non-dict to dict."""
        result = TelemetryFeedbackValidator.sanitize_insight("string insight")
        assert isinstance(result, dict)
        assert result["insight_type"] == "unknown"
        assert "string insight" in result["description"]

    def test_sanitize_preserves_other_fields(self):
        """Test sanitize preserves other fields."""
        insight = {
            "insight_type": "cost_sink",
            "description": "Valid",
            "phase_id": "phase-001",
            "run_id": "run-001",
            "custom_field": "preserved",
        }
        result = TelemetryFeedbackValidator.sanitize_insight(insight)
        assert result["phase_id"] == "phase-001"
        assert result["run_id"] == "run-001"
        assert result["custom_field"] == "preserved"


class TestAutonomousLoopTelemetryValidation:
    """Tests for telemetry validation in AutonomousLoop."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor."""
        executor = MagicMock()
        executor.db_session = MagicMock()
        executor.memory_service = MagicMock()
        return executor

    @pytest.fixture
    def autonomous_loop(self, mock_executor):
        """Create an AutonomousLoop instance."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        return AutonomousLoop(mock_executor)

    def test_validate_telemetry_feedback_valid_data(self, autonomous_loop):
        """Test validation passes for valid telemetry feedback."""
        ranked_issues = {
            "top_cost_sinks": [{"description": "High cost", "phase_id": "p1"}],
            "top_failure_modes": [{"description": "Test failure", "phase_id": "p2"}],
            "top_retry_causes": [],
        }
        is_valid, validated, error_count = autonomous_loop._validate_telemetry_feedback(
            ranked_issues
        )
        assert is_valid is True
        assert error_count == 0
        assert len(validated["top_cost_sinks"]) == 1
        assert len(validated["top_failure_modes"]) == 1

    def test_validate_telemetry_feedback_non_dict(self, autonomous_loop):
        """Test validation handles non-dict input."""
        is_valid, validated, error_count = autonomous_loop._validate_telemetry_feedback(
            "not a dict"
        )
        assert is_valid is False
        assert error_count == 1
        assert validated == {}

    def test_validate_telemetry_feedback_invalid_category_type(self, autonomous_loop):
        """Test validation handles invalid category type."""
        ranked_issues = {
            "top_cost_sinks": "not a list",  # Should be list
            "top_failure_modes": [],
            "top_retry_causes": [],
        }
        is_valid, validated, error_count = autonomous_loop._validate_telemetry_feedback(
            ranked_issues
        )
        assert is_valid is False
        assert error_count >= 1
        assert validated["top_cost_sinks"] == []

    def test_validate_telemetry_feedback_sanitizes_invalid_issues(self, autonomous_loop):
        """Test validation sanitizes invalid issues instead of dropping them."""
        ranked_issues = {
            "top_cost_sinks": [{"description": None}],  # Invalid - description is None
            "top_failure_modes": [],
            "top_retry_causes": [],
        }
        is_valid, validated, error_count = autonomous_loop._validate_telemetry_feedback(
            ranked_issues
        )
        # Should still have the issue (sanitized)
        assert len(validated["top_cost_sinks"]) == 1
        assert error_count >= 1

    def test_validate_telemetry_feedback_missing_categories(self, autonomous_loop):
        """Test validation handles missing categories."""
        ranked_issues = {}  # Empty dict
        is_valid, validated, error_count = autonomous_loop._validate_telemetry_feedback(
            ranked_issues
        )
        assert is_valid is True  # Empty is valid
        assert validated["top_cost_sinks"] == []
        assert validated["top_failure_modes"] == []
        assert validated["top_retry_causes"] == []


class TestMemoryServiceWriteTelemetryInsight:
    """Tests for MemoryService.write_telemetry_insight with validation."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance with mocked store."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda x: None):
            service = MemoryService.__new__(MemoryService)
            service.enabled = True
            service.store = MagicMock()
            service.max_embed_chars = 8000
            service.top_k = 5
            return service

    def test_write_telemetry_insight_validates_by_default(self, memory_service):
        """Test write_telemetry_insight validates insight by default."""
        insight = {
            "insight_type": "cost_sink",
            "description": "Valid description",
        }
        with patch("autopack.memory.memory_service.sync_embed_text") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            memory_service.store.upsert = MagicMock(return_value=1)
            result = memory_service.write_telemetry_insight(insight, project_id="test-project")
            assert result != ""

    def test_write_telemetry_insight_sanitizes_invalid(self, memory_service):
        """Test write_telemetry_insight sanitizes invalid insight."""
        insight = {
            "description": "Missing insight_type",  # Missing required field
        }
        with patch("autopack.memory.memory_service.sync_embed_text") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            memory_service.store.upsert = MagicMock(return_value=1)
            with patch("autopack.memory.memory_service.logger") as mock_logger:
                result = memory_service.write_telemetry_insight(insight, project_id="test-project")
                # Should log warning about validation failure
                assert mock_logger.warning.called
                # Should still write (after sanitization)
                assert result != ""

    def test_write_telemetry_insight_strict_mode_raises(self, memory_service):
        """Test write_telemetry_insight raises in strict mode for invalid insight."""
        insight = {
            "description": "Missing insight_type",
        }
        with pytest.raises(TelemetryFeedbackValidationError):
            memory_service.write_telemetry_insight(insight, project_id="test-project", strict=True)

    def test_write_telemetry_insight_skip_validation(self, memory_service):
        """Test write_telemetry_insight can skip validation."""
        insight = {
            "insight_type": 123,  # Invalid type
            "description": "Some description",
        }
        with patch("autopack.memory.memory_service.sync_embed_text") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            memory_service.store.upsert = MagicMock(return_value=1)
            # Should not raise even with invalid data when validate=False
            _ = memory_service.write_telemetry_insight(
                insight, project_id="test-project", validate=False
            )
            # Will fail during actual write but not during validation
            # Reaching this point means no validation error was raised

    def test_write_telemetry_insight_disabled_memory(self, memory_service):
        """Test write_telemetry_insight returns empty when memory disabled."""
        memory_service.enabled = False
        insight = {
            "insight_type": "cost_sink",
            "description": "Valid description",
        }
        result = memory_service.write_telemetry_insight(insight, project_id="test-project")
        assert result == ""
