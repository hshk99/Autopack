"""Feedback loop controller for continuous system improvement."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class LoopState(Enum):
    """States of the feedback loop."""

    IDLE = "idle"
    MONITORING = "monitoring"
    ANALYZING = "analyzing"
    ACTING = "acting"
    PAUSED = "paused"


@dataclass
class LoopAction:
    """Represents an action to be taken by the feedback loop."""

    action_type: str  # 'alert', 'auto_fix', 'suggest', 'escalate'
    priority: str  # 'low', 'medium', 'high', 'critical'
    description: str
    target: Optional[str] = None  # Phase ID, file path, etc.
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    executed: bool = False


class FeedbackLoopController:
    """Orchestrates the feedback loop between monitoring components."""

    THRESHOLDS = {
        "stagnation_minutes": 30,
        "ci_failure_streak": 3,
        "optimization_check_interval_hours": 1,
        "metrics_aggregation_interval_hours": 6,
    }

    def __init__(
        self,
        metrics_db=None,
        failure_analyzer=None,
        optimization_detector=None,
        event_logger=None,
    ):
        """Initialize with feedback components."""
        self.metrics_db = metrics_db
        self.failure_analyzer = failure_analyzer
        self.optimization_detector = optimization_detector
        self.event_logger = event_logger

        self.state = LoopState.IDLE
        self.pending_actions: List[LoopAction] = []
        self.action_history: List[LoopAction] = []
        self.last_check: Dict[str, datetime] = {}
        self._action_handlers: Dict[str, Callable] = {}

    def register_action_handler(self, action_type: str, handler: Callable):
        """Register a handler for a specific action type."""
        self._action_handlers[action_type] = handler

    def run_cycle(self) -> List[LoopAction]:
        """Run one cycle of the feedback loop."""
        self.state = LoopState.MONITORING
        new_actions = []

        # Step 1: Check for stagnation
        stagnation_actions = self._check_stagnation()
        new_actions.extend(stagnation_actions)

        # Step 2: Check failure patterns
        self.state = LoopState.ANALYZING
        failure_actions = self._analyze_failures()
        new_actions.extend(failure_actions)

        # Step 3: Check optimization opportunities
        optimization_actions = self._check_optimizations()
        new_actions.extend(optimization_actions)

        # Step 4: Execute pending actions
        self.state = LoopState.ACTING
        for action in new_actions:
            self._execute_action(action)

        self.pending_actions.extend(new_actions)
        self.state = LoopState.IDLE

        return new_actions

    def _check_stagnation(self) -> List[LoopAction]:
        """Check for stagnant phases or slots."""
        actions = []

        if not self.metrics_db:
            return actions

        # Get recent phase outcomes
        outcomes = self.metrics_db.get_phase_outcomes()

        # Check for phases stuck in progress
        now = datetime.now()
        threshold = timedelta(minutes=self.THRESHOLDS["stagnation_minutes"])

        for outcome in outcomes:
            if outcome.get("outcome") != "in_progress":
                continue

            start_time = datetime.fromisoformat(outcome.get("timestamp", now.isoformat()))
            if now - start_time > threshold:
                duration_minutes = (now - start_time).seconds // 60
                actions.append(
                    LoopAction(
                        action_type="alert",
                        priority="high",
                        description=(
                            f"Phase {outcome.get('phase_id')} stagnant "
                            f"for {duration_minutes} minutes"
                        ),
                        target=outcome.get("phase_id"),
                        payload={"duration_minutes": duration_minutes},
                    )
                )

        return actions

    def _analyze_failures(self) -> List[LoopAction]:
        """Analyze failure patterns and generate actions."""
        actions = []

        if not self.failure_analyzer:
            return actions

        stats = self.failure_analyzer.get_failure_statistics()

        # Check for recurring unresolved failures
        for pattern in stats.get("top_patterns", []):
            occurrence_count = pattern.get("occurrence_count", 0)
            if occurrence_count >= self.THRESHOLDS["ci_failure_streak"]:
                if not pattern.get("resolution"):
                    actions.append(
                        LoopAction(
                            action_type="escalate",
                            priority="high",
                            description=(
                                f"Recurring {pattern.get('failure_type')} failure "
                                f"({occurrence_count} times)"
                            ),
                            target=pattern.get("pattern_hash"),
                            payload={
                                "failure_type": pattern.get("failure_type"),
                                "count": occurrence_count,
                            },
                        )
                    )
                else:
                    # Has resolution - suggest auto-fix
                    actions.append(
                        LoopAction(
                            action_type="suggest",
                            priority="medium",
                            description=(
                                f"Known failure pattern - try: {pattern.get('resolution')}"
                            ),
                            target=pattern.get("pattern_hash"),
                            payload={"resolution": pattern.get("resolution")},
                        )
                    )

        return actions

    def _check_optimizations(self) -> List[LoopAction]:
        """Check for optimization opportunities."""
        actions = []

        if not self.optimization_detector:
            return actions

        # Rate limit optimization checks
        last_opt_check = self.last_check.get("optimization")
        if last_opt_check:
            elapsed = datetime.now() - last_opt_check
            if elapsed < timedelta(hours=self.THRESHOLDS["optimization_check_interval_hours"]):
                return actions

        self.last_check["optimization"] = datetime.now()

        suggestions = self.optimization_detector.detect_all()

        for suggestion in suggestions:
            if suggestion.severity in ["high", "critical"]:
                actions.append(
                    LoopAction(
                        action_type="suggest",
                        priority=suggestion.severity,
                        description=f"Optimization: {suggestion.description}",
                        target=suggestion.category,
                        payload={
                            "category": suggestion.category,
                            "current_value": suggestion.current_value,
                            "threshold": suggestion.threshold,
                            "hint": suggestion.implementation_hint,
                        },
                    )
                )

        return actions

    def _execute_action(self, action: LoopAction):
        """Execute an action if handler is registered."""
        handler = self._action_handlers.get(action.action_type)

        if handler:
            try:
                handler(action)
                action.executed = True
            except Exception as e:
                action.payload["execution_error"] = str(e)

        self.action_history.append(action)

        # Log the action if event logger is available
        if self.event_logger:
            self.event_logger.log(
                f"feedback_loop_{action.action_type}",
                {
                    "priority": action.priority,
                    "description": action.description,
                    "target": action.target,
                    "executed": action.executed,
                },
            )

    def get_pending_actions(self, priority: Optional[str] = None) -> List[LoopAction]:
        """Get pending actions, optionally filtered by priority."""
        if priority:
            return [a for a in self.pending_actions if a.priority == priority and not a.executed]
        return [a for a in self.pending_actions if not a.executed]

    def get_summary(self) -> str:
        """Get human-readable loop status summary."""
        lines = [f"Feedback Loop Status: {self.state.value}"]

        pending = self.get_pending_actions()
        lines.append(f"Pending Actions: {len(pending)}")

        if pending:
            by_priority = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for action in pending:
                by_priority[action.priority] = by_priority.get(action.priority, 0) + 1

            lines.append(
                f"  Critical: {by_priority['critical']}, High: {by_priority['high']}, "
                f"Medium: {by_priority['medium']}, Low: {by_priority['low']}"
            )

        executed_count = len([a for a in self.action_history if a.executed])
        lines.append(f"\nTotal Actions Executed: {executed_count}")

        return "\n".join(lines)

    def export_state(self, output_path: str) -> None:
        """Export loop state to JSON."""
        output = {
            "state": self.state.value,
            "last_check": {k: v.isoformat() for k, v in self.last_check.items()},
            "pending_actions": [
                {
                    "action_type": a.action_type,
                    "priority": a.priority,
                    "description": a.description,
                    "target": a.target,
                    "created_at": a.created_at,
                    "executed": a.executed,
                }
                for a in self.pending_actions
            ],
            "action_history_count": len(self.action_history),
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
