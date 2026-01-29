"""Tests for LLM service public functions (IMP-TEST-010).

This module provides comprehensive test coverage for the public functions
in src/autopack/llm_service.py including:
- estimate_tokens (module-level function)
- LlmService class public methods
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

# =============================================================================
# Tests for estimate_tokens (module-level function)
# =============================================================================


class TestEstimateTokens:
    """Tests for the estimate_tokens module-level function."""

    def test_estimate_tokens_empty_string(self):
        """Empty string returns minimum of 1 token."""
        from autopack.llm_service import estimate_tokens

        result = estimate_tokens("")
        assert result == 1

    def test_estimate_tokens_short_text(self):
        """Short text estimates tokens correctly."""
        from autopack.llm_service import estimate_tokens

        # 4 chars = 1 token at default 4.0 chars/token
        result = estimate_tokens("test")
        assert result == 1

    def test_estimate_tokens_longer_text(self):
        """Longer text estimates tokens based on character count."""
        from autopack.llm_service import estimate_tokens

        # 40 chars / 4 chars per token = 10 tokens
        text = "a" * 40
        result = estimate_tokens(text)
        assert result == 10

    def test_estimate_tokens_custom_chars_per_token(self):
        """Custom chars_per_token parameter is respected."""
        from autopack.llm_service import estimate_tokens

        # 20 chars / 2 chars per token = 10 tokens
        text = "a" * 20
        result = estimate_tokens(text, chars_per_token=2.0)
        assert result == 10

    def test_estimate_tokens_fractional_rounds_down(self):
        """Fractional token estimates are converted to int."""
        from autopack.llm_service import estimate_tokens

        # 5 chars / 4 = 1.25 -> int(1.25) = 1
        text = "hello"
        result = estimate_tokens(text)
        assert result == 1
        assert isinstance(result, int)

    def test_estimate_tokens_never_returns_zero(self):
        """Estimate never returns 0, minimum is 1."""
        from autopack.llm_service import estimate_tokens

        # Single character should still return 1
        result = estimate_tokens("a")
        assert result >= 1


# =============================================================================
# Tests for LlmService.__init__
# =============================================================================


class TestLlmServiceInit:
    """Tests for LlmService initialization."""

    @patch("autopack.llm_service.ModelRouter")
    @patch("autopack.llm_service.QualityGate")
    @patch("autopack.llm_service.OPENAI_AVAILABLE", False)
    @patch("autopack.llm_service.ANTHROPIC_AVAILABLE", False)
    @patch("autopack.llm_service.GEMINI_AVAILABLE", False)
    def test_init_no_providers_available(self, mock_quality_gate, mock_router):
        """LlmService initializes with no providers available."""
        from autopack.llm_service import LlmService

        mock_db = MagicMock()
        service = LlmService(db=mock_db)

        assert service.openai_builder is None
        assert service.openai_auditor is None
        assert service.anthropic_builder is None
        assert service.anthropic_auditor is None
        assert service.gemini_builder is None
        assert service.gemini_auditor is None

    @patch("autopack.llm_service.ModelRouter")
    @patch("autopack.llm_service.QualityGate")
    @patch("autopack.llm_service.OPENAI_AVAILABLE", True)
    @patch("autopack.llm_service.ANTHROPIC_AVAILABLE", False)
    @patch("autopack.llm_service.GEMINI_AVAILABLE", False)
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False)
    @patch("autopack.llm_service.OpenAIBuilderClient")
    @patch("autopack.llm_service.OpenAIAuditorClient")
    def test_init_openai_available_with_key(
        self,
        mock_auditor,
        mock_builder,
        mock_quality_gate,
        mock_router,
    ):
        """LlmService initializes OpenAI clients when available with key."""
        from autopack.llm_service import LlmService

        mock_db = MagicMock()
        service = LlmService(db=mock_db)

        assert service.openai_builder is not None
        assert service.openai_auditor is not None

    @patch("autopack.llm_service.ModelRouter")
    @patch("autopack.llm_service.QualityGate")
    @patch("autopack.llm_service.OPENAI_AVAILABLE", True)
    @patch("autopack.llm_service.ANTHROPIC_AVAILABLE", False)
    @patch("autopack.llm_service.GEMINI_AVAILABLE", False)
    @patch.dict("os.environ", {}, clear=True)
    def test_init_openai_available_no_key(self, mock_quality_gate, mock_router):
        """LlmService skips OpenAI when no API key set."""
        from autopack.llm_service import LlmService

        mock_db = MagicMock()
        service = LlmService(db=mock_db)

        assert service.openai_builder is None
        assert service.openai_auditor is None

    @patch("autopack.llm_service.ModelRouter")
    @patch("autopack.llm_service.QualityGate")
    def test_init_sets_repo_root(self, mock_quality_gate, mock_router):
        """LlmService sets repo_root correctly."""
        from pathlib import Path

        from autopack.llm_service import LlmService

        mock_db = MagicMock()
        custom_root = Path("/custom/root")

        with patch("autopack.llm_service.OPENAI_AVAILABLE", False):
            with patch("autopack.llm_service.ANTHROPIC_AVAILABLE", False):
                with patch("autopack.llm_service.GEMINI_AVAILABLE", False):
                    service = LlmService(db=mock_db, repo_root=custom_root)

        assert service.repo_root == custom_root


# =============================================================================
# Tests for LlmService.generate_deliverables_manifest
# =============================================================================


class TestGenerateDeliverablesManifest:
    """Tests for generate_deliverables_manifest method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            return service

    def test_generate_manifest_success(self):
        """Manifest generation succeeds with valid inputs."""
        service = self._create_mock_service()

        success, manifest, error, raw = service.generate_deliverables_manifest(
            expected_paths=["src/file1.py", "src/file2.py"],
            allowed_roots=["src/"],
            run_id="test-run",
            phase_id="phase-1",
        )

        assert success is True
        assert manifest == ["src/file1.py", "src/file2.py"]
        assert error is None
        assert raw is not None

    def test_generate_manifest_empty_paths(self):
        """Manifest with empty paths returns empty list."""
        service = self._create_mock_service()

        success, manifest, error, raw = service.generate_deliverables_manifest(
            expected_paths=[],
            allowed_roots=["src/"],
        )

        assert success is True
        assert manifest == []

    def test_generate_manifest_deduplicates(self):
        """Manifest deduplicates paths."""
        service = self._create_mock_service()

        success, manifest, error, raw = service.generate_deliverables_manifest(
            expected_paths=["src/file.py", "src/file.py", "src/file.py"],
            allowed_roots=["src/"],
        )

        assert success is True
        assert manifest == ["src/file.py"]

    def test_generate_manifest_sorts_paths(self):
        """Manifest returns sorted paths."""
        service = self._create_mock_service()

        success, manifest, error, raw = service.generate_deliverables_manifest(
            expected_paths=["src/z.py", "src/a.py", "src/m.py"],
            allowed_roots=["src/"],
        )

        assert success is True
        assert manifest == ["src/a.py", "src/m.py", "src/z.py"]

    def test_generate_manifest_fails_outside_allowed_roots(self):
        """Manifest fails when paths outside allowed roots."""
        service = self._create_mock_service()

        success, manifest, error, raw = service.generate_deliverables_manifest(
            expected_paths=["src/file.py", "tests/test.py"],
            allowed_roots=["src/"],
        )

        assert success is False
        assert "outside allowed_roots" in error

    def test_generate_manifest_filters_empty_strings(self):
        """Manifest filters out empty strings and whitespace."""
        service = self._create_mock_service()

        success, manifest, error, raw = service.generate_deliverables_manifest(
            expected_paths=["src/file.py", "", "  ", "src/other.py"],
            allowed_roots=["src/"],
        )

        assert success is True
        assert "" not in manifest
        assert "  " not in manifest

    def test_generate_manifest_no_allowed_roots(self):
        """Manifest succeeds with no allowed roots (no validation)."""
        service = self._create_mock_service()

        success, manifest, error, raw = service.generate_deliverables_manifest(
            expected_paths=["anywhere/file.py"],
            allowed_roots=[],
        )

        assert success is True
        assert manifest == ["anywhere/file.py"]


# =============================================================================
# Tests for LlmService.execute_builder_phase
# =============================================================================


class TestExecuteBuilderPhase:
    """Tests for execute_builder_phase method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            service.model_router = MagicMock()
            return service

    def test_execute_builder_phase_success(self):
        """Builder phase execution succeeds with valid inputs."""
        from autopack.llm_client import BuilderResult

        service = self._create_mock_service()

        # Mock model selection
        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )

        # Mock client resolution
        mock_client = MagicMock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff content",
            builder_messages=["Build successful"],
            tokens_used=100,
            model_used="claude-sonnet-4-5",
            prompt_tokens=80,
            completion_tokens=20,
        )
        mock_client.execute_phase.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")
        service.record_attempt_outcome = MagicMock()

        # Execute
        phase_spec = {"task_category": "general", "complexity": "medium"}
        result = service.execute_builder_phase(
            phase_spec=phase_spec,
            run_id="test-run",
            phase_id="phase-1",
        )

        assert result.success is True
        assert result.patch_content == "diff content"

    def test_execute_builder_phase_budget_exceeded(self):
        """Builder phase returns budget exceeded when over budget."""

        service = self._create_mock_service()

        # Mock budget check to fail
        service._check_pre_call_budget = MagicMock(
            return_value={
                "within_budget": False,
                "estimated_input_tokens": 10000,
                "estimated_output_tokens": 4000,
                "budget_remaining": 5000,
                "reason": "Estimated exceeds budget",
            }
        )

        phase_spec = {"task_category": "general", "complexity": "medium"}
        result = service.execute_builder_phase(
            phase_spec=phase_spec,
            run_id="test-run",
            phase_id="phase-1",
            run_token_budget=10000,
            tokens_used_so_far=5000,
        )

        assert result.success is False
        assert "budget_exceeded" in result.error

    def test_execute_builder_phase_records_outcome(self):
        """Builder phase records attempt outcome."""
        from autopack.llm_client import BuilderResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )

        mock_client = MagicMock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff",
            builder_messages=[],
            tokens_used=100,
            model_used="claude-sonnet-4-5",
            prompt_tokens=80,
            completion_tokens=20,
        )
        mock_client.execute_phase.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")
        service.record_attempt_outcome = MagicMock()

        service.execute_builder_phase(
            phase_spec={},
            phase_id="phase-1",
        )

        service.record_attempt_outcome.assert_called_once()


# =============================================================================
# Tests for LlmService.execute_auditor_review
# =============================================================================


class TestExecuteAuditorReview:
    """Tests for execute_auditor_review method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            service.model_router = MagicMock()
            service.quality_gate = MagicMock()
            return service

    def test_execute_auditor_review_approved(self):
        """Auditor review returns approved result."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )
        service.model_router.config = {}

        mock_client = MagicMock()
        mock_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["LGTM"],
            tokens_used=50,
            model_used="claude-sonnet-4-5",
            prompt_tokens=40,
            completion_tokens=10,
        )
        mock_client.review_patch.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._should_use_dual_audit = MagicMock(return_value=False)
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")
        service.record_attempt_outcome = MagicMock()
        service.quality_gate.assess_phase.return_value = {}
        service.quality_gate.format_report.return_value = ""

        result = service.execute_auditor_review(
            patch_content="diff content",
            phase_spec={"task_category": "general"},
            phase_id="phase-1",
        )

        assert result.approved is True
        assert result.issues_found == []

    def test_execute_auditor_review_rejected_with_issues(self):
        """Auditor review returns rejected with issues."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )
        service.model_router.config = {}

        mock_client = MagicMock()
        mock_result = AuditorResult(
            approved=False,
            issues_found=[{"severity": "major", "description": "Missing tests"}],
            auditor_messages=["Needs work"],
            tokens_used=50,
            model_used="claude-sonnet-4-5",
            prompt_tokens=40,
            completion_tokens=10,
        )
        mock_client.review_patch.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._should_use_dual_audit = MagicMock(return_value=False)
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")
        service.record_attempt_outcome = MagicMock()
        service.quality_gate.assess_phase.return_value = {}
        service.quality_gate.format_report.return_value = ""

        result = service.execute_auditor_review(
            patch_content="bad diff",
            phase_spec={"task_category": "general"},
            phase_id="phase-1",
        )

        assert result.approved is False
        assert len(result.issues_found) == 1

    def test_execute_auditor_review_records_usage(self):
        """Auditor review records usage."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )
        service.model_router.config = {}

        mock_client = MagicMock()
        mock_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=100,
            model_used="claude-sonnet-4-5",
            prompt_tokens=80,
            completion_tokens=20,
        )
        mock_client.review_patch.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._should_use_dual_audit = MagicMock(return_value=False)
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")
        service.record_attempt_outcome = MagicMock()
        service.quality_gate.assess_phase.return_value = {}
        service.quality_gate.format_report.return_value = ""

        service.execute_auditor_review(
            patch_content="diff",
            phase_spec={},
            run_id="test-run",
            phase_id="phase-1",
        )

        service._record_usage.assert_called_once()


# =============================================================================
# Tests for LlmService.record_attempt_outcome
# =============================================================================


class TestRecordAttemptOutcome:
    """Tests for record_attempt_outcome method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            return service

    def test_record_success_outcome(self):
        """Recording success outcome delegates to model_router."""
        service = self._create_mock_service()
        service._model_to_provider = MagicMock(return_value="anthropic")

        service.record_attempt_outcome(
            phase_id="phase-1",
            model="claude-sonnet-4-5",
            outcome="success",
            details=None,
        )

        service.model_router.record_attempt_outcome.assert_called_once_with(
            phase_id="phase-1",
            model="claude-sonnet-4-5",
            outcome="success",
            details=None,
        )

    def test_record_failure_outcome(self):
        """Recording failure outcome delegates to model_router."""
        service = self._create_mock_service()
        service._model_to_provider = MagicMock(return_value="anthropic")

        service.record_attempt_outcome(
            phase_id="phase-1",
            model="claude-sonnet-4-5",
            outcome="auditor_reject",
            details="Patch not approved",
        )

        service.model_router.record_attempt_outcome.assert_called_once()

    def test_record_infra_error_disables_provider(self):
        """Recording infra_error disables non-OpenAI provider."""
        service = self._create_mock_service()
        service._model_to_provider = MagicMock(return_value="anthropic")

        service.record_attempt_outcome(
            phase_id="phase-1",
            model="claude-sonnet-4-5",
            outcome="infra_error",
            details="Connection timeout",
        )

        service.model_router.disable_provider.assert_called_once()


# =============================================================================
# Tests for LlmService.get_max_attempts
# =============================================================================


class TestGetMaxAttempts:
    """Tests for get_max_attempts method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            return service

    def test_get_max_attempts_returns_router_value(self):
        """get_max_attempts returns value from model_router."""
        service = self._create_mock_service()
        service.model_router.get_max_attempts.return_value = 5

        result = service.get_max_attempts()

        assert result == 5
        service.model_router.get_max_attempts.assert_called_once()


# =============================================================================
# Tests for LlmService.execute_doctor
# =============================================================================


class TestExecuteDoctor:
    """Tests for execute_doctor method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            service.model_router = MagicMock()
            return service

    @patch("autopack.error_recovery.get_diagnosis_with_cache")
    @patch("autopack.llm_service.choose_doctor_model")
    def test_execute_doctor_success(self, mock_choose_model, mock_get_diagnosis):
        """Doctor execution returns diagnosis response."""
        from autopack.error_recovery import DoctorRequest, DoctorResponse

        service = self._create_mock_service()

        mock_choose_model.return_value = ("claude-sonnet-4-5", None)
        service._resolve_client_and_model = MagicMock(
            return_value=(MagicMock(), "claude-sonnet-4-5")
        )

        mock_response = DoctorResponse(
            action="retry_with_fix",
            confidence=0.8,
            rationale="Likely transient error",
            builder_hint="Try again with more context",
        )
        mock_get_diagnosis.return_value = mock_response

        request = DoctorRequest(
            phase_id="phase-1",
            error_category="build_error",
            builder_attempts=1,
            health_budget={"http_500": 0, "patch_failures": 1, "total_failures": 1},
            logs_excerpt="Compilation failed",
        )

        result = service.execute_doctor(
            request=request,
            run_id="test-run",
            phase_id="phase-1",
        )

        assert result.action == "retry_with_fix"
        assert result.confidence == 0.8

    @patch("autopack.error_recovery.get_diagnosis_with_cache")
    @patch("autopack.llm_service.choose_doctor_model")
    def test_execute_doctor_uses_cache(self, mock_choose_model, mock_get_diagnosis):
        """Doctor uses caching for repeated error patterns."""
        from autopack.error_recovery import DoctorRequest, DoctorResponse

        service = self._create_mock_service()

        mock_choose_model.return_value = ("claude-sonnet-4-5", None)
        service._resolve_client_and_model = MagicMock(
            return_value=(MagicMock(), "claude-sonnet-4-5")
        )

        # Return a mock response to avoid None issues
        mock_response = DoctorResponse(
            action="skip_phase",
            confidence=0.7,
            rationale="Test failure",
        )
        mock_get_diagnosis.return_value = mock_response

        request = DoctorRequest(
            phase_id="phase-1",
            error_category="test_failure",
            builder_attempts=1,
            health_budget={"http_500": 0, "patch_failures": 0, "total_failures": 1},
            logs_excerpt="Test failed",
        )

        service.execute_doctor(request=request, phase_id="phase-1")

        # Verify get_diagnosis_with_cache was called
        mock_get_diagnosis.assert_called_once()


# =============================================================================
# Tests for LlmService._check_pre_call_budget
# =============================================================================


class TestCheckPreCallBudget:
    """Tests for _check_pre_call_budget private method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            return service

    def test_within_budget(self):
        """Budget check passes when within budget."""
        service = self._create_mock_service()

        result = service._check_pre_call_budget(
            phase_spec={"task": "test"},
            file_context=None,
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=100000,
            tokens_used_so_far=0,
        )

        assert result["within_budget"] is True

    def test_exceeds_budget(self):
        """Budget check fails when exceeds budget."""
        service = self._create_mock_service()

        # Use most of the budget already
        result = service._check_pre_call_budget(
            phase_spec={"task": "test"},
            file_context={"large": "x" * 50000},  # Large context
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=10000,
            tokens_used_so_far=9000,  # Already used most of budget
        )

        assert result["within_budget"] is False
        assert "budget" in result["reason"].lower()


# =============================================================================
# Tests for LlmService._estimate_dict_tokens (IMP-PERF-004)
# =============================================================================


class TestEstimateDictTokens:
    """Tests for _estimate_dict_tokens static method (IMP-PERF-004).

    This method estimates tokens directly from dict structures without
    JSON serialization, improving performance for large contexts (5MB+).
    """

    def test_estimate_none_returns_one(self):
        """None value returns 1 token."""
        from autopack.llm_service import LlmService

        result = LlmService._estimate_dict_tokens(None)
        assert result == 1

    def test_estimate_bool_returns_one(self):
        """Boolean values return 1 token each."""
        from autopack.llm_service import LlmService

        assert LlmService._estimate_dict_tokens(True) == 1
        assert LlmService._estimate_dict_tokens(False) == 1

    def test_estimate_int_returns_one(self):
        """Integer values return 1 token."""
        from autopack.llm_service import LlmService

        assert LlmService._estimate_dict_tokens(0) == 1
        assert LlmService._estimate_dict_tokens(42) == 1
        assert LlmService._estimate_dict_tokens(-100) == 1

    def test_estimate_float_returns_one(self):
        """Float values return 1 token."""
        from autopack.llm_service import LlmService

        assert LlmService._estimate_dict_tokens(3.14) == 1
        assert LlmService._estimate_dict_tokens(0.0) == 1

    def test_estimate_short_string(self):
        """Short strings return minimum of 1 token."""
        from autopack.llm_service import LlmService

        # Less than 4 chars -> 1 token
        assert LlmService._estimate_dict_tokens("abc") == 1
        assert LlmService._estimate_dict_tokens("") == 1

    def test_estimate_longer_string(self):
        """Longer strings estimate ~4 chars per token."""
        from autopack.llm_service import LlmService

        # 40 chars / 4 = 10 tokens
        result = LlmService._estimate_dict_tokens("a" * 40)
        assert result == 10

    def test_estimate_empty_list(self):
        """Empty list returns 1 token."""
        from autopack.llm_service import LlmService

        result = LlmService._estimate_dict_tokens([])
        assert result == 1

    def test_estimate_list_with_items(self):
        """List estimates sum of items plus structural overhead."""
        from autopack.llm_service import LlmService

        # [1, 2, 3] -> 3 items (1 token each) + 3 structural overhead
        result = LlmService._estimate_dict_tokens([1, 2, 3])
        assert result == 6

    def test_estimate_empty_dict(self):
        """Empty dict returns 1 token."""
        from autopack.llm_service import LlmService

        result = LlmService._estimate_dict_tokens({})
        assert result == 1

    def test_estimate_simple_dict(self):
        """Simple dict estimates keys, values, and structural overhead."""
        from autopack.llm_service import LlmService

        # {"a": 1} -> key "a" (1 token) + value 1 (1 token) + overhead (2)
        result = LlmService._estimate_dict_tokens({"a": 1})
        assert result == 4

    def test_estimate_nested_dict(self):
        """Nested dicts are traversed recursively."""
        from autopack.llm_service import LlmService

        nested = {"outer": {"inner": "value"}}
        result = LlmService._estimate_dict_tokens(nested)
        # Should be > 0 and handle nesting
        assert result > 0

    def test_estimate_deeply_nested_stops_at_depth_limit(self):
        """Recursion stops at depth 10 with conservative estimate."""
        from autopack.llm_service import LlmService

        # Create deeply nested structure
        deep = {"level": 0}
        current = deep
        for i in range(15):
            current["nested"] = {"level": i + 1}
            current = current["nested"]

        result = LlmService._estimate_dict_tokens(deep)
        # Should complete without error and return a positive value
        assert result > 0

    def test_estimate_mixed_content(self):
        """Complex mixed content is handled correctly."""
        from autopack.llm_service import LlmService

        mixed = {
            "string_field": "hello world",
            "int_field": 42,
            "float_field": 3.14,
            "bool_field": True,
            "null_field": None,
            "list_field": [1, 2, 3],
            "nested": {"key": "value"},
        }

        result = LlmService._estimate_dict_tokens(mixed)
        # Should complete and return positive estimate
        assert result > 0

    def test_estimate_large_file_context_structure(self):
        """Large file context structure is estimated efficiently."""
        from autopack.llm_service import LlmService

        # Simulate file context structure with multiple files
        file_context = {f"src/file_{i}.py": "x" * 1000 for i in range(10)}  # 1000 chars per file

        result = LlmService._estimate_dict_tokens(file_context)
        # 10 files * ~250 tokens per file content + overhead
        assert result > 2000

    def test_estimate_unknown_type_returns_default(self):
        """Unknown types return conservative default estimate."""
        from autopack.llm_service import LlmService

        # Create a custom object type
        class CustomObject:
            pass

        result = LlmService._estimate_dict_tokens(CustomObject())
        assert result == 10  # Default for unknown types

    def test_performance_no_json_serialization(self):
        """Verify no JSON serialization is used (performance test)."""
        from autopack.llm_service import LlmService

        # Create a moderately large context
        context = {f"file_{i}": "content " * 100 for i in range(50)}

        # This should complete quickly without json.dumps overhead
        import time

        start = time.time()
        for _ in range(100):
            LlmService._estimate_dict_tokens(context)
        elapsed = time.time() - start

        # Should be fast (< 1 second for 100 iterations)
        assert elapsed < 1.0


class TestCheckPreCallBudgetWithDictEstimation:
    """Tests for _check_pre_call_budget using new dict estimation (IMP-PERF-004)."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            return service

    def test_budget_check_with_large_file_context(self):
        """Budget check handles large file context without JSON serialization."""
        service = self._create_mock_service()

        # Large file context (simulating 5MB+ scenario)
        large_context = {f"file_{i}.py": "x" * 10000 for i in range(50)}

        result = service._check_pre_call_budget(
            phase_spec={"task": "test"},
            file_context=large_context,
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=1000000,
            tokens_used_so_far=0,
        )

        # Should complete without error
        assert "within_budget" in result
        assert "estimated_input_tokens" in result
        assert result["estimated_input_tokens"] > 0

    def test_budget_check_estimates_nested_dict_correctly(self):
        """Budget check estimates nested dict structures correctly."""
        service = self._create_mock_service()

        nested_spec = {
            "task_category": "security",
            "complexity": "high",
            "metadata": {
                "files": ["file1.py", "file2.py"],
                "options": {"strict": True, "verbose": False},
            },
        }

        result = service._check_pre_call_budget(
            phase_spec=nested_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
            retrieved_context=None,
            run_token_budget=100000,
            tokens_used_so_far=0,
        )

        assert result["within_budget"] is True
        assert result["estimated_input_tokens"] > 0


# =============================================================================
# Tests for LlmService._model_to_provider
# =============================================================================


class TestModelToProvider:
    """Tests for _model_to_provider method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            return service

    def test_gemini_model(self):
        """Gemini models map to google provider."""
        service = self._create_mock_service()

        assert service._model_to_provider("gemini-pro") == "google"
        assert service._model_to_provider("gemini-1.5-pro") == "google"

    def test_gpt_model(self):
        """GPT models map to openai provider."""
        service = self._create_mock_service()

        assert service._model_to_provider("gpt-4") == "openai"
        assert service._model_to_provider("gpt-4-turbo") == "openai"

    def test_o1_model(self):
        """O1 models map to openai provider."""
        service = self._create_mock_service()

        assert service._model_to_provider("o1-preview") == "openai"
        assert service._model_to_provider("o1-mini") == "openai"

    def test_claude_model(self):
        """Claude models map to anthropic provider."""
        service = self._create_mock_service()

        assert service._model_to_provider("claude-sonnet-4-5") == "anthropic"
        assert service._model_to_provider("claude-opus-4-5") == "anthropic"

    def test_opus_model(self):
        """Opus models map to anthropic provider."""
        service = self._create_mock_service()

        assert service._model_to_provider("opus-4-5") == "anthropic"

    def test_unknown_model_defaults_to_openai(self):
        """Unknown models default to openai provider."""
        service = self._create_mock_service()

        assert service._model_to_provider("unknown-model") == "openai"


# =============================================================================
# Tests for LlmService dual audit methods
# =============================================================================


class TestDualAuditMethods:
    """Tests for dual audit related methods."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            return service

    def test_should_use_dual_audit_enabled(self):
        """_should_use_dual_audit returns True when configured."""
        service = self._create_mock_service()
        service.model_router.config = {
            "llm_routing_policies": {
                "security": {"dual_audit": True},
            }
        }

        assert service._should_use_dual_audit("security") is True

    def test_should_use_dual_audit_disabled(self):
        """_should_use_dual_audit returns False when not configured."""
        service = self._create_mock_service()
        service.model_router.config = {
            "llm_routing_policies": {
                "general": {"dual_audit": False},
            }
        }

        assert service._should_use_dual_audit("general") is False

    def test_should_use_dual_audit_missing_category(self):
        """_should_use_dual_audit returns False for missing category."""
        service = self._create_mock_service()
        service.model_router.config = {"llm_routing_policies": {}}

        assert service._should_use_dual_audit("unknown") is False

    def test_detect_dual_audit_disagreement_approval_mismatch(self):
        """Detects approval mismatch between auditors."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        primary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="primary",
        )
        secondary = AuditorResult(
            approved=False,
            issues_found=[{"severity": "major"}],
            auditor_messages=[],
            tokens_used=50,
            model_used="secondary",
        )

        result = service._detect_dual_audit_disagreement(primary, secondary)

        assert result["has_disagreement"] is True
        assert result["type"] == "approval_mismatch"

    def test_detect_dual_audit_no_disagreement(self):
        """No disagreement when both agree."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        primary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="primary",
        )
        secondary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="secondary",
        )

        result = service._detect_dual_audit_disagreement(primary, secondary)

        assert result["has_disagreement"] is False


# =============================================================================
# Tests for LlmService.generate_scope_reduction_proposal
# =============================================================================


class TestGenerateScopeReductionProposal:
    """Tests for generate_scope_reduction_proposal method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            return service

    def test_generate_proposal_success(self):
        """Scope reduction proposal generated successfully."""
        service = self._create_mock_service()

        mock_response_data = {
            "run_id": "test-run",
            "phase_id": "phase-1",
            "anchor_id": "anchor-123",
            "diff": {
                "original_deliverables": ["task-1", "task-2"],
                "kept_deliverables": ["task-1"],
                "dropped_deliverables": ["task-2"],
                "rationale": {
                    "success_criteria_preserved": ["Core functionality"],
                    "success_criteria_deferred": ["Nice-to-have"],
                    "constraints_still_met": ["API compatibility"],
                    "reason": "Budget constraint",
                },
            },
            "estimated_budget_savings": 0.5,
        }

        mock_inner_client = MagicMock(spec=["messages"])
        mock_completion = MagicMock()
        mock_completion.content = [MagicMock(text=json.dumps(mock_response_data))]
        mock_completion.usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 200})()
        mock_inner_client.messages.create.return_value = mock_completion

        mock_client = MagicMock()
        mock_client.client = mock_inner_client

        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._model_to_provider = MagicMock(return_value="anthropic")
        service._record_usage = MagicMock()

        result = service.generate_scope_reduction_proposal(
            prompt="Test prompt",
            run_id="test-run",
            phase_id="phase-1",
        )

        assert result is not None
        assert result["run_id"] == "test-run"
        assert result["diff"]["kept_deliverables"] == ["task-1"]

    def test_generate_proposal_failure_raises_exception(self):
        """Scope reduction raises ScopeReductionError on failure."""
        import pytest

        from autopack.exceptions import ScopeReductionError

        service = self._create_mock_service()

        # Use spec to control which attributes exist on the mock client
        mock_inner_client = MagicMock(spec=["messages"])
        mock_inner_client.messages.create.side_effect = Exception("API error")

        mock_client = MagicMock()
        mock_client.client = mock_inner_client

        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )

        with pytest.raises(ScopeReductionError) as excinfo:
            service.generate_scope_reduction_proposal(
                prompt="Test prompt",
                run_id="test-run",
            )

        assert "API error" in str(excinfo.value)

    def test_generate_proposal_invalid_json_raises_exception(self):
        """Scope reduction raises ScopeReductionError on invalid JSON response."""
        import pytest

        from autopack.exceptions import ScopeReductionError

        service = self._create_mock_service()

        mock_inner_client = MagicMock(spec=["messages"])
        mock_completion = MagicMock()
        mock_completion.content = [MagicMock(text="not valid json")]
        mock_completion.usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 50})()
        mock_inner_client.messages.create.return_value = mock_completion

        mock_client = MagicMock()
        mock_client.client = mock_inner_client

        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._model_to_provider = MagicMock(return_value="anthropic")
        service._record_usage = MagicMock()

        with pytest.raises(ScopeReductionError) as excinfo:
            service.generate_scope_reduction_proposal(
                prompt="Test prompt",
            )

        assert "parse" in str(excinfo.value).lower()


# =============================================================================
# Tests for LlmService._resolve_client_and_model
# =============================================================================


class TestResolveClientAndModel:
    """Tests for _resolve_client_and_model method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.glm_builder = None
            service.glm_auditor = None
            service.openai_builder = MagicMock()
            service.openai_auditor = MagicMock()
            service.anthropic_builder = MagicMock()
            service.anthropic_auditor = MagicMock()
            service.gemini_builder = MagicMock()
            service.gemini_auditor = MagicMock()
            return service

    @patch("autopack.llm_service.resolve_client_and_model")
    def test_resolve_builder_client(self, mock_resolve):
        """Resolves builder client correctly."""
        service = self._create_mock_service()
        mock_resolve.return_value = (service.anthropic_builder, "claude-sonnet-4-5")

        client, model = service._resolve_client_and_model("builder", "claude-sonnet-4-5")

        mock_resolve.assert_called_once()
        assert client == service.anthropic_builder
        assert model == "claude-sonnet-4-5"

    @patch("autopack.llm_service.resolve_client_and_model")
    def test_resolve_auditor_client(self, mock_resolve):
        """Resolves auditor client correctly."""
        service = self._create_mock_service()
        mock_resolve.return_value = (service.anthropic_auditor, "claude-sonnet-4-5")

        client, model = service._resolve_client_and_model("auditor", "claude-sonnet-4-5")

        mock_resolve.assert_called_once()
        assert client == service.anthropic_auditor


# =============================================================================
# Tests for LlmService._record_usage and _record_usage_total_only
# =============================================================================


class TestRecordUsage:
    """Tests for _record_usage and _record_usage_total_only methods."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            return service

    def test_record_usage_success(self):
        """Records usage successfully with exact token splits."""
        service = self._create_mock_service()

        service._record_usage(
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="builder",
            prompt_tokens=100,
            completion_tokens=50,
            run_id="test-run",
            phase_id="phase-1",
        )

        service.db.add.assert_called_once()
        service.db.commit.assert_called_once()

    def test_record_usage_handles_exception(self):
        """Records usage handles database exception gracefully."""
        service = self._create_mock_service()
        service.db.add.side_effect = Exception("DB error")

        # Should not raise
        service._record_usage(
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="builder",
            prompt_tokens=100,
            completion_tokens=50,
        )

        service.db.rollback.assert_called_once()

    def test_record_usage_total_only_success(self):
        """Records total-only usage successfully."""
        service = self._create_mock_service()

        service._record_usage_total_only(
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="builder",
            total_tokens=150,
            run_id="test-run",
            phase_id="phase-1",
        )

        service.db.add.assert_called_once()
        service.db.commit.assert_called_once()

    def test_record_usage_total_only_handles_exception(self):
        """Records total-only usage handles database exception gracefully."""
        service = self._create_mock_service()
        service.db.add.side_effect = Exception("DB error")

        # Should not raise
        service._record_usage_total_only(
            provider="anthropic",
            model="claude-sonnet-4-5",
            role="builder",
            total_tokens=150,
        )

        service.db.rollback.assert_called_once()


# =============================================================================
# Tests for LlmService._get_secondary_auditor_model
# =============================================================================


class TestGetSecondaryAuditorModel:
    """Tests for _get_secondary_auditor_model method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            return service

    @patch("autopack.config.settings")
    def test_uses_global_secondary_model(self, mock_settings):
        """Uses global secondary model when configured."""
        service = self._create_mock_service()
        mock_settings.dual_audit_secondary_model = "gpt-4"

        result = service._get_secondary_auditor_model("security")

        assert result == "gpt-4"

    @patch("autopack.config.settings")
    def test_uses_category_specific_model(self, mock_settings):
        """Uses category-specific model when global not set."""
        service = self._create_mock_service()
        mock_settings.dual_audit_secondary_model = None
        service.model_router.config = {
            "llm_routing_policies": {
                "security": {"secondary_auditor": "claude-opus-4-5"},
            }
        }

        result = service._get_secondary_auditor_model("security")

        assert result == "claude-opus-4-5"

    @patch("autopack.config.settings")
    def test_uses_default_model(self, mock_settings):
        """Uses default model when no configuration found."""
        service = self._create_mock_service()
        mock_settings.dual_audit_secondary_model = None
        service.model_router.config = {"llm_routing_policies": {}}

        result = service._get_secondary_auditor_model("general")

        assert result == "claude-sonnet-4-5"


# =============================================================================
# Tests for LlmService._merge_dual_audit_results
# =============================================================================


class TestMergeDualAuditResults:
    """Tests for _merge_dual_audit_results method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            return service

    @patch("autopack.llm_service.DualAuditor")
    def test_merge_results_both_approved(self, mock_dual_auditor):
        """Merge returns approved when no major issues."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        # Mock DualAuditor's merge logic
        mock_instance = MagicMock()
        mock_instance._build_merged_issue_set.return_value = []
        mock_dual_auditor.return_value = mock_instance

        primary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["Primary LGTM"],
            tokens_used=50,
            model_used="claude-sonnet-4-5",
        )
        secondary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["Secondary LGTM"],
            tokens_used=30,
            model_used="gpt-4",
        )

        result = service._merge_dual_audit_results(primary, secondary)

        assert result.approved is True
        assert result.tokens_used == 80
        assert "claude-sonnet-4-5+gpt-4" in result.model_used

    @patch("autopack.llm_service.DualAuditor")
    def test_merge_results_uses_judge_decision(self, mock_dual_auditor):
        """Merge uses judge decision when judge is provided."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        mock_instance = MagicMock()
        mock_instance._build_merged_issue_set.return_value = []
        mock_dual_auditor.return_value = mock_instance

        primary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="model-a",
        )
        secondary = AuditorResult(
            approved=False,
            issues_found=[{"severity": "major"}],
            auditor_messages=[],
            tokens_used=30,
            model_used="model-b",
        )
        judge = AuditorResult(
            approved=False,
            issues_found=[{"severity": "major", "description": "Judge agrees"}],
            auditor_messages=["Judge decision"],
            tokens_used=100,
            model_used="claude-opus-4-5",
        )

        result = service._merge_dual_audit_results(primary, secondary, judge)

        assert result.approved is False
        assert result.tokens_used == 180
        assert "claude-opus-4-5" in result.model_used


# =============================================================================
# Tests for LlmService._log_dual_audit_telemetry
# =============================================================================


class TestLogDualAuditTelemetry:
    """Tests for _log_dual_audit_telemetry method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            return service

    def test_logs_telemetry_to_file(self, tmp_path):
        """Telemetry is logged to JSONL file."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        primary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="primary-model",
        )
        secondary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=30,
            model_used="secondary-model",
        )
        final = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=80,
            model_used="merged",
        )
        disagreement = {"has_disagreement": False, "type": None}

        with patch("autopack.llm_service.Path") as mock_path:
            mock_telemetry_dir = MagicMock()
            mock_path.return_value = mock_telemetry_dir

            service._log_dual_audit_telemetry(
                phase_id="phase-1",
                task_category="security",
                primary_model="primary-model",
                secondary_model="secondary-model",
                primary_result=primary,
                secondary_result=secondary,
                disagreement=disagreement,
                judge_result=None,
                final_result=final,
            )

            # Should have attempted to create directory
            mock_telemetry_dir.mkdir.assert_called()

    def test_handles_file_write_error(self):
        """Telemetry handles file write errors gracefully."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        primary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="primary",
        )
        secondary = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=30,
            model_used="secondary",
        )
        final = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=80,
            model_used="merged",
        )
        disagreement = {"has_disagreement": False, "type": None}

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            # Should not raise - just log warning
            service._log_dual_audit_telemetry(
                phase_id="phase-1",
                task_category="general",
                primary_model="primary",
                secondary_model="secondary",
                primary_result=primary,
                secondary_result=secondary,
                disagreement=disagreement,
                judge_result=None,
                final_result=final,
            )


# =============================================================================
# Tests for LlmService._run_dual_audit
# =============================================================================


class TestRunDualAudit:
    """Tests for _run_dual_audit method."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            return service

    def test_runs_both_auditors(self):
        """Runs both primary and secondary auditors."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        primary_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["Primary OK"],
            tokens_used=50,
            model_used="primary-model",
            prompt_tokens=40,
            completion_tokens=10,
        )
        secondary_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["Secondary OK"],
            tokens_used=30,
            model_used="secondary-model",
            prompt_tokens=25,
            completion_tokens=5,
        )

        mock_primary_client = MagicMock()
        mock_primary_client.review_patch.return_value = primary_result

        mock_secondary_client = MagicMock()
        mock_secondary_client.review_patch.return_value = secondary_result

        def mock_resolve(role, model):
            if model == "primary-model":
                return (mock_primary_client, model)
            return (mock_secondary_client, model)

        service._resolve_client_and_model = MagicMock(side_effect=mock_resolve)
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")

        # IMP-PERF-002: Set early_exit_threshold to 1.0 to force both auditors to run
        primary, secondary = service._run_dual_audit(
            patch_content="diff content",
            phase_spec={"task_category": "security"},
            primary_model="primary-model",
            secondary_model="secondary-model",
            max_tokens=1000,
            project_rules=[],
            run_hints=[],
            run_id="test-run",
            phase_id="phase-1",
            early_exit_threshold=1.0,  # Disable early exit for this test
        )

        assert primary.approved is True
        assert secondary.approved is True
        assert service._record_usage.call_count == 2

    def test_records_usage_for_both_auditors(self):
        """Records usage for both primary and secondary auditors."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="model",
            prompt_tokens=40,
            completion_tokens=10,
        )

        mock_client = MagicMock()
        mock_client.review_patch.return_value = result

        service._resolve_client_and_model = MagicMock(return_value=(mock_client, "model"))
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")

        # IMP-PERF-002: Set early_exit_threshold to 1.0 to force both auditors to run
        service._run_dual_audit(
            patch_content="diff",
            phase_spec={},
            primary_model="model",
            secondary_model="model",
            max_tokens=1000,
            project_rules=None,
            run_hints=None,
            run_id="test-run",
            phase_id="phase-1",
            early_exit_threshold=1.0,  # Disable early exit for this test
        )

        # Should record usage for both auditors
        assert service._record_usage.call_count == 2


# =============================================================================
# Tests for edge cases and additional coverage
# =============================================================================


class TestAdditionalEdgeCases:
    """Tests for edge cases to ensure comprehensive coverage."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()
            service.model_router = MagicMock()
            return service

    def test_execute_builder_phase_with_all_optional_params(self):
        """Builder phase with all optional parameters."""
        from autopack.llm_client import BuilderResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "high",
            {
                "complexity_escalation_reason": "Retry attempt",
                "model_escalation_reason": "High complexity",
                "budget_warning": {"level": "warn", "message": "Budget low"},
            },
        )

        mock_client = MagicMock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff",
            builder_messages=[],
            tokens_used=100,
            model_used="claude-sonnet-4-5",
            prompt_tokens=80,
            completion_tokens=20,
        )
        mock_client.execute_phase.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._record_usage = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")
        service.record_attempt_outcome = MagicMock()

        result = service.execute_builder_phase(
            phase_spec={"task_category": "security", "complexity": "high"},
            file_context={"file.py": "content"},
            max_tokens=2000,
            project_rules=["rule1"],
            run_hints=["hint1"],
            run_id="test-run",
            phase_id="phase-1",
            run_context={"model_overrides": {}},
            attempt_index=2,
            use_full_file_mode=True,
            config=None,
            retrieved_context="memory context",
        )

        assert result.success is True

    def test_execute_builder_phase_failure_records_outcome(self):
        """Builder phase failure records appropriate outcome."""
        from autopack.llm_client import BuilderResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )

        mock_client = MagicMock()
        mock_result = BuilderResult(
            success=False,
            patch_content="",
            builder_messages=[],
            tokens_used=0,
            model_used="claude-sonnet-4-5",
            error="churn_limit_exceeded: Too many retries",
        )
        mock_client.execute_phase.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service.record_attempt_outcome = MagicMock()

        service.execute_builder_phase(
            phase_spec={},
            phase_id="phase-1",
        )

        # Should record builder_churn_limit_exceeded outcome
        service.record_attempt_outcome.assert_called_once()
        call_args = service.record_attempt_outcome.call_args
        assert call_args[1]["outcome"] == "builder_churn_limit_exceeded"

    def test_execute_builder_phase_infra_error(self):
        """Builder phase infra error records appropriate outcome."""
        from autopack.llm_client import BuilderResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )

        mock_client = MagicMock()
        mock_result = BuilderResult(
            success=False,
            patch_content="",
            builder_messages=[],
            tokens_used=0,
            model_used="claude-sonnet-4-5",
            error="connection error: timeout",
        )
        mock_client.execute_phase.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service.record_attempt_outcome = MagicMock()

        service.execute_builder_phase(
            phase_spec={},
            phase_id="phase-1",
        )

        service.record_attempt_outcome.assert_called_once()
        call_args = service.record_attempt_outcome.call_args
        assert call_args[1]["outcome"] == "infra_error"

    def test_execute_builder_phase_records_total_only_usage(self):
        """Builder phase records total-only usage when splits unavailable."""
        from autopack.llm_client import BuilderResult

        service = self._create_mock_service()

        service.model_router.select_model_with_escalation.return_value = (
            "claude-sonnet-4-5",
            "medium",
            {},
        )

        mock_client = MagicMock()
        mock_result = BuilderResult(
            success=True,
            patch_content="diff",
            builder_messages=[],
            tokens_used=100,
            model_used="claude-sonnet-4-5",
            prompt_tokens=None,
            completion_tokens=None,
        )
        mock_client.execute_phase.return_value = mock_result
        service._resolve_client_and_model = MagicMock(
            return_value=(mock_client, "claude-sonnet-4-5")
        )
        service._record_usage = MagicMock()
        service._record_usage_total_only = MagicMock()
        service._model_to_provider = MagicMock(return_value="anthropic")
        service.record_attempt_outcome = MagicMock()

        service.execute_builder_phase(
            phase_spec={},
            run_id="test-run",
            phase_id="phase-1",
        )

        service._record_usage_total_only.assert_called_once()
        service._record_usage.assert_not_called()

    def test_detect_severity_mismatch_disagreement(self):
        """Detects severity mismatch when both reject with different major counts."""
        from autopack.llm_client import AuditorResult
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)

        primary = AuditorResult(
            approved=False,
            issues_found=[
                {"severity": "major", "category": "security"},
                {"severity": "major", "category": "performance"},
                {"severity": "major", "category": "logic"},
            ],
            auditor_messages=[],
            tokens_used=50,
            model_used="primary",
        )
        secondary = AuditorResult(
            approved=False,
            issues_found=[{"severity": "minor", "category": "style"}],
            auditor_messages=[],
            tokens_used=30,
            model_used="secondary",
        )

        result = service._detect_dual_audit_disagreement(primary, secondary)

        assert result["has_disagreement"] is True
        assert result["type"] == "severity_mismatch"

    def test_detect_category_miss_disagreement(self):
        """Detects category miss when one finds major issues the other missed."""
        from autopack.llm_client import AuditorResult
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)

        primary = AuditorResult(
            approved=False,
            issues_found=[{"severity": "minor", "category": "style"}],
            auditor_messages=[],
            tokens_used=50,
            model_used="primary",
        )
        secondary = AuditorResult(
            approved=False,
            issues_found=[{"severity": "major", "category": "security"}],
            auditor_messages=[],
            tokens_used=30,
            model_used="secondary",
        )

        result = service._detect_dual_audit_disagreement(primary, secondary)

        assert result["has_disagreement"] is True
        assert result["type"] == "category_miss"

    def test_record_attempt_outcome_does_not_disable_openai(self):
        """Infra error for OpenAI model does not disable provider."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()

        service._model_to_provider = MagicMock(return_value="openai")

        service.record_attempt_outcome(
            phase_id="phase-1",
            model="gpt-4",
            outcome="infra_error",
            details="Timeout",
        )

        # OpenAI is the fallback, should not be disabled
        service.model_router.disable_provider.assert_not_called()


# =============================================================================
# Tests for IMP-PERF-002: Adaptive Dual Audit with Early Exit
# =============================================================================


class TestCalculateAuditorConfidence:
    """Tests for _calculate_auditor_confidence method (IMP-PERF-002)."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            return service

    def test_confidence_error_state_returns_zero(self):
        """Error state returns 0.0 confidence."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="test-model",
            error="Some error occurred",
        )

        confidence = service._calculate_auditor_confidence(result)
        assert confidence == 0.0

    def test_confidence_approved_no_issues_high(self):
        """Approved with no issues returns very high confidence (0.98)."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["LGTM"],
            tokens_used=50,
            model_used="test-model",
        )

        confidence = service._calculate_auditor_confidence(result)
        assert confidence == 0.98

    def test_confidence_approved_with_minor_issues(self):
        """Approved with minor issues reduces confidence."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        result = AuditorResult(
            approved=True,
            issues_found=[
                {"severity": "minor", "description": "Style issue"},
                {"severity": "low", "description": "Minor concern"},
            ],
            auditor_messages=[],
            tokens_used=50,
            model_used="test-model",
        )

        confidence = service._calculate_auditor_confidence(result)
        # 1.0 - (2 * 0.05) = 0.90
        assert confidence == 0.90

    def test_confidence_approved_with_major_issues(self):
        """Approved with major issues significantly reduces confidence."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        result = AuditorResult(
            approved=True,
            issues_found=[
                {"severity": "major", "description": "Important issue"},
            ],
            auditor_messages=[],
            tokens_used=50,
            model_used="test-model",
        )

        confidence = service._calculate_auditor_confidence(result)
        # 1.0 - (1 * 0.15) = 0.85
        assert confidence == 0.85

    def test_confidence_rejected_base(self):
        """Rejected starts at 0.8 confidence."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        result = AuditorResult(
            approved=False,
            issues_found=[],
            auditor_messages=["Rejected"],
            tokens_used=50,
            model_used="test-model",
        )

        confidence = service._calculate_auditor_confidence(result)
        assert confidence == 0.8

    def test_confidence_mixed_severity_issues(self):
        """Mixed severity issues reduce confidence appropriately."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        result = AuditorResult(
            approved=True,
            issues_found=[
                {"severity": "critical", "description": "Critical issue"},
                {"severity": "high", "description": "High severity"},
                {"severity": "minor", "description": "Minor issue"},
            ],
            auditor_messages=[],
            tokens_used=50,
            model_used="test-model",
        )

        confidence = service._calculate_auditor_confidence(result)
        # 1.0 - (2 * 0.15) - (1 * 0.05) = 0.65
        # Use approximate comparison for floating point
        assert abs(confidence - 0.65) < 0.001

    def test_confidence_clamped_to_valid_range(self):
        """Confidence is clamped between 0.0 and 1.0."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        # Many issues should clamp to 0.0, not go negative
        result = AuditorResult(
            approved=True,
            issues_found=[{"severity": "major", "description": f"Issue {i}"} for i in range(10)],
            auditor_messages=[],
            tokens_used=50,
            model_used="test-model",
        )

        confidence = service._calculate_auditor_confidence(result)
        assert confidence >= 0.0
        assert confidence <= 1.0


class TestAdaptiveDualAuditEarlyExit:
    """Tests for _run_dual_audit early exit behavior (IMP-PERF-002)."""

    def _create_mock_service(self):
        """Create a mock LlmService for testing."""
        from autopack.llm_service import LlmService

        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service._resolve_client_and_model = MagicMock()
            service._record_usage = MagicMock()
            service._record_usage_total_only = MagicMock()
            service._model_to_provider = MagicMock(return_value="anthropic")
            return service

    def test_early_exit_when_primary_high_confidence(self):
        """Early exit when primary approves with high confidence."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        # Mock primary auditor result - approved with no issues (high confidence)
        primary_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["LGTM"],
            tokens_used=50,
            model_used="primary-model",
            prompt_tokens=40,
            completion_tokens=10,
        )

        mock_primary_client = MagicMock()
        mock_primary_client.review_patch.return_value = primary_result

        mock_secondary_client = MagicMock()

        # First call returns primary client, second would return secondary
        service._resolve_client_and_model.side_effect = [
            (mock_primary_client, "primary-model"),
            (mock_secondary_client, "secondary-model"),
        ]

        # Run dual audit
        result_primary, result_secondary = service._run_dual_audit(
            patch_content="test patch",
            phase_spec={"task_category": "general"},
            primary_model="primary-model",
            secondary_model="secondary-model",
            max_tokens=1000,
            project_rules=None,
            run_hints=None,
            run_id="test-run",
            phase_id="phase-1",
        )

        # Should early exit - secondary should be None
        assert result_secondary is None
        assert result_primary.approved is True
        assert result_primary.confidence == 0.98

        # Secondary client should NOT have been called
        mock_secondary_client.review_patch.assert_not_called()

    def test_no_early_exit_when_primary_low_confidence(self):
        """No early exit when primary has low confidence."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        # Mock primary auditor result - approved but with issues (lower confidence)
        primary_result = AuditorResult(
            approved=True,
            issues_found=[
                {"severity": "major", "description": "Issue 1"},
                {"severity": "major", "description": "Issue 2"},
            ],
            auditor_messages=["Approved with concerns"],
            tokens_used=50,
            model_used="primary-model",
            prompt_tokens=40,
            completion_tokens=10,
        )

        secondary_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["LGTM"],
            tokens_used=30,
            model_used="secondary-model",
            prompt_tokens=20,
            completion_tokens=10,
        )

        mock_primary_client = MagicMock()
        mock_primary_client.review_patch.return_value = primary_result

        mock_secondary_client = MagicMock()
        mock_secondary_client.review_patch.return_value = secondary_result

        service._resolve_client_and_model.side_effect = [
            (mock_primary_client, "primary-model"),
            (mock_secondary_client, "secondary-model"),
        ]

        # Run dual audit
        result_primary, result_secondary = service._run_dual_audit(
            patch_content="test patch",
            phase_spec={"task_category": "general"},
            primary_model="primary-model",
            secondary_model="secondary-model",
            max_tokens=1000,
            project_rules=None,
            run_hints=None,
            run_id="test-run",
            phase_id="phase-1",
        )

        # Should NOT early exit - both results should be present
        assert result_secondary is not None
        assert result_primary.approved is True
        # Primary confidence with 2 major issues: 1.0 - (2 * 0.15) = 0.70
        assert result_primary.confidence == 0.70

        # Secondary client should have been called
        mock_secondary_client.review_patch.assert_called_once()

    def test_no_early_exit_when_primary_rejects(self):
        """No early exit when primary rejects (even with high confidence)."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        # Mock primary auditor result - rejected
        primary_result = AuditorResult(
            approved=False,
            issues_found=[{"severity": "critical", "description": "Critical bug"}],
            auditor_messages=["Rejected"],
            tokens_used=50,
            model_used="primary-model",
            prompt_tokens=40,
            completion_tokens=10,
        )

        secondary_result = AuditorResult(
            approved=False,
            issues_found=[],
            auditor_messages=["Also rejected"],
            tokens_used=30,
            model_used="secondary-model",
            prompt_tokens=20,
            completion_tokens=10,
        )

        mock_primary_client = MagicMock()
        mock_primary_client.review_patch.return_value = primary_result

        mock_secondary_client = MagicMock()
        mock_secondary_client.review_patch.return_value = secondary_result

        service._resolve_client_and_model.side_effect = [
            (mock_primary_client, "primary-model"),
            (mock_secondary_client, "secondary-model"),
        ]

        # Run dual audit
        result_primary, result_secondary = service._run_dual_audit(
            patch_content="test patch",
            phase_spec={"task_category": "general"},
            primary_model="primary-model",
            secondary_model="secondary-model",
            max_tokens=1000,
            project_rules=None,
            run_hints=None,
            run_id="test-run",
            phase_id="phase-1",
        )

        # Should NOT early exit when rejected - secondary should be present
        assert result_secondary is not None
        assert result_primary.approved is False

        # Secondary client should have been called
        mock_secondary_client.review_patch.assert_called_once()

    def test_custom_early_exit_threshold(self):
        """Custom early exit threshold is respected."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        # Mock primary result with 1 minor issue (confidence = 0.95)
        primary_result = AuditorResult(
            approved=True,
            issues_found=[{"severity": "minor", "description": "Minor style issue"}],
            auditor_messages=["Mostly good"],
            tokens_used=50,
            model_used="primary-model",
            prompt_tokens=40,
            completion_tokens=10,
        )

        secondary_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["LGTM"],
            tokens_used=30,
            model_used="secondary-model",
            prompt_tokens=20,
            completion_tokens=10,
        )

        mock_primary_client = MagicMock()
        mock_primary_client.review_patch.return_value = primary_result

        mock_secondary_client = MagicMock()
        mock_secondary_client.review_patch.return_value = secondary_result

        service._resolve_client_and_model.side_effect = [
            (mock_primary_client, "primary-model"),
            (mock_secondary_client, "secondary-model"),
        ]

        # With default threshold (0.9), confidence 0.95 should early exit
        result_primary, result_secondary = service._run_dual_audit(
            patch_content="test patch",
            phase_spec={"task_category": "general"},
            primary_model="primary-model",
            secondary_model="secondary-model",
            max_tokens=1000,
            project_rules=None,
            run_hints=None,
            run_id="test-run",
            phase_id="phase-1",
            early_exit_threshold=0.9,
        )

        # Confidence 0.95 > 0.9, should early exit
        assert result_secondary is None
        assert result_primary.confidence == 0.95

    def test_early_exit_records_usage_for_primary_only(self):
        """Early exit records usage only for primary auditor."""
        from autopack.llm_client import AuditorResult

        service = self._create_mock_service()

        primary_result = AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=["LGTM"],
            tokens_used=50,
            model_used="primary-model",
            prompt_tokens=40,
            completion_tokens=10,
        )

        mock_primary_client = MagicMock()
        mock_primary_client.review_patch.return_value = primary_result

        service._resolve_client_and_model.return_value = (
            mock_primary_client,
            "primary-model",
        )

        # Run dual audit (should early exit)
        service._run_dual_audit(
            patch_content="test patch",
            phase_spec={"task_category": "general"},
            primary_model="primary-model",
            secondary_model="secondary-model",
            max_tokens=1000,
            project_rules=None,
            run_hints=None,
            run_id="test-run",
            phase_id="phase-1",
        )

        # Should record usage for primary only
        service._record_usage.assert_called_once()
        call_args = service._record_usage.call_args
        assert call_args.kwargs["role"] == "auditor:primary"
