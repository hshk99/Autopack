"""Integration tests for IMP-ARCH-001: Telemetry Analyzer to Memory Service.

Tests verify:
1. TelemetryAnalyzer.aggregate_telemetry() analyzes and persists insights
2. Memory service correctly routes telemetry insights
3. Integration in autonomous_loop.py works end-to-end
"""

import pytest
from unittest.mock import Mock, patch
from src.autopack.telemetry.analyzer import TelemetryAnalyzer, RankedIssue
from src.autopack.memory.memory_service import MemoryService
from src.autopack.executor.autonomous_loop import AutonomousLoop


class TestTelemetryAnalyzerMemoryIntegration:
    """Test TelemetryAnalyzer persistence to memory."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        mock_session = Mock()
        mock_session.execute = Mock()
        return mock_session

    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service."""
        mock = Mock(spec=MemoryService)
        mock.enabled = True
        mock.write_telemetry_insight = Mock(return_value="insight-001")
        return mock

    @pytest.fixture
    def analyzer(self, mock_db_session, mock_memory_service):
        """Create TelemetryAnalyzer with mocks."""
        return TelemetryAnalyzer(db_session=mock_db_session, memory_service=mock_memory_service)

    def test_analyze_and_persist_enabled(self, analyzer, mock_db_session, mock_memory_service):
        """Test that analyze_and_persist persists insights when memory is enabled."""
        # Mock telemetry queries to return sample data
        mock_result_cost_sinks = [
            Mock(
                phase_id="build",
                phase_type="BUILD",
                total_tokens=250000,
                avg_tokens=50000,
                count=5,
            )
        ]
        mock_result_failures = [
            Mock(
                phase_id="test",
                phase_type="TEST",
                phase_outcome="TIMEOUT",
                stop_reason="timeout",
                count=3,
            )
        ]
        mock_result_retries = [
            Mock(
                phase_id="audit",
                phase_type="AUDIT",
                stop_reason="validation_error",
                retry_count=2,
                success_count=1,
            )
        ]

        # Setup mock to return different results for different queries
        mock_db_session.execute.side_effect = [
            mock_result_cost_sinks,
            mock_result_failures,
            mock_result_retries,
            [],  # phase_type_stats
        ]

        # Call aggregate_telemetry which persists insights
        with patch.object(
            analyzer,
            "_find_cost_sinks",
            return_value=[
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="build",
                    phase_type="BUILD",
                    metric_value=250000,
                    details={"avg_tokens": 50000, "count": 5},
                )
            ],
        ):
            with patch.object(
                analyzer,
                "_find_failure_modes",
                return_value=[
                    RankedIssue(
                        rank=1,
                        issue_type="failure_mode",
                        phase_id="test",
                        phase_type="TEST",
                        metric_value=3,
                        details={"outcome": "TIMEOUT", "stop_reason": "timeout"},
                    )
                ],
            ):
                with patch.object(analyzer, "_find_retry_causes", return_value=[]):
                    with patch.object(analyzer, "_compute_phase_type_stats", return_value={}):
                        result = analyzer.aggregate_telemetry(window_days=7)

        # Verify insights were retrieved (even though persisted by the bridge)
        assert result["top_cost_sinks"]
        assert result["top_failure_modes"]

    def test_memory_service_disabled(self, mock_db_session):
        """Test that analyzer handles disabled memory gracefully."""
        mock_memory = Mock(spec=MemoryService)
        mock_memory.enabled = False

        analyzer = TelemetryAnalyzer(db_session=mock_db_session, memory_service=mock_memory)

        with patch.object(analyzer, "_find_cost_sinks", return_value=[]):
            with patch.object(analyzer, "_find_failure_modes", return_value=[]):
                with patch.object(analyzer, "_find_retry_causes", return_value=[]):
                    with patch.object(analyzer, "_compute_phase_type_stats", return_value={}):
                        result = analyzer.aggregate_telemetry()

        # Should still work, just not persist to memory
        assert "top_cost_sinks" in result


class TestMemoryServiceTelemetryInsightRouting:
    """Test that MemoryService correctly routes telemetry insights."""

    @pytest.fixture
    def memory_service(self):
        """Create MemoryService with actual methods (mocked store)."""
        service = MemoryService(enabled=True)
        service.store = Mock()
        return service

    def test_write_telemetry_insight_cost_sink(self, memory_service):
        """Test cost_sink routing to write_phase_summary."""
        insight = {
            "insight_type": "cost_sink",
            "description": "High token usage in build phase",
            "phase_id": "build",
            "run_id": "run-123",
            "severity": "high",
        }

        memory_service.write_telemetry_insight(insight, project_id="proj-1")

        # Should have called write_phase_summary indirectly through store.upsert
        assert memory_service.store.upsert.called

    def test_write_telemetry_insight_failure_mode(self, memory_service):
        """Test failure_mode routing to write_error."""
        insight = {
            "insight_type": "failure_mode",
            "description": "Timeout failures in test phase",
            "phase_id": "test",
            "run_id": "run-123",
            "severity": "high",
        }

        memory_service.write_telemetry_insight(insight, project_id="proj-1")

        assert memory_service.store.upsert.called

    def test_write_telemetry_insight_retry_cause(self, memory_service):
        """Test retry_cause routing to write_doctor_hint."""
        insight = {
            "insight_type": "retry_cause",
            "description": "Phase retries due to validation errors",
            "phase_id": "audit",
            "run_id": "run-123",
            "severity": "medium",
        }

        memory_service.write_telemetry_insight(insight, project_id="proj-1")

        assert memory_service.store.upsert.called


class TestAutonomousLoopTelemetryPersistence:
    """Test telemetry persistence in autonomous loop finalization."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        executor = Mock()
        executor.db_session = Mock()
        executor.run_id = "run-123"
        executor._get_project_slug = Mock(return_value="test-project")
        return executor

    def test_persist_telemetry_insights_on_completion(self, mock_executor):
        """Test that telemetry insights are persisted when run completes."""
        loop = AutonomousLoop(mock_executor)

        # Create mock analyzer
        mock_analyzer = Mock()
        mock_analyzer.aggregate_telemetry = Mock(
            return_value={
                "top_cost_sinks": [
                    Mock(
                        rank=1,
                        phase_id="build",
                        metric_value=250000,
                        details={"count": 5},
                    )
                ],
                "top_failure_modes": [],
                "top_retry_causes": [],
                "phase_type_stats": {},
            }
        )

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            loop._persist_telemetry_insights()

        # Verify analyzer was consulted
        mock_analyzer.aggregate_telemetry.assert_called_once_with(window_days=7)

    def test_persist_telemetry_no_analyzer(self, mock_executor):
        """Test graceful handling when analyzer is unavailable."""
        loop = AutonomousLoop(mock_executor)
        mock_executor.db_session = None  # No database session

        # Should not raise exception
        loop._persist_telemetry_insights()

    def test_persist_telemetry_analyzer_error(self, mock_executor):
        """Test graceful error handling when analyzer fails."""
        loop = AutonomousLoop(mock_executor)

        mock_analyzer = Mock()
        mock_analyzer.aggregate_telemetry = Mock(side_effect=Exception("Database error"))

        with patch.object(loop, "_get_telemetry_analyzer", return_value=mock_analyzer):
            # Should not raise exception
            loop._persist_telemetry_insights()


class TestTelemetryBridgeIntegration:
    """Test TelemetryToMemoryBridge in the persistence pipeline."""

    def test_bridge_converts_and_persists_issues(self):
        """Test that bridge converts ranked issues and persists them."""
        from src.autopack.telemetry.telemetry_to_memory_bridge import (
            TelemetryToMemoryBridge,
        )

        mock_memory = Mock(spec=MemoryService)
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(return_value="insight-001")

        bridge = TelemetryToMemoryBridge(mock_memory, enabled=True)

        ranked_issues = [
            {
                "issue_type": "cost_sink",
                "phase_id": "build",
                "metric_value": 250000,
                "severity": "high",
                "description": "High token usage",
                "occurrences": 5,
                "suggested_action": "Reduce context window",
                "rank": 1,
                "details": {"count": 5},
            }
        ]

        count = bridge.persist_insights(ranked_issues, run_id="run-123")

        assert count == 1
        mock_memory.write_telemetry_insight.assert_called_once()

    def test_bridge_deduplication_across_runs(self):
        """Test that bridge deduplicates insights within session."""
        from src.autopack.telemetry.telemetry_to_memory_bridge import (
            TelemetryToMemoryBridge,
        )

        mock_memory = Mock(spec=MemoryService)
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(return_value="insight-001")

        bridge = TelemetryToMemoryBridge(mock_memory, enabled=True)

        ranked_issues = [
            {
                "issue_type": "cost_sink",
                "phase_id": "build",
                "metric_value": 250000,
                "severity": "high",
                "description": "High token usage",
                "occurrences": 5,
                "suggested_action": "Reduce context window",
                "rank": 1,
                "details": {"count": 5},
            }
        ]

        # First call should persist
        count1 = bridge.persist_insights(ranked_issues, run_id="run-123")
        assert count1 == 1

        # Second call with same insights should be deduplicated
        count2 = bridge.persist_insights(ranked_issues, run_id="run-123")
        assert count2 == 0

        # Total calls should be 1 (only from first call)
        assert mock_memory.write_telemetry_insight.call_count == 1
