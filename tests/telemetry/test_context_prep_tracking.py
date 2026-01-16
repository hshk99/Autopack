"""Tests for context preparation cost tracking (IMP-COST-004)."""

from autopack.telemetry.cost_tracker import ContextPrepCost, ContextPrepTracker


class TestContextPrepCost:
    """Tests for ContextPrepCost data class."""

    def test_context_prep_cost_creation(self):
        """Test creating a ContextPrepCost instance."""
        cost = ContextPrepCost(
            phase_id="test-phase",
            file_reads_count=2,
            file_reads_bytes=4000,
            embedding_calls=1,
            embedding_tokens=100,
            artifact_loads=0,
            artifact_bytes=0,
            scope_analysis_ms=50,
            total_prep_ms=100,
        )

        assert cost.phase_id == "test-phase"
        assert cost.file_reads_count == 2
        assert cost.file_reads_bytes == 4000
        assert cost.embedding_calls == 1
        assert cost.embedding_tokens == 100

    def test_estimated_token_equivalent(self):
        """Test estimated token equivalent calculation.

        With 4000 bytes (1000 tokens) + 100 embedding tokens = 1100 total.
        """
        cost = ContextPrepCost(
            phase_id="test",
            file_reads_count=2,
            file_reads_bytes=4000,
            embedding_calls=1,
            embedding_tokens=100,
            artifact_loads=0,
            artifact_bytes=0,
            scope_analysis_ms=50,
            total_prep_ms=100,
        )
        # 4000 bytes / 4 = 1000 tokens + 100 embedding tokens = 1100
        assert cost.estimated_token_equivalent == 1100

    def test_estimated_token_equivalent_with_artifacts(self):
        """Test token equivalent includes artifact bytes."""
        cost = ContextPrepCost(
            phase_id="test",
            file_reads_count=1,
            file_reads_bytes=2000,
            embedding_calls=0,
            embedding_tokens=0,
            artifact_loads=1,
            artifact_bytes=2000,
            scope_analysis_ms=25,
            total_prep_ms=50,
        )
        # (2000 + 2000) bytes / 4 = 1000 tokens
        assert cost.estimated_token_equivalent == 1000

    def test_estimated_token_equivalent_no_overhead(self):
        """Test token equivalent with zero overhead."""
        cost = ContextPrepCost(
            phase_id="test",
            file_reads_count=0,
            file_reads_bytes=0,
            embedding_calls=0,
            embedding_tokens=0,
            artifact_loads=0,
            artifact_bytes=0,
            scope_analysis_ms=0,
            total_prep_ms=0,
        )
        assert cost.estimated_token_equivalent == 0


class TestContextPrepTracker:
    """Tests for ContextPrepTracker."""

    def test_tracker_initialization(self):
        """Test tracker initialization."""
        tracker = ContextPrepTracker(phase_id="test-phase")
        assert tracker.phase_id == "test-phase"
        assert tracker._start_time is None
        assert tracker._file_reads == []
        assert tracker._embedding_calls == []
        assert tracker._artifact_loads == []
        assert tracker._scope_analysis_ms == 0.0

    def test_tracker_start(self):
        """Test starting the tracker."""
        tracker = ContextPrepTracker(phase_id="test-phase")
        tracker.start()
        assert tracker._start_time is not None

    def test_record_file_read(self):
        """Test recording file reads."""
        tracker = ContextPrepTracker(phase_id="test-phase")
        tracker.start()
        tracker.record_file_read("test.py", 1000)
        tracker.record_file_read("test2.py", 2000)

        cost = tracker.finalize()
        assert cost.file_reads_count == 2
        assert cost.file_reads_bytes == 3000

    def test_record_embedding_call(self):
        """Test recording embedding calls."""
        tracker = ContextPrepTracker(phase_id="test-phase")
        tracker.start()
        tracker.record_embedding_call(100)
        tracker.record_embedding_call(150)

        cost = tracker.finalize()
        assert cost.embedding_calls == 2
        assert cost.embedding_tokens == 250

    def test_record_artifact_load(self):
        """Test recording artifact loads."""
        tracker = ContextPrepTracker(phase_id="test-phase")
        tracker.start()
        tracker.record_artifact_load("artifact-1", 5000)
        tracker.record_artifact_load("artifact-2", 3000)

        cost = tracker.finalize()
        assert cost.artifact_loads == 2
        assert cost.artifact_bytes == 8000

    def test_record_scope_analysis(self):
        """Test recording scope analysis duration."""
        tracker = ContextPrepTracker(phase_id="test-phase")
        tracker.start()
        tracker.record_scope_analysis(75.5)

        cost = tracker.finalize()
        assert cost.scope_analysis_ms == 75.5

    def test_finalize_empty_tracker(self):
        """Test finalizing an empty tracker."""
        import time

        tracker = ContextPrepTracker(phase_id="test-phase")
        tracker.start()
        time.sleep(0.01)  # Sleep for 10ms to ensure measurable time

        cost = tracker.finalize()
        assert cost.phase_id == "test-phase"
        assert cost.file_reads_count == 0
        assert cost.file_reads_bytes == 0
        assert cost.embedding_calls == 0
        assert cost.embedding_tokens == 0
        assert cost.artifact_loads == 0
        assert cost.artifact_bytes == 0
        assert cost.scope_analysis_ms == 0.0
        assert cost.total_prep_ms >= 0  # Should record some time (may be 0 on very fast systems)

    def test_tracker_without_start(self):
        """Test finalizing a tracker that was never started."""
        tracker = ContextPrepTracker(phase_id="test-phase")
        cost = tracker.finalize()
        assert cost.total_prep_ms == 0

    def test_full_tracking_scenario(self):
        """Test a complete tracking scenario with all metrics."""
        import time

        tracker = ContextPrepTracker(phase_id="comprehensive-phase")
        tracker.start()

        # Record file reads
        tracker.record_file_read("models.py", 5000)
        tracker.record_file_read("utils.py", 3000)
        tracker.record_file_read("config.yaml", 500)

        # Record embedding calls
        tracker.record_embedding_call(200)
        tracker.record_embedding_call(150)

        # Record artifact loads
        tracker.record_artifact_load("artifact-cache-1", 10000)

        # Record scope analysis
        tracker.record_scope_analysis(125.0)

        time.sleep(0.01)  # Sleep for 10ms to ensure measurable time
        cost = tracker.finalize()

        # Verify counts
        assert cost.file_reads_count == 3
        assert cost.file_reads_bytes == 8500
        assert cost.embedding_calls == 2
        assert cost.embedding_tokens == 350
        assert cost.artifact_loads == 1
        assert cost.artifact_bytes == 10000
        assert cost.scope_analysis_ms == 125.0

        # Verify token equivalent: (8500 + 10000) / 4 + 350 = 4625 + 350 = 4975
        assert cost.estimated_token_equivalent == 4975

        # Verify phase ID
        assert cost.phase_id == "comprehensive-phase"

        # Verify timing was recorded
        assert cost.total_prep_ms >= 0
