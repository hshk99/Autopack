"""Tests for TelemetryToMemoryBridge."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.autopack.memory.memory_service import MemoryService
from src.autopack.telemetry.telemetry_to_memory_bridge import TelemetryToMemoryBridge


@pytest.fixture
def mock_memory_service():
    """Mock memory service."""
    mock = Mock(spec=MemoryService)
    mock.enabled = True
    mock.write_telemetry_insight.return_value = "doc-001"
    return mock


@pytest.fixture
def temp_fallback_queue_path(tmp_path):
    """Create temporary path for fallback queue."""
    return str(tmp_path / "fallback_queue.json")


@pytest.fixture
def bridge(mock_memory_service, temp_fallback_queue_path):
    """Create TelemetryToMemoryBridge instance with temp fallback path."""
    return TelemetryToMemoryBridge(
        mock_memory_service, fallback_queue_path=temp_fallback_queue_path
    )


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


def test_bridge_is_mandatory(bridge, mock_memory_service, sample_ranked_issues):
    """Test IMP-LOOP-020: Bridge is mandatory and cannot be disabled.

    The bridge persists insights whenever memory service is available and enabled.
    There is no 'enabled' parameter - the bridge is always active.
    """
    # Verify bridge has no 'enabled' attribute (removed by IMP-LOOP-020)
    assert not hasattr(bridge, "enabled")

    # Verify insights are persisted
    count = bridge.persist_insights(sample_ranked_issues, run_id="test-run")
    assert count == 3
    assert mock_memory_service.write_telemetry_insight.call_count == 3


def test_clear_cache(bridge, mock_memory_service, sample_ranked_issues):
    """Test cache clearing allows re-persisting same insights."""
    bridge.persist_insights(sample_ranked_issues, run_id="test-run")
    bridge.clear_cache()
    count = bridge.persist_insights(sample_ranked_issues, run_id="test-run")

    assert count == 3  # All re-persisted after cache clear
    assert mock_memory_service.write_telemetry_insight.call_count == 6  # 3 + 3


# ---------------------------------------------------------------------------
# IMP-REL-011: Circuit Breaker Tests
# ---------------------------------------------------------------------------


def test_circuit_breaker_initial_state(bridge):
    """Test that circuit breaker starts in closed state."""
    assert bridge.get_circuit_breaker_state() == "closed"


def test_fallback_queue_initial_empty(bridge):
    """Test that fallback queue starts empty."""
    assert bridge.get_fallback_queue_size() == 0


def test_circuit_breaker_opens_after_failures(
    mock_memory_service, temp_fallback_queue_path, sample_ranked_issues
):
    """Test that circuit breaker opens after threshold failures."""
    # Make memory service fail
    mock_memory_service.write_telemetry_insight.side_effect = Exception("Connection failed")

    bridge = TelemetryToMemoryBridge(
        mock_memory_service, fallback_queue_path=temp_fallback_queue_path
    )

    # First persist should trigger failures and open circuit
    # The tenacity retry will retry 3 times, and circuit breaker will track failures
    count = bridge.persist_insights([sample_ranked_issues[0]], run_id="test-run")

    # Should still return 1 because insight is queued
    assert count == 1
    # Fallback queue should have the insight
    assert bridge.get_fallback_queue_size() >= 1


def test_fallback_queue_persists_to_file(
    mock_memory_service, temp_fallback_queue_path, sample_ranked_issues
):
    """Test that fallback queue is persisted to file."""
    # Make memory service fail
    mock_memory_service.write_telemetry_insight.side_effect = Exception("Connection failed")

    bridge = TelemetryToMemoryBridge(
        mock_memory_service, fallback_queue_path=temp_fallback_queue_path
    )

    # Persist should queue to fallback
    bridge.persist_insights([sample_ranked_issues[0]], run_id="test-run")

    # Check file exists and has content
    queue_file = Path(temp_fallback_queue_path)
    assert queue_file.exists()

    with open(queue_file, "r") as f:
        queue_data = json.load(f)
    assert len(queue_data) >= 1


def test_fallback_queue_loads_on_init(
    mock_memory_service, temp_fallback_queue_path, sample_ranked_issues
):
    """Test that fallback queue is loaded from file on initialization."""
    # Pre-populate the fallback queue file
    queue_file = Path(temp_fallback_queue_path)
    queue_file.parent.mkdir(parents=True, exist_ok=True)

    existing_queue = [
        {"insight": {"insight_id": "test-1", "insight_type": "cost_sink"}, "project_id": None}
    ]
    with open(queue_file, "w") as f:
        json.dump(existing_queue, f)

    # Create bridge - should load existing queue
    bridge = TelemetryToMemoryBridge(
        mock_memory_service, fallback_queue_path=temp_fallback_queue_path
    )

    assert bridge.get_fallback_queue_size() == 1


def test_drain_fallback_queue_on_recovery(
    mock_memory_service, temp_fallback_queue_path, sample_ranked_issues
):
    """Test that fallback queue is drained when circuit recovers."""
    # Pre-populate the fallback queue file
    queue_file = Path(temp_fallback_queue_path)
    queue_file.parent.mkdir(parents=True, exist_ok=True)

    existing_queue = [
        {
            "insight": {
                "insight_id": "test-1",
                "insight_type": "cost_sink",
                "phase_id": "test",
                "severity": "high",
                "description": "test",
                "metric_value": 100.0,
                "occurrences": 1,
                "suggested_action": "test",
            },
            "project_id": None,
        }
    ]
    with open(queue_file, "w") as f:
        json.dump(existing_queue, f)

    # Create bridge with working memory service
    bridge = TelemetryToMemoryBridge(
        mock_memory_service, fallback_queue_path=temp_fallback_queue_path
    )

    # Queue should be loaded
    assert bridge.get_fallback_queue_size() == 1

    # Persist new insights - should also drain queue
    bridge.persist_insights([sample_ranked_issues[0]], run_id="test-run")

    # Queue should now be empty (drained)
    assert bridge.get_fallback_queue_size() == 0

    # Both queued item and new item should have been persisted
    assert mock_memory_service.write_telemetry_insight.call_count >= 2


def test_circuit_breaker_state_accessor(bridge):
    """Test get_circuit_breaker_state returns valid state."""
    state = bridge.get_circuit_breaker_state()
    assert state in ["closed", "open", "half_open"]


def test_persist_with_circuit_breaker_success(bridge, mock_memory_service, sample_ranked_issues):
    """Test successful persistence through circuit breaker."""
    count = bridge.persist_insights(sample_ranked_issues, run_id="test-run")

    assert count == 3
    assert mock_memory_service.write_telemetry_insight.call_count == 3
    assert bridge.get_fallback_queue_size() == 0


@patch("src.autopack.telemetry.telemetry_to_memory_bridge.atexit")
def test_cleanup_registered(mock_atexit, mock_memory_service, temp_fallback_queue_path):
    """Test that cleanup is registered with atexit."""
    TelemetryToMemoryBridge(mock_memory_service, fallback_queue_path=temp_fallback_queue_path)
    mock_atexit.register.assert_called()
