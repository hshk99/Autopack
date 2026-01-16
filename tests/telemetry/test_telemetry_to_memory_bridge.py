"""Tests for TelemetryToMemoryBridge."""

import pytest
from unittest.mock import Mock
from src.autopack.telemetry.telemetry_to_memory_bridge import TelemetryToMemoryBridge
from src.autopack.memory.memory_service import MemoryService


@pytest.fixture
def mock_memory_service():
    """Mock memory service."""
    mock = Mock(spec=MemoryService)
    mock.enabled = True
    mock.write_telemetry_insight.return_value = "doc-001"
    return mock


@pytest.fixture
def bridge(mock_memory_service):
    """Create TelemetryToMemoryBridge instance."""
    return TelemetryToMemoryBridge(mock_memory_service, enabled=True)


@pytest.fixture
def sample_ranked_issues():
    """Sample ranked issues from telemetry."""
    return [
        {
            "issue_type": "cost_sink",
            "phase_id": "phase_build",
            "metric_value": 350000.0,
            "occurrences": 10,
            "suggested_action": "Reduce context window by 30%",
            "rank": 1,
            "details": {"avg_tokens": 350000.0, "count": 10},
        },
        {
            "issue_type": "failure_mode",
            "phase_id": "phase_test",
            "metric_value": 15.0,
            "occurrences": 15,
            "suggested_action": "Add token budget check before LLM call",
            "rank": 2,
            "details": {"outcome": "timeout", "stop_reason": "token_limit"},
        },
        {
            "issue_type": "retry_cause",
            "phase_id": "phase_audit",
            "metric_value": 5.0,
            "occurrences": 5,
            "suggested_action": "Increase timeout threshold",
            "rank": 3,
            "details": {"stop_reason": "timeout"},
        },
    ]


def test_persist_insights_cost_sink(bridge, mock_memory_service, sample_ranked_issues):
    """Test persisting cost sink insights."""
    count = bridge.persist_insights([sample_ranked_issues[0]], run_id="test-run")

    assert count == 1
    mock_memory_service.write_telemetry_insight.assert_called_once()


def test_persist_insights_failure_mode(bridge, mock_memory_service, sample_ranked_issues):
    """Test persisting failure mode insights."""
    count = bridge.persist_insights([sample_ranked_issues[1]], run_id="test-run")

    assert count == 1
    mock_memory_service.write_telemetry_insight.assert_called_once()


def test_persist_insights_retry_cause(bridge, mock_memory_service, sample_ranked_issues):
    """Test persisting retry cause insights."""
    count = bridge.persist_insights([sample_ranked_issues[2]], run_id="test-run")

    assert count == 1
    mock_memory_service.write_telemetry_insight.assert_called_once()


def test_deduplication(bridge, mock_memory_service, sample_ranked_issues):
    """Test that duplicate insights are not persisted twice."""
    bridge.persist_insights(sample_ranked_issues, run_id="test-run")
    count_1 = bridge.persist_insights(sample_ranked_issues, run_id="test-run")

    assert count_1 == 0  # All duplicates, no new insights
    # Only first call should have persisted (3 total for first call)
    assert mock_memory_service.write_telemetry_insight.call_count == 3


def test_disabled_service(bridge, mock_memory_service, sample_ranked_issues):
    """Test that disabled service returns 0."""
    bridge.enabled = False
    count = bridge.persist_insights(sample_ranked_issues, run_id="test-run")

    assert count == 0
    mock_memory_service.write_telemetry_insight.assert_not_called()


def test_clear_cache(bridge, mock_memory_service, sample_ranked_issues):
    """Test cache clearing allows re-persisting same insights."""
    bridge.persist_insights(sample_ranked_issues, run_id="test-run")
    bridge.clear_cache()
    count = bridge.persist_insights(sample_ranked_issues, run_id="test-run")

    assert count == 3  # All re-persisted after cache clear
    assert mock_memory_service.write_telemetry_insight.call_count == 6  # 3 + 3
