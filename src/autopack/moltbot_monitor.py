"""Moltbot Monitor with Shadow Mode and Kill Switch (MOLT-006).

Safety mechanisms for Moltbot autonomous operations:
1. Shadow Mode: Logs triggers without taking action for 1-2 weeks baseline collection
2. Kill Switch: moltbot_paused.signal file instantly disables all Moltbot activity

Usage:
    from autopack.moltbot_monitor import MoltbotMonitor, MoltbotMode

    monitor = MoltbotMonitor(workspace_root=Path("."))

    # Check if operations should proceed
    if monitor.is_active():
        # Execute action
        monitor.record_action_executed("my_action", {"key": "value"})
    else:
        # Log what would have happened
        monitor.record_shadow_trigger("my_action", {"key": "value"})
"""

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Signal file name for kill switch
KILL_SWITCH_SIGNAL_FILE = "moltbot_paused.signal"

# Environment variable to force shadow mode
MOLTBOT_SHADOW_MODE_ENV = "MOLTBOT_SHADOW_MODE"

# Environment variable to set custom signal file location
MOLTBOT_SIGNAL_PATH_ENV = "MOLTBOT_SIGNAL_PATH"


class MoltbotMode(Enum):
    """Operating modes for Moltbot monitor."""

    ACTIVE = "active"  # Normal operation - actions are executed
    SHADOW = "shadow"  # Shadow mode - log only, no execution
    KILLED = "killed"  # Kill switch engaged - all operations blocked


@dataclass
class ShadowTriggerRecord:
    """Record of a trigger that occurred during shadow mode.

    Used for baseline collection to understand trigger patterns
    before enabling active mode.
    """

    trigger_id: str
    action_type: str
    timestamp: str
    context: Dict[str, Any] = field(default_factory=dict)
    would_execute: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class MoltbotMetrics:
    """Metrics for Moltbot monitor operations."""

    total_triggers: int = 0
    shadow_triggers: int = 0
    executed_actions: int = 0
    kill_switch_blocks: int = 0
    mode_transitions: Dict[str, int] = field(default_factory=dict)
    start_time: Optional[str] = None
    last_trigger_time: Optional[str] = None

    def record_shadow_trigger(self) -> None:
        """Record a shadow mode trigger."""
        self.total_triggers += 1
        self.shadow_triggers += 1
        self.last_trigger_time = datetime.now().isoformat()

    def record_executed_action(self) -> None:
        """Record an executed action."""
        self.total_triggers += 1
        self.executed_actions += 1
        self.last_trigger_time = datetime.now().isoformat()

    def record_kill_switch_block(self) -> None:
        """Record a kill switch block."""
        self.total_triggers += 1
        self.kill_switch_blocks += 1
        self.last_trigger_time = datetime.now().isoformat()

    def record_mode_transition(self, from_mode: MoltbotMode, to_mode: MoltbotMode) -> None:
        """Record a mode transition."""
        key = f"{from_mode.value}_to_{to_mode.value}"
        self.mode_transitions[key] = self.mode_transitions.get(key, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class MoltbotKillSwitchError(Exception):
    """Raised when kill switch is engaged and operation is blocked."""

    pass


class MoltbotMonitor:
    """Monitor for Moltbot autonomous operations with safety controls.

    Provides two safety mechanisms:
    1. Shadow Mode: During baseline collection period, all triggers are logged
       but no actions are executed. This allows observation of trigger patterns
       without risk for 1-2 weeks.
    2. Kill Switch: Creating a moltbot_paused.signal file instantly disables
       all Moltbot activity for emergency pause scenarios.

    Example:
        monitor = MoltbotMonitor(workspace_root=Path("."))

        # Start in shadow mode for baseline collection
        monitor.enable_shadow_mode()

        # Check mode before operations
        if monitor.is_active():
            result = execute_action()
            monitor.record_action_executed("action_name", {"result": result})
        elif monitor.is_shadow_mode():
            monitor.record_shadow_trigger("action_name", {"would_do": "something"})

        # Emergency pause
        monitor.engage_kill_switch("Emergency: unexpected behavior detected")
    """

    def __init__(
        self,
        workspace_root: Path,
        shadow_mode: bool = False,
        signal_file_path: Optional[Path] = None,
        baseline_storage_path: Optional[Path] = None,
    ):
        """Initialize Moltbot monitor.

        Args:
            workspace_root: Root directory for workspace
            shadow_mode: If True, start in shadow mode (default: False)
            signal_file_path: Custom path for kill switch signal file.
                            If None, uses workspace_root / moltbot_paused.signal
            baseline_storage_path: Path to store baseline data during shadow mode.
                                  If None, uses workspace_root / .moltbot / baseline.json
        """
        self.workspace_root = Path(workspace_root)
        self._lock = threading.RLock()

        # Determine signal file location
        env_signal_path = os.getenv(MOLTBOT_SIGNAL_PATH_ENV)
        if signal_file_path:
            self.signal_file_path = Path(signal_file_path)
        elif env_signal_path:
            self.signal_file_path = Path(env_signal_path)
        else:
            self.signal_file_path = self.workspace_root / KILL_SWITCH_SIGNAL_FILE

        # Baseline storage for shadow mode data
        if baseline_storage_path:
            self.baseline_storage_path = Path(baseline_storage_path)
        else:
            self.baseline_storage_path = self.workspace_root / ".moltbot" / "baseline.json"

        # Initialize state
        self._mode = MoltbotMode.SHADOW if shadow_mode else MoltbotMode.ACTIVE
        self._shadow_triggers: List[ShadowTriggerRecord] = []
        self._trigger_counter = 0
        self.metrics = MoltbotMetrics(start_time=datetime.now().isoformat())

        # Check for environment variable override
        if os.getenv(MOLTBOT_SHADOW_MODE_ENV) == "1":
            self._mode = MoltbotMode.SHADOW
            logger.info(
                f"[MOLTBOT] Shadow mode enabled via {MOLTBOT_SHADOW_MODE_ENV} environment variable"
            )

        # Check for existing kill switch signal file
        if self._check_kill_switch_signal():
            self._mode = MoltbotMode.KILLED
            logger.warning(
                f"[MOLTBOT] Kill switch signal file detected at startup: {self.signal_file_path}"
            )

        logger.info(
            f"[MOLTBOT] Monitor initialized: mode={self._mode.value}, "
            f"signal_file={self.signal_file_path}"
        )

    def _check_kill_switch_signal(self) -> bool:
        """Check if kill switch signal file exists.

        Returns:
            True if signal file exists, False otherwise
        """
        return self.signal_file_path.exists()

    def _generate_trigger_id(self) -> str:
        """Generate a unique trigger ID.

        Returns:
            Unique trigger identifier
        """
        with self._lock:
            self._trigger_counter += 1
            timestamp = int(time.time() * 1000)
            return f"trigger_{timestamp}_{self._trigger_counter}"

    def get_mode(self) -> MoltbotMode:
        """Get current operating mode.

        Checks kill switch signal file on each call for real-time response.

        Returns:
            Current MoltbotMode
        """
        with self._lock:
            # Always check kill switch signal file for real-time response
            if self._check_kill_switch_signal():
                if self._mode != MoltbotMode.KILLED:
                    old_mode = self._mode
                    self._mode = MoltbotMode.KILLED
                    self.metrics.record_mode_transition(old_mode, MoltbotMode.KILLED)
                    logger.warning(f"[MOLTBOT] Kill switch engaged: {old_mode.value} -> killed")
            elif self._mode == MoltbotMode.KILLED:
                # Signal file was removed - check if we should restore previous mode
                # Default to shadow mode for safety
                self._mode = MoltbotMode.SHADOW
                self.metrics.record_mode_transition(MoltbotMode.KILLED, MoltbotMode.SHADOW)
                logger.info(
                    "[MOLTBOT] Kill switch disengaged, transitioning to shadow mode for safety"
                )

            return self._mode

    def is_active(self) -> bool:
        """Check if monitor is in active mode (actions will execute).

        Returns:
            True if in active mode, False otherwise
        """
        return self.get_mode() == MoltbotMode.ACTIVE

    def is_shadow_mode(self) -> bool:
        """Check if monitor is in shadow mode (log only, no execution).

        Returns:
            True if in shadow mode, False otherwise
        """
        return self.get_mode() == MoltbotMode.SHADOW

    def is_killed(self) -> bool:
        """Check if kill switch is engaged.

        Returns:
            True if killed, False otherwise
        """
        return self.get_mode() == MoltbotMode.KILLED

    def enable_shadow_mode(self) -> None:
        """Enable shadow mode for baseline collection.

        In shadow mode, all triggers are logged but no actions are executed.
        This is useful for 1-2 weeks of baseline collection to understand
        trigger patterns before enabling active mode.
        """
        with self._lock:
            if self._mode == MoltbotMode.KILLED:
                logger.warning("[MOLTBOT] Cannot enable shadow mode while kill switch is engaged")
                return

            if self._mode != MoltbotMode.SHADOW:
                old_mode = self._mode
                self._mode = MoltbotMode.SHADOW
                self.metrics.record_mode_transition(old_mode, MoltbotMode.SHADOW)
                logger.info(f"[MOLTBOT] Shadow mode enabled: {old_mode.value} -> shadow")

    def enable_active_mode(self) -> None:
        """Enable active mode for normal operation.

        In active mode, actions are executed normally.
        Only enable after sufficient baseline collection in shadow mode.
        """
        with self._lock:
            if self._mode == MoltbotMode.KILLED:
                logger.warning("[MOLTBOT] Cannot enable active mode while kill switch is engaged")
                return

            if self._mode != MoltbotMode.ACTIVE:
                old_mode = self._mode
                self._mode = MoltbotMode.ACTIVE
                self.metrics.record_mode_transition(old_mode, MoltbotMode.ACTIVE)
                logger.info(f"[MOLTBOT] Active mode enabled: {old_mode.value} -> active")

    def engage_kill_switch(self, reason: str = "") -> None:
        """Engage kill switch to instantly disable all Moltbot activity.

        Creates the signal file and transitions to killed mode.

        Args:
            reason: Optional reason for engaging kill switch
        """
        with self._lock:
            try:
                # Ensure parent directory exists
                self.signal_file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write signal file with metadata
                signal_data = {
                    "engaged_at": datetime.now().isoformat(),
                    "reason": reason,
                    "previous_mode": self._mode.value,
                }
                self.signal_file_path.write_text(
                    json.dumps(signal_data, indent=2), encoding="utf-8"
                )

                old_mode = self._mode
                self._mode = MoltbotMode.KILLED
                self.metrics.record_mode_transition(old_mode, MoltbotMode.KILLED)

                logger.warning(
                    f"[MOLTBOT] Kill switch ENGAGED: reason='{reason}', "
                    f"signal_file={self.signal_file_path}"
                )

            except Exception as e:
                logger.error(f"[MOLTBOT] Failed to engage kill switch: {e}")
                raise

    def disengage_kill_switch(self) -> None:
        """Disengage kill switch by removing signal file.

        Transitions to shadow mode by default for safety.
        Call enable_active_mode() explicitly to resume normal operation.
        """
        with self._lock:
            try:
                if self.signal_file_path.exists():
                    self.signal_file_path.unlink()
                    logger.info(
                        f"[MOLTBOT] Kill switch signal file removed: {self.signal_file_path}"
                    )

                if self._mode == MoltbotMode.KILLED:
                    self._mode = MoltbotMode.SHADOW
                    self.metrics.record_mode_transition(MoltbotMode.KILLED, MoltbotMode.SHADOW)
                    logger.info("[MOLTBOT] Kill switch disengaged, transitioning to shadow mode")

            except Exception as e:
                logger.error(f"[MOLTBOT] Failed to disengage kill switch: {e}")
                raise

    def record_shadow_trigger(
        self,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ShadowTriggerRecord:
        """Record a trigger during shadow mode for baseline collection.

        Args:
            action_type: Type of action that would have been executed
            context: Additional context about the trigger

        Returns:
            The created ShadowTriggerRecord
        """
        with self._lock:
            trigger = ShadowTriggerRecord(
                trigger_id=self._generate_trigger_id(),
                action_type=action_type,
                timestamp=datetime.now().isoformat(),
                context=context or {},
                would_execute=True,
            )

            self._shadow_triggers.append(trigger)
            self.metrics.record_shadow_trigger()

            logger.info(
                f"[SHADOW_MODE] Trigger recorded: action_type={action_type}, "
                f"trigger_id={trigger.trigger_id}, context={context}"
            )

            return trigger

    def record_action_executed(
        self,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an action that was executed in active mode.

        Args:
            action_type: Type of action that was executed
            context: Additional context about the action
        """
        with self._lock:
            self.metrics.record_executed_action()
            logger.info(f"[MOLTBOT] Action executed: action_type={action_type}, context={context}")

    def record_kill_switch_block(
        self,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an action that was blocked by kill switch.

        Args:
            action_type: Type of action that was blocked
            context: Additional context about the blocked action
        """
        with self._lock:
            self.metrics.record_kill_switch_block()
            logger.warning(
                f"[MOLTBOT] Action BLOCKED by kill switch: action_type={action_type}, "
                f"context={context}"
            )

    def should_execute(self, action_type: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Check if an action should be executed and record appropriately.

        This is the main entry point for checking whether to proceed with an action.
        It handles all mode-specific recording automatically.

        Args:
            action_type: Type of action to potentially execute
            context: Additional context about the action

        Returns:
            True if action should be executed, False otherwise
        """
        mode = self.get_mode()

        if mode == MoltbotMode.ACTIVE:
            return True
        elif mode == MoltbotMode.SHADOW:
            self.record_shadow_trigger(action_type, context)
            return False
        else:  # KILLED
            self.record_kill_switch_block(action_type, context)
            return False

    def get_shadow_triggers(self) -> List[ShadowTriggerRecord]:
        """Get all recorded shadow mode triggers.

        Returns:
            List of shadow trigger records
        """
        with self._lock:
            return list(self._shadow_triggers)

    def get_baseline_summary(self) -> Dict[str, Any]:
        """Get summary of baseline data collected during shadow mode.

        Returns:
            Dictionary with baseline statistics
        """
        with self._lock:
            triggers = self._shadow_triggers

            # Count triggers by action type
            action_type_counts: Dict[str, int] = {}
            for trigger in triggers:
                action_type_counts[trigger.action_type] = (
                    action_type_counts.get(trigger.action_type, 0) + 1
                )

            return {
                "total_triggers": len(triggers),
                "action_type_counts": action_type_counts,
                "collection_start": self.metrics.start_time,
                "collection_end": datetime.now().isoformat(),
                "metrics": self.metrics.to_dict(),
            }

    def save_baseline(self, path: Optional[Path] = None) -> Path:
        """Save baseline data to file.

        Args:
            path: Path to save baseline data. If None, uses default baseline_storage_path.

        Returns:
            Path where baseline was saved
        """
        save_path = path or self.baseline_storage_path

        with self._lock:
            # Ensure directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            baseline_data = {
                "summary": self.get_baseline_summary(),
                "triggers": [t.to_dict() for t in self._shadow_triggers],
            }

            save_path.write_text(json.dumps(baseline_data, indent=2), encoding="utf-8")

            logger.info(f"[MOLTBOT] Baseline data saved to {save_path}")
            return save_path

    def load_baseline(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """Load baseline data from file.

        Args:
            path: Path to load baseline data from. If None, uses default baseline_storage_path.

        Returns:
            Loaded baseline data dictionary
        """
        load_path = path or self.baseline_storage_path

        if not load_path.exists():
            logger.warning(f"[MOLTBOT] No baseline data found at {load_path}")
            return {"summary": {}, "triggers": []}

        with self._lock:
            data = json.loads(load_path.read_text(encoding="utf-8"))
            logger.info(f"[MOLTBOT] Baseline data loaded from {load_path}")
            return data

    def get_metrics(self) -> MoltbotMetrics:
        """Get current metrics.

        Returns:
            Current MoltbotMetrics
        """
        with self._lock:
            return self.metrics

    def to_dict(self) -> Dict[str, Any]:
        """Serialize monitor state to dictionary.

        Returns:
            Dictionary representation of monitor state
        """
        with self._lock:
            return {
                "mode": self._mode.value,
                "signal_file_path": str(self.signal_file_path),
                "baseline_storage_path": str(self.baseline_storage_path),
                "shadow_trigger_count": len(self._shadow_triggers),
                "metrics": self.metrics.to_dict(),
            }
