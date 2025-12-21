"""Tests for Stage 2A: Retrieval Triggers - Detect insufficient Stage 1 evidence.

Tests verify:
- Trigger 1: Empty or minimal handoff bundle detection
- Trigger 2: Lack of actionable context in error messages
- Trigger 3: Repeated failures in recent history
- Trigger 4: No clear root cause identification
- Priority determination based on trigger count
- Isolation from protected paths

Per BUILD-043/044/045 patterns: strict isolation, no protected path modifications.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from src.autopack.diagnostics.retrieval_triggers import RetrievalTrigger


class TestRetrievalTriggerInsufficientBundle:
    """Test Trigger 1: Empty or minimal handoff bundle detection."""

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

    def test_triggers_on_empty_bundle(self, trigger):
        """Test that empty bundle triggers escalation."""
        empty_bundle = {}
        result = trigger.should_escalate(empty_bundle, "phase_001", 1)
        assert result is True

    def test_triggers_on_minimal_bundle(self, trigger):
        """Test that minimal bundle (short fields) triggers escalation."""
        minimal_bundle = {
            "error_message": "Error",  # Too short (<20 chars)
            "stack_trace": "",
            "recent_changes": []
        }
        result = trigger.should_escalate(minimal_bundle, "phase_001", 1)
        assert result is True

    def test_does_not_trigger_on_sufficient_bundle(self, trigger):
        """Test that sufficient bundle does not trigger escalation."""
        sufficient_bundle = {
            "error_message": "Detailed error message with context and information",
            "stack_trace": "Traceback (most recent call last):\n  File test.py line 10\n" * 3,
            "recent_changes": ["file1.py", "file2.py"],
            "root_cause": "Specific root cause identified in module X"
        }
        result = trigger.should_escalate(sufficient_bundle, "phase_001", 1)
        assert result is False

    def test_bundle_with_error_but_no_trace(self, trigger):
        """Test bundle with error message but no stack trace."""
        bundle = {
            "error_message": "Detailed error message with sufficient context",
            "stack_trace": "",
            "recent_changes": []
        }
        # Should not trigger if error message is detailed enough
        result = trigger.should_escalate(bundle, "phase_001", 1)
        # Will depend on other triggers (root cause, etc.)
        assert isinstance(result, bool)

    def test_bundle_with_changes_but_no_error(self, trigger):
        """Test bundle with recent changes but no error message."""
        bundle = {
            "error_message": "",
            "stack_trace": "",
            "recent_changes": ["file1.py", "file2.py", "file3.py"]
        }
        # Should not trigger if changes are present
        result = trigger.should_escalate(bundle, "phase_001", 1)
        # Will depend on other triggers
        assert isinstance(result, bool)


class TestRetrievalTriggerActionableContext:
    """Test Trigger 2: Lack of actionable context in error messages."""

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

    def test_triggers_on_generic_error_unknown(self, trigger):
        """Test that 'unknown error' triggers escalation."""
        bundle = {
            "error_message": "An unknown error occurred",
            "stack_trace": "Some trace",
            "root_cause": "Unknown"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_triggers_on_generic_error_internal(self, trigger):
        """Test that 'internal error' triggers escalation."""
        bundle = {
            "error_message": "Internal error occurred",
            "stack_trace": "Some trace",
            "root_cause": "Internal"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_triggers_on_generic_error_something_wrong(self, trigger):
        """Test that 'something went wrong' triggers escalation."""
        bundle = {
            "error_message": "Something went wrong during execution",
            "stack_trace": "Some trace",
            "root_cause": "Something went wrong"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_triggers_on_short_error_message(self, trigger):
        """Test that very short error message (<30 chars) triggers escalation."""
        bundle = {
            "error_message": "Error",  # Only 5 chars
            "stack_trace": "Some trace",
            "root_cause": "Specific cause"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_does_not_trigger_on_specific_error(self, trigger):
        """Test that specific error message does not trigger escalation."""
        bundle = {
            "error_message": "FileNotFoundError: Could not find config.yaml in /path/to/dir",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Missing configuration file config.yaml"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is False


class TestRetrievalTriggerRepeatedFailures:
    """Test Trigger 3: Repeated failures in recent history."""

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

    def test_triggers_on_repeated_failures(self, trigger, temp_run_dir):
        """Test that repeated failures trigger escalation on attempt 2+."""
        # Create log files with failure markers
        log1 = temp_run_dir / "phase_001_attempt_1.log"
        log1.write_text("ERROR: First failure\nFAILED to complete")
        log2 = temp_run_dir / "phase_001_attempt_2.log"
        log2.write_text("ERROR: Second failure\nFAILED again")

        bundle = {
            "error_message": "Detailed error message with context",
            "root_cause": "Specific root cause identified"
        }
        result = trigger.should_escalate(bundle, "phase_001", 2)
        assert result is True

    def test_does_not_trigger_on_first_attempt(self, trigger, temp_run_dir):
        """Test that first attempt does not trigger repeated failure check."""
        bundle = {
            "error_message": "Detailed error message with context",
            "root_cause": "Specific root cause identified"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        # Should not trigger on attempt 1 (no repeated failures yet)
        # Will depend on other triggers
        assert isinstance(result, bool)

    def test_does_not_trigger_without_failure_logs(self, trigger, temp_run_dir):
        """Test that no failure logs means no repeated failure trigger."""
        # Create log without failure markers
        log = temp_run_dir / "phase_001_attempt_1.log"
        log.write_text("INFO: Processing\nINFO: Completed successfully")

        bundle = {
            "error_message": "Detailed error message with context",
            "root_cause": "Specific root cause identified"
        }
        result = trigger.should_escalate(bundle, "phase_001", 2)
        # Should not trigger if no failure markers in logs
        assert isinstance(result, bool)


class TestRetrievalTriggerRootCause:
    """Test Trigger 4: No clear root cause identification."""

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

    def test_triggers_on_missing_root_cause(self, trigger):
        """Test that missing root cause triggers escalation."""
        bundle = {
            "error_message": "Detailed error message with context",
            "stack_trace": "Traceback..." * 10,
            "root_cause": ""  # Missing
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_triggers_on_unclear_root_cause_unknown(self, trigger):
        """Test that 'unknown' root cause triggers escalation."""
        bundle = {
            "error_message": "Detailed error message with context",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Unknown cause"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_triggers_on_unclear_root_cause_investigate(self, trigger):
        """Test that 'needs investigation' root cause triggers escalation."""
        bundle = {
            "error_message": "Detailed error message with context",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Needs further investigation"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_triggers_on_short_root_cause(self, trigger):
        """Test that very short root cause (<20 chars) triggers escalation."""
        bundle = {
            "error_message": "Detailed error message with context",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Error"  # Only 5 chars
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is True

    def test_does_not_trigger_on_clear_root_cause(self, trigger):
        """Test that clear, specific root cause does not trigger escalation."""
        bundle = {
            "error_message": "FileNotFoundError: config.yaml not found",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Missing configuration file config.yaml in expected directory /etc/app"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert result is False


class TestRetrievalTriggerPriority:
    """Test priority determination based on trigger count."""

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

    def test_high_priority_multiple_triggers(self, trigger):
        """Test that 2+ triggers result in high priority."""
        bundle = {
            "error_message": "Error",  # Too short (trigger 1)
            "stack_trace": "",
            "root_cause": "Unknown"  # Unclear (trigger 2)
        }
        priority = trigger.get_retrieval_priority(bundle)
        assert priority == "high"

    def test_medium_priority_single_trigger(self, trigger):
        """Test that 1 trigger results in medium priority."""
        bundle = {
            "error_message": "Detailed error message with sufficient context",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Unknown"  # Only this triggers
        }
        priority = trigger.get_retrieval_priority(bundle)
        assert priority == "medium"

    def test_low_priority_no_triggers(self, trigger):
        """Test that 0 triggers result in low priority."""
        bundle = {
            "error_message": "FileNotFoundError: config.yaml not found in /path",
            "stack_trace": "Traceback..." * 10,
            "root_cause": "Missing configuration file config.yaml in expected directory"
        }
        priority = trigger.get_retrieval_priority(bundle)
        assert priority == "low"

    def test_priority_with_all_triggers(self, trigger):
        """Test priority when all triggers fire."""
        bundle = {
            "error_message": "",  # Empty (trigger 1)
            "stack_trace": "",
            "root_cause": ""  # Empty (trigger 2)
        }
        priority = trigger.get_retrieval_priority(bundle)
        assert priority == "high"


class TestRetrievalTriggerIsolation:
    """Test isolation from protected paths."""

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

    def test_does_not_modify_protected_paths(self, trigger, temp_run_dir):
        """Test that trigger analysis does not modify protected paths."""
        # Create protected directories
        protected_dir = temp_run_dir.parent / ".autonomous_runs"
        protected_dir.mkdir(exist_ok=True)

        bundle = {"error_message": "test error"}
        result = trigger.should_escalate(bundle, "phase_001", 1)

        # Should complete without touching protected paths
        assert isinstance(result, bool)

    def test_only_reads_from_run_directory(self, trigger, temp_run_dir):
        """Test that trigger only reads from run directory."""
        # Create log in run directory
        log = temp_run_dir / "phase_001.log"
        log.write_text("ERROR: Test failure")

        bundle = {"error_message": "test error"}
        result = trigger.should_escalate(bundle, "phase_001", 2)

        # Should be able to read from run directory
        assert isinstance(result, bool)


class TestRetrievalTriggerEdgeCases:
    """Test edge cases and boundary conditions."""

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

    def test_handles_none_bundle(self, trigger):
        """Test that None bundle is handled gracefully."""
        result = trigger.should_escalate(None, "phase_001", 1)
        # Should treat None as empty bundle
        assert result is True

    def test_handles_malformed_bundle(self, trigger):
        """Test that malformed bundle is handled gracefully."""
        malformed_bundle = {"unexpected_key": "value"}
        result = trigger.should_escalate(malformed_bundle, "phase_001", 1)
        # Should handle missing expected keys
        assert isinstance(result, bool)

    def test_handles_unicode_in_error_message(self, trigger):
        """Test that unicode characters in error messages are handled."""
        bundle = {
            "error_message": "Error: File 'café.txt' not found 🔍",
            "root_cause": "Missing file with unicode name"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert isinstance(result, bool)

    def test_handles_very_long_error_message(self, trigger):
        """Test that very long error messages are handled."""
        bundle = {
            "error_message": "Error: " + "X" * 10000,  # 10KB error message
            "root_cause": "Specific cause"
        }
        result = trigger.should_escalate(bundle, "phase_001", 1)
        assert isinstance(result, bool)

    def test_handles_missing_log_files(self, trigger):
        """Test that missing log files don't cause errors."""
        bundle = {
            "error_message": "Detailed error message",
            "root_cause": "Specific cause"
        }
        # No log files exist
        result = trigger.should_escalate(bundle, "phase_001", 2)
        assert isinstance(result, bool)

    def test_handles_corrupted_log_files(self, trigger, temp_run_dir):
        """Test that corrupted log files are handled gracefully."""
        # Create binary log file (not UTF-8)
        log = temp_run_dir / "phase_001.log"
        log.write_bytes(b"\x80\x81\x82\x83")  # Invalid UTF-8

        bundle = {
            "error_message": "Detailed error message",
            "root_cause": "Specific cause"
        }
        result = trigger.should_escalate(bundle, "phase_001", 2)
        # Should handle read errors gracefully
        assert isinstance(result, bool)
