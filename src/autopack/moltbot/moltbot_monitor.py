"""Moltbot Monitor - Integration with Existing State Files.

Read-only integration with OCR Handler's stagnant_state.json and PR Monitor's
nudge_state.json to determine when previous nudges were sent and avoid
duplicate interventions.

This module provides:
- StateFileReader: Base class for reading JSON state files
- NudgeStateReader: Reads nudge_state.json to check nudge history
- StagnantStateReader: Reads stagnant_state.json to check stagnant PR status
- MoltbotMonitor: Main orchestrator that prevents duplicate interventions
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NudgeRecord:
    """Represents a single nudge event from nudge_state.json."""

    nudge_id: str
    pr_number: int | None = None
    pr_url: str | None = None
    phase_id: str | None = None
    phase_type: str | None = None
    timestamp: datetime | None = None
    status: str = "unknown"
    escalation_level: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NudgeRecord:
        """Create a NudgeRecord from a dictionary."""
        timestamp = None
        ts_str = data.get("timestamp")
        if ts_str:
            try:
                timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            nudge_id=data.get("id", data.get("nudge_id", "")),
            pr_number=data.get("pr_number"),
            pr_url=data.get("pr_url"),
            phase_id=data.get("phase_id"),
            phase_type=data.get("phase_type"),
            timestamp=timestamp,
            status=data.get("status", "unknown"),
            escalation_level=data.get("escalation_level", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StagnantPRRecord:
    """Represents a stagnant PR record from stagnant_state.json."""

    pr_number: int
    pr_url: str | None = None
    detected_at: datetime | None = None
    last_nudge_at: datetime | None = None
    nudge_count: int = 0
    status: str = "stagnant"
    days_stagnant: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StagnantPRRecord:
        """Create a StagnantPRRecord from a dictionary."""
        detected_at = None
        last_nudge_at = None

        detected_str = data.get("detected_at")
        if detected_str:
            try:
                detected_at = datetime.fromisoformat(detected_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        nudge_str = data.get("last_nudge_at")
        if nudge_str:
            try:
                last_nudge_at = datetime.fromisoformat(nudge_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            pr_number=data.get("pr_number", 0),
            pr_url=data.get("pr_url"),
            detected_at=detected_at,
            last_nudge_at=last_nudge_at,
            nudge_count=data.get("nudge_count", 0),
            status=data.get("status", "stagnant"),
            days_stagnant=data.get("days_stagnant", 0),
            metadata=data.get("metadata", {}),
        )


class StateFileReader(ABC):
    """Abstract base class for reading JSON state files.

    Provides common functionality for loading and caching JSON state files
    in a read-only manner. Subclasses implement specific parsing logic.
    """

    def __init__(self, file_path: Path | str) -> None:
        """Initialize the state file reader.

        Args:
            file_path: Path to the JSON state file
        """
        self.file_path = Path(file_path)
        self._data: dict[str, Any] | None = None
        self._last_loaded: datetime | None = None

    def _load_file(self) -> dict[str, Any]:
        """Load the JSON file from disk.

        Returns:
            Parsed JSON data or empty dict if file doesn't exist or is invalid
        """
        if not self.file_path.exists():
            logger.debug("State file not found: %s", self.file_path)
            return {}

        try:
            with open(self.file_path, encoding="utf-8") as f:
                data = json.load(f)
                logger.debug("Loaded state file %s", self.file_path)
                return data
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse state file %s: %s", self.file_path, e)
            return {}
        except OSError as e:
            logger.warning("Failed to read state file %s: %s", self.file_path, e)
            return {}

    def refresh(self) -> None:
        """Reload the state file from disk."""
        self._data = self._load_file()
        self._last_loaded = datetime.now(timezone.utc)

    @property
    def data(self) -> dict[str, Any]:
        """Get the cached data, loading if necessary."""
        if self._data is None:
            self.refresh()
        return self._data or {}

    @property
    def is_loaded(self) -> bool:
        """Check if the state file has been successfully loaded."""
        return self._data is not None and bool(self._data)

    @property
    def last_loaded(self) -> datetime | None:
        """Get the timestamp of the last successful load."""
        return self._last_loaded

    @abstractmethod
    def get_records(self) -> list[Any]:
        """Get all records from the state file."""
        pass


class NudgeStateReader(StateFileReader):
    """Reads and parses PR Monitor's nudge_state.json file.

    This reader provides access to nudge history, allowing the system
    to determine when previous nudges were sent to avoid duplicates.

    Expected file structure:
    {
        "nudges": [
            {
                "id": "nudge-123",
                "pr_number": 456,
                "pr_url": "https://github.com/...",
                "phase_id": "phase-abc",
                "phase_type": "build",
                "timestamp": "2025-01-15T10:30:00Z",
                "status": "completed",
                "escalation_level": 1,
                "metadata": {...}
            },
            ...
        ]
    }
    """

    def get_records(self) -> list[NudgeRecord]:
        """Get all nudge records from the state file.

        Returns:
            List of NudgeRecord objects
        """
        records = []
        nudges = self.data.get("nudges", [])

        if not isinstance(nudges, list):
            logger.warning("nudge_state.json has invalid 'nudges' field")
            return records

        for nudge_data in nudges:
            if isinstance(nudge_data, dict):
                try:
                    records.append(NudgeRecord.from_dict(nudge_data))
                except (KeyError, ValueError) as e:
                    logger.debug("Skipping invalid nudge record: %s", e)

        return records

    def get_nudges_for_pr(self, pr_number: int) -> list[NudgeRecord]:
        """Get all nudges sent for a specific PR.

        Args:
            pr_number: The PR number to look up

        Returns:
            List of NudgeRecord objects for the specified PR
        """
        return [r for r in self.get_records() if r.pr_number == pr_number]

    def get_nudges_for_phase(self, phase_id: str) -> list[NudgeRecord]:
        """Get all nudges sent for a specific phase.

        Args:
            phase_id: The phase ID to look up

        Returns:
            List of NudgeRecord objects for the specified phase
        """
        return [r for r in self.get_records() if r.phase_id == phase_id]

    def get_last_nudge_for_pr(self, pr_number: int) -> NudgeRecord | None:
        """Get the most recent nudge for a specific PR.

        Args:
            pr_number: The PR number to look up

        Returns:
            The most recent NudgeRecord, or None if no nudges found
        """
        nudges = self.get_nudges_for_pr(pr_number)
        if not nudges:
            return None

        # Sort by timestamp, most recent first
        nudges_with_ts = [n for n in nudges if n.timestamp is not None]
        if not nudges_with_ts:
            return nudges[-1] if nudges else None

        return max(nudges_with_ts, key=lambda n: n.timestamp)  # type: ignore[arg-type,return-value]

    def get_nudges_since(self, since: datetime) -> list[NudgeRecord]:
        """Get all nudges sent since a specific time.

        Args:
            since: The datetime to filter from

        Returns:
            List of NudgeRecord objects sent after the specified time
        """
        return [r for r in self.get_records() if r.timestamp is not None and r.timestamp >= since]


class StagnantStateReader(StateFileReader):
    """Reads and parses OCR Handler's stagnant_state.json file.

    This reader provides access to stagnant PR status, helping identify
    PRs that need attention and tracking intervention history.

    Expected file structure:
    {
        "stagnant_prs": [
            {
                "pr_number": 123,
                "pr_url": "https://github.com/...",
                "detected_at": "2025-01-10T08:00:00Z",
                "last_nudge_at": "2025-01-12T14:00:00Z",
                "nudge_count": 2,
                "status": "stagnant",
                "days_stagnant": 5,
                "metadata": {...}
            },
            ...
        ]
    }
    """

    def get_records(self) -> list[StagnantPRRecord]:
        """Get all stagnant PR records from the state file.

        Returns:
            List of StagnantPRRecord objects
        """
        records = []
        stagnant_prs = self.data.get("stagnant_prs", [])

        if not isinstance(stagnant_prs, list):
            logger.warning("stagnant_state.json has invalid 'stagnant_prs' field")
            return records

        for pr_data in stagnant_prs:
            if isinstance(pr_data, dict):
                try:
                    records.append(StagnantPRRecord.from_dict(pr_data))
                except (KeyError, ValueError) as e:
                    logger.debug("Skipping invalid stagnant PR record: %s", e)

        return records

    def get_stagnant_pr(self, pr_number: int) -> StagnantPRRecord | None:
        """Get the stagnant record for a specific PR.

        Args:
            pr_number: The PR number to look up

        Returns:
            StagnantPRRecord if found, None otherwise
        """
        for record in self.get_records():
            if record.pr_number == pr_number:
                return record
        return None

    def is_pr_stagnant(self, pr_number: int) -> bool:
        """Check if a PR is currently marked as stagnant.

        Args:
            pr_number: The PR number to check

        Returns:
            True if the PR is marked as stagnant
        """
        record = self.get_stagnant_pr(pr_number)
        return record is not None and record.status == "stagnant"

    def get_stagnant_prs_needing_nudge(
        self, min_days_since_nudge: int = 1
    ) -> list[StagnantPRRecord]:
        """Get stagnant PRs that haven't been nudged recently.

        Args:
            min_days_since_nudge: Minimum days since last nudge before
                another nudge is warranted

        Returns:
            List of StagnantPRRecord objects that may need nudging
        """
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=min_days_since_nudge)
        results = []

        for record in self.get_records():
            if record.status != "stagnant":
                continue

            # Never nudged, or nudged before threshold
            if record.last_nudge_at is None or record.last_nudge_at < threshold:
                results.append(record)

        return results


@dataclass
class InterventionCheck:
    """Result of checking whether an intervention should proceed."""

    should_intervene: bool
    reason: str
    last_intervention_at: datetime | None = None
    intervention_count: int = 0
    cooldown_remaining_hours: float = 0.0


class MoltbotMonitor:
    """Main orchestrator for Moltbot state integration.

    Combines NudgeStateReader and StagnantStateReader to provide
    unified duplicate intervention prevention logic.

    Usage:
        monitor = MoltbotMonitor(state_dir=Path(".state"))

        # Check if we can nudge a PR
        check = monitor.can_nudge_pr(pr_number=123, cooldown_hours=24)
        if check.should_intervene:
            # Proceed with nudge
            ...
        else:
            print(f"Skipping: {check.reason}")

        # Check if we can nudge a phase
        check = monitor.can_nudge_phase(phase_id="build-456", cooldown_hours=12)
    """

    # Default file names
    NUDGE_STATE_FILE = "nudge_state.json"
    STAGNANT_STATE_FILE = "stagnant_state.json"

    # Default cooldown periods
    DEFAULT_COOLDOWN_HOURS = 24.0
    MIN_COOLDOWN_HOURS = 1.0
    MAX_ESCALATION_LEVEL = 3

    def __init__(
        self,
        state_dir: Path | str,
        nudge_state_file: str | None = None,
        stagnant_state_file: str | None = None,
    ) -> None:
        """Initialize the Moltbot monitor.

        Args:
            state_dir: Directory containing state files
            nudge_state_file: Override filename for nudge state
            stagnant_state_file: Override filename for stagnant state
        """
        self.state_dir = Path(state_dir)
        self.nudge_reader = NudgeStateReader(
            self.state_dir / (nudge_state_file or self.NUDGE_STATE_FILE)
        )
        self.stagnant_reader = StagnantStateReader(
            self.state_dir / (stagnant_state_file or self.STAGNANT_STATE_FILE)
        )

    def refresh(self) -> None:
        """Refresh all state file data from disk."""
        self.nudge_reader.refresh()
        self.stagnant_reader.refresh()

    def can_nudge_pr(
        self, pr_number: int, cooldown_hours: float | None = None
    ) -> InterventionCheck:
        """Check if a nudge can be sent for a PR.

        Checks both nudge history and stagnant state to determine if
        an intervention is appropriate.

        Args:
            pr_number: The PR number to check
            cooldown_hours: Hours to wait between nudges (default: 24)

        Returns:
            InterventionCheck with decision and reasoning
        """
        cooldown = cooldown_hours if cooldown_hours is not None else self.DEFAULT_COOLDOWN_HOURS
        cooldown = max(cooldown, self.MIN_COOLDOWN_HOURS)
        now = datetime.now(timezone.utc)

        # Check nudge history
        nudges = self.nudge_reader.get_nudges_for_pr(pr_number)
        last_nudge = self.nudge_reader.get_last_nudge_for_pr(pr_number)

        if last_nudge and last_nudge.timestamp:
            time_since = now - last_nudge.timestamp
            hours_since = time_since.total_seconds() / 3600

            if hours_since < cooldown:
                remaining = cooldown - hours_since
                return InterventionCheck(
                    should_intervene=False,
                    reason=f"PR #{pr_number} nudged {hours_since:.1f}h ago, cooldown is {cooldown}h",
                    last_intervention_at=last_nudge.timestamp,
                    intervention_count=len(nudges),
                    cooldown_remaining_hours=remaining,
                )

            # Check escalation level
            if last_nudge.escalation_level >= self.MAX_ESCALATION_LEVEL:
                return InterventionCheck(
                    should_intervene=False,
                    reason=f"PR #{pr_number} at max escalation level ({last_nudge.escalation_level})",
                    last_intervention_at=last_nudge.timestamp,
                    intervention_count=len(nudges),
                    cooldown_remaining_hours=0.0,
                )

        # Check stagnant state for additional context
        stagnant_record = self.stagnant_reader.get_stagnant_pr(pr_number)
        if stagnant_record:
            if stagnant_record.last_nudge_at:
                time_since = now - stagnant_record.last_nudge_at
                hours_since = time_since.total_seconds() / 3600

                if hours_since < cooldown:
                    remaining = cooldown - hours_since
                    return InterventionCheck(
                        should_intervene=False,
                        reason=f"Stagnant PR #{pr_number} nudged {hours_since:.1f}h ago",
                        last_intervention_at=stagnant_record.last_nudge_at,
                        intervention_count=stagnant_record.nudge_count,
                        cooldown_remaining_hours=remaining,
                    )

        # All checks passed
        return InterventionCheck(
            should_intervene=True,
            reason=f"PR #{pr_number} eligible for nudge",
            last_intervention_at=last_nudge.timestamp if last_nudge else None,
            intervention_count=len(nudges),
            cooldown_remaining_hours=0.0,
        )

    def can_nudge_phase(
        self, phase_id: str, cooldown_hours: float | None = None
    ) -> InterventionCheck:
        """Check if a nudge can be sent for a phase.

        Args:
            phase_id: The phase ID to check
            cooldown_hours: Hours to wait between nudges (default: 24)

        Returns:
            InterventionCheck with decision and reasoning
        """
        cooldown = cooldown_hours if cooldown_hours is not None else self.DEFAULT_COOLDOWN_HOURS
        cooldown = max(cooldown, self.MIN_COOLDOWN_HOURS)
        now = datetime.now(timezone.utc)

        # Check nudge history for this phase
        nudges = self.nudge_reader.get_nudges_for_phase(phase_id)

        if nudges:
            # Find the most recent nudge
            nudges_with_ts = [n for n in nudges if n.timestamp is not None]
            if nudges_with_ts:
                last_nudge = max(nudges_with_ts, key=lambda n: n.timestamp)  # type: ignore[arg-type,return-value]
                time_since = now - last_nudge.timestamp  # type: ignore[operator]
                hours_since = time_since.total_seconds() / 3600

                if hours_since < cooldown:
                    remaining = cooldown - hours_since
                    return InterventionCheck(
                        should_intervene=False,
                        reason=f"Phase {phase_id} nudged {hours_since:.1f}h ago, cooldown is {cooldown}h",
                        last_intervention_at=last_nudge.timestamp,
                        intervention_count=len(nudges),
                        cooldown_remaining_hours=remaining,
                    )

                # Check escalation level
                if last_nudge.escalation_level >= self.MAX_ESCALATION_LEVEL:
                    return InterventionCheck(
                        should_intervene=False,
                        reason=f"Phase {phase_id} at max escalation level ({last_nudge.escalation_level})",
                        last_intervention_at=last_nudge.timestamp,
                        intervention_count=len(nudges),
                        cooldown_remaining_hours=0.0,
                    )

        # All checks passed
        last_ts = None
        if nudges:
            nudges_with_ts = [n for n in nudges if n.timestamp is not None]
            if nudges_with_ts:
                last_ts = max(n.timestamp for n in nudges_with_ts if n.timestamp)

        return InterventionCheck(
            should_intervene=True,
            reason=f"Phase {phase_id} eligible for nudge",
            last_intervention_at=last_ts,
            intervention_count=len(nudges),
            cooldown_remaining_hours=0.0,
        )

    def get_recent_interventions(self, hours: float = 24.0) -> dict[str, Any]:
        """Get summary of recent interventions across all state files.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary with intervention statistics
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        recent_nudges = self.nudge_reader.get_nudges_since(since)
        stagnant_prs = self.stagnant_reader.get_records()

        # Group nudges by PR
        nudges_by_pr: dict[int, list[NudgeRecord]] = {}
        for nudge in recent_nudges:
            if nudge.pr_number is not None:
                if nudge.pr_number not in nudges_by_pr:
                    nudges_by_pr[nudge.pr_number] = []
                nudges_by_pr[nudge.pr_number].append(nudge)

        # Group nudges by phase type
        nudges_by_type: dict[str, int] = {}
        for nudge in recent_nudges:
            phase_type = nudge.phase_type or "unknown"
            nudges_by_type[phase_type] = nudges_by_type.get(phase_type, 0) + 1

        return {
            "period_hours": hours,
            "total_nudges": len(recent_nudges),
            "unique_prs_nudged": len(nudges_by_pr),
            "nudges_by_phase_type": nudges_by_type,
            "stagnant_prs_total": len(stagnant_prs),
            "stagnant_prs_active": len([p for p in stagnant_prs if p.status == "stagnant"]),
        }

    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary of the monitoring state.

        Returns:
            Dictionary with state file health information
        """
        # Get records first to trigger data loading before checking is_loaded
        nudge_records = self.nudge_reader.get_records()
        stagnant_records = self.stagnant_reader.get_records()

        return {
            "nudge_state": {
                "loaded": self.nudge_reader.is_loaded,
                "file_exists": self.nudge_reader.file_path.exists(),
                "last_loaded": (
                    self.nudge_reader.last_loaded.isoformat()
                    if self.nudge_reader.last_loaded
                    else None
                ),
                "record_count": len(nudge_records),
            },
            "stagnant_state": {
                "loaded": self.stagnant_reader.is_loaded,
                "file_exists": self.stagnant_reader.file_path.exists(),
                "last_loaded": (
                    self.stagnant_reader.last_loaded.isoformat()
                    if self.stagnant_reader.last_loaded
                    else None
                ),
                "record_count": len(stagnant_records),
            },
        }
