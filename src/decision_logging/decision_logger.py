"""Structured decision logger for tracking system decisions with reasoning.

This module provides a structured way to log and audit all system decisions
including wave splits, escalations, nudges, phase transitions, and retries.
Each decision is recorded with full context, options considered, and reasoning.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

DecisionType = Literal[
    "wave_split",
    "escalation",
    "nudge",
    "phase_transition",
    "retry",
    "ci_failure_categorization",
    "slot_assignment",
    "autonomous_discovery",
    "wave_planning",
]


@dataclass
class Decision:
    """Represents a system decision with full context and reasoning.

    Attributes:
        timestamp: When the decision was made.
        decision_type: Category of decision (wave_split, escalation, etc.).
        context: Relevant state and information at decision time.
        options_considered: List of options that were evaluated.
        chosen_option: The option that was selected.
        reasoning: Explanation of why this option was chosen.
        outcome: Result of the decision (filled in later if applicable).
    """

    timestamp: datetime
    decision_type: DecisionType
    context: Dict[str, Any]
    options_considered: List[str]
    chosen_option: str
    reasoning: str
    outcome: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to a JSON-serializable dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Decision":
        """Create a Decision from a dictionary."""
        data = data.copy()
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class DecisionLog:
    """Container for a collection of decisions with metadata."""

    decisions: List[Decision] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision log to a JSON-serializable dictionary."""
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "decisions": [d.to_dict() for d in self.decisions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionLog":
        """Create a DecisionLog from a dictionary."""
        return cls(
            version=data.get("version", "1.0.0"),
            created_at=datetime.fromisoformat(data["created_at"]),
            decisions=[Decision.from_dict(d) for d in data.get("decisions", [])],
        )


class DecisionLogger:
    """Logger for tracking and persisting system decisions.

    Provides methods to log decisions with full context and reasoning,
    query decisions by type, and persist decisions to JSON files.
    """

    def __init__(self, log_path: Optional[str] = None):
        """Initialize the decision logger.

        Args:
            log_path: Path to the decision log file. Defaults to
                     AUTOPACK_DECISION_LOG env var or .autopack/decision_log.json.
        """
        default_path = ".autopack/decision_log.json"
        self.log_path = Path(log_path or os.environ.get("AUTOPACK_DECISION_LOG", default_path))
        self._log: Optional[DecisionLog] = None
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        """Ensure the log directory exists."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_log(self) -> DecisionLog:
        """Load the decision log from disk, or create a new one."""
        if self._log is not None:
            return self._log

        if self.log_path.exists():
            try:
                with open(self.log_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._log = DecisionLog.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError):
                self._log = DecisionLog()
        else:
            self._log = DecisionLog()

        return self._log

    def _save_log(self) -> None:
        """Save the decision log to disk."""
        if self._log is not None:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(self._log.to_dict(), f, indent=2)

    def log_decision(self, decision: Decision) -> None:
        """Log a decision with full context.

        Args:
            decision: The decision to log.
        """
        log = self._load_log()
        log.decisions.append(decision)
        self._save_log()

    def create_and_log_decision(
        self,
        decision_type: DecisionType,
        context: Dict[str, Any],
        options_considered: List[str],
        chosen_option: str,
        reasoning: str,
        outcome: Optional[str] = None,
    ) -> Decision:
        """Create and log a decision in one call.

        Args:
            decision_type: Category of decision.
            context: Relevant state at decision time.
            options_considered: List of options evaluated.
            chosen_option: The selected option.
            reasoning: Why this option was chosen.
            outcome: Optional result of the decision.

        Returns:
            The created Decision object.
        """
        decision = Decision(
            timestamp=datetime.now(),
            decision_type=decision_type,
            context=context,
            options_considered=options_considered,
            chosen_option=chosen_option,
            reasoning=reasoning,
            outcome=outcome,
        )
        self.log_decision(decision)
        return decision

    def update_outcome(self, decision_index: int, outcome: str) -> bool:
        """Update the outcome of a previously logged decision.

        Args:
            decision_index: Index of the decision to update.
            outcome: The outcome to record.

        Returns:
            True if updated successfully, False if index is invalid.
        """
        log = self._load_log()
        if 0 <= decision_index < len(log.decisions):
            log.decisions[decision_index].outcome = outcome
            self._save_log()
            return True
        return False

    def get_decisions_by_type(self, decision_type: DecisionType) -> List[Decision]:
        """Query decisions by type.

        Args:
            decision_type: The type of decisions to retrieve.

        Returns:
            List of decisions matching the specified type.
        """
        log = self._load_log()
        return [d for d in log.decisions if d.decision_type == decision_type]

    def get_recent_decisions(self, limit: int = 10) -> List[Decision]:
        """Get the most recent decisions.

        Args:
            limit: Maximum number of decisions to return.

        Returns:
            List of recent decisions, newest first.
        """
        log = self._load_log()
        return list(reversed(log.decisions[-limit:]))

    def get_decisions_in_range(self, start: datetime, end: datetime) -> List[Decision]:
        """Get decisions within a time range.

        Args:
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).

        Returns:
            List of decisions within the specified range.
        """
        log = self._load_log()
        return [d for d in log.decisions if start <= d.timestamp <= end]

    def get_decision_count_by_type(self) -> Dict[str, int]:
        """Get count of decisions grouped by type.

        Returns:
            Dictionary mapping decision types to their counts.
        """
        log = self._load_log()
        counts: Dict[str, int] = {}
        for decision in log.decisions:
            counts[decision.decision_type] = counts.get(decision.decision_type, 0) + 1
        return counts

    def clear_log(self) -> None:
        """Clear all decisions from the log."""
        self._log = DecisionLog()
        self._save_log()


# Singleton instance for convenience
_decision_logger: Optional[DecisionLogger] = None


def get_decision_logger(log_path: Optional[str] = None) -> DecisionLogger:
    """Get the singleton decision logger instance.

    Args:
        log_path: Optional path to override the default log location.

    Returns:
        The DecisionLogger singleton instance.
    """
    global _decision_logger
    if _decision_logger is None or log_path is not None:
        _decision_logger = DecisionLogger(log_path)
    return _decision_logger
