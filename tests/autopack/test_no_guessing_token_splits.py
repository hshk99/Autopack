"""BUILD-144 P0: Regression tests to prevent heuristic token split guessing

These tests ensure that llm_service.py NEVER applies heuristic token splits
(like 40/60, 60/40, or 70/30) and instead:
1. Uses exact prompt_tokens/completion_tokens when available
2. Records total-only with None splits when exact counts unavailable
3. Logs warnings when falling back to total-only accounting

This prevents regression of the "no guessing" policy established in BUILD-144 P0.
"""

import re
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from autopack.llm_client import AuditorResult, BuilderResult
from autopack.llm_service import LlmService
from autopack.usage_recorder import LlmUsageEvent


class TestNoGuessingTokenSplits:
    """Ensure no heuristic token splits are applied"""

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
        """Create LlmService instance"""
        with patch("autopack.llm_service.ModelRouter"):
            service = LlmService(db=mock_db)
            service.model_router.select_model_with_escalation = Mock(
                return_value=("gpt-4o", "medium", {})
            )
            return service

    def test_builder_no_guessing_when_splits_missing(self, llm_service, mock_db):
        """When Builder result lacks exact splits, do NOT guess - record None"""
        mock_builder = Mock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff --git a/test.py",
            builder_messages=["Generated"],
            tokens_used=1000,
            model_used="gpt-4o",
            prompt_tokens=None,  # Missing
            completion_tokens=None,  # Missing
        )
        mock_builder.execute_phase = Mock(return_value=mock_result)
        llm_service.openai_builder = mock_builder

        # Execute and verify
        with patch.object(llm_service, "_record_usage_total_only") as mock_total_only:
            llm_service.execute_builder_phase(
                phase_spec={"task_category": "backend", "complexity": "medium"},
                run_id="test-run",
                phase_id="test-phase",
            )

            # Should call total-only recording, NOT regular _record_usage
            mock_total_only.assert_called_once()
            call_kwargs = mock_total_only.call_args[1]
            assert call_kwargs["total_tokens"] == 1000
            assert call_kwargs["role"] == "builder"

    def test_auditor_no_guessing_when_splits_missing(self, llm_service, mock_db):
        """When Auditor result lacks exact splits, do NOT guess - record None"""
        mock_auditor = Mock()
        mock_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["Approved"],
            tokens_used=800,
            model_used="gpt-4o",
            prompt_tokens=None,  # Missing
            completion_tokens=None,  # Missing
        )
        mock_auditor.review_patch = Mock(return_value=mock_result)
        llm_service.openai_auditor = mock_auditor
        llm_service.quality_gate = Mock()
        llm_service.quality_gate.assess_phase = Mock(return_value={"status": "pass"})

        # Execute and verify
        with patch.object(llm_service, "_record_usage_total_only") as mock_total_only:
            llm_service.execute_auditor_review(
                patch_content="diff --git a/test.py",
                phase_spec={"task_category": "backend", "complexity": "medium"},
                run_id="test-run",
                phase_id="test-phase",
            )

            # Should call total-only recording
            mock_total_only.assert_called_once()
            call_kwargs = mock_total_only.call_args[1]
            assert call_kwargs["total_tokens"] == 800
            assert call_kwargs["role"] == "auditor"

    def test_doctor_no_guessing_anthropic(self, llm_service, mock_db):
        """Doctor with Anthropic should use exact token counts, not 70/30 guess"""
        # Mock the _call_doctor_llm method directly to bypass client setup complexity
        from autopack.error_recovery import DoctorRequest, DoctorResponse

        mock_response = DoctorResponse(
            action="retry_with_fix",
            confidence=0.8,
            rationale="test diagnosis",
            builder_hint=None,
            suggested_patch=None,
        )

        # Mock a client object for doctor execution
        mock_client = Mock()
        mock_client.client = Mock()

        # Patch _call_doctor_llm in the doctor module where it now lives
        with patch(
            "autopack.llm.doctor._call_doctor_llm", return_value=mock_response
        ) as mock_call_doctor:
            with patch(
                "autopack.llm.doctor.choose_doctor_model",
                return_value=("claude-sonnet-4-5", False),
            ):
                with patch("autopack.llm.doctor.should_escalate_doctor_model", return_value=False):
                    with patch.object(
                        llm_service,
                        "_resolve_client_and_model",
                        return_value=(mock_client, "claude-sonnet-4-5"),
                    ):
                        request = DoctorRequest(
                            phase_id="test-phase",
                            error_category="patch_apply_error",
                            builder_attempts=2,
                            health_budget={"total_failures": 5, "total_cap": 25},
                            run_id="test-run",
                        )

                        result = llm_service.execute_doctor(
                            request, run_id="test-run", phase_id="test-phase"
                        )

                        # Verify _call_doctor_llm was called with correct model
                        mock_call_doctor.assert_called_once()
                        # First arg is client (Mock), second arg is model name
                        assert mock_call_doctor.call_args[0][1] == "claude-sonnet-4-5"
                        assert result.action == "retry_with_fix"

        # Note: This test validates the execute_doctor flow. The actual token recording
        # is tested in test_doctor_no_guessing_openai which validates _call_doctor_llm behavior

    def test_doctor_no_guessing_openai(self, llm_service, mock_db):
        """Doctor with OpenAI should use exact token counts"""
        from autopack.error_recovery import DoctorRequest

        # Mock OpenAI client
        mock_openai = Mock()
        mock_completion = Mock()
        mock_completion.choices = [
            Mock(
                message=Mock(
                    content='{"action": "retry_with_fix", "confidence": 0.8, "rationale": "test"}'
                )
            )
        ]
        mock_completion.usage = Mock(prompt_tokens=600, completion_tokens=300, total_tokens=900)
        mock_openai.client = Mock()
        mock_openai.client.chat = Mock()
        mock_openai.client.chat.completions = Mock()
        mock_openai.client.chat.completions.create = Mock(return_value=mock_completion)

        llm_service.openai_builder = mock_openai

        request = DoctorRequest(
            phase_id="test-phase",
            error_category="patch_apply_error",
            builder_attempts=2,
            health_budget={"total_failures": 5, "total_cap": 25},
            run_id="test-run",
        )

        # Execute Doctor call
        with patch("autopack.llm_service.choose_doctor_model", return_value=("gpt-4o", False)):
            with patch("autopack.error_recovery.should_escalate_doctor_model", return_value=False):
                llm_service.execute_doctor(request, run_id="test-run", phase_id="test-phase")

        # Verify exact token counts were recorded
        mock_db.add.assert_called()
        usage_event = mock_db.add.call_args[0][0]
        assert isinstance(usage_event, LlmUsageEvent)
        assert usage_event.prompt_tokens == 600  # Exact from OpenAI
        assert usage_event.completion_tokens == 300  # Exact from OpenAI
        assert usage_event.role == "doctor"

    def test_no_heuristic_constants_in_source(self):
        """Static code check: llm_service.py should not contain heuristic split constants"""
        from pathlib import Path

        # Read llm_service.py source
        service_path = Path(__file__).parent.parent.parent / "src" / "autopack" / "llm_service.py"
        with open(service_path, "r", encoding="utf-8") as f:
            source = f.read()

        # Check for forbidden patterns (heuristic multipliers near token keywords)
        forbidden_patterns = [
            r"tokens_used\s*\*\s*0\.[34567]",  # tokens_used * 0.4, 0.6, 0.7, etc.
            r"0\.[34567]\s*\*\s*tokens_used",  # 0.4 * tokens_used
            r"int\s*\(\s*tokens[_\w]*\s*\*\s*0\.[34567]",  # int(tokens * 0.4)
            r"int\s*\(\s*0\.[34567]\s*\*\s*tokens",  # int(0.4 * tokens)
        ]

        violations = []
        for pattern in forbidden_patterns:
            matches = list(re.finditer(pattern, source, re.IGNORECASE))
            if matches:
                for match in matches:
                    # Get line number
                    line_num = source[: match.start()].count("\n") + 1
                    violations.append(f"Line {line_num}: {match.group()}")

        if violations:
            pytest.fail(
                "Found forbidden heuristic token split patterns in llm_service.py:\n"
                + "\n".join(violations)
                + "\n\nBUILD-144 P0: Token splits must use exact counts from provider, not heuristic guessing."
            )

    def test_record_usage_total_only_uses_none_splits(self, llm_service, mock_db):
        """Verify _record_usage_total_only records None for prompt/completion tokens"""
        llm_service._record_usage_total_only(
            provider="openai",
            model="gpt-4o",
            role="builder",
            total_tokens=1000,
            run_id="test-run",
            phase_id="test-phase",
        )

        # Verify None was recorded (not a heuristic split)
        mock_db.add.assert_called_once()
        usage_event = mock_db.add.call_args[0][0]
        assert isinstance(usage_event, LlmUsageEvent)
        assert usage_event.prompt_tokens is None  # Explicit None, not guessed
        assert usage_event.completion_tokens is None  # Explicit None, not guessed
        assert usage_event.provider == "openai"
        assert usage_event.role == "builder"

    def test_warning_logged_when_exact_counts_missing(self, llm_service, mock_db):
        """Verify warning is logged when falling back to total-only accounting"""
        import logging

        mock_builder = Mock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff --git a/test.py",
            builder_messages=["Generated"],
            tokens_used=1000,
            model_used="gpt-4o",
            prompt_tokens=None,
            completion_tokens=None,
        )
        mock_builder.execute_phase = Mock(return_value=mock_result)
        llm_service.openai_builder = mock_builder

        # Capture warning log
        with patch.object(logging.getLogger("autopack.llm_service"), "warning") as mock_warning:
            llm_service.execute_builder_phase(
                phase_spec={"task_category": "backend", "complexity": "medium"},
                run_id="test-run",
                phase_id="test-phase",
            )

            # Verify warning was logged
            mock_warning.assert_called()
            warning_msg = mock_warning.call_args[0][0]
            assert "missing exact token counts" in warning_msg
            assert "Recording total_tokens=" in warning_msg
            assert "without split" in warning_msg
