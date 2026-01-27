"""Tests for FeedbackPipeline (IMP-LOOP-001).

Tests cover:
- FeedbackPipeline initialization
- process_phase_outcome() method
- get_context_for_phase() method
- flush_pending_insights() method
- persist_learning_hints() method
- Integration with memory service
"""

from unittest.mock import Mock


from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome, PhaseContext


class TestPhaseOutcome:
    """Tests for PhaseOutcome dataclass."""

    def test_phase_outcome_creation(self):
        """PhaseOutcome should be creatable with required fields."""
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )

        assert outcome.phase_id == "phase_1"
        assert outcome.phase_type == "build"
        assert outcome.success is True
        assert outcome.status == "completed"

    def test_phase_outcome_optional_fields(self):
        """PhaseOutcome should support optional fields."""
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="test",
            success=False,
            status="failed",
            execution_time_seconds=45.5,
            tokens_used=5000,
            error_message="Test failed",
            learnings=["Improve test coverage"],
            run_id="run_001",
            project_id="my_project",
        )

        assert outcome.execution_time_seconds == 45.5
        assert outcome.tokens_used == 5000
        assert outcome.error_message == "Test failed"
        assert outcome.learnings == ["Improve test coverage"]
        assert outcome.run_id == "run_001"
        assert outcome.project_id == "my_project"


class TestPhaseContext:
    """Tests for PhaseContext dataclass."""

    def test_phase_context_creation(self):
        """PhaseContext should be creatable with required fields."""
        context = PhaseContext(
            relevant_insights=[{"content": "insight1"}],
            similar_errors=[{"error": "error1"}],
            success_patterns=[{"pattern": "pattern1"}],
            recommendations=[{"action": "action1"}],
            formatted_context="## Context\n- insight1",
        )

        assert len(context.relevant_insights) == 1
        assert len(context.similar_errors) == 1
        assert len(context.success_patterns) == 1
        assert len(context.recommendations) == 1
        assert "## Context" in context.formatted_context


class TestFeedbackPipelineInit:
    """Tests for FeedbackPipeline initialization."""

    def test_init_with_defaults(self):
        """FeedbackPipeline should initialize with default values."""
        pipeline = FeedbackPipeline()

        assert pipeline.memory_service is None
        assert pipeline.telemetry_analyzer is None
        assert pipeline.learning_pipeline is None
        assert pipeline.run_id is not None  # Auto-generated
        assert pipeline.project_id == "default"
        assert pipeline.enabled is True

    def test_init_with_services(self):
        """FeedbackPipeline should accept memory and telemetry services."""
        mock_memory = Mock()
        mock_telemetry = Mock()
        mock_learning = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            telemetry_analyzer=mock_telemetry,
            learning_pipeline=mock_learning,
            run_id="run_001",
            project_id="test_project",
            enabled=True,
        )

        assert pipeline.memory_service == mock_memory
        assert pipeline.telemetry_analyzer == mock_telemetry
        assert pipeline.learning_pipeline == mock_learning
        assert pipeline.run_id == "run_001"
        assert pipeline.project_id == "test_project"

    def test_init_disabled(self):
        """FeedbackPipeline can be disabled."""
        pipeline = FeedbackPipeline(enabled=False)

        assert pipeline.enabled is False

    def test_init_stats_tracking(self):
        """FeedbackPipeline should track statistics."""
        pipeline = FeedbackPipeline()

        stats = pipeline.get_stats()
        assert stats["outcomes_processed"] == 0
        assert stats["insights_persisted"] == 0
        assert stats["context_retrievals"] == 0
        assert stats["learning_hints_recorded"] == 0


class TestProcessPhaseOutcome:
    """Tests for process_phase_outcome method."""

    def test_process_outcome_disabled(self):
        """process_phase_outcome should return early when disabled."""
        pipeline = FeedbackPipeline(enabled=False)
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )

        result = pipeline.process_phase_outcome(outcome)

        assert result["success"] is True
        assert result["insights_created"] == 0

    def test_process_outcome_success(self):
        """process_phase_outcome should process successful outcomes."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_task_execution_feedback = Mock()
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
            execution_time_seconds=30.0,
        )

        result = pipeline.process_phase_outcome(outcome)

        assert result["success"] is True
        assert result["insights_created"] >= 1
        mock_memory.write_task_execution_feedback.assert_called_once()

    def test_process_outcome_failure_records_hint(self):
        """process_phase_outcome should record learning hints for failures."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_learning = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            learning_pipeline=mock_learning,
        )
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Build error",
        )

        result = pipeline.process_phase_outcome(outcome)

        assert result["success"] is True
        assert result["hints_recorded"] == 1
        mock_learning.record_hint.assert_called_once()

    def test_process_outcome_deduplication(self):
        """process_phase_outcome should deduplicate outcomes."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
            run_id="run_001",
        )

        # Process first time
        result1 = pipeline.process_phase_outcome(outcome)
        assert result1["success"] is True
        assert result1["insights_created"] >= 1

        # Process second time - should be deduplicated
        result2 = pipeline.process_phase_outcome(outcome)
        assert result2["success"] is True
        assert result2["insights_created"] == 0  # No new insights

    def test_process_outcome_updates_stats(self):
        """process_phase_outcome should update statistics."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )

        pipeline.process_phase_outcome(outcome)

        stats = pipeline.get_stats()
        assert stats["outcomes_processed"] == 1


class TestGetContextForPhase:
    """Tests for get_context_for_phase method."""

    def test_get_context_disabled(self):
        """get_context_for_phase should return empty context when disabled."""
        pipeline = FeedbackPipeline(enabled=False)

        context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Fix compilation error",
        )

        assert context.relevant_insights == []
        assert context.similar_errors == []
        assert context.success_patterns == []
        assert context.recommendations == []
        assert context.formatted_context == ""

    def test_get_context_no_memory_service(self):
        """get_context_for_phase should handle missing memory service."""
        pipeline = FeedbackPipeline(memory_service=None)

        context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Fix compilation error",
        )

        assert isinstance(context, PhaseContext)
        assert context.formatted_context == ""

    def test_get_context_with_memory_service(self):
        """get_context_for_phase should retrieve context from memory service."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.retrieve_insights = Mock(
            return_value=[{"content": "insight1", "metadata": {"score": 0.9}}]
        )
        mock_memory.search_errors = Mock(
            return_value=[{"payload": {"error_type": "build", "error_text": "error1"}}]
        )
        mock_memory.search_execution_feedback = Mock(
            return_value=[{"payload": {"context_summary": "success pattern"}}]
        )

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Fix compilation error",
        )

        assert len(context.relevant_insights) == 1
        assert len(context.similar_errors) == 1
        assert len(context.success_patterns) == 1
        mock_memory.retrieve_insights.assert_called_once()

    def test_get_context_with_telemetry_recommendations(self):
        """get_context_for_phase should include telemetry recommendations."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.retrieve_insights = Mock(return_value=[])
        mock_memory.search_errors = Mock(return_value=[])
        mock_memory.search_execution_feedback = Mock(return_value=[])

        mock_telemetry = Mock()
        mock_telemetry.get_recommendations_for_phase = Mock(
            return_value=[
                {
                    "severity": "HIGH",
                    "action": "reduce_context_size",
                    "reason": "High token usage",
                }
            ]
        )

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            telemetry_analyzer=mock_telemetry,
        )

        context = pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Fix compilation error",
        )

        assert len(context.recommendations) == 1
        mock_telemetry.get_recommendations_for_phase.assert_called_once()

    def test_get_context_updates_stats(self):
        """get_context_for_phase should update context_retrievals stat."""
        pipeline = FeedbackPipeline()

        pipeline.get_context_for_phase(
            phase_type="build",
            phase_goal="Fix compilation error",
        )

        stats = pipeline.get_stats()
        assert stats["context_retrievals"] == 1


class TestFlushPendingInsights:
    """Tests for flush_pending_insights method."""

    def test_flush_no_pending_insights(self):
        """flush_pending_insights should return 0 with no pending insights."""
        pipeline = FeedbackPipeline()

        flushed = pipeline.flush_pending_insights()

        assert flushed == 0

    def test_flush_with_pending_insights(self):
        """flush_pending_insights should flush accumulated insights."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_task_execution_feedback = Mock()
        mock_memory.write_telemetry_insight = Mock(return_value="point_id")

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        # Process an outcome to accumulate insights
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )
        pipeline.process_phase_outcome(outcome)

        # Flush insights
        flushed = pipeline.flush_pending_insights()

        assert flushed >= 1
        assert len(pipeline._pending_insights) == 0


class TestPersistLearningHints:
    """Tests for persist_learning_hints method."""

    def test_persist_no_learning_pipeline(self):
        """persist_learning_hints should return 0 with no learning pipeline."""
        pipeline = FeedbackPipeline()

        persisted = pipeline.persist_learning_hints()

        assert persisted == 0

    def test_persist_with_learning_pipeline(self):
        """persist_learning_hints should call learning pipeline persist."""
        mock_memory = Mock()
        mock_learning = Mock()
        mock_learning.persist_to_memory = Mock(return_value=3)

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            learning_pipeline=mock_learning,
            project_id="test_project",
        )

        persisted = pipeline.persist_learning_hints()

        assert persisted == 3
        mock_learning.persist_to_memory.assert_called_once_with(
            memory_service=mock_memory,
            project_id="test_project",
        )


class TestStatsTracking:
    """Tests for statistics tracking."""

    def test_reset_stats(self):
        """reset_stats should clear all statistics."""
        pipeline = FeedbackPipeline()

        # Process some outcomes to accumulate stats
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )
        pipeline.process_phase_outcome(outcome)
        pipeline.get_context_for_phase(phase_type="build", phase_goal="test")

        # Verify stats accumulated
        assert pipeline.get_stats()["outcomes_processed"] > 0

        # Reset stats
        pipeline.reset_stats()

        stats = pipeline.get_stats()
        assert stats["outcomes_processed"] == 0
        assert stats["insights_persisted"] == 0
        assert stats["context_retrievals"] == 0
        assert stats["learning_hints_recorded"] == 0


class TestInsightTypeMapping:
    """Tests for insight type determination."""

    def test_cost_sink_detection(self):
        """High token usage should be detected as cost_sink."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="completed",
            tokens_used=150000,  # Over 100k threshold
        )

        insight = pipeline._create_insight_from_outcome(outcome)

        assert insight["insight_type"] == "cost_sink"

    def test_retry_cause_detection(self):
        """Timeout errors should be detected as retry_cause."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Request timeout exceeded",
        )

        insight = pipeline._create_insight_from_outcome(outcome)

        assert insight["insight_type"] == "retry_cause"

    def test_failure_mode_detection(self):
        """General failures should be detected as failure_mode."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Build error",
        )

        insight = pipeline._create_insight_from_outcome(outcome)

        assert insight["insight_type"] == "failure_mode"


class TestHintTypeMapping:
    """Tests for learning hint type determination."""

    def test_auditor_reject_hint(self):
        """Audit-related errors should map to auditor_reject hint type."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Phase rejected by auditor",
        )

        hint_type = pipeline._determine_hint_type(outcome)

        assert hint_type == "auditor_reject"

    def test_ci_fail_hint(self):
        """Test-related errors should map to ci_fail hint type."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="test",
            success=False,
            status="failed",
            error_message="Test suite failed",
        )

        hint_type = pipeline._determine_hint_type(outcome)

        assert hint_type == "ci_fail"

    def test_infra_error_hint(self):
        """Infrastructure errors should map to infra_error hint type."""
        pipeline = FeedbackPipeline()
        # Note: "fail" in error message matches ci_fail before infra_error,
        # so we use a message without "fail" to test infra_error detection
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="error",
            error_message="Network connection timeout on API call",
        )

        hint_type = pipeline._determine_hint_type(outcome)

        assert hint_type == "infra_error"


class TestContextFormatting:
    """Tests for context formatting."""

    def test_format_context_with_recommendations(self):
        """_format_context should include recommendations section."""
        pipeline = FeedbackPipeline()

        formatted = pipeline._format_context(
            insights=[],
            errors=[],
            success_patterns=[],
            recommendations=[
                {"severity": "CRITICAL", "action": "reduce_context", "reason": "High usage"}
            ],
            phase_type="build",
        )

        assert "### Recommendations" in formatted
        assert "[CRITICAL]" in formatted

    def test_format_context_with_insights(self):
        """_format_context should include insights section."""
        pipeline = FeedbackPipeline()

        formatted = pipeline._format_context(
            insights=[{"content": "Important insight about build process"}],
            errors=[],
            success_patterns=[],
            recommendations=[],
            phase_type="build",
        )

        assert "### Relevant Insights" in formatted
        assert "Important insight" in formatted

    def test_format_context_with_errors(self):
        """_format_context should include errors section."""
        pipeline = FeedbackPipeline()

        formatted = pipeline._format_context(
            insights=[],
            errors=[{"payload": {"error_type": "build_error", "error_text": "Compilation failed"}}],
            success_patterns=[],
            recommendations=[],
            phase_type="build",
        )

        assert "### Similar Past Errors" in formatted
        assert "build_error" in formatted

    def test_format_context_empty(self):
        """_format_context should return minimal header with no context sections."""
        pipeline = FeedbackPipeline()

        formatted = pipeline._format_context(
            insights=[],
            errors=[],
            success_patterns=[],
            recommendations=[],
            phase_type="build",
        )

        # With no content sections, we get just the header
        assert "## Context from Previous Executions" in formatted
        # But no subsections
        assert "### Recommendations" not in formatted
        assert "### Relevant Insights" not in formatted


class TestSuggestedActionGeneration:
    """Tests for suggested action generation."""

    def test_suggest_timeout_increase(self):
        """Timeout errors should suggest increasing timeout."""
        pipeline = FeedbackPipeline()
        # Use error message with exact "timeout" substring
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Request timeout exceeded",
        )

        action = pipeline._generate_suggested_action(outcome)

        assert "timeout" in action.lower() or "increase" in action.lower()

    def test_suggest_context_reduction(self):
        """Token/budget errors should suggest reducing context."""
        pipeline = FeedbackPipeline()
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Token budget exceeded",
        )

        action = pipeline._generate_suggested_action(outcome)

        assert "context" in action.lower() or "reduce" in action.lower()
