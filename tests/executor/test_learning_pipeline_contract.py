"""
Contract tests for Learning Pipeline Module (PR-EXE-10)

Tests the LearningPipeline class that records lessons learned during troubleshooting.
"""

import pytest
from autopack.executor.learning_pipeline import LearningPipeline, LearningHint


class TestHintRecording:
    """Test hint recording"""

    def test_hint_recorded_with_correct_metadata(self):
        """Test hints are recorded with correct metadata"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test-phase", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Test details")

        hints = pipeline.get_all_hints()
        assert len(hints) == 1
        assert hints[0].phase_id == "test-phase"
        assert hints[0].hint_type == "auditor_reject"
        assert "Test Phase" in hints[0].hint_text
        assert "Test details" in hints[0].hint_text

    def test_multiple_hints_recorded(self):
        """Test multiple hints can be recorded"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test-phase", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details 1")
        pipeline.record_hint(phase, "ci_fail", "Details 2")
        pipeline.record_hint(phase, "patch_apply_error", "Details 3")

        assert pipeline.get_hint_count() == 3

    def test_hint_recording_graceful_failure(self):
        """Test graceful failure if hint recording fails"""
        pipeline = LearningPipeline(run_id="test-run")

        # Pass invalid phase (should not crash)
        pipeline.record_hint(None, "auditor_reject", "Details")

        # Should still be operational
        valid_phase = {"phase_id": "valid", "name": "Valid"}
        pipeline.record_hint(valid_phase, "ci_fail", "Valid details")
        assert pipeline.get_hint_count() >= 1


class TestHintTemplates:
    """Test hint text generation"""

    def test_auditor_reject_template(self):
        """Test auditor_reject hint template"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Code quality issues")

        hints = pipeline.get_all_hints()
        assert "rejected by auditor" in hints[0].hint_text
        assert "Code quality issues" in hints[0].hint_text

    def test_ci_fail_template(self):
        """Test ci_fail hint template"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "ci_fail", "Tests failed")

        hints = pipeline.get_all_hints()
        assert "failed CI tests" in hints[0].hint_text

    def test_patch_apply_error_template(self):
        """Test patch_apply_error hint template"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "patch_apply_error", "Invalid diff format")

        hints = pipeline.get_all_hints()
        assert "invalid patch" in hints[0].hint_text.lower()

    def test_infra_error_template(self):
        """Test infra_error hint template"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "infra_error", "API timeout")

        hints = pipeline.get_all_hints()
        assert "infrastructure error" in hints[0].hint_text.lower()

    def test_success_after_retry_template(self):
        """Test success_after_retry hint template"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "success_after_retry", "Succeeded on attempt 3")

        hints = pipeline.get_all_hints()
        assert "succeeded after retries" in hints[0].hint_text.lower()

    def test_builder_churn_limit_exceeded_template(self):
        """Test builder_churn_limit_exceeded hint template"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "builder_churn_limit_exceeded", "Too many changes")

        hints = pipeline.get_all_hints()
        assert "churn limit" in hints[0].hint_text.lower()

    def test_builder_guardrail_template(self):
        """Test builder_guardrail hint template"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "builder_guardrail", "Output too large")

        hints = pipeline.get_all_hints()
        assert "guardrail" in hints[0].hint_text.lower()

    def test_unknown_hint_type_template(self):
        """Test fallback template for unknown hint types"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "unknown_type", "Some details")

        hints = pipeline.get_all_hints()
        assert "Test Phase" in hints[0].hint_text
        assert "unknown_type" in hints[0].hint_text


class TestHintRetrieval:
    """Test hint retrieval"""

    def test_hints_filtered_by_phase(self):
        """Test hints filtered for relevant phase"""
        pipeline = LearningPipeline(run_id="test-run")

        phase1 = {"phase_id": "phase-1", "name": "Phase 1"}
        phase2 = {"phase_id": "phase-2", "name": "Phase 2"}

        pipeline.record_hint(phase1, "auditor_reject", "Details 1")
        pipeline.record_hint(phase2, "ci_fail", "Details 2")
        pipeline.record_hint(phase1, "patch_apply_error", "Details 3")

        # Get hints for phase-1
        hints = pipeline.get_hints_for_phase(phase1)

        # Should get hints from phase-1
        assert len(hints) == 2

    def test_hints_limited_to_top_10(self):
        """Test hints limited to top 10"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        # Record 15 hints
        for i in range(15):
            pipeline.record_hint(phase, "auditor_reject", f"Details {i}")

        hints = pipeline.get_hints_for_phase(phase)
        assert len(hints) <= 10

    def test_get_hints_for_nonexistent_phase(self):
        """Test getting hints for phase with no hints"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "nonexistent", "name": "Nonexistent"}

        hints = pipeline.get_hints_for_phase(phase)
        assert hints == []


class TestHintCount:
    """Test hint count tracking"""

    def test_hint_count_increments(self):
        """Test hint count increments correctly"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        assert pipeline.get_hint_count() == 0

        pipeline.record_hint(phase, "auditor_reject", "Details 1")
        assert pipeline.get_hint_count() == 1

        pipeline.record_hint(phase, "ci_fail", "Details 2")
        assert pipeline.get_hint_count() == 2

    def test_get_all_hints_returns_all(self):
        """Test get_all_hints returns all recorded hints"""
        pipeline = LearningPipeline(run_id="test-run")
        phase1 = {"phase_id": "phase-1", "name": "Phase 1"}
        phase2 = {"phase_id": "phase-2", "name": "Phase 2"}

        pipeline.record_hint(phase1, "auditor_reject", "Details 1")
        pipeline.record_hint(phase2, "ci_fail", "Details 2")

        all_hints = pipeline.get_all_hints()
        assert len(all_hints) == 2
        assert all_hints[0].phase_id == "phase-1"
        assert all_hints[1].phase_id == "phase-2"


class TestHintDataStructure:
    """Test LearningHint dataclass"""

    def test_hint_has_required_fields(self):
        """Test LearningHint has all required fields"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details")

        hint = pipeline.get_all_hints()[0]
        assert hasattr(hint, "phase_id")
        assert hasattr(hint, "hint_type")
        assert hasattr(hint, "hint_text")
        assert hasattr(hint, "source_issue_keys")
        assert hasattr(hint, "recorded_at")

    def test_source_issue_keys_generated(self):
        """Test source_issue_keys are generated correctly"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test-phase", "name": "Test"}

        pipeline.record_hint(phase, "auditor_reject", "Details")

        hint = pipeline.get_all_hints()[0]
        assert "auditor_reject_test-phase" in hint.source_issue_keys

    def test_recorded_at_timestamp(self):
        """Test recorded_at timestamp is set"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test"}

        pipeline.record_hint(phase, "auditor_reject", "Details")

        hint = pipeline.get_all_hints()[0]
        assert hint.recorded_at > 0


class TestHintClearing:
    """Test hint clearing"""

    def test_clear_hints(self):
        """Test hints can be cleared"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test"}

        pipeline.record_hint(phase, "auditor_reject", "Details")
        assert pipeline.get_hint_count() == 1

        pipeline.clear_hints()
        assert pipeline.get_hint_count() == 0


class TestRunIdTracking:
    """Test run_id tracking"""

    def test_run_id_stored(self):
        """Test run_id is stored correctly"""
        pipeline = LearningPipeline(run_id="test-run-123")
        assert pipeline.run_id == "test-run-123"

    def test_different_runs_have_separate_pipelines(self):
        """Test different runs have separate pipelines"""
        pipeline1 = LearningPipeline(run_id="run-1")
        pipeline2 = LearningPipeline(run_id="run-2")

        phase = {"phase_id": "test", "name": "Test"}
        pipeline1.record_hint(phase, "auditor_reject", "Details 1")
        pipeline2.record_hint(phase, "ci_fail", "Details 2")

        assert pipeline1.get_hint_count() == 1
        assert pipeline2.get_hint_count() == 1
        assert pipeline1.get_all_hints()[0].hint_type == "auditor_reject"
        assert pipeline2.get_all_hints()[0].hint_type == "ci_fail"
