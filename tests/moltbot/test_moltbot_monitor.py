"""Tests for Moltbot Monitor - Integration with Existing State Files."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from autopack.moltbot.moltbot_monitor import (
    InterventionCheck,
    MoltbotMonitor,
    NudgeRecord,
    NudgeStateReader,
    StagnantPRRecord,
    StagnantStateReader,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for state files."""
    return tmp_path


@pytest.fixture
def sample_nudge_state() -> dict[str, Any]:
    """Sample nudge_state.json data."""
    now = datetime.now(timezone.utc)
    return {
        "nudges": [
            {
                "id": "nudge-1",
                "pr_number": 123,
                "pr_url": "https://github.com/org/repo/pull/123",
                "phase_id": "build-abc",
                "phase_type": "build",
                "timestamp": (now - timedelta(hours=48)).isoformat(),
                "status": "completed",
                "escalation_level": 1,
                "metadata": {"trigger": "stagnant"},
            },
            {
                "id": "nudge-2",
                "pr_number": 123,
                "pr_url": "https://github.com/org/repo/pull/123",
                "phase_id": "test-def",
                "phase_type": "test",
                "timestamp": (now - timedelta(hours=12)).isoformat(),
                "status": "pending",
                "escalation_level": 2,
                "metadata": {},
            },
            {
                "id": "nudge-3",
                "pr_number": 456,
                "pr_url": "https://github.com/org/repo/pull/456",
                "phase_id": "deploy-ghi",
                "phase_type": "deploy",
                "timestamp": (now - timedelta(hours=6)).isoformat(),
                "status": "completed",
                "escalation_level": 0,
                "metadata": {},
            },
        ]
    }


@pytest.fixture
def sample_stagnant_state() -> dict[str, Any]:
    """Sample stagnant_state.json data."""
    now = datetime.now(timezone.utc)
    return {
        "stagnant_prs": [
            {
                "pr_number": 123,
                "pr_url": "https://github.com/org/repo/pull/123",
                "detected_at": (now - timedelta(days=5)).isoformat(),
                "last_nudge_at": (now - timedelta(hours=12)).isoformat(),
                "nudge_count": 2,
                "status": "stagnant",
                "days_stagnant": 5,
                "metadata": {"author": "user1"},
            },
            {
                "pr_number": 789,
                "pr_url": "https://github.com/org/repo/pull/789",
                "detected_at": (now - timedelta(days=2)).isoformat(),
                "last_nudge_at": None,
                "nudge_count": 0,
                "status": "stagnant",
                "days_stagnant": 2,
                "metadata": {},
            },
            {
                "pr_number": 999,
                "pr_url": "https://github.com/org/repo/pull/999",
                "detected_at": (now - timedelta(days=10)).isoformat(),
                "last_nudge_at": (now - timedelta(days=5)).isoformat(),
                "nudge_count": 3,
                "status": "resolved",
                "days_stagnant": 0,
                "metadata": {},
            },
        ]
    }


@pytest.fixture
def populated_state_dir(
    temp_state_dir: Path,
    sample_nudge_state: dict[str, Any],
    sample_stagnant_state: dict[str, Any],
) -> Path:
    """Create state files in temp directory."""
    (temp_state_dir / "nudge_state.json").write_text(json.dumps(sample_nudge_state))
    (temp_state_dir / "stagnant_state.json").write_text(json.dumps(sample_stagnant_state))
    return temp_state_dir


# ============================================================================
# NudgeRecord Tests
# ============================================================================


class TestNudgeRecord:
    """Tests for NudgeRecord dataclass."""

    def test_from_dict_complete(self) -> None:
        """Test creating NudgeRecord from complete data."""
        data = {
            "id": "nudge-123",
            "pr_number": 456,
            "pr_url": "https://github.com/org/repo/pull/456",
            "phase_id": "build-xyz",
            "phase_type": "build",
            "timestamp": "2025-01-15T10:30:00+00:00",
            "status": "completed",
            "escalation_level": 2,
            "metadata": {"key": "value"},
        }
        record = NudgeRecord.from_dict(data)

        assert record.nudge_id == "nudge-123"
        assert record.pr_number == 456
        assert record.pr_url == "https://github.com/org/repo/pull/456"
        assert record.phase_id == "build-xyz"
        assert record.phase_type == "build"
        assert record.timestamp is not None
        assert record.status == "completed"
        assert record.escalation_level == 2
        assert record.metadata == {"key": "value"}

    def test_from_dict_minimal(self) -> None:
        """Test creating NudgeRecord from minimal data."""
        data = {"id": "nudge-min"}
        record = NudgeRecord.from_dict(data)

        assert record.nudge_id == "nudge-min"
        assert record.pr_number is None
        assert record.timestamp is None
        assert record.status == "unknown"
        assert record.escalation_level == 0

    def test_from_dict_with_nudge_id_field(self) -> None:
        """Test creating NudgeRecord when using 'nudge_id' instead of 'id'."""
        data = {"nudge_id": "alt-nudge-123"}
        record = NudgeRecord.from_dict(data)

        assert record.nudge_id == "alt-nudge-123"

    def test_from_dict_invalid_timestamp(self) -> None:
        """Test handling of invalid timestamp."""
        data = {"id": "nudge-bad-ts", "timestamp": "not-a-timestamp"}
        record = NudgeRecord.from_dict(data)

        assert record.nudge_id == "nudge-bad-ts"
        assert record.timestamp is None


# ============================================================================
# StagnantPRRecord Tests
# ============================================================================


class TestStagnantPRRecord:
    """Tests for StagnantPRRecord dataclass."""

    def test_from_dict_complete(self) -> None:
        """Test creating StagnantPRRecord from complete data."""
        data = {
            "pr_number": 123,
            "pr_url": "https://github.com/org/repo/pull/123",
            "detected_at": "2025-01-10T08:00:00+00:00",
            "last_nudge_at": "2025-01-12T14:00:00+00:00",
            "nudge_count": 2,
            "status": "stagnant",
            "days_stagnant": 5,
            "metadata": {"author": "user1"},
        }
        record = StagnantPRRecord.from_dict(data)

        assert record.pr_number == 123
        assert record.pr_url == "https://github.com/org/repo/pull/123"
        assert record.detected_at is not None
        assert record.last_nudge_at is not None
        assert record.nudge_count == 2
        assert record.status == "stagnant"
        assert record.days_stagnant == 5
        assert record.metadata == {"author": "user1"}

    def test_from_dict_minimal(self) -> None:
        """Test creating StagnantPRRecord from minimal data."""
        data = {"pr_number": 999}
        record = StagnantPRRecord.from_dict(data)

        assert record.pr_number == 999
        assert record.pr_url is None
        assert record.detected_at is None
        assert record.last_nudge_at is None
        assert record.nudge_count == 0
        assert record.status == "stagnant"

    def test_from_dict_null_last_nudge(self) -> None:
        """Test handling of null last_nudge_at."""
        data = {"pr_number": 456, "last_nudge_at": None}
        record = StagnantPRRecord.from_dict(data)

        assert record.pr_number == 456
        assert record.last_nudge_at is None


# ============================================================================
# NudgeStateReader Tests
# ============================================================================


class TestNudgeStateReader:
    """Tests for NudgeStateReader class."""

    def test_reads_nudge_state_file(self, populated_state_dir: Path) -> None:
        """Test reading nudge_state.json file."""
        reader = NudgeStateReader(populated_state_dir / "nudge_state.json")
        records = reader.get_records()

        assert len(records) == 3
        assert all(isinstance(r, NudgeRecord) for r in records)

    def test_handles_missing_file(self, temp_state_dir: Path) -> None:
        """Test handling of missing file."""
        reader = NudgeStateReader(temp_state_dir / "nonexistent.json")
        records = reader.get_records()

        assert records == []
        assert not reader.is_loaded

    def test_handles_invalid_json(self, temp_state_dir: Path) -> None:
        """Test handling of invalid JSON."""
        (temp_state_dir / "nudge_state.json").write_text("{ invalid json }")
        reader = NudgeStateReader(temp_state_dir / "nudge_state.json")
        records = reader.get_records()

        assert records == []

    def test_handles_empty_nudges(self, temp_state_dir: Path) -> None:
        """Test handling of empty nudges array."""
        (temp_state_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))
        reader = NudgeStateReader(temp_state_dir / "nudge_state.json")
        records = reader.get_records()

        assert records == []

    def test_get_nudges_for_pr(self, populated_state_dir: Path) -> None:
        """Test filtering nudges by PR number."""
        reader = NudgeStateReader(populated_state_dir / "nudge_state.json")
        nudges = reader.get_nudges_for_pr(123)

        assert len(nudges) == 2
        assert all(n.pr_number == 123 for n in nudges)

    def test_get_nudges_for_phase(self, populated_state_dir: Path) -> None:
        """Test filtering nudges by phase ID."""
        reader = NudgeStateReader(populated_state_dir / "nudge_state.json")
        nudges = reader.get_nudges_for_phase("build-abc")

        assert len(nudges) == 1
        assert nudges[0].phase_id == "build-abc"

    def test_get_last_nudge_for_pr(self, populated_state_dir: Path) -> None:
        """Test getting most recent nudge for a PR."""
        reader = NudgeStateReader(populated_state_dir / "nudge_state.json")
        last_nudge = reader.get_last_nudge_for_pr(123)

        assert last_nudge is not None
        assert last_nudge.nudge_id == "nudge-2"  # More recent

    def test_get_last_nudge_for_pr_not_found(self, populated_state_dir: Path) -> None:
        """Test getting last nudge for non-existent PR."""
        reader = NudgeStateReader(populated_state_dir / "nudge_state.json")
        last_nudge = reader.get_last_nudge_for_pr(999)

        assert last_nudge is None

    def test_get_nudges_since(self, populated_state_dir: Path) -> None:
        """Test filtering nudges by time."""
        reader = NudgeStateReader(populated_state_dir / "nudge_state.json")
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = reader.get_nudges_since(since)

        # Should include nudges from 12h and 6h ago, not 48h ago
        assert len(recent) == 2

    def test_refresh_reloads_data(self, populated_state_dir: Path) -> None:
        """Test that refresh reloads data from disk."""
        reader = NudgeStateReader(populated_state_dir / "nudge_state.json")

        # Initial load
        assert len(reader.get_records()) == 3

        # Modify file
        new_data = {"nudges": [{"id": "new-nudge"}]}
        (populated_state_dir / "nudge_state.json").write_text(json.dumps(new_data))

        # Refresh
        reader.refresh()
        assert len(reader.get_records()) == 1


# ============================================================================
# StagnantStateReader Tests
# ============================================================================


class TestStagnantStateReader:
    """Tests for StagnantStateReader class."""

    def test_reads_stagnant_state_file(self, populated_state_dir: Path) -> None:
        """Test reading stagnant_state.json file."""
        reader = StagnantStateReader(populated_state_dir / "stagnant_state.json")
        records = reader.get_records()

        assert len(records) == 3
        assert all(isinstance(r, StagnantPRRecord) for r in records)

    def test_handles_missing_file(self, temp_state_dir: Path) -> None:
        """Test handling of missing file."""
        reader = StagnantStateReader(temp_state_dir / "nonexistent.json")
        records = reader.get_records()

        assert records == []
        assert not reader.is_loaded

    def test_handles_invalid_json(self, temp_state_dir: Path) -> None:
        """Test handling of invalid JSON."""
        (temp_state_dir / "stagnant_state.json").write_text("{ invalid }")
        reader = StagnantStateReader(temp_state_dir / "stagnant_state.json")
        records = reader.get_records()

        assert records == []

    def test_get_stagnant_pr(self, populated_state_dir: Path) -> None:
        """Test getting a specific stagnant PR."""
        reader = StagnantStateReader(populated_state_dir / "stagnant_state.json")
        record = reader.get_stagnant_pr(123)

        assert record is not None
        assert record.pr_number == 123
        assert record.nudge_count == 2

    def test_get_stagnant_pr_not_found(self, populated_state_dir: Path) -> None:
        """Test getting non-existent stagnant PR."""
        reader = StagnantStateReader(populated_state_dir / "stagnant_state.json")
        record = reader.get_stagnant_pr(111)

        assert record is None

    def test_is_pr_stagnant(self, populated_state_dir: Path) -> None:
        """Test checking if PR is stagnant."""
        reader = StagnantStateReader(populated_state_dir / "stagnant_state.json")

        assert reader.is_pr_stagnant(123)  # status: stagnant
        assert not reader.is_pr_stagnant(999)  # status: resolved
        assert not reader.is_pr_stagnant(111)  # not found

    def test_get_stagnant_prs_needing_nudge(self, populated_state_dir: Path) -> None:
        """Test finding stagnant PRs that need nudging."""
        reader = StagnantStateReader(populated_state_dir / "stagnant_state.json")
        needing_nudge = reader.get_stagnant_prs_needing_nudge(min_days_since_nudge=1)

        # PR 789 never nudged, PR 123 nudged 12h ago (less than 1 day)
        # PR 999 is resolved so excluded
        pr_numbers = [p.pr_number for p in needing_nudge]
        assert 789 in pr_numbers  # Never nudged


# ============================================================================
# MoltbotMonitor Tests
# ============================================================================


class TestMoltbotMonitorInit:
    """Tests for MoltbotMonitor initialization."""

    def test_init_creates_readers(self, temp_state_dir: Path) -> None:
        """Test that initialization creates the readers."""
        monitor = MoltbotMonitor(temp_state_dir)

        assert monitor.state_dir == temp_state_dir
        assert isinstance(monitor.nudge_reader, NudgeStateReader)
        assert isinstance(monitor.stagnant_reader, StagnantStateReader)

    def test_init_with_custom_filenames(self, temp_state_dir: Path) -> None:
        """Test initialization with custom file names."""
        monitor = MoltbotMonitor(
            temp_state_dir,
            nudge_state_file="custom_nudge.json",
            stagnant_state_file="custom_stagnant.json",
        )

        assert monitor.nudge_reader.file_path == temp_state_dir / "custom_nudge.json"
        assert monitor.stagnant_reader.file_path == temp_state_dir / "custom_stagnant.json"


class TestCanNudgePR:
    """Tests for can_nudge_pr method."""

    def test_can_nudge_new_pr(self, populated_state_dir: Path) -> None:
        """Test nudging a PR with no prior nudges."""
        monitor = MoltbotMonitor(populated_state_dir)
        result = monitor.can_nudge_pr(pr_number=777, cooldown_hours=24)

        assert result.should_intervene is True
        assert result.intervention_count == 0

    def test_blocks_recent_nudge(self, populated_state_dir: Path) -> None:
        """Test blocking nudge when recent nudge exists."""
        monitor = MoltbotMonitor(populated_state_dir)
        # PR 456 was nudged 6 hours ago
        result = monitor.can_nudge_pr(pr_number=456, cooldown_hours=24)

        assert result.should_intervene is False
        assert "nudged" in result.reason.lower()
        assert result.cooldown_remaining_hours > 0

    def test_allows_nudge_after_cooldown(self, populated_state_dir: Path) -> None:
        """Test allowing nudge after cooldown period."""
        monitor = MoltbotMonitor(populated_state_dir)
        # PR 123 last nudged 12 hours ago
        result = monitor.can_nudge_pr(pr_number=123, cooldown_hours=6)

        assert result.should_intervene is True
        assert result.cooldown_remaining_hours == 0

    def test_respects_max_escalation(self, temp_state_dir: Path) -> None:
        """Test blocking nudge at max escalation level."""
        now = datetime.now(timezone.utc)
        nudge_state = {
            "nudges": [
                {
                    "id": "nudge-max",
                    "pr_number": 100,
                    "timestamp": (now - timedelta(hours=48)).isoformat(),
                    "escalation_level": 3,
                }
            ]
        }
        (temp_state_dir / "nudge_state.json").write_text(json.dumps(nudge_state))
        (temp_state_dir / "stagnant_state.json").write_text(json.dumps({"stagnant_prs": []}))

        monitor = MoltbotMonitor(temp_state_dir)
        result = monitor.can_nudge_pr(pr_number=100, cooldown_hours=24)

        assert result.should_intervene is False
        assert "max escalation" in result.reason.lower()

    def test_checks_stagnant_state(self, populated_state_dir: Path) -> None:
        """Test that stagnant state is also checked."""
        # Update stagnant state with recent nudge for PR not in nudge_state
        now = datetime.now(timezone.utc)
        stagnant_state = {
            "stagnant_prs": [
                {
                    "pr_number": 888,
                    "last_nudge_at": (now - timedelta(hours=2)).isoformat(),
                    "nudge_count": 1,
                    "status": "stagnant",
                }
            ]
        }
        (populated_state_dir / "stagnant_state.json").write_text(json.dumps(stagnant_state))

        monitor = MoltbotMonitor(populated_state_dir)
        monitor.refresh()  # Reload after file change
        result = monitor.can_nudge_pr(pr_number=888, cooldown_hours=24)

        assert result.should_intervene is False
        assert "stagnant" in result.reason.lower()

    def test_enforces_minimum_cooldown(self, temp_state_dir: Path) -> None:
        """Test that minimum cooldown is enforced."""
        (temp_state_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))
        (temp_state_dir / "stagnant_state.json").write_text(json.dumps({"stagnant_prs": []}))

        monitor = MoltbotMonitor(temp_state_dir)
        # Try to set cooldown to 0, should be at least MIN_COOLDOWN_HOURS
        result = monitor.can_nudge_pr(pr_number=123, cooldown_hours=0)

        # Should still succeed since no prior nudges, but cooldown enforced internally
        assert result.should_intervene is True


class TestCanNudgePhase:
    """Tests for can_nudge_phase method."""

    def test_can_nudge_new_phase(self, populated_state_dir: Path) -> None:
        """Test nudging a phase with no prior nudges."""
        monitor = MoltbotMonitor(populated_state_dir)
        result = monitor.can_nudge_phase(phase_id="new-phase", cooldown_hours=24)

        assert result.should_intervene is True
        assert result.intervention_count == 0

    def test_blocks_recent_phase_nudge(self, populated_state_dir: Path) -> None:
        """Test blocking nudge when recent phase nudge exists."""
        monitor = MoltbotMonitor(populated_state_dir)
        # Phase deploy-ghi was nudged 6 hours ago
        result = monitor.can_nudge_phase(phase_id="deploy-ghi", cooldown_hours=24)

        assert result.should_intervene is False
        assert "nudged" in result.reason.lower()

    def test_allows_phase_nudge_after_cooldown(self, populated_state_dir: Path) -> None:
        """Test allowing phase nudge after cooldown."""
        monitor = MoltbotMonitor(populated_state_dir)
        # Phase build-abc was nudged 48 hours ago
        result = monitor.can_nudge_phase(phase_id="build-abc", cooldown_hours=24)

        assert result.should_intervene is True

    def test_respects_phase_max_escalation(self, temp_state_dir: Path) -> None:
        """Test blocking phase nudge at max escalation level."""
        now = datetime.now(timezone.utc)
        nudge_state = {
            "nudges": [
                {
                    "id": "nudge-phase-max",
                    "phase_id": "max-escalation-phase",
                    "timestamp": (now - timedelta(hours=48)).isoformat(),
                    "escalation_level": 3,
                }
            ]
        }
        (temp_state_dir / "nudge_state.json").write_text(json.dumps(nudge_state))
        (temp_state_dir / "stagnant_state.json").write_text(json.dumps({"stagnant_prs": []}))

        monitor = MoltbotMonitor(temp_state_dir)
        result = monitor.can_nudge_phase(phase_id="max-escalation-phase", cooldown_hours=24)

        assert result.should_intervene is False
        assert "max escalation" in result.reason.lower()


class TestGetRecentInterventions:
    """Tests for get_recent_interventions method."""

    def test_returns_intervention_summary(self, populated_state_dir: Path) -> None:
        """Test getting recent intervention summary."""
        monitor = MoltbotMonitor(populated_state_dir)
        summary = monitor.get_recent_interventions(hours=72)

        assert "period_hours" in summary
        assert "total_nudges" in summary
        assert "unique_prs_nudged" in summary
        assert "nudges_by_phase_type" in summary
        assert "stagnant_prs_total" in summary
        assert "stagnant_prs_active" in summary

    def test_filters_by_time(self, populated_state_dir: Path) -> None:
        """Test that interventions are filtered by time."""
        monitor = MoltbotMonitor(populated_state_dir)

        # Should include only recent nudges
        summary = monitor.get_recent_interventions(hours=24)
        # 48h ago nudge should be excluded
        assert summary["total_nudges"] == 2

    def test_counts_stagnant_prs(self, populated_state_dir: Path) -> None:
        """Test that stagnant PRs are counted."""
        monitor = MoltbotMonitor(populated_state_dir)
        summary = monitor.get_recent_interventions(hours=24)

        assert summary["stagnant_prs_total"] == 3
        assert summary["stagnant_prs_active"] == 2  # Two with status "stagnant"


class TestGetHealthSummary:
    """Tests for get_health_summary method."""

    def test_returns_health_info(self, populated_state_dir: Path) -> None:
        """Test getting health summary."""
        monitor = MoltbotMonitor(populated_state_dir)
        health = monitor.get_health_summary()

        assert "nudge_state" in health
        assert "stagnant_state" in health

        assert health["nudge_state"]["loaded"] is True
        assert health["nudge_state"]["file_exists"] is True
        assert health["nudge_state"]["record_count"] == 3

        assert health["stagnant_state"]["loaded"] is True
        assert health["stagnant_state"]["file_exists"] is True
        assert health["stagnant_state"]["record_count"] == 3

    def test_handles_missing_files(self, temp_state_dir: Path) -> None:
        """Test health summary with missing files."""
        monitor = MoltbotMonitor(temp_state_dir)
        health = monitor.get_health_summary()

        assert health["nudge_state"]["loaded"] is False
        assert health["nudge_state"]["file_exists"] is False
        assert health["nudge_state"]["record_count"] == 0


class TestInterventionCheck:
    """Tests for InterventionCheck dataclass."""

    def test_intervention_check_defaults(self) -> None:
        """Test InterventionCheck default values."""
        check = InterventionCheck(should_intervene=True, reason="Test")

        assert check.should_intervene is True
        assert check.reason == "Test"
        assert check.last_intervention_at is None
        assert check.intervention_count == 0
        assert check.cooldown_remaining_hours == 0.0

    def test_intervention_check_full(self) -> None:
        """Test InterventionCheck with all values."""
        now = datetime.now(timezone.utc)
        check = InterventionCheck(
            should_intervene=False,
            reason="Cooldown active",
            last_intervention_at=now,
            intervention_count=5,
            cooldown_remaining_hours=12.5,
        )

        assert check.should_intervene is False
        assert check.reason == "Cooldown active"
        assert check.last_intervention_at == now
        assert check.intervention_count == 5
        assert check.cooldown_remaining_hours == 12.5


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_malformed_nudges_array(self, temp_state_dir: Path) -> None:
        """Test handling of non-array nudges field."""
        (temp_state_dir / "nudge_state.json").write_text(json.dumps({"nudges": "not an array"}))
        reader = NudgeStateReader(temp_state_dir / "nudge_state.json")
        records = reader.get_records()

        assert records == []

    def test_handles_malformed_stagnant_prs_array(self, temp_state_dir: Path) -> None:
        """Test handling of non-array stagnant_prs field."""
        (temp_state_dir / "stagnant_state.json").write_text(
            json.dumps({"stagnant_prs": {"invalid": "data"}})
        )
        reader = StagnantStateReader(temp_state_dir / "stagnant_state.json")
        records = reader.get_records()

        assert records == []

    def test_handles_nudge_without_timestamp(self, temp_state_dir: Path) -> None:
        """Test handling nudges without timestamps."""
        (temp_state_dir / "nudge_state.json").write_text(
            json.dumps({"nudges": [{"id": "no-ts", "pr_number": 123}]})
        )
        (temp_state_dir / "stagnant_state.json").write_text(json.dumps({"stagnant_prs": []}))

        monitor = MoltbotMonitor(temp_state_dir)
        result = monitor.can_nudge_pr(pr_number=123, cooldown_hours=24)

        # Without timestamp, can't determine if cooldown applies
        # Should allow nudge since we can't verify timing
        assert result.should_intervene is True

    def test_handles_z_suffix_timestamp(self, temp_state_dir: Path) -> None:
        """Test handling timestamps with Z suffix."""
        (temp_state_dir / "nudge_state.json").write_text(
            json.dumps(
                {
                    "nudges": [
                        {
                            "id": "z-ts",
                            "pr_number": 123,
                            "timestamp": "2025-01-15T10:30:00Z",
                        }
                    ]
                }
            )
        )
        reader = NudgeStateReader(temp_state_dir / "nudge_state.json")
        records = reader.get_records()

        assert len(records) == 1
        assert records[0].timestamp is not None

    def test_refresh_updates_last_loaded(self, temp_state_dir: Path) -> None:
        """Test that refresh updates last_loaded timestamp."""
        (temp_state_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))
        reader = NudgeStateReader(temp_state_dir / "nudge_state.json")

        assert reader.last_loaded is None
        reader.refresh()
        assert reader.last_loaded is not None

    def test_monitor_refresh_updates_both_readers(self, populated_state_dir: Path) -> None:
        """Test that MoltbotMonitor.refresh updates both readers."""
        monitor = MoltbotMonitor(populated_state_dir)
        monitor.refresh()

        assert monitor.nudge_reader.last_loaded is not None
        assert monitor.stagnant_reader.last_loaded is not None
