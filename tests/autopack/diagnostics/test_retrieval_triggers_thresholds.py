"""Tests for IMP-DIAG-003: Deep Retrieval Escalation Thresholds improvements.

Tests verify:
- Lowered thresholds (MIN_ERROR_LENGTH=10, MIN_ROOT_CAUSE_LENGTH=15)
- Immediate escalation patterns trigger on first attempt
- Root cause confidence threshold (< 0.5 triggers escalation)
- Semantic pattern matching for error detection

Per BUILD-043/044/045 patterns: strict isolation, no protected path modifications.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from autopack.diagnostics.retrieval_triggers import RetrievalTrigger


class TestLoweredThresholds:
    """Test IMP-DIAG-003: Lowered threshold values."""

    @pytest.fixture
    def temp_run_dir(self):
        """Create temporary run directory."""
        run_dir = Path(tempfile.mkdtemp())
        yield run_dir
        shutil.rmtree(run_dir, ignore_errors=True)

    @pytest.fixture
    def trigger(self, temp_run_dir):
        """Create RetrievalTrigger instance."""
        return RetrievalTrigger(run_dir=temp_run_dir)

    def test_min_error_length_constant(self, trigger):
        """Test MIN_ERROR_LENGTH is set to 10."""
        assert trigger.MIN_ERROR_LENGTH == 10

    def test_min_root_cause_length_constant(self, trigger):
        """Test MIN_ROOT_CAUSE_LENGTH is set to 15."""
        assert trigger.MIN_ROOT_CAUSE_LENGTH == 15

    def test_error_11_chars_not_insufficient(self, trigger):
        """Test that 11 char error is not considered insufficient."""
        bundle = {
            "error_message": "X" * 11,  # Just above threshold
            "stack_trace": "",
            "recent_changes": [],
            "root_cause": "Specific root cause description here",
        }
        result = trigger._is_bundle_insufficient(bundle)
        assert result is False

    def test_error_10_chars_is_insufficient(self, trigger):
        """Test that 10 char error is considered insufficient."""
        bundle = {
            "error_message": "X" * 10,  # At threshold (not above)
            "stack_trace": "",
            "recent_changes": [],
        }
        result = trigger._is_bundle_insufficient(bundle)
        assert result is True

    def test_error_15_chars_has_actionable_context(self, trigger):
        """Test that 15+ char error has actionable context."""
        bundle = {
            "error_message": "X" * 15,  # At threshold
            "stack_trace": "",
            "root_cause": "Specific cause",
        }
        result = trigger._lacks_actionable_context(bundle)
        assert result is False

    def test_error_14_chars_lacks_actionable_context(self, trigger):
        """Test that 14 char error lacks actionable context."""
        bundle = {
            "error_message": "X" * 14,  # Below threshold
            "stack_trace": "",
            "root_cause": "Specific cause",
        }
        result = trigger._lacks_actionable_context(bundle)
        assert result is True

    def test_root_cause_15_chars_is_clear(self, trigger):
        """Test that 15+ char root cause is considered clear."""
        bundle = {
            "error_message": "Detailed error message here",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "X" * 15,  # At threshold
        }
        result = trigger._has_clear_root_cause(bundle)
        assert result is True

    def test_root_cause_14_chars_is_not_clear(self, trigger):
        """Test that 14 char root cause is not considered clear."""
        bundle = {
            "error_message": "Detailed error message here",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "X" * 14,  # Below threshold
        }
        result = trigger._has_clear_root_cause(bundle)
        assert result is False


class TestImmediateEscalationPatterns:
    """Test IMP-DIAG-003: Immediate escalation for known error patterns."""

    @pytest.fixture
    def temp_run_dir(self):
        """Create temporary run directory."""
        run_dir = Path(tempfile.mkdtemp())
        yield run_dir
        shutil.rmtree(run_dir, ignore_errors=True)

    @pytest.fixture
    def trigger(self, temp_run_dir):
        """Create RetrievalTrigger instance."""
        return RetrievalTrigger(run_dir=temp_run_dir)

    def test_immediate_patterns_defined(self, trigger):
        """Test that IMMEDIATE_ESCALATION_PATTERNS is defined."""
        assert hasattr(trigger, "IMMEDIATE_ESCALATION_PATTERNS")
        assert len(trigger.IMMEDIATE_ESCALATION_PATTERNS) > 0

    def test_escalates_on_traceback_pattern(self, trigger):
        """Test that 'traceback' in error triggers immediate escalation."""
        bundle = {
            "error_message": "Traceback (most recent call last):",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_threw_exception_pattern(self, trigger):
        """Test that 'threw exception' in error triggers immediate escalation."""
        bundle = {
            "error_message": "Method threw exception during processing",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_error_colon_pattern(self, trigger):
        """Test that ' error:' in error triggers immediate escalation."""
        bundle = {
            "error_message": "Build error: missing dependency in module",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_failed_colon_pattern(self, trigger):
        """Test that ' failed:' in error triggers immediate escalation."""
        bundle = {
            "error_message": "Operation failed: missing dependency",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_assertion_error_pattern(self, trigger):
        """Test that 'assertionerror' in error triggers immediate escalation."""
        bundle = {
            "error_message": "AssertionError: test condition failed in test_foo",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_timeout_pattern(self, trigger):
        """Test that 'timeout' in error triggers immediate escalation."""
        bundle = {
            "error_message": "Connection timeout after 30 seconds",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_connection_refused_pattern(self, trigger):
        """Test that 'connection refused' in error triggers immediate escalation."""
        bundle = {
            "error_message": "Socket error: connection refused on port 8080",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_pattern_matching_is_case_insensitive(self, trigger):
        """Test that pattern matching is case insensitive."""
        bundle = {
            "error_message": "TRACEBACK: Error occurred",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_first_attempt(self, trigger):
        """Test that immediate patterns escalate on first attempt."""
        bundle = {
            "error_message": "Traceback in module initialization",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        # First attempt should escalate with pattern match
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True


class TestRootCauseConfidence:
    """Test IMP-DIAG-003: Root cause confidence threshold."""

    @pytest.fixture
    def temp_run_dir(self):
        """Create temporary run directory."""
        run_dir = Path(tempfile.mkdtemp())
        yield run_dir
        shutil.rmtree(run_dir, ignore_errors=True)

    @pytest.fixture
    def trigger(self, temp_run_dir):
        """Create RetrievalTrigger instance."""
        return RetrievalTrigger(run_dir=temp_run_dir)

    def test_escalates_on_low_confidence(self, trigger):
        """Test that low root cause confidence triggers escalation."""
        bundle = {
            "error_message": "Some error occurred in the application",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Specific root cause identified here",
            "root_cause_confidence": 0.3,  # Below 0.5 threshold
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_zero_confidence(self, trigger):
        """Test that zero confidence triggers escalation."""
        bundle = {
            "error_message": "Some error occurred in the application",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Specific root cause identified here",
            "root_cause_confidence": 0.0,
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_escalates_on_confidence_just_below_threshold(self, trigger):
        """Test that confidence just below 0.5 triggers escalation."""
        bundle = {
            "error_message": "Some error occurred in the application",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Specific root cause identified here",
            "root_cause_confidence": 0.49,
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_no_escalation_on_high_confidence(self, trigger):
        """Test that high confidence does not trigger escalation."""
        bundle = {
            "error_message": "Some error occurred in the application",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Specific root cause identified here",
            "root_cause_confidence": 0.8,
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is False

    def test_no_escalation_on_confidence_at_threshold(self, trigger):
        """Test that confidence at 0.5 does not trigger escalation."""
        bundle = {
            "error_message": "Some error occurred in the application",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Specific root cause identified here",
            "root_cause_confidence": 0.5,
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is False

    def test_default_confidence_is_high(self, trigger):
        """Test that missing confidence defaults to high (no escalation)."""
        bundle = {
            "error_message": "Some error occurred in the application",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Specific root cause identified here",
            # No root_cause_confidence key - should default to 1.0
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        # Should not escalate due to confidence alone
        assert result is False


class TestFirstAttemptEscalation:
    """Test IMP-DIAG-003: First attempt escalation capabilities."""

    @pytest.fixture
    def temp_run_dir(self):
        """Create temporary run directory."""
        run_dir = Path(tempfile.mkdtemp())
        yield run_dir
        shutil.rmtree(run_dir, ignore_errors=True)

    @pytest.fixture
    def trigger(self, temp_run_dir):
        """Create RetrievalTrigger instance."""
        return RetrievalTrigger(run_dir=temp_run_dir)

    def test_first_attempt_escalation_via_pattern(self, trigger):
        """Test first attempt can escalate via immediate pattern."""
        bundle = {
            "error_message": "Timeout waiting for response",
            "stack_trace": "",
            "root_cause": "Specific root cause identified here",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_first_attempt_escalation_via_low_confidence(self, trigger):
        """Test first attempt can escalate via low confidence."""
        bundle = {
            "error_message": "Generic application message",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Specific root cause identified here",
            "root_cause_confidence": 0.2,
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_first_attempt_escalation_via_insufficient_bundle(self, trigger):
        """Test first attempt can escalate via insufficient bundle."""
        bundle = {
            "error_message": "",
            "stack_trace": "",
            "recent_changes": [],
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_first_attempt_escalation_via_no_root_cause(self, trigger):
        """Test first attempt can escalate via missing root cause."""
        bundle = {
            "error_message": "Detailed error message with context here",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "",
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True
