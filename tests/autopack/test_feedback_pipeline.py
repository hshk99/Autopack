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

from autopack.feedback_pipeline import FeedbackPipeline, PhaseContext, PhaseOutcome


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

        # IMP-REL-010: With eager flush, process_phase_outcome flushes immediately.
        # To test flush_pending_insights with pending insights, we need to
        # manually add insights to the queue.
        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)

        # Manually add pending insights to simulate accumulation
        pipeline._pending_insights.append({"test": "insight_1"})
        pipeline._pending_insights.append({"test": "insight_2"})

        # Flush insights
        flushed = pipeline.flush_pending_insights()

        assert flushed == 2
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


class TestAutoFlushTimer:
    """Tests for IMP-LOOP-004 auto-flush functionality."""

    def test_auto_flush_timer_starts_when_enabled(self):
        """Auto-flush timer should start when pipeline is enabled."""
        pipeline = FeedbackPipeline(enabled=True)

        assert pipeline._auto_flush_enabled is True
        assert pipeline._flush_timer is not None

        # Clean up
        pipeline.stop_auto_flush()

    def test_auto_flush_timer_not_started_when_disabled(self):
        """Auto-flush timer should not start when pipeline is disabled."""
        pipeline = FeedbackPipeline(enabled=False)

        assert pipeline._auto_flush_enabled is False
        assert pipeline._flush_timer is None

    def test_auto_flush_interval_default(self):
        """Auto-flush interval should default to 300 seconds (5 minutes)."""
        pipeline = FeedbackPipeline(enabled=False)  # Don't start timer

        assert pipeline._auto_flush_interval == 300

    def test_insight_threshold_default(self):
        """Insight threshold should default to 100."""
        pipeline = FeedbackPipeline(enabled=False)

        assert pipeline._insight_threshold == 100

    def test_stop_auto_flush(self):
        """stop_auto_flush should cancel timer and flush remaining insights."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_task_execution_feedback = Mock()
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=True)

        # Add some pending insights
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )
        pipeline.process_phase_outcome(outcome)

        # Stop auto-flush
        pipeline.stop_auto_flush()

        assert pipeline._auto_flush_enabled is False
        assert pipeline._flush_timer is None
        assert len(pipeline._pending_insights) == 0  # Flushed on stop

    def test_threshold_flush_triggered(self):
        """Flush should trigger when insight threshold is reached."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_task_execution_feedback = Mock()
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._insight_threshold = 3  # Lower threshold for testing

        # Add insights up to threshold
        for i in range(3):
            outcome = PhaseOutcome(
                phase_id=f"phase_{i}",
                phase_type="build",
                success=True,
                status="completed",
                run_id=f"run_{i}",  # Unique run_id to avoid deduplication
            )
            pipeline.process_phase_outcome(outcome)

        # Should have been flushed when threshold reached
        assert len(pipeline._pending_insights) == 0

    def test_auto_flush_method_flushes_insights(self):
        """_auto_flush method should flush pending insights."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)

        # Manually add an insight
        pipeline._pending_insights.append({"test": "insight"})

        # Call auto-flush directly
        pipeline._auto_flush()

        # Insight should be flushed
        assert len(pipeline._pending_insights) == 0
        mock_memory.write_telemetry_insight.assert_called_once()

    def test_auto_flush_handles_errors_gracefully(self):
        """_auto_flush should handle errors without crashing."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(side_effect=Exception("Test error"))

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._pending_insights.append({"test": "insight"})

        # Should not raise exception
        pipeline._auto_flush()

        # Insights should be cleared even on error
        assert len(pipeline._pending_insights) == 0

    def test_check_threshold_flush_below_threshold(self):
        """_check_threshold_flush should not flush below threshold."""
        pipeline = FeedbackPipeline(enabled=False)
        pipeline._insight_threshold = 100

        # Add insights below threshold
        for i in range(50):
            pipeline._pending_insights.append({"test": f"insight_{i}"})

        pipeline._check_threshold_flush()

        # Should not be flushed
        assert len(pipeline._pending_insights) == 50


class TestEagerFlushOnPhaseCompletion:
    """Tests for IMP-REL-010 eager flush on phase completion."""

    def test_eager_flush_called_on_phase_outcome(self):
        """Eager flush should be called after processing phase outcome."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_task_execution_feedback = Mock()
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=True)
        # Stop the auto-flush timer to avoid interference
        pipeline.stop_auto_flush()

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
        )

        # Process outcome - should trigger eager flush
        pipeline.process_phase_outcome(outcome)

        # Pending insights should be empty after eager flush
        assert len(pipeline._pending_insights) == 0

        # write_telemetry_insight should have been called (once for immediate persist,
        # once for flush)
        assert mock_memory.write_telemetry_insight.call_count >= 1

    def test_eager_flush_method_flushes_insights(self):
        """_eager_flush_phase_insights should flush pending insights."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)

        # Manually add a pending insight
        pipeline._pending_insights.append({"test": "insight"})

        # Call eager flush
        flushed = pipeline._eager_flush_phase_insights()

        assert flushed == 1
        assert len(pipeline._pending_insights) == 0
        mock_memory.write_telemetry_insight.assert_called_once()

    def test_eager_flush_returns_zero_with_no_pending(self):
        """_eager_flush_phase_insights should return 0 when no pending insights."""
        pipeline = FeedbackPipeline(enabled=False)

        flushed = pipeline._eager_flush_phase_insights()

        assert flushed == 0

    def test_eager_flush_handles_errors_gracefully(self):
        """_eager_flush_phase_insights should handle errors without crashing."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(side_effect=Exception("Test error"))

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._pending_insights.append({"test": "insight"})

        # Should not raise exception
        flushed = pipeline._eager_flush_phase_insights()

        # Should return 0 on error
        assert flushed == 0

    def test_eager_flush_thread_safe(self):
        """_eager_flush_phase_insights should be thread-safe."""
        import threading

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)

        # Add multiple insights
        for i in range(10):
            pipeline._pending_insights.append({"test": f"insight_{i}"})

        results = []

        def flush_thread():
            result = pipeline._eager_flush_phase_insights()
            results.append(result)

        # Run multiple flushes concurrently
        threads = [threading.Thread(target=flush_thread) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All insights should be flushed (only one thread should have flushed them)
        assert len(pipeline._pending_insights) == 0
        # Total flushed should equal original count
        assert sum(results) == 10


class TestShutdownFlush:
    """Tests for IMP-REL-010 shutdown flush via atexit."""

    def test_shutdown_flush_persists_insights(self):
        """_shutdown_flush should persist all pending insights."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)

        # Add pending insights
        for i in range(5):
            pipeline._pending_insights.append({"test": f"insight_{i}"})

        # Call shutdown flush
        pipeline._shutdown_flush()

        # All insights should be flushed
        assert len(pipeline._pending_insights) == 0
        assert mock_memory.write_telemetry_insight.call_count == 5

    def test_shutdown_flush_cancels_timer(self):
        """_shutdown_flush should cancel any pending timer."""
        pipeline = FeedbackPipeline(enabled=True)

        # Timer should be running
        assert pipeline._flush_timer is not None

        # Call shutdown flush
        pipeline._shutdown_flush()

        # Timer should be cancelled
        assert pipeline._flush_timer is None

    def test_shutdown_flush_handles_no_pending_insights(self):
        """_shutdown_flush should handle case with no pending insights."""
        pipeline = FeedbackPipeline(enabled=False)

        # Should not raise exception
        pipeline._shutdown_flush()

        assert len(pipeline._pending_insights) == 0

    def test_shutdown_flush_saves_hint_occurrences(self):
        """_shutdown_flush should persist hint occurrences."""
        pipeline = FeedbackPipeline(enabled=False)

        # Add some hint occurrences
        pipeline._hint_occurrences["test:hint"] = 2

        # Mock the save method to verify it's called
        original_save = pipeline._save_hint_occurrences
        save_called = [False]

        def mock_save():
            save_called[0] = True
            return True

        pipeline._save_hint_occurrences = mock_save

        # Call shutdown flush
        pipeline._shutdown_flush()

        # Save should have been called
        assert save_called[0] is True

        # Restore original
        pipeline._save_hint_occurrences = original_save

    def test_shutdown_flush_handles_errors_gracefully(self):
        """_shutdown_flush should handle errors without crashing."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(side_effect=Exception("Test error"))

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._pending_insights.append({"test": "insight"})

        # Should not raise exception
        pipeline._shutdown_flush()

        # Insights should be cleared
        assert len(pipeline._pending_insights) == 0

    def test_atexit_handler_registered(self):
        """Atexit handler should be registered on pipeline initialization."""

        # Create a pipeline and verify atexit is called
        # We can't directly verify atexit registration, but we can verify
        # the method exists and is callable
        pipeline = FeedbackPipeline(enabled=False)

        assert hasattr(pipeline, "_shutdown_flush")
        assert callable(pipeline._shutdown_flush)

        # The method should work correctly
        pipeline._shutdown_flush()  # Should not raise


class TestHintToRulePromotion:
    """Tests for IMP-TST-006: hint-to-rule promotion logic (_promote_hint_to_rule).

    Tests cover:
    - Multiple hint types (auditor_reject, ci_fail, patch_apply_error, etc.)
    - Memory service failure during promotion
    - Concurrent hint occurrences
    - Promotion threshold behavior
    - Edge cases for null/empty values
    """

    def test_promote_hint_with_memory_service(self):
        """Promotion should succeed when memory service is enabled."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["ci_fail:build"] = 3

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Test failed",
        )

        result = pipeline._promote_hint_to_rule("ci_fail", "ci_fail:build", outcome)

        assert result is True
        mock_memory.write_telemetry_insight.assert_called_once()
        assert pipeline._stats["hints_promoted_to_rules"] == 1

    def test_promote_hint_without_memory_service(self):
        """Promotion should fail gracefully without memory service."""
        pipeline = FeedbackPipeline(memory_service=None, enabled=False)

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        result = pipeline._promote_hint_to_rule("ci_fail", "ci_fail:build", outcome)

        assert result is False
        assert pipeline._stats["hints_promoted_to_rules"] == 0

    def test_promote_hint_with_disabled_memory_service(self):
        """Promotion should fail when memory service is disabled."""
        mock_memory = Mock()
        mock_memory.enabled = False

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        result = pipeline._promote_hint_to_rule("ci_fail", "ci_fail:build", outcome)

        assert result is False

    def test_promote_auditor_reject_hint_type(self):
        """Promotion should work for auditor_reject hint type."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["auditor_reject:review"] = 4

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="review",
            success=False,
            status="rejected",
            error_message="Auditor rejected the code",
        )

        result = pipeline._promote_hint_to_rule("auditor_reject", "auditor_reject:review", outcome)

        assert result is True
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]
        assert insight["hint_type"] == "auditor_reject"
        assert insight["is_rule"] is True

    def test_promote_patch_apply_error_hint_type(self):
        """Promotion should work for patch_apply_error hint type."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["patch_apply_error:fix"] = 5

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="fix",
            success=False,
            status="failed",
            error_message="Patch could not be applied",
        )

        result = pipeline._promote_hint_to_rule(
            "patch_apply_error", "patch_apply_error:fix", outcome
        )

        assert result is True
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]
        assert insight["hint_type"] == "patch_apply_error"

    def test_promote_infra_error_hint_type(self):
        """Promotion should work for infra_error hint type."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["infra_error:deploy"] = 3

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="deploy",
            success=False,
            status="failed",
            error_message="Network connection failed",
        )

        result = pipeline._promote_hint_to_rule("infra_error", "infra_error:deploy", outcome)

        assert result is True
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]
        assert insight["hint_type"] == "infra_error"

    def test_promote_builder_guardrail_hint_type(self):
        """Promotion should work for builder_guardrail hint type."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["builder_guardrail:build"] = 3

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
            error_message="Output exceeded guardrail limit",
        )

        result = pipeline._promote_hint_to_rule(
            "builder_guardrail", "builder_guardrail:build", outcome
        )

        assert result is True
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]
        assert insight["hint_type"] == "builder_guardrail"

    def test_promote_hint_memory_service_failure(self):
        """Promotion should handle memory service exceptions gracefully."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(
            side_effect=Exception("Memory service unavailable")
        )

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["ci_fail:test"] = 3

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="test",
            success=False,
            status="failed",
        )

        result = pipeline._promote_hint_to_rule("ci_fail", "ci_fail:test", outcome)

        assert result is False
        # Stats should not be incremented on failure
        assert pipeline._stats["hints_promoted_to_rules"] == 0

    def test_promote_hint_concurrent_occurrences(self):
        """Concurrent hint promotion should be thread-safe."""
        import threading

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["ci_fail:build"] = 5

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        results = []

        def promote_thread():
            result = pipeline._promote_hint_to_rule("ci_fail", "ci_fail:build", outcome)
            results.append(result)

        # Run multiple promotions concurrently
        threads = [threading.Thread(target=promote_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert all(results)
        # Memory service should be called 5 times
        assert mock_memory.write_telemetry_insight.call_count == 5

    def test_promotion_threshold_not_reached(self):
        """Hint should not be promoted before reaching threshold."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_learning = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            learning_pipeline=mock_learning,
            enabled=True,
        )
        pipeline.stop_auto_flush()
        # Clear any persisted hint occurrences to ensure fresh start
        pipeline._hint_occurrences = {}

        # Process outcome twice (below threshold of 3)
        for i in range(2):
            outcome = PhaseOutcome(
                phase_id=f"phase_{i}",
                phase_type="build",
                success=False,
                status="failed",
                error_message="Test failed",
                run_id=f"run_{i}",
            )
            pipeline.process_phase_outcome(outcome)

        # Promotion should not have occurred
        assert pipeline._stats["hints_promoted_to_rules"] == 0

    def test_promotion_threshold_reached(self):
        """Hint should be promoted when threshold is reached."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_task_execution_feedback = Mock()
        mock_memory.write_telemetry_insight = Mock()
        mock_learning = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            learning_pipeline=mock_learning,
            enabled=True,
        )
        pipeline.stop_auto_flush()
        # Clear any persisted hint occurrences to ensure fresh start
        pipeline._hint_occurrences = {}

        # Process outcome 3 times (at threshold)
        for i in range(3):
            outcome = PhaseOutcome(
                phase_id=f"phase_{i}",
                phase_type="build",
                success=False,
                status="failed",
                error_message="Test failed",
                run_id=f"run_{i}",
            )
            pipeline.process_phase_outcome(outcome)

        # Promotion should have occurred on the 3rd occurrence
        assert pipeline._stats["hints_promoted_to_rules"] == 1

    def test_promotion_with_none_phase_type(self):
        """Promotion should handle None phase_type gracefully."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["ci_fail:unknown"] = 3

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type=None,  # None phase type
            success=False,
            status="failed",
        )

        result = pipeline._promote_hint_to_rule("ci_fail", "ci_fail:unknown", outcome)

        assert result is True
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]
        assert insight["phase_type"] == "unknown"

    def test_hint_promotion_key_generation(self):
        """_get_hint_promotion_key should generate correct keys."""
        pipeline = FeedbackPipeline(enabled=False)

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        key = pipeline._get_hint_promotion_key("ci_fail", outcome)

        assert key == "ci_fail:build"

    def test_hint_promotion_key_with_none_phase_type(self):
        """_get_hint_promotion_key should handle None phase_type."""
        pipeline = FeedbackPipeline(enabled=False)

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type=None,
            success=False,
            status="failed",
        )

        key = pipeline._get_hint_promotion_key("ci_fail", outcome)

        assert key == "ci_fail:unknown"

    def test_generate_rule_action_auditor_reject(self):
        """_generate_rule_action should generate appropriate action for auditor_reject."""
        pipeline = FeedbackPipeline(enabled=False)

        action = pipeline._generate_rule_action("auditor_reject", "review")

        assert "review" in action.lower()
        assert "error handling" in action.lower() or "quality" in action.lower()

    def test_generate_rule_action_ci_fail(self):
        """_generate_rule_action should generate appropriate action for ci_fail."""
        pipeline = FeedbackPipeline(enabled=False)

        action = pipeline._generate_rule_action("ci_fail", "test")

        assert "test" in action.lower()

    def test_generate_rule_action_patch_apply_error(self):
        """_generate_rule_action should generate appropriate action for patch_apply_error."""
        pipeline = FeedbackPipeline(enabled=False)

        action = pipeline._generate_rule_action("patch_apply_error", "fix")

        assert "fix" in action.lower()
        assert "diff" in action.lower() or "patch" in action.lower() or "file" in action.lower()

    def test_generate_rule_action_infra_error(self):
        """_generate_rule_action should generate appropriate action for infra_error."""
        pipeline = FeedbackPipeline(enabled=False)

        action = pipeline._generate_rule_action("infra_error", "deploy")

        assert "deploy" in action.lower()
        assert "retry" in action.lower() or "api" in action.lower()

    def test_generate_rule_action_builder_guardrail(self):
        """_generate_rule_action should generate appropriate action for builder_guardrail."""
        pipeline = FeedbackPipeline(enabled=False)

        action = pipeline._generate_rule_action("builder_guardrail", "build")

        assert "build" in action.lower()
        assert "size" in action.lower() or "chunk" in action.lower() or "limit" in action.lower()

    def test_generate_rule_action_unknown_type(self):
        """_generate_rule_action should handle unknown hint types."""
        pipeline = FeedbackPipeline(enabled=False)

        action = pipeline._generate_rule_action("unknown_type", "build")

        assert "build" in action.lower()
        assert "unknown_type" in action.lower()

    def test_promoted_rule_insight_structure(self):
        """Promoted rule insight should have correct structure."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)
        pipeline._hint_occurrences["ci_fail:build"] = 5

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        pipeline._promote_hint_to_rule("ci_fail", "ci_fail:build", outcome)

        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]

        # Verify required fields
        assert insight["insight_type"] == "promoted_rule"
        assert insight["phase_type"] == "build"
        assert insight["hint_type"] == "ci_fail"
        assert insight["occurrences"] == 5
        assert insight["severity"] == "high"
        assert insight["is_rule"] is True
        assert "suggested_action" in insight
        assert "timestamp" in insight
        assert "RULE" in insight["description"]

    def test_promotion_updates_stats_incrementally(self):
        """Each successful promotion should increment stats by 1."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory, enabled=False)

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        # Promote multiple times
        for i in range(3):
            pipeline._hint_occurrences[f"ci_fail_{i}:build"] = 3
            pipeline._promote_hint_to_rule("ci_fail", f"ci_fail_{i}:build", outcome)

        assert pipeline._stats["hints_promoted_to_rules"] == 3

    def test_promotion_uses_run_id_from_pipeline(self):
        """Promoted rule should use run_id from pipeline."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory, run_id="test_run_123", enabled=False
        )
        pipeline._hint_occurrences["ci_fail:build"] = 3

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        pipeline._promote_hint_to_rule("ci_fail", "ci_fail:build", outcome)

        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args[1]["insight"]
        assert insight["run_id"] == "test_run_123"

    def test_promotion_calls_write_telemetry_insight_with_correct_params(self):
        """Promotion should call write_telemetry_insight with correct parameters."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory, project_id="test_project", enabled=False
        )
        pipeline._hint_occurrences["ci_fail:build"] = 3

        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=False,
            status="failed",
        )

        pipeline._promote_hint_to_rule("ci_fail", "ci_fail:build", outcome)

        mock_memory.write_telemetry_insight.assert_called_once()
        call_kwargs = mock_memory.write_telemetry_insight.call_args[1]
        assert call_kwargs["project_id"] == "test_project"
        assert call_kwargs["validate"] is True
        assert call_kwargs["strict"] is False
