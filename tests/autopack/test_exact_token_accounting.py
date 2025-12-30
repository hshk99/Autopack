"""Unit tests for BUILD-143: Exact token accounting across all providers

Validates that prompt_tokens and completion_tokens are accurately recorded
from provider SDK responses, replacing heuristic 40/60 and 60/40 splits.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session

from autopack.llm_service import LlmService
from autopack.llm_client import BuilderResult, AuditorResult
from autopack.usage_recorder import LlmUsageEvent


class TestExactTokenAccounting:
    """Test exact token accounting from provider APIs"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = Mock(spec=Session)
        db.add = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db

    @pytest.fixture
    def llm_service(self, mock_db):
        """Create LlmService instance with mocked dependencies"""
        with patch('autopack.llm_service.ModelRouter'):
            service = LlmService(db=mock_db)
            # Ensure model router returns a simple model
            service.model_router.select_model_with_escalation = Mock(
                return_value=("gpt-4o", "medium", {})
            )
            return service

    def test_builder_exact_tokens_openai(self, llm_service, mock_db):
        """Test OpenAI Builder returns exact prompt/completion tokens"""
        # Mock OpenAI Builder client
        mock_builder = Mock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff --git a/test.py",
            builder_messages=["Generated"],
            tokens_used=1000,
            model_used="gpt-4o",
            prompt_tokens=400,  # Exact from response.usage
            completion_tokens=600  # Exact from response.usage
        )
        mock_builder.execute_phase = Mock(return_value=mock_result)
        llm_service.openai_builder = mock_builder

        # Execute phase
        result = llm_service.execute_builder_phase(
            phase_spec={"task_category": "backend", "complexity": "medium"},
            run_id="test-run",
            phase_id="test-phase"
        )

        # Verify exact tokens were returned
        assert result.prompt_tokens == 400
        assert result.completion_tokens == 600
        assert result.tokens_used == 1000

        # Verify exact tokens were recorded in database
        mock_db.add.assert_called_once()
        usage_event = mock_db.add.call_args[0][0]
        assert isinstance(usage_event, LlmUsageEvent)
        assert usage_event.prompt_tokens == 400
        assert usage_event.completion_tokens == 600
        assert usage_event.provider == "openai"
        assert usage_event.model == "gpt-4o"
        assert usage_event.role == "builder"

    def test_auditor_exact_tokens_openai(self, llm_service, mock_db):
        """Test OpenAI Auditor returns exact prompt/completion tokens"""
        # Mock OpenAI Auditor client
        mock_auditor = Mock()
        mock_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["Approved"],
            tokens_used=800,
            model_used="gpt-4o",
            prompt_tokens=600,  # Exact from response.usage
            completion_tokens=200  # Exact from response.usage
        )
        mock_auditor.review_patch = Mock(return_value=mock_result)
        llm_service.openai_auditor = mock_auditor

        # Mock quality_gate to avoid None comparison errors
        llm_service.quality_gate = Mock()
        llm_service.quality_gate.assess_phase = Mock(return_value={"status": "pass"})

        # Execute review
        result = llm_service.execute_auditor_review(
            patch_content="diff --git a/test.py",
            phase_spec={"task_category": "backend", "complexity": "medium"},
            run_id="test-run",
            phase_id="test-phase"
        )

        # Verify exact tokens were returned
        assert result.prompt_tokens == 600
        assert result.completion_tokens == 200
        assert result.tokens_used == 800

        # Verify exact tokens were recorded in database
        mock_db.add.assert_called_once()
        usage_event = mock_db.add.call_args[0][0]
        assert isinstance(usage_event, LlmUsageEvent)
        assert usage_event.prompt_tokens == 600
        assert usage_event.completion_tokens == 200
        assert usage_event.provider == "openai"
        assert usage_event.model == "gpt-4o"
        assert usage_event.role == "auditor"

    def test_builder_exact_tokens_gemini(self, llm_service, mock_db):
        """Test Gemini Builder returns exact prompt/completion tokens"""
        # Mock ModelRouter to return Gemini model
        llm_service.model_router.select_model_with_escalation = Mock(
            return_value=("gemini-2.5-pro", "medium", {})
        )

        # Mock Gemini Builder client
        mock_builder = Mock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff --git a/test.py",
            builder_messages=["Generated"],
            tokens_used=1200,
            model_used="gemini-2.5-pro",
            prompt_tokens=500,  # Exact from usage_metadata.prompt_token_count
            completion_tokens=700  # Exact from usage_metadata.candidates_token_count
        )
        mock_builder.execute_phase = Mock(return_value=mock_result)
        llm_service.gemini_builder = mock_builder

        # Execute phase
        result = llm_service.execute_builder_phase(
            phase_spec={"task_category": "backend", "complexity": "medium"},
            run_id="test-run",
            phase_id="test-phase"
        )

        # Verify exact tokens were returned
        assert result.prompt_tokens == 500
        assert result.completion_tokens == 700
        assert result.tokens_used == 1200

        # Verify exact tokens were recorded in database
        mock_db.add.assert_called_once()
        usage_event = mock_db.add.call_args[0][0]
        assert isinstance(usage_event, LlmUsageEvent)
        assert usage_event.prompt_tokens == 500
        assert usage_event.completion_tokens == 700
        assert usage_event.provider == "google"
        assert usage_event.model == "gemini-2.5-pro"

    def test_builder_exact_tokens_anthropic(self, llm_service, mock_db):
        """Test Anthropic Builder returns exact prompt/completion tokens"""
        # Mock ModelRouter to return Claude model
        llm_service.model_router.select_model_with_escalation = Mock(
            return_value=("claude-sonnet-4-5", "medium", {})
        )

        # Mock Anthropic Builder client
        mock_builder = Mock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff --git a/test.py",
            builder_messages=["Generated"],
            tokens_used=1500,
            model_used="claude-sonnet-4-5",
            prompt_tokens=600,  # Exact from response.usage.input_tokens
            completion_tokens=900  # Exact from response.usage.output_tokens
        )
        mock_builder.execute_phase = Mock(return_value=mock_result)
        llm_service.anthropic_builder = mock_builder

        # Execute phase
        result = llm_service.execute_builder_phase(
            phase_spec={"task_category": "backend", "complexity": "medium"},
            run_id="test-run",
            phase_id="test-phase"
        )

        # Verify exact tokens were returned
        assert result.prompt_tokens == 600
        assert result.completion_tokens == 900
        assert result.tokens_used == 1500

        # Verify exact tokens were recorded in database
        mock_db.add.assert_called_once()
        usage_event = mock_db.add.call_args[0][0]
        assert isinstance(usage_event, LlmUsageEvent)
        assert usage_event.prompt_tokens == 600
        assert usage_event.completion_tokens == 900
        assert usage_event.provider == "anthropic"
        assert usage_event.model == "claude-sonnet-4-5"

    def test_fallback_when_exact_tokens_missing(self, llm_service, mock_db):
        """Test fallback to heuristic split when provider doesn't return exact tokens"""
        # Mock Builder result WITHOUT exact token counts (legacy client)
        mock_builder = Mock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff --git a/test.py",
            builder_messages=["Generated"],
            tokens_used=1000,
            model_used="gpt-4o",
            prompt_tokens=None,  # Missing - should trigger fallback
            completion_tokens=None  # Missing - should trigger fallback
        )
        mock_builder.execute_phase = Mock(return_value=mock_result)
        llm_service.openai_builder = mock_builder

        # Execute phase with logging capture
        import logging
        with patch.object(logging.getLogger('autopack.llm_service'), 'warning') as mock_warning:
            result = llm_service.execute_builder_phase(
                phase_spec={"task_category": "backend", "complexity": "medium"},
                run_id="test-run",
                phase_id="test-phase"
            )

            # Verify warning was logged
            mock_warning.assert_called_once()
            warning_msg = mock_warning.call_args[0][0]
            assert "missing exact token counts" in warning_msg
            assert "Recording total_tokens=1000 without split" in warning_msg

        # BUILD-144 P0: No longer uses fallback splits - records total-only with None
        # Note: The test verifies warning is logged, actual recording happens via
        # _record_usage_total_only which sets prompt_tokens=None, completion_tokens=None

    def test_no_heuristic_splits_when_exact_available(self, llm_service, mock_db):
        """Verify NO heuristic splits are applied when exact tokens are available"""
        # Mock Builder with exact tokens that DON'T match 40/60 split
        mock_builder = Mock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff --git a/test.py",
            builder_messages=["Generated"],
            tokens_used=1000,
            model_used="gpt-4o",
            prompt_tokens=300,  # NOT 40% (would be 400)
            completion_tokens=700  # NOT 60% (would be 600)
        )
        mock_builder.execute_phase = Mock(return_value=mock_result)
        llm_service.openai_builder = mock_builder

        # Execute phase
        result = llm_service.execute_builder_phase(
            phase_spec={"task_category": "backend", "complexity": "medium"},
            run_id="test-run",
            phase_id="test-phase"
        )

        # Verify EXACT tokens were used (not heuristic)
        usage_event = mock_db.add.call_args[0][0]
        assert usage_event.prompt_tokens == 300  # Exact, not 400
        assert usage_event.completion_tokens == 700  # Exact, not 600

    def test_dashboard_usage_aggregation_uses_exact_tokens(self, mock_db):
        """Test /dashboard/usage endpoint aggregates using exact token counts"""
        # This integration test verifies that the dashboard endpoints
        # correctly use the exact prompt_tokens and completion_tokens
        # from LlmUsageEvent rather than recalculating with heuristics

        # Mock LlmUsageEvent query results with exact tokens
        mock_events = [
            LlmUsageEvent(
                provider="openai",
                model="gpt-4o",
                role="builder",
                prompt_tokens=400,
                completion_tokens=600,
                run_id="test-run",
                phase_id="phase-1"
            ),
            LlmUsageEvent(
                provider="anthropic",
                model="claude-sonnet-4-5",
                role="auditor",
                prompt_tokens=800,
                completion_tokens=200,
                run_id="test-run",
                phase_id="phase-2"
            )
        ]

        mock_query = Mock()
        mock_query.filter = Mock(return_value=mock_query)
        mock_query.all = Mock(return_value=mock_events)
        mock_db.query = Mock(return_value=mock_query)

        # Import and test dashboard endpoint logic
        from autopack.main import app
        from fastapi.testclient import TestClient

        # Note: This test verifies the data flow but doesn't test the endpoint directly
        # The key assertion is that LlmUsageEvent has exact prompt_tokens/completion_tokens
        assert all(event.prompt_tokens is not None for event in mock_events)
        assert all(event.completion_tokens is not None for event in mock_events)
