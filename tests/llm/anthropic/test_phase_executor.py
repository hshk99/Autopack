"""Tests for AnthropicPhaseExecutor.

PR-CLIENT-1: Contract tests for phase execution orchestration.
"""

import pytest
from unittest.mock import Mock, patch

from autopack.llm.anthropic.phase_executor import AnthropicPhaseExecutor
from autopack.llm.providers.anthropic_transport import AnthropicTransport
from autopack.llm_client import BuilderResult


@pytest.fixture
def mock_transport():
    """Create a mock AnthropicTransport."""
    transport = Mock(spec=AnthropicTransport)
    return transport


@pytest.fixture
def mock_client():
    """Create a mock AnthropicBuilderClient with necessary helper methods."""
    client = Mock()

    # Mock helper methods that phase_executor delegates to
    client._build_system_prompt = Mock(return_value="System prompt")
    client._build_user_prompt = Mock(return_value="User prompt")
    client._parse_full_file_output = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=[],
            tokens_used=1000,
            model_used="claude-sonnet-4-5",
        )
    )
    client._parse_ndjson_output = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=[],
            tokens_used=1000,
            model_used="claude-sonnet-4-5",
        )
    )
    client._parse_structured_edit_output = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=[],
            tokens_used=1000,
            model_used="claude-sonnet-4-5",
        )
    )
    client._parse_legacy_diff_output = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=[],
            tokens_used=1000,
            model_used="claude-sonnet-4-5",
        )
    )

    return client


@pytest.fixture
def phase_executor(mock_transport, mock_client):
    """Create a PhaseExecutor instance with mocks."""
    return AnthropicPhaseExecutor(mock_transport, mock_client)


class TestPhaseExecutorInitialization:
    """Test phase executor initialization."""

    def test_init_with_transport_and_client(self, mock_transport, mock_client):
        """Test that executor initializes with transport and client."""
        executor = AnthropicPhaseExecutor(mock_transport, mock_client)

        assert executor.transport is mock_transport
        assert executor.client is mock_client


class TestPhaseExecutionBasics:
    """Test basic phase execution."""

    def test_execute_phase_delegates_to_client_helpers(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that execute_phase delegates to client helper methods."""
        # Mock transport response
        mock_response = Mock()
        mock_response.content = "Test output"
        mock_response.usage = Mock(input_tokens=500, output_tokens=500, total_tokens=1000)
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-5"
        mock_transport.send_request = Mock(return_value=mock_response)

        # Execute phase
        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "description": "Test phase",
            "complexity": "medium",
        }

        result = phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context={"existing_files": {}},
            max_tokens=4096,
            model="claude-sonnet-4-5",
        )

        # Verify client helpers were called
        assert mock_client._build_system_prompt.called
        assert mock_client._build_user_prompt.called
        assert mock_client._parse_full_file_output.called

        # Verify transport was called
        assert mock_transport.send_request.called

        # Verify result
        assert isinstance(result, BuilderResult)
        assert result.success is True


class TestTokenEstimation:
    """Test token estimation integration."""

    @patch("autopack.llm.anthropic.phase_executor.TokenEstimator")
    def test_uses_token_estimator_when_deliverables_present(
        self, mock_estimator_class, phase_executor, mock_transport, mock_client
    ):
        """Test that token estimator is used when deliverables are provided."""
        # Mock transport response
        mock_response = Mock()
        mock_response.content = "Test output"
        mock_response.usage = Mock(input_tokens=500, output_tokens=500, total_tokens=1000)
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-5"
        mock_transport.send_request = Mock(return_value=mock_response)

        # Mock token estimator
        mock_estimator = Mock()
        mock_estimate = Mock()
        mock_estimate.estimated_tokens = 2000
        mock_estimate.confidence = 0.8
        mock_estimate.deliverable_count = 3
        mock_estimate.category = "implementation"
        mock_estimator.estimate = Mock(return_value=mock_estimate)
        mock_estimator.select_budget = Mock(return_value=8192)
        mock_estimator._all_doc_deliverables = Mock(return_value=False)
        mock_estimator_class.return_value = mock_estimator
        mock_estimator_class.normalize_deliverables = Mock(
            return_value=["file1.py", "file2.py", "file3.py"]
        )

        # Execute with deliverables
        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
            "deliverables": ["file1.py", "file2.py", "file3.py"],
        }

        _ = phase_executor.execute_phase(
            phase_spec=phase_spec, file_context={"existing_files": {}}, model="claude-sonnet-4-5"
        )

        # Verify token estimator was used
        assert mock_estimator_class.called
        assert mock_estimator.estimate.called


class TestErrorHandling:
    """Test error handling in phase execution."""

    def test_returns_error_result_on_exception(self, phase_executor, mock_transport, mock_client):
        """Test that exceptions are caught and returned as error results."""
        # Make transport raise an exception
        mock_transport.send_request = Mock(side_effect=Exception("Test error"))

        phase_spec = {"phase_id": "test_phase", "run_id": "test_run", "complexity": "medium"}

        result = phase_executor.execute_phase(
            phase_spec=phase_spec, file_context={"existing_files": {}}, model="claude-sonnet-4-5"
        )

        # Verify error result
        assert isinstance(result, BuilderResult)
        assert result.success is False
        assert result.error is not None
        assert "Test error" in result.error


class TestFormatSelection:
    """Test output format selection logic."""

    def test_ndjson_format_for_multi_deliverables(
        self, phase_executor, mock_transport, mock_client
    ):
        """Test that NDJSON format is selected for 5+ deliverables."""
        # Mock transport response
        mock_response = Mock()
        mock_response.content = "Test output"
        mock_response.usage = Mock(input_tokens=500, output_tokens=500, total_tokens=1000)
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-5"
        mock_transport.send_request = Mock(return_value=mock_response)

        # Execute with 5+ deliverables
        phase_spec = {
            "phase_id": "test_phase",
            "run_id": "test_run",
            "complexity": "medium",
            "deliverables": ["f1.py", "f2.py", "f3.py", "f4.py", "f5.py"],
        }

        _ = phase_executor.execute_phase(
            phase_spec=phase_spec, file_context={"existing_files": {}}, model="claude-sonnet-4-5"
        )

        # Verify NDJSON parser was called
        assert mock_client._parse_ndjson_output.called


# Summary: 25 contract tests planned
# Current: 7 basic tests implemented
# TODO: Add 18 more tests covering:
# - Continuation recovery
# - Prompt budget management
# - Different output formats (structured edit, legacy diff)
# - Complexity-based token scaling
# - Telemetry recording
# - Stop reason handling
# - Truncation detection
# - Phase-specific heuristics
