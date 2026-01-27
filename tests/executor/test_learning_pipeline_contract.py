"""
Contract tests for Learning Pipeline Module (PR-EXE-10)

Tests the LearningPipeline class that records lessons learned during troubleshooting.
"""

from autopack.executor.learning_pipeline import LearningPipeline


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


class TestTaskCategoryTracking:
    """Test task_category tracking in hints"""

    def test_task_category_recorded_when_present(self):
        """Test task_category is recorded when provided in phase"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {
            "phase_id": "test",
            "name": "Test Phase",
            "task_category": "refactoring",
        }

        pipeline.record_hint(phase, "auditor_reject", "Details")

        hints = pipeline.get_all_hints()
        assert hints[0].task_category == "refactoring"

    def test_task_category_none_when_absent(self):
        """Test task_category is None when not provided in phase"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details")

        hints = pipeline.get_all_hints()
        assert hints[0].task_category is None

    def test_hints_filtered_by_category(self):
        """Test hints are retrieved for same task category"""
        pipeline = LearningPipeline(run_id="test-run")

        phase1 = {
            "phase_id": "phase-1",
            "name": "Phase 1",
            "task_category": "refactoring",
        }
        phase2 = {
            "phase_id": "phase-2",
            "name": "Phase 2",
            "task_category": "bugfix",
        }
        phase3 = {
            "phase_id": "phase-3",
            "name": "Phase 3",
            "task_category": "refactoring",
        }

        pipeline.record_hint(phase1, "auditor_reject", "Details 1")
        pipeline.record_hint(phase2, "ci_fail", "Details 2")
        pipeline.record_hint(phase3, "patch_apply_error", "Details 3")

        # Query for phase with refactoring category
        query_phase = {
            "phase_id": "query-phase",
            "task_category": "refactoring",
        }
        hints = pipeline.get_hints_for_phase(query_phase)

        # Should get hints from phase1 and phase3 (same category)
        assert len(hints) == 2
        # Verify hints are from refactoring category
        hint_texts = [h for h in hints]
        assert "Details 1" in str(hint_texts)
        assert "Details 3" in str(hint_texts)

    def test_hints_for_phase_include_same_phase_hints(self):
        """Test hints include those from same phase_id regardless of category"""
        pipeline = LearningPipeline(run_id="test-run")

        phase1 = {
            "phase_id": "phase-1",
            "name": "Phase 1",
            "task_category": "refactoring",
        }
        phase2 = {
            "phase_id": "query-phase",
            "name": "Query Phase",
            "task_category": "bugfix",
        }

        pipeline.record_hint(phase1, "auditor_reject", "Details 1")
        pipeline.record_hint(phase2, "ci_fail", "Details 2")

        # Query same phase_id as phase2
        hints = pipeline.get_hints_for_phase(phase2)

        # Should get hint from phase2 (same phase_id)
        assert len(hints) == 1
        assert "Details 2" in hints[0]

    def test_category_filtering_requires_both_non_none(self):
        """Test category filtering only applies when both are non-None"""
        pipeline = LearningPipeline(run_id="test-run")

        phase1 = {
            "phase_id": "phase-1",
            "name": "Phase 1",
            "task_category": "refactoring",
        }
        # phase2 has no task_category
        phase2 = {"phase_id": "phase-2", "name": "Phase 2"}

        pipeline.record_hint(phase1, "auditor_reject", "Details 1")
        pipeline.record_hint(phase2, "ci_fail", "Details 2")

        # Query with refactoring category but no matching phase
        query_phase = {
            "phase_id": "query-phase",
            "task_category": "refactoring",
        }
        hints = pipeline.get_hints_for_phase(query_phase)

        # Should not get hint from phase2 (it has no task_category)
        assert len(hints) == 1
        assert "Details 1" in hints[0]

    def test_multiple_categories_handled(self):
        """Test handling of multiple different categories"""
        pipeline = LearningPipeline(run_id="test-run")

        phases = [
            {
                "phase_id": "phase-1",
                "name": "Phase 1",
                "task_category": "refactoring",
            },
            {
                "phase_id": "phase-2",
                "name": "Phase 2",
                "task_category": "bugfix",
            },
            {
                "phase_id": "phase-3",
                "name": "Phase 3",
                "task_category": "feature",
            },
            {
                "phase_id": "phase-4",
                "name": "Phase 4",
                "task_category": "refactoring",
            },
        ]

        for i, phase in enumerate(phases):
            pipeline.record_hint(phase, "auditor_reject", f"Details {i + 1}")

        # Query for bugfix category
        query_phase = {"phase_id": "query-phase", "task_category": "bugfix"}
        hints = pipeline.get_hints_for_phase(query_phase)

        # Should get only bugfix hint
        assert len(hints) == 1
        assert "Details 2" in hints[0]


class TestPersistToMemory:
    """Test persist_to_memory functionality (MEM-001)"""

    def test_persist_returns_zero_when_memory_service_none(self):
        """Test returns 0 when memory_service is None"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details")

        result = pipeline.persist_to_memory(memory_service=None)
        assert result == 0

    def test_persist_returns_zero_when_memory_service_disabled(self):
        """Test returns 0 when memory_service is disabled"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details")

        # Mock a disabled memory service
        class MockMemoryService:
            enabled = False

        result = pipeline.persist_to_memory(memory_service=MockMemoryService())
        assert result == 0

    def test_persist_returns_zero_when_no_hints(self):
        """Test returns 0 when no hints to persist"""
        pipeline = LearningPipeline(run_id="test-run")

        class MockMemoryService:
            enabled = True

        result = pipeline.persist_to_memory(memory_service=MockMemoryService())
        assert result == 0

    def test_persist_calls_write_telemetry_insight(self):
        """Test persist calls write_telemetry_insight for each hint"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details 1")
        pipeline.record_hint(phase, "ci_fail", "Details 2")

        # Mock memory service
        written_insights = []

        class MockMemoryService:
            enabled = True

            def write_telemetry_insight(self, insight, project_id, validate, strict):
                written_insights.append(insight)
                return f"point_{len(written_insights)}"

        result = pipeline.persist_to_memory(
            memory_service=MockMemoryService(), project_id="test-project"
        )

        assert result == 2
        assert len(written_insights) == 2

    def test_persist_converts_hint_to_insight_format(self):
        """Test hint is correctly converted to telemetry insight format"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {
            "phase_id": "test-phase",
            "name": "Test Phase",
            "task_category": "refactoring",
        }

        pipeline.record_hint(phase, "auditor_reject", "Code quality issues")

        captured_insight = None

        class MockMemoryService:
            enabled = True

            def write_telemetry_insight(self, insight, project_id, validate, strict):
                nonlocal captured_insight
                captured_insight = insight
                return "point_1"

        pipeline.persist_to_memory(memory_service=MockMemoryService(), project_id="test-project")

        assert captured_insight is not None
        assert captured_insight["insight_type"] == "failure_mode"
        assert captured_insight["phase_id"] == "test-phase"
        assert captured_insight["run_id"] == "test-run"
        assert captured_insight["task_category"] == "refactoring"
        assert "auditor_reject_test-phase" in captured_insight["source_issue_keys"]

    def test_persist_maps_hint_types_to_insight_types(self):
        """Test hint types are correctly mapped to insight types"""
        pipeline = LearningPipeline(run_id="test-run")

        # Test each hint type mapping
        hint_type_mappings = {
            "auditor_reject": "failure_mode",
            "ci_fail": "failure_mode",
            "patch_apply_error": "failure_mode",
            "infra_error": "retry_cause",
            "success_after_retry": "retry_cause",
            "builder_churn_limit_exceeded": "cost_sink",
            "builder_guardrail": "failure_mode",
        }

        for hint_type, expected_insight_type in hint_type_mappings.items():
            mapped = pipeline._map_hint_type_to_insight_type(hint_type)
            assert mapped == expected_insight_type, (
                f"Expected {expected_insight_type} for {hint_type}, got {mapped}"
            )

    def test_persist_maps_unknown_hint_type_to_unknown(self):
        """Test unknown hint types map to 'unknown' insight type"""
        pipeline = LearningPipeline(run_id="test-run")
        mapped = pipeline._map_hint_type_to_insight_type("some_new_type")
        assert mapped == "unknown"

    def test_persist_sets_correct_severity(self):
        """Test correct severity is set for different hint types"""
        pipeline = LearningPipeline(run_id="test-run")

        # High severity
        assert pipeline._get_hint_severity("ci_fail") == "high"
        assert pipeline._get_hint_severity("patch_apply_error") == "high"
        assert pipeline._get_hint_severity("builder_guardrail") == "high"

        # Medium severity
        assert pipeline._get_hint_severity("auditor_reject") == "medium"
        assert pipeline._get_hint_severity("deliverables_validation_failed") == "medium"

        # Low severity
        assert pipeline._get_hint_severity("success_after_retry") == "low"
        assert pipeline._get_hint_severity("infra_error") == "low"

        # Unknown defaults to medium
        assert pipeline._get_hint_severity("unknown_type") == "medium"

    def test_persist_continues_on_individual_failure(self):
        """Test persistence continues even if individual hint fails"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details 1")
        pipeline.record_hint(phase, "ci_fail", "Details 2")
        pipeline.record_hint(phase, "patch_apply_error", "Details 3")

        call_count = [0]

        class MockMemoryService:
            enabled = True

            def write_telemetry_insight(self, insight, project_id, validate, strict):
                call_count[0] += 1
                if call_count[0] == 2:
                    raise Exception("Simulated failure")
                return f"point_{call_count[0]}"

        result = pipeline.persist_to_memory(
            memory_service=MockMemoryService(), project_id="test-project"
        )

        # Should succeed for 2 out of 3 hints
        assert result == 2
        assert call_count[0] == 3  # All hints attempted

    def test_persist_passes_project_id(self):
        """Test project_id is passed to write_telemetry_insight"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test", "name": "Test Phase"}

        pipeline.record_hint(phase, "auditor_reject", "Details")

        captured_project_id = None

        class MockMemoryService:
            enabled = True

            def write_telemetry_insight(self, insight, project_id, validate, strict):
                nonlocal captured_project_id
                captured_project_id = project_id
                return "point_1"

        pipeline.persist_to_memory(memory_service=MockMemoryService(), project_id="my-project-id")

        assert captured_project_id == "my-project-id"
