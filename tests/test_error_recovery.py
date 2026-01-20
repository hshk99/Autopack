"""Comprehensive tests for error_recovery.py

Tests for error recovery system including:
- Error classification (ErrorSeverity, ErrorCategory)
- Doctor data structures (DoctorRequest, DoctorResponse, DoctorContextSummary)
- Doctor model routing (is_complex_failure, choose_doctor_model, should_escalate_doctor_model)
- Diagnosis cache (IMP-COST-007)
- ErrorRecoverySystem class
- Global functions (get_error_recovery, safe_execute)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from autopack.error_recovery import (
    # Enums
    ErrorSeverity,
    ErrorCategory,
    # Data classes
    ErrorContext,
    DoctorRequest,
    DoctorResponse,
    DoctorContextSummary,
    # Type alias
    is_complex_failure,
    choose_doctor_model,
    should_escalate_doctor_model,
    # Diagnosis cache
    _get_diagnosis_cache_key,
    get_diagnosis_from_cache,
    cache_diagnosis,
    get_diagnosis_cache_stats,
    clear_diagnosis_cache,
    get_diagnosis_with_cache,
    # Error recovery system
    ErrorRecoverySystem,
    get_error_recovery,
    safe_execute,
    # Constants
    DOCTOR_MAX_BUILDER_ATTEMPTS_BEFORE_COMPLEX,
    DOCTOR_CHEAP_MODEL,
    DOCTOR_STRONG_MODEL,
    DOCTOR_HIGH_RISK_CATEGORIES,
)


# =============================================================================
# Tests: Enums
# =============================================================================


class TestErrorSeverity:
    """Test ErrorSeverity enum."""

    def test_enum_values(self):
        """Verify all expected severity levels exist."""
        assert hasattr(ErrorSeverity, "TRANSIENT")
        assert hasattr(ErrorSeverity, "RECOVERABLE")
        assert hasattr(ErrorSeverity, "FATAL")

    def test_enum_values_are_strings(self):
        """Verify enum values are strings."""
        assert ErrorSeverity.TRANSIENT.value == "transient"
        assert ErrorSeverity.RECOVERABLE.value == "recoverable"
        assert ErrorSeverity.FATAL.value == "fatal"


class TestErrorCategory:
    """Test ErrorCategory enum."""

    def test_enum_values(self):
        """Verify all expected categories exist."""
        assert hasattr(ErrorCategory, "ENCODING")
        assert hasattr(ErrorCategory, "NETWORK")
        assert hasattr(ErrorCategory, "FILE_IO")
        assert hasattr(ErrorCategory, "IMPORT")
        assert hasattr(ErrorCategory, "VALIDATION")
        assert hasattr(ErrorCategory, "LOGIC")
        assert hasattr(ErrorCategory, "UNKNOWN")

    def test_enum_values_are_strings(self):
        """Verify enum values are strings."""
        assert ErrorCategory.ENCODING.value == "encoding"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.FILE_IO.value == "file_io"
        assert ErrorCategory.IMPORT.value == "import"
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.LOGIC.value == "logic"
        assert ErrorCategory.UNKNOWN.value == "unknown"


# =============================================================================
# Tests: ErrorContext
# =============================================================================


class TestErrorContext:
    """Test ErrorContext dataclass."""

    def test_create_error_context(self):
        """Test creating an ErrorContext with all fields."""
        error = ValueError("test error")
        ctx = ErrorContext(
            error=error,
            error_type="ValueError",
            error_message="test error",
            traceback_str="Traceback...",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.RECOVERABLE,
            retry_count=0,
            max_retries=3,
            context_data={"key": "value"},
        )

        assert ctx.error == error
        assert ctx.error_type == "ValueError"
        assert ctx.error_message == "test error"
        assert ctx.category == ErrorCategory.VALIDATION
        assert ctx.severity == ErrorSeverity.RECOVERABLE
        assert ctx.retry_count == 0
        assert ctx.max_retries == 3
        assert ctx.context_data == {"key": "value"}

    def test_to_dict(self):
        """Test converting ErrorContext to dictionary."""
        error = ValueError("test")
        ctx = ErrorContext(
            error=error,
            error_type="ValueError",
            error_message="test error",
            traceback_str="traceback",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.RECOVERABLE,
            retry_count=1,
            max_retries=3,
            context_data={"phase": "build"},
        )

        result = ctx.to_dict()

        assert result["error_type"] == "ValueError"
        assert result["error_message"] == "test error"
        assert result["traceback"] == "traceback"
        assert result["category"] == "validation"
        assert result["severity"] == "recoverable"
        assert result["retry_count"] == 1
        assert result["max_retries"] == 3
        assert result["context_data"] == {"phase": "build"}

    def test_to_dict_with_none_context_data(self):
        """Test to_dict handles None context_data."""
        error = ValueError("test")
        ctx = ErrorContext(
            error=error,
            error_type="ValueError",
            error_message="test error",
            traceback_str="traceback",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.RECOVERABLE,
        )

        result = ctx.to_dict()

        assert result["context_data"] == {}


# =============================================================================
# Tests: DoctorRequest
# =============================================================================


class TestDoctorRequest:
    """Test DoctorRequest dataclass."""

    def test_create_doctor_request(self):
        """Test creating a DoctorRequest."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=2,
            health_budget={"http_500": 3, "total_failures": 5},
            last_patch="diff content",
            patch_errors=[{"field": "invalid"}],
            logs_excerpt="Error logs...",
            run_id="run-001",
        )

        assert req.phase_id == "F1.1"
        assert req.error_category == "network"
        assert req.builder_attempts == 2
        assert req.health_budget == {"http_500": 3, "total_failures": 5}
        assert req.last_patch == "diff content"
        assert req.patch_errors == [{"field": "invalid"}]
        assert req.logs_excerpt == "Error logs..."
        assert req.run_id == "run-001"

    def test_to_dict(self):
        """Test converting DoctorRequest to dictionary."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=2,
            health_budget={"http_500": 3, "total_failures": 5},
            last_patch="a" * 3000,  # Large patch
            logs_excerpt="b" * 1500,  # Large log excerpt
        )

        result = req.to_dict()

        assert result["phase_id"] == "F1.1"
        assert result["error_category"] == "network"
        assert result["builder_attempts"] == 2
        assert result["health_budget"] == {"http_500": 3, "total_failures": 5}
        # Verify truncation
        assert len(result["last_patch"]) <= 2000
        assert len(result["logs_excerpt"]) <= 1000

    def test_to_dict_with_none_fields(self):
        """Test to_dict handles None optional fields."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=2,
            health_budget={"total_failures": 0},
        )

        result = req.to_dict()

        assert result["last_patch"] is None
        assert result["logs_excerpt"] == ""


# =============================================================================
# Tests: DoctorResponse
# =============================================================================


class TestDoctorResponse:
    """Test DoctorResponse dataclass."""

    def test_create_basic_response(self):
        """Test creating a basic DoctorResponse."""
        resp = DoctorResponse(
            action="retry_with_fix",
            confidence=0.8,
            rationale="Network timeout, should retry",
        )

        assert resp.action == "retry_with_fix"
        assert resp.confidence == 0.8
        assert resp.rationale == "Network timeout, should retry"
        assert resp.builder_hint is None
        assert resp.suggested_patch is None

    def test_create_response_with_all_fields(self):
        """Test creating DoctorResponse with all fields."""
        resp = DoctorResponse(
            action="execute_fix",
            confidence=0.9,
            rationale="Git conflict detected",
            builder_hint="Resolve git conflicts",
            suggested_patch="diff fix",
            fix_commands=["git reset --hard HEAD"],
            fix_type="git",
            verify_command="git status",
            error_type="infra_error",
            disable_providers=["openai"],
            maintenance_phase="maintenance-001",
        )

        assert resp.action == "execute_fix"
        assert resp.confidence == 0.9
        assert resp.rationale == "Git conflict detected"
        assert resp.builder_hint == "Resolve git conflicts"
        assert resp.fix_commands == ["git reset --hard HEAD"]
        assert resp.fix_type == "git"
        assert resp.verify_command == "git status"
        assert resp.error_type == "infra_error"
        assert resp.disable_providers == ["openai"]
        assert resp.maintenance_phase == "maintenance-001"

    def test_to_dict(self):
        """Test converting DoctorResponse to dictionary."""
        resp = DoctorResponse(
            action="retry_with_fix",
            confidence=0.75,
            rationale="Test rationale",
            builder_hint="fix it",
            suggested_patch="a" * 600,  # Large patch
        )

        result = resp.to_dict()

        assert result["action"] == "retry_with_fix"
        assert result["confidence"] == 0.75
        assert result["rationale"] == "Test rationale"
        assert result["builder_hint"] == "fix it"
        # Verify truncation
        assert len(result["suggested_patch"]) <= 500
        # execute_fix fields not included
        assert "fix_commands" not in result

    def test_to_dict_execute_fix_includes_fields(self):
        """Test to_dict includes execute_fix fields when action is execute_fix."""
        resp = DoctorResponse(
            action="execute_fix",
            confidence=0.9,
            rationale="Fix infrastructure",
            fix_commands=["rm -rf /tmp/file"],
            fix_type="file",
            verify_command="ls /tmp",
        )

        result = resp.to_dict()

        assert result["action"] == "execute_fix"
        assert result["fix_commands"] == ["rm -rf /tmp/file"]
        assert result["fix_type"] == "file"
        assert result["verify_command"] == "ls /tmp"

    def test_from_dict(self):
        """Test creating DoctorResponse from dictionary."""
        data = {
            "action": "replan",
            "confidence": 0.85,
            "rationale": "Complex failure",
            "builder_hint": "try different approach",
            "suggested_patch": "fix",
            "fix_commands": ["cmd1", "cmd2"],
            "fix_type": "python",
            "verify_command": "test",
            "error_type": "patch_apply_error",
            "disable_providers": ["anthropic"],
            "maintenance_phase": "maint-001",
        }

        resp = DoctorResponse.from_dict(data)

        assert resp.action == "replan"
        assert resp.confidence == 0.85
        assert resp.rationale == "Complex failure"
        assert resp.builder_hint == "try different approach"
        assert resp.suggested_patch == "fix"
        assert resp.fix_commands == ["cmd1", "cmd2"]
        assert resp.fix_type == "python"
        assert resp.verify_command == "test"
        assert resp.error_type == "patch_apply_error"
        assert resp.disable_providers == ["anthropic"]
        assert resp.maintenance_phase == "maint-001"

    def test_from_dict_defaults(self):
        """Test from_dict provides sensible defaults."""
        data = {"action": "retry_with_fix"}

        resp = DoctorResponse.from_dict(data)

        assert resp.action == "retry_with_fix"
        assert resp.confidence == 0.5
        assert resp.rationale == "No rationale provided"
        assert resp.builder_hint is None
        assert resp.suggested_patch is None


# =============================================================================
# Tests: DoctorContextSummary
# =============================================================================


class TestDoctorContextSummary:
    """Test DoctorContextSummary dataclass."""

    def test_initial_state(self):
        """Test initial state of DoctorContextSummary."""
        summary = DoctorContextSummary()

        assert summary.distinct_error_categories_for_phase == 1
        assert summary.prior_doctor_action is None
        assert summary.prior_doctor_confidence is None

    def test_record_error_category(self):
        """Test recording error categories."""
        summary = DoctorContextSummary()

        summary.record_error_category("network")
        assert summary.distinct_error_categories_for_phase == 1

        summary.record_error_category("encoding")
        assert summary.distinct_error_categories_for_phase == 2

        summary.record_error_category("network")  # Duplicate
        assert summary.distinct_error_categories_for_phase == 2

    def test_record_error_category_normalization(self):
        """Test error category normalization."""
        summary = DoctorContextSummary()

        summary.record_error_category("  Network  ")
        assert summary.distinct_error_categories_for_phase == 1

        summary.record_error_category("NETWORK")
        assert summary.distinct_error_categories_for_phase == 1  # Same as above

        summary.record_error_category("Encoding")
        assert summary.distinct_error_categories_for_phase == 2

    def test_record_error_category_empty(self):
        """Test recording empty/None categories doesn't increment count."""
        summary = DoctorContextSummary()

        summary.record_error_category("")
        # Empty categories don't count - stays at default 1
        assert summary.distinct_error_categories_for_phase == 1

        summary.record_error_category(None)
        # None categories don't count - still at 1
        assert summary.distinct_error_categories_for_phase == 1

        summary.record_error_category("network")
        # Only valid category counts, but max(1, 1) = 1
        assert summary.distinct_error_categories_for_phase == 1

    def test_record_doctor_response(self):
        """Test recording Doctor response."""
        summary = DoctorContextSummary()
        resp = DoctorResponse(action="replan", confidence=0.9, rationale="test")

        summary.record_doctor_response(resp)

        assert summary.prior_doctor_action == "replan"
        assert summary.prior_doctor_confidence == 0.9

    def test_record_doctor_response_none(self):
        """Test recording None response doesn't crash."""
        summary = DoctorContextSummary()

        summary.record_doctor_response(None)

        assert summary.prior_doctor_action is None
        assert summary.prior_doctor_confidence is None

    def test_record_doctor_response_escalated_flag(self):
        """Test escalated flag in record_doctor_response."""
        summary = DoctorContextSummary()
        resp = DoctorResponse(action="replan", confidence=0.9, rationale="test")

        # The escalated parameter exists but is currently unused
        summary.record_doctor_response(resp, escalated=True)

        assert summary.prior_doctor_action == "replan"
        assert summary.prior_doctor_confidence == 0.9


# =============================================================================
# Tests: is_complex_failure
# =============================================================================


class TestIsComplexFailure:
    """Test is_complex_failure function."""

    def test_simple_failure_not_complex(self):
        """Test simple failure is not complex."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[],
        )
        ctx = DoctorContextSummary()

        is_complex = is_complex_failure(req, ctx)

        assert is_complex is False

    def test_multiple_error_types_complex(self):
        """Test multiple error types makes failure complex."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[],
        )
        ctx = DoctorContextSummary()
        ctx.record_error_category("network")
        ctx.record_error_category("encoding")

        is_complex = is_complex_failure(req, ctx)

        assert is_complex is True

    def test_structural_patch_issue_complex(self):
        """Test structural patch issues make failure complex."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[{"error": "field1"}, {"error": "field2"}],
        )
        ctx = DoctorContextSummary()

        is_complex = is_complex_failure(req, ctx)

        assert is_complex is True

    def test_many_attempts_complex(self):
        """Test many builder attempts make failure complex."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=DOCTOR_MAX_BUILDER_ATTEMPTS_BEFORE_COMPLEX,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[],
        )
        ctx = DoctorContextSummary()

        is_complex = is_complex_failure(req, ctx)

        assert is_complex is True

    def test_near_budget_limit_complex(self):
        """Test being near budget limit makes failure complex."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={
                "total_failures": 20,
                "total_cap": 25,
            },  # 20/25 = 0.8
            patch_errors=[],
        )
        ctx = DoctorContextSummary()

        is_complex = is_complex_failure(req, ctx)

        assert is_complex is True

    def test_high_risk_category_complex(self):
        """Test high-risk error category makes failure complex."""
        # Assuming "import" is in DOCTOR_HIGH_RISK_CATEGORIES
        if "import" in DOCTOR_HIGH_RISK_CATEGORIES:
            req = DoctorRequest(
                phase_id="F1.1",
                error_category="import",
                builder_attempts=1,
                health_budget={"total_failures": 5, "total_cap": 25},
                patch_errors=[],
            )
            ctx = DoctorContextSummary()

            is_complex = is_complex_failure(req, ctx)

            assert is_complex is True

    def test_prior_escalated_complex(self):
        """Test prior escalation makes failure complex."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[],
        )
        ctx = DoctorContextSummary()
        resp = DoctorResponse(action="replan", confidence=0.9, rationale="test")
        ctx.record_doctor_response(resp)

        is_complex = is_complex_failure(req, ctx)

        assert is_complex is True

    def test_none_context_summary(self):
        """Test None context summary is handled gracefully."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[],
        )

        is_complex = is_complex_failure(req, None)

        # Should work with default summary
        assert isinstance(is_complex, bool)


# =============================================================================
# Tests: choose_doctor_model
# =============================================================================


class TestChooseDoctorModel:
    """Test choose_doctor_model function."""

    def test_health_budget_override_uses_strong(self):
        """Test health budget override forces strong model."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={
                "total_failures": 20,
                "total_cap": 25,
            },  # Near limit
            patch_errors=[],
        )

        model, is_complex = choose_doctor_model(req)

        assert model == DOCTOR_STRONG_MODEL
        assert is_complex is True

    def test_complex_failure_uses_strong(self):
        """Test complex failure uses strong model."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=5,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[],
        )

        model, is_complex = choose_doctor_model(req)

        assert model == DOCTOR_STRONG_MODEL
        assert is_complex is True

    def test_routine_failure_uses_cheap(self):
        """Test routine failure uses cheap model."""
        req = DoctorRequest(
            phase_id="F1.1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 5, "total_cap": 25},
            patch_errors=[],
        )

        model, is_complex = choose_doctor_model(req)

        assert model == DOCTOR_CHEAP_MODEL
        assert is_complex is False


# =============================================================================
# Tests: should_escalate_doctor_model
# =============================================================================


class TestShouldEscalateDoctorModel:
    """Test should_escalate_doctor_model function."""

    def test_strong_model_no_escalate(self):
        """Test no escalation when already using strong model."""
        resp = DoctorResponse(action="retry_with_fix", confidence=0.6, rationale="test")

        should_escalate = should_escalate_doctor_model(resp, DOCTOR_STRONG_MODEL, 2)

        assert should_escalate is False

    def test_high_confidence_no_escalate(self):
        """Test no escalation when confidence is high."""
        resp = DoctorResponse(action="retry_with_fix", confidence=0.9, rationale="test")

        should_escalate = should_escalate_doctor_model(resp, DOCTOR_CHEAP_MODEL, 2)

        assert should_escalate is False

    def test_low_confidence_escalates(self):
        """Test escalation when confidence is low and attempts sufficient."""
        resp = DoctorResponse(action="retry_with_fix", confidence=0.5, rationale="test")

        should_escalate = should_escalate_doctor_model(resp, DOCTOR_CHEAP_MODEL, 2)

        assert should_escalate is True

    def test_early_attempt_no_escalate(self):
        """Test no escalation on early attempts."""
        resp = DoctorResponse(action="retry_with_fix", confidence=0.5, rationale="test")

        should_escalate = should_escalate_doctor_model(resp, DOCTOR_CHEAP_MODEL, 1)

        assert should_escalate is False


# =============================================================================
# Tests: Diagnosis Cache
# =============================================================================


class TestDiagnosisCacheKey:
    """Test _get_diagnosis_cache_key function."""

    def test_cache_key_with_phase(self):
        """Test cache key includes phase."""
        key = _get_diagnosis_cache_key("network", "connection timeout", "F1.1")

        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length

    def test_cache_key_without_phase(self):
        """Test cache key without phase."""
        key = _get_diagnosis_cache_key("network", "connection timeout")

        assert isinstance(key, str)
        assert len(key) == 32

    def test_cache_key_truncates_message(self):
        """Test cache key truncates long error messages."""
        long_message = "x" * 500
        key1 = _get_diagnosis_cache_key("network", long_message, "F1.1")
        key2 = _get_diagnosis_cache_key("network", long_message[:200], "F1.1")

        assert key1 == key2

    def test_cache_key_consistency(self):
        """Test cache key is deterministic."""
        key1 = _get_diagnosis_cache_key("network", "timeout", "F1.1")
        key2 = _get_diagnosis_cache_key("network", "timeout", "F1.1")

        assert key1 == key2

    def test_cache_key_uniqueness(self):
        """Test different inputs produce different keys."""
        key1 = _get_diagnosis_cache_key("network", "timeout", "F1.1")
        key2 = _get_diagnosis_cache_key("encoding", "timeout", "F1.1")
        key3 = _get_diagnosis_cache_key("network", "different", "F1.1")
        key4 = _get_diagnosis_cache_key("network", "timeout", "F2.1")

        assert key1 != key2
        assert key1 != key3
        assert key1 != key4


class TestDiagnosisCache:
    """Test diagnosis cache functions."""

    def test_cache_miss(self):
        """Test cache miss returns None."""
        result = get_diagnosis_from_cache("network", "timeout", "F1.1")

        assert result is None

    def test_cache_hit(self):
        """Test cache hit returns cached diagnosis."""
        diagnosis = DoctorResponse(action="retry_with_fix", confidence=0.8, rationale="test")
        cache_diagnosis("network", "timeout", diagnosis, "F1.1")

        result = get_diagnosis_from_cache("network", "timeout", "F1.1")

        assert result is not None
        assert result.action == "retry_with_fix"
        assert result.confidence == 0.8

    def test_cache_miss_different_key(self):
        """Test cache miss for different key."""
        diagnosis = DoctorResponse(action="retry_with_fix", confidence=0.8, rationale="test")
        cache_diagnosis("network", "timeout", diagnosis, "F1.1")

        result = get_diagnosis_from_cache("encoding", "timeout", "F1.1")

        assert result is None

    def test_cache_stats(self):
        """Test cache statistics."""
        clear_diagnosis_cache()

        diagnosis = DoctorResponse(action="retry_with_fix", confidence=0.8, rationale="test")

        # Miss
        get_diagnosis_from_cache("network", "timeout", "F1.1")

        # Cache
        cache_diagnosis("network", "timeout", diagnosis, "F1.1")

        # Hit
        get_diagnosis_from_cache("network", "timeout", "F1.1")

        stats = get_diagnosis_cache_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == "50.00%"

    def test_cache_stats_empty(self):
        """Test cache stats when empty."""
        clear_diagnosis_cache()
        stats = get_diagnosis_cache_stats()

        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["hit_rate"] == "0.00%"

    def test_clear_cache(self):
        """Test clearing cache."""
        diagnosis = DoctorResponse(action="retry_with_fix", confidence=0.8, rationale="test")
        cache_diagnosis("network", "timeout", diagnosis, "F1.1")
        cache_diagnosis("encoding", "error", diagnosis, "F2.1")

        assert get_diagnosis_cache_stats()["size"] == 2

        clear_diagnosis_cache()

        assert get_diagnosis_cache_stats()["size"] == 0
        assert get_diagnosis_from_cache("network", "timeout", "F1.1") is None

    def test_get_diagnosis_with_cache_miss(self):
        """Test get_diagnosis_with_cache calls doctor function on miss."""
        called = []

        def mock_doctor():
            called.append(True)
            return DoctorResponse(action="retry_with_fix", confidence=0.9, rationale="test")

        result = get_diagnosis_with_cache("network", "timeout", "F1.1", mock_doctor)

        assert len(called) == 1
        assert result.action == "retry_with_fix"

    def test_get_diagnosis_with_cache_hit(self):
        """Test get_diagnosis_with_cache uses cache on hit."""
        cached = DoctorResponse(action="skip_phase", confidence=0.95, rationale="cached")
        cache_diagnosis("network", "timeout", cached, "F1.1")

        called = []

        def mock_doctor():
            called.append(True)
            return DoctorResponse(action="retry_with_fix", confidence=0.9, rationale="test")

        result = get_diagnosis_with_cache("network", "timeout", "F1.1", mock_doctor)

        assert len(called) == 0  # Should not be called
        assert result.action == "skip_phase"


# =============================================================================
# Tests: ErrorRecoverySystem
# =============================================================================


class TestErrorRecoverySystem:
    """Test ErrorRecoverySystem class."""

    def test_initialization(self):
        """Test ErrorRecoverySystem initialization."""
        recovery = ErrorRecoverySystem()

        assert recovery.error_history == []
        assert recovery.encoding_fixed is False
        assert recovery._error_counts_by_category == {}
        assert recovery._error_counts_by_signature == {}
        assert recovery._escalated_errors == set()

    def test_classify_error_network(self):
        """Test classifying network error."""
        recovery = ErrorRecoverySystem()
        error = ConnectionError("Connection refused")

        ctx = recovery.classify_error(error, {"phase_id": "F1.1"})

        assert ctx.error_type == "ConnectionError"
        assert ctx.category == ErrorCategory.NETWORK
        assert ctx.severity == ErrorSeverity.TRANSIENT
        assert len(recovery.error_history) == 1

    def test_classify_error_encoding(self):
        """Test classifying encoding error."""
        recovery = ErrorRecoverySystem()
        error = UnicodeEncodeError("utf-8", "test", 0, 1, "reason")

        ctx = recovery.classify_error(error)

        assert ctx.category == ErrorCategory.ENCODING
        assert ctx.severity == ErrorSeverity.RECOVERABLE

    def test_classify_error_import(self):
        """Test classifying import error."""
        recovery = ErrorRecoverySystem()
        error = ImportError("No module named 'missing'")

        ctx = recovery.classify_error(error)

        assert ctx.category == ErrorCategory.IMPORT
        assert ctx.severity == ErrorSeverity.FATAL

    def test_classify_error_file_io(self):
        """Test classifying file I/O error."""
        recovery = ErrorRecoverySystem()
        error = FileNotFoundError("File not found")

        ctx = recovery.classify_error(error)

        assert ctx.category == ErrorCategory.FILE_IO
        assert ctx.severity == ErrorSeverity.RECOVERABLE

    def test_classify_error_unknown(self):
        """Test classifying unknown error."""
        recovery = ErrorRecoverySystem()
        error = ValueError("Unknown error")

        ctx = recovery.classify_error(error)

        assert ctx.category == ErrorCategory.UNKNOWN
        assert ctx.severity == ErrorSeverity.RECOVERABLE

    def test_attempt_self_healing_encoding_success(self):
        """Test self-healing for encoding error succeeds."""
        recovery = ErrorRecoverySystem()
        error = UnicodeEncodeError("utf-8", "test", 0, 1, "reason")
        ctx = recovery.classify_error(error)

        with patch("sys.stdout.reconfigure"):
            with patch("sys.stderr.reconfigure"):
                success = recovery.attempt_self_healing(ctx)

        assert success is True
        assert recovery.encoding_fixed is True

    def test_attempt_self_healing_network_no_fix(self):
        """Test self-healing for network error returns False."""
        recovery = ErrorRecoverySystem()
        error = ConnectionError("timeout")
        ctx = recovery.classify_error(error)
        ctx.retry_count = 5  # Max retries
        ctx.max_retries = 3

        with patch("time.sleep"):  # Avoid actual sleep
            success = recovery.attempt_self_healing(ctx)

        assert success is False

    def test_attempt_self_healing_unknown_category(self):
        """Test self-healing for unknown category returns False."""
        recovery = ErrorRecoverySystem()
        error = ValueError("test")
        ctx = recovery.classify_error(error)

        success = recovery.attempt_self_healing(ctx)

        assert success is False

    def test_execute_with_retry_success(self):
        """Test execute_with_retry succeeds on first try."""
        recovery = ErrorRecoverySystem()
        call_count = []

        def test_func():
            call_count.append(1)
            return "success"

        result = recovery.execute_with_retry(test_func, operation_name="test op")

        assert result == "success"
        assert len(call_count) == 1

    def test_execute_with_retry_transient_error_retry(self):
        """Test execute_with_retry retries transient errors."""
        recovery = ErrorRecoverySystem()
        call_count = []

        def test_func():
            call_count.append(1)
            if len(call_count) < 3:
                raise ConnectionError("timeout")
            return "success"

        with patch("time.sleep"):  # Avoid actual sleep
            result = recovery.execute_with_retry(test_func, max_retries=3, operation_name="test op")

        assert result == "success"
        assert len(call_count) == 3

    def test_execute_with_retry_fatal_error_no_retry(self):
        """Test execute_with_retry doesn't retry fatal errors."""
        recovery = ErrorRecoverySystem()
        call_count = []

        def test_func():
            call_count.append(1)
            raise ImportError("module not found")

        with pytest.raises(ImportError):
            recovery.execute_with_retry(test_func, max_retries=3, operation_name="test op")

        assert len(call_count) == 1  # No retries for fatal

    def test_execute_with_retry_max_retries_exceeded(self):
        """Test execute_with_retry raises after max retries."""
        recovery = ErrorRecoverySystem()
        call_count = []

        def test_func():
            call_count.append(1)
            raise ConnectionError("timeout")

        with patch("time.sleep"):
            with pytest.raises(ConnectionError):
                recovery.execute_with_retry(test_func, max_retries=2, operation_name="test op")

        assert len(call_count) == 3  # Initial + 2 retries

    def test_escalation_callback(self):
        """Test escalation callback is invoked."""
        recovery = ErrorRecoverySystem()
        escalation_called = []

        def callback(category, reason):
            escalation_called.append((category, reason))

        recovery.set_escalation_callback(callback)

        # Trigger same error 3 times
        error = ValueError("test error")
        for _ in range(3):
            recovery.classify_error(error)

        assert len(escalation_called) == 1
        assert escalation_called[0][0] == "unknown"
        assert "occurred 3 times" in escalation_called[0][1]

    def test_escalation_status(self):
        """Test getting escalation status."""
        recovery = ErrorRecoverySystem()

        # Trigger some errors
        error = ConnectionError("timeout")
        for _ in range(2):
            recovery.classify_error(error)

        status = recovery.get_escalation_status()

        assert "error_counts_by_category" in status
        assert "error_counts_by_signature" in status
        assert "escalated_errors" in status
        assert "threshold" in status
        assert "fatal_threshold" in status

    def test_reset_counts(self):
        """Test resetting error counts."""
        recovery = ErrorRecoverySystem()

        # Add some errors
        recovery.classify_error(ValueError("test"))
        recovery.classify_error(ConnectionError("timeout"))

        assert len(recovery._error_counts_by_category) > 0

        recovery.reset_counts()

        assert recovery._error_counts_by_category == {}
        assert recovery._error_counts_by_signature == {}
        assert recovery._escalated_errors == set()

    def test_get_error_summary(self):
        """Test getting error summary."""
        recovery = ErrorRecoverySystem()

        # Add some errors
        recovery.classify_error(ConnectionError("timeout"))
        recovery.classify_error(ValueError("test"))
        recovery.classify_error(ConnectionError("timeout"))

        summary = recovery.get_error_summary()

        assert summary["total_errors"] == 3
        assert "by_category" in summary
        assert "by_severity" in summary
        assert "doctor_diagnosis_cache" in summary
        assert "recent_errors" in summary
        assert len(summary["recent_errors"]) == 3

    def test_sync_wait(self):
        """Test sync_wait method."""
        recovery = ErrorRecoverySystem()

        start = time.time()
        recovery.sync_wait(0.1)
        elapsed = time.time() - start

        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_async_wait(self):
        """Test async_wait method."""
        recovery = ErrorRecoverySystem()

        start = time.time()
        await recovery.async_wait(0.1)
        elapsed = time.time() - start

        assert elapsed >= 0.1

    def test_wait_sync_context(self):
        """Test wait in sync context doesn't warn."""
        recovery = ErrorRecoverySystem()

        with patch("autopack.error_recovery.logger") as mock_logger:
            recovery.wait(0.1)

            # Should not call warning
            mock_logger.warning.assert_not_called()

    def test_wait_async_context_warns(self):
        """Test wait in async context warns."""
        recovery = ErrorRecoverySystem()

        async def run_in_async():
            with patch("autopack.error_recovery.logger") as mock_logger:
                with patch("time.sleep"):
                    recovery.wait(0.1)

                # Should warn about blocking
                mock_logger.warning.assert_called_once()

        asyncio.run(run_in_async())


# =============================================================================
# Tests: Global Functions
# =============================================================================


class TestGlobalFunctions:
    """Test global error recovery functions."""

    def test_get_error_recovery_singleton(self):
        """Test get_error_recovery returns singleton instance."""
        recovery1 = get_error_recovery()
        recovery2 = get_error_recovery()

        assert recovery1 is recovery2

    def test_safe_execute_success(self):
        """Test safe_execute returns result on success."""

        def test_func():
            return "success"

        result = safe_execute(test_func, operation_name="test op")

        assert result == "success"

    def test_safe_execute_with_default(self):
        """Test safe_execute returns default on failure."""

        def test_func():
            raise ValueError("error")

        result = safe_execute(test_func, operation_name="test op", default_return="default")

        assert result == "default"

    def test_safe_execute_no_default(self):
        """Test safe_execute returns None on failure without default."""

        def test_func():
            raise ValueError("error")

        result = safe_execute(test_func, operation_name="test op", log_errors=False)

        assert result is None

    def test_safe_execute_retries(self):
        """Test safe_execute uses retry logic."""
        call_count = []

        def test_func():
            call_count.append(1)
            if len(call_count) < 2:
                raise ConnectionError("timeout")
            return "success"

        with patch("time.sleep"):
            result = safe_execute(test_func, operation_name="test op")

        assert result == "success"
        assert len(call_count) == 2
