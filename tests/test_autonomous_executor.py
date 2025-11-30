"""Tests for autonomous executor error handling."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from src.autopack.autonomous_executor import AutonomousExecutor
from src.autopack.error_recovery import ErrorCategory

# MAX_RETRIES is now configurable via LlmService.get_max_attempts()
MAX_RETRIES = 5  # Default value
from src.autopack.exceptions import (
    NetworkError,
    APIError,
    PatchValidationError,
    BuilderError,
    ValidationError,
)
from src.autopack.models import Phase, PhaseState


@pytest.fixture
def mock_builder_client():
    """Create a mock builder client."""
    client = Mock()
    client.generate_code = AsyncMock()
    return client


@pytest.fixture
def executor(mock_builder_client, monkeypatch, tmp_path):
    """Create an executor instance with mock client.

    The AutonomousExecutor now uses LlmService internally, so we need to
    mock the infrastructure initialization and provide required params.
    """
    # Mock environment variables
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    # Mock the infrastructure initialization to avoid real API calls
    with patch.object(AutonomousExecutor, '_init_infrastructure'):
        with patch.object(AutonomousExecutor, '_run_startup_checks'):
            executor = AutonomousExecutor(
                run_id="test-run",
                api_url="http://localhost:8000",
                workspace=str(tmp_path),
            )
            # Manually set up mocked attributes that would be set by _init_infrastructure
            executor.llm_service = Mock()
            executor.llm_service.get_max_attempts.return_value = MAX_RETRIES
            executor.quality_gate = Mock()
            executor._error_history = []
            return executor


@pytest.fixture
def sample_phase():
    """Create a sample phase for testing."""
    return Phase(
        description="Test phase",
        category="test",
        complexity="medium",
        status=PhaseStatus.PENDING,
    )


class TestErrorCategorization:
    """Tests for error categorization logic."""

    def test_categorize_network_error_by_type(self, executor):
        """Test categorization of network errors by exception type."""
        error = ConnectionError("Connection refused")
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.NETWORK

    def test_categorize_network_error_by_message(self, executor):
        """Test categorization of network errors by message pattern."""
        error = Exception("Network timeout occurred")
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.NETWORK

    def test_categorize_api_error_by_type(self, executor):
        """Test categorization of API errors by exception type."""
        error = APIError("Rate limit exceeded", status_code=429)
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.API

    def test_categorize_api_error_by_message(self, executor):
        """Test categorization of API errors by message pattern."""
        error = Exception("API returned 503 Service Unavailable")
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.API

    def test_categorize_patch_error_by_type(self, executor):
        """Test categorization of patch errors by exception type."""
        error = PatchValidationError("Patch validation failed")
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.PATCH

    def test_categorize_patch_error_by_message(self, executor):
        """Test categorization of patch errors by message pattern."""
        error = Exception("Merge conflict detected")
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.PATCH

    def test_categorize_validation_error_by_type(self, executor):
        """Test categorization of validation errors by exception type."""
        error = ValueError("Invalid input format")
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.VALIDATION

    def test_categorize_unknown_error(self, executor):
        """Test categorization of unknown errors."""
        error = Exception("Something unexpected happened")
        category = executor._categorize_error(error, str(error).lower())
        assert category == ErrorCategory.UNKNOWN


class TestRetryLogic:
    """Tests for retry decision logic."""

    def test_network_error_is_retryable(self, executor):
        """Test that network errors are retryable."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.NETWORK,
            error_message="connection timeout",
            retry_count=0,
        )
        assert should_retry is True

    def test_api_rate_limit_is_retryable(self, executor):
        """Test that API rate limit errors are retryable."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.API,
            error_message="rate limit exceeded",
            retry_count=0,
        )
        assert should_retry is True

    def test_api_503_is_retryable(self, executor):
        """Test that API 503 errors are retryable."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.API,
            error_message="503 service unavailable",
            retry_count=0,
        )
        assert should_retry is True

    def test_api_401_is_not_retryable(self, executor):
        """Test that API 401 errors are not retryable."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.API,
            error_message="401 unauthorized",
            retry_count=0,
        )
        assert should_retry is False

    def test_validation_error_is_not_retryable(self, executor):
        """Test that validation errors are not retryable."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.VALIDATION,
            error_message="invalid input",
            retry_count=0,
        )
        assert should_retry is False

    def test_patch_error_retryable_on_first_attempt(self, executor):
        """Test that patch errors are retryable on first attempt."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.PATCH,
            error_message="patch failed",
            retry_count=0,
        )
        assert should_retry is True

    def test_patch_error_not_retryable_on_second_attempt(self, executor):
        """Test that patch errors are not retryable on second attempt."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.PATCH,
            error_message="patch failed",
            retry_count=1,
        )
        assert should_retry is False

    def test_max_retries_prevents_retry(self, executor):
        """Test that max retries prevents further retry attempts."""
        should_retry = executor._is_retryable_error(
            error_category=ErrorCategory.NETWORK,
            error_message="connection timeout",
            retry_count=MAX_RETRIES,
        )
        assert should_retry is False

    def test_unknown_error_retryable_once(self, executor):
        """Test that unknown errors are retryable once."""
        should_retry_first = executor._is_retryable_error(
            error_category=ErrorCategory.UNKNOWN,
            error_message="unknown error",
            retry_count=0,
        )
        should_retry_second = executor._is_retryable_error(
            error_category=ErrorCategory.UNKNOWN,
            error_message="unknown error",
            retry_count=1,
        )
        assert should_retry_first is True
        assert should_retry_second is False


class TestHandleBuilderError:
    """Tests for the _handle_builder_error method."""

    def test_handle_network_error(self, executor, sample_phase):
        """Test handling of network errors."""
        error = NetworkError("Connection timeout")
        should_retry, category, details = executor._handle_builder_error(
            error=error,
            phase=sample_phase,
            retry_count=0,
        )

        assert should_retry is True
        assert category == ErrorCategory.NETWORK
        assert details["error_type"] == "NetworkError"
        assert details["phase_description"] == sample_phase.description
        assert details["retry_count"] == 0
        assert "timestamp" in details

    def test_handle_api_error(self, executor, sample_phase):
        """Test handling of API errors."""
        error = APIError("Rate limit exceeded", status_code=429)
        should_retry, category, details = executor._handle_builder_error(
            error=error,
            phase=sample_phase,
            retry_count=1,
        )

        assert should_retry is True
        assert category == ErrorCategory.API
        assert details["retry_count"] == 1

    def test_handle_validation_error(self, executor, sample_phase):
        """Test handling of validation errors."""
        error = ValidationError("Invalid result format")
        should_retry, category, details = executor._handle_builder_error(
            error=error,
            phase=sample_phase,
            retry_count=0,
        )

        assert should_retry is False
        assert category == ErrorCategory.VALIDATION
        assert "stack_trace" in details

    def test_error_history_tracking(self, executor, sample_phase):
        """Test that errors are tracked in history."""
        error = NetworkError("Connection timeout")
        executor._handle_builder_error(
            error=error,
            phase=sample_phase,
            retry_count=0,
        )

        history = executor.get_error_history()
        assert len(history) == 1
        assert history[0]["error_type"] == "NetworkError"

    def test_stack_trace_included_for_final_retry(self, executor, sample_phase):
        """Test that stack trace is included for final retry attempt."""
        error = NetworkError("Connection timeout")
        _, _, details = executor._handle_builder_error(
            error=error,
            phase=sample_phase,
            retry_count=MAX_RETRIES - 1,
        )

        assert "stack_trace" in details


class TestExecutePhase:
    """Tests for phase execution with error handling."""

    @pytest.mark.asyncio
    async def test_successful_phase_execution(self, executor, sample_phase, mock_builder_client):
        """Test successful phase execution."""
        mock_builder_client.generate_code.return_value = {
            "success": True,
            "patch": "diff --git a/test.py b/test.py\n+print('test')",
        }

        result = await executor.execute_phase(sample_phase, {})

        assert result["success"] is True
        assert "patch" in result
        assert sample_phase.status == PhaseStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_phase_retry_on_network_error(self, executor, sample_phase, mock_builder_client):
        """Test that phase retries on network error."""
        mock_builder_client.generate_code.side_effect = [
            NetworkError("Connection timeout"),
            {"success": True, "patch": "diff --git a/test.py b/test.py\n+print('test')"},
        ]

        result = await executor.execute_phase(sample_phase, {})

        assert result["success"] is True
        assert mock_builder_client.generate_code.call_count == 2

    @pytest.mark.asyncio
    async def test_phase_fails_after_max_retries(self, executor, sample_phase, mock_builder_client):
        """Test that phase fails after max retries."""
        mock_builder_client.generate_code.side_effect = NetworkError("Connection timeout")

        with pytest.raises(BuilderError):
            await executor.execute_phase(sample_phase, {})

        assert sample_phase.status == PhaseStatus.FAILED
        assert mock_builder_client.generate_code.call_count == MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_phase_no_retry_on_validation_error(self, executor, sample_phase, mock_builder_client):
        """Test that phase doesn't retry on validation error."""
        mock_builder_client.generate_code.side_effect = ValidationError("Invalid format")

        with pytest.raises(BuilderError):
            await executor.execute_phase(sample_phase, {})

        assert sample_phase.status == PhaseStatus.FAILED
        assert mock_builder_client.generate_code.call_count == 1

    @pytest.mark.asyncio
    async def test_phase_metadata_includes_error_info(self, executor, sample_phase, mock_builder_client):
        """Test that phase metadata includes error information on failure."""
        mock_builder_client.generate_code.side_effect = ValidationError("Invalid format")

        with pytest.raises(BuilderError):
            await executor.execute_phase(sample_phase, {})

        assert sample_phase.metadata is not None
        assert "error_category" in sample_phase.metadata
        assert sample_phase.metadata["error_category"] == ErrorCategory.VALIDATION


class TestErrorStatistics:
    """Tests for error statistics tracking."""

    def test_empty_error_statistics(self, executor):
        """Test statistics with no errors."""
        stats = executor.get_error_statistics()
        assert stats["total_errors"] == 0
        assert stats["by_category"] == {}
        assert stats["retry_rate"] == 0.0

    def test_error_statistics_tracking(self, executor, sample_phase):
        """Test that error statistics are tracked correctly."""
        # Simulate multiple errors
        executor._handle_builder_error(NetworkError("timeout"), sample_phase, 0)
        executor._handle_builder_error(APIError("rate limit"), sample_phase, 0)
        executor._handle_builder_error(ValidationError("invalid"), sample_phase, 0)

        stats = executor.get_error_statistics()
        assert stats["total_errors"] == 3
        assert stats["by_category"][ErrorCategory.NETWORK] == 1
        assert stats["by_category"][ErrorCategory.API] == 1
        assert stats["by_category"][ErrorCategory.VALIDATION] == 1
        assert stats["retryable_errors"] == 2  # Network and API are retryable
        assert stats["retry_rate"] == pytest.approx(66.67, rel=0.1)
