"""Tests for LlmService scope reduction proposal wiring (GAP-8.2.1).

These tests verify:
- LlmService.generate_scope_reduction_proposal method exists and is callable
- Returns dict matching ScopeReductionProposal schema on success
- Raises ScopeReductionError on LLM call failure (IMP-REL-002)
- Raises ScopeReductionError on JSON parse failure (IMP-REL-002)
- Records usage correctly
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestLlmServiceScopeReductionWiring:
    """Tests for scope reduction proposal generation via LlmService."""

    def test_generate_scope_reduction_proposal_method_exists(self):
        """LlmService has generate_scope_reduction_proposal method."""
        from autopack.llm_service import LlmService

        assert hasattr(LlmService, "generate_scope_reduction_proposal")

    def test_generate_scope_reduction_proposal_returns_dict_on_success(self):
        """generate_scope_reduction_proposal returns parsed dict on success."""
        from autopack.llm_service import LlmService

        # Mock successful LLM response
        mock_response_data = {
            "run_id": "test-run",
            "phase_id": "phase-1",
            "anchor_id": "anchor-123",
            "diff": {
                "original_deliverables": ["task-1", "task-2", "task-3"],
                "kept_deliverables": ["task-1", "task-2"],
                "dropped_deliverables": ["task-3"],
                "rationale": {
                    "success_criteria_preserved": ["Complete core functionality"],
                    "success_criteria_deferred": ["Add comprehensive tests"],
                    "constraints_still_met": ["Must not break existing API"],
                    "reason": "Budget exhausted, deferring non-critical test coverage",
                },
            },
            "estimated_budget_savings": 0.3,
        }

        # Create mock service
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock the _resolve_client_and_model method for Anthropic client
            # Create a mock that passes the Anthropic branch check:
            # hasattr(client, "client") and hasattr(client.client, "messages")
            # but NOT hasattr(client.client, "chat")
            mock_inner_client = MagicMock(spec=["messages"])  # Only has "messages"
            mock_completion = MagicMock()
            mock_completion.content = [MagicMock(text=json.dumps(mock_response_data))]
            # Create usage as a simple object with integer attributes (not MagicMock)
            # to avoid MagicMock arithmetic issues
            mock_completion.usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 200})()
            mock_inner_client.messages.create.return_value = mock_completion

            mock_client = MagicMock()
            mock_client.client = mock_inner_client

            service._resolve_client_and_model = MagicMock(
                return_value=(mock_client, "claude-sonnet-4-5")
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()

            # Call method
            prompt = "Test scope reduction prompt"
            result = service.generate_scope_reduction_proposal(
                prompt=prompt, run_id="test-run", phase_id="phase-1"
            )

            # Verify result
            assert result is not None
            assert result["run_id"] == "test-run"
            assert result["diff"]["kept_deliverables"] == ["task-1", "task-2"]
            assert result["diff"]["dropped_deliverables"] == ["task-3"]

    def test_generate_scope_reduction_proposal_raises_on_api_failure(self):
        """generate_scope_reduction_proposal raises ScopeReductionError on LLM failure."""
        from autopack.exceptions import ScopeReductionError
        from autopack.llm_service import LlmService

        # Create mock service with failing LLM
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock Anthropic client that raises exception on messages.create
            # Need to properly setup spec so hasattr checks work correctly
            mock_inner_client = MagicMock(spec=["messages"])  # Only has "messages", not "chat"
            mock_inner_client.messages.create.side_effect = Exception("API error")

            mock_client = MagicMock()
            mock_client.client = mock_inner_client

            service._resolve_client_and_model = MagicMock(
                return_value=(mock_client, "claude-sonnet-4-5")
            )

            # Verify raises ScopeReductionError with context
            with pytest.raises(ScopeReductionError) as exc_info:
                service.generate_scope_reduction_proposal(
                    prompt="Test prompt", run_id="test-run", phase_id="phase-1"
                )

            # Verify exception contains context
            assert exc_info.value.run_id == "test-run"
            assert exc_info.value.phase_id == "phase-1"
            assert exc_info.value.component == "scope_reduction"
            assert "API error" in str(exc_info.value)

    def test_generate_scope_reduction_proposal_raises_on_json_parse_failure(self):
        """generate_scope_reduction_proposal raises ScopeReductionError on JSON parse failure."""
        from autopack.exceptions import ScopeReductionError
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock client that returns invalid JSON
            mock_inner_client = MagicMock(spec=["messages"])
            mock_completion = MagicMock()
            mock_completion.content = [MagicMock(text="not valid json")]
            mock_completion.usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 200})()
            mock_inner_client.messages.create.return_value = mock_completion

            mock_client = MagicMock()
            mock_client.client = mock_inner_client

            service._resolve_client_and_model = MagicMock(
                return_value=(mock_client, "claude-sonnet-4-5")
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()

            # Verify raises ScopeReductionError for JSON parsing errors
            with pytest.raises(ScopeReductionError) as exc_info:
                service.generate_scope_reduction_proposal(
                    prompt="Test prompt", run_id="test-run", phase_id="phase-1"
                )

            # Verify exception contains context
            assert exc_info.value.run_id == "test-run"
            assert exc_info.value.phase_id == "phase-1"
            assert "parse" in str(exc_info.value).lower()

    def test_generate_scope_reduction_proposal_records_usage(self):
        """generate_scope_reduction_proposal records LLM usage."""
        from autopack.llm_service import LlmService

        mock_response_data = {
            "run_id": "test-run",
            "phase_id": "phase-1",
            "anchor_id": "anchor-123",
            "diff": {
                "original_deliverables": ["task-1"],
                "kept_deliverables": ["task-1"],
                "dropped_deliverables": [],
                "rationale": {
                    "success_criteria_preserved": ["All"],
                    "success_criteria_deferred": [],
                    "constraints_still_met": ["All"],
                    "reason": "No reduction needed",
                },
            },
            "estimated_budget_savings": 0.0,
        }

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock the _resolve_client_and_model method for Anthropic client
            mock_inner_client = MagicMock(spec=["messages"])  # Only has "messages"
            mock_completion = MagicMock()
            mock_completion.content = [MagicMock(text=json.dumps(mock_response_data))]
            # Create usage as a simple object with integer attributes (not MagicMock)
            # to avoid MagicMock arithmetic issues
            mock_completion.usage = type("Usage", (), {"input_tokens": 150, "output_tokens": 250})()
            mock_inner_client.messages.create.return_value = mock_completion

            mock_client = MagicMock()
            mock_client.client = mock_inner_client

            service._resolve_client_and_model = MagicMock(
                return_value=(mock_client, "claude-sonnet-4-5")
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()

            # Call method
            service.generate_scope_reduction_proposal(
                prompt="Test prompt", run_id="test-run", phase_id="phase-1"
            )

            # Verify usage was recorded
            service._record_usage.assert_called_once()
            call_kwargs = service._record_usage.call_args[1]
            assert call_kwargs["role"] == "scope_reduction"
            assert call_kwargs["prompt_tokens"] == 150
            assert call_kwargs["completion_tokens"] == 250


class TestExecutorWiringScopeReduction:
    """Tests for executor_wiring integration with LlmService scope reduction."""

    def test_generate_scope_reduction_proposal_uses_llm_service(self):
        """executor_wiring.generate_scope_reduction_proposal calls LlmService."""
        from autopack.autonomous.executor_wiring import (
            ExecutorWiringState,
            generate_scope_reduction_proposal,
        )
        from autopack.autonomous.intention_first_loop import IntentionFirstLoop
        from autopack.intention_anchor.models import IntentionAnchor, IntentionConstraints

        now = datetime.now(timezone.utc)
        # Create minimal anchor with all required fields
        anchor = IntentionAnchor(
            anchor_id="test-anchor",
            run_id="test-run",
            project_id="test-project",
            created_at=now,
            updated_at=now,
            north_star="Complete the feature",
            success_criteria=["Implement core functionality"],
            constraints=IntentionConstraints(
                must=["Must not break API"],
                must_not=["Must not remove existing tests"],
                preferences=["Prefer minimal changes"],
            ),
        )

        # Create wiring state with mocked loop
        mock_loop = MagicMock(spec=IntentionFirstLoop)
        mock_loop.build_scope_reduction_prompt.return_value = "Test prompt"

        wiring = ExecutorWiringState(
            loop=mock_loop,
            run_state=MagicMock(),
        )

        # Mock LlmService
        mock_llm_service = MagicMock()
        mock_llm_service.generate_scope_reduction_proposal.return_value = {
            "run_id": "test-run",
            "phase_id": "phase-1",
            "anchor_id": "test-anchor",
            "diff": {
                "original_deliverables": ["task-1", "task-2"],
                "kept_deliverables": ["task-1"],
                "dropped_deliverables": ["task-2"],
                "rationale": {
                    "success_criteria_preserved": ["Implement core functionality"],
                    "success_criteria_deferred": [],
                    "constraints_still_met": ["Must not break API"],
                    "reason": "Budget constraint",
                },
            },
            "estimated_budget_savings": 0.5,
        }

        # Call the function
        current_plan = {"deliverables": ["task-1", "task-2"]}
        result = generate_scope_reduction_proposal(
            wiring=wiring,
            anchor=anchor,
            current_plan=current_plan,
            budget_remaining=0.2,
            llm_service=mock_llm_service,
            run_id="test-run",
            phase_id="phase-1",
        )

        # Verify LlmService was called
        mock_llm_service.generate_scope_reduction_proposal.assert_called_once()

        # Verify result is a valid proposal
        assert result is not None
        assert result.diff.kept_deliverables == ["task-1"]
        assert result.diff.dropped_deliverables == ["task-2"]

    def test_generate_scope_reduction_proposal_returns_none_without_llm_service(self):
        """generate_scope_reduction_proposal returns None when no LlmService."""
        from autopack.autonomous.executor_wiring import (
            ExecutorWiringState,
            generate_scope_reduction_proposal,
        )
        from autopack.autonomous.intention_first_loop import IntentionFirstLoop
        from autopack.intention_anchor.models import IntentionAnchor, IntentionConstraints

        now = datetime.now(timezone.utc)
        anchor = IntentionAnchor(
            anchor_id="test-anchor",
            run_id="test-run",
            project_id="test-project",
            created_at=now,
            updated_at=now,
            north_star="Complete the feature",
            success_criteria=["Implement core functionality"],
            constraints=IntentionConstraints(
                must=["Must not break API"],
                must_not=[],
                preferences=[],
            ),
        )

        mock_loop = MagicMock(spec=IntentionFirstLoop)
        mock_loop.build_scope_reduction_prompt.return_value = "Test prompt"

        wiring = ExecutorWiringState(
            loop=mock_loop,
            run_state=MagicMock(),
        )

        # Call without LlmService
        result = generate_scope_reduction_proposal(
            wiring=wiring,
            anchor=anchor,
            current_plan={"deliverables": ["task-1"]},
            budget_remaining=0.2,
            llm_service=None,  # No LlmService
        )

        # Should return None gracefully
        assert result is None
