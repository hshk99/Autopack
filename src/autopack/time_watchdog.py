"""Simple Time Watchdog - Coarse kill switch for runaway executions

Following GPT consensus: No heavy time budget system, just a simple
run-level wall-clock timeout to prevent infinite loops or stuck phases.

Philosophy:
- Token caps handle 95%+ of execution time (LLM calls dominate)
- This is a last-resort safety net for edge cases
- ~20 lines of code, not a full BudgetController

IMP-STUCK-001: Added per-phase timeout tracking to prevent runaway phases
from burning entire run budget. Default: 15 min per phase with 50% soft warning.
"""

import time
from typing import Dict, Optional


class TimeWatchdog:
    """Simple wall-clock timeout watchdog for runs and phases.

    Provides coarse kill switch without complex time budget system.
    IMP-STUCK-001: Added per-phase timeout enforcement.
    """

    def __init__(
        self,
        max_run_wall_clock_sec: int = 7200,
        max_phase_wall_clock_sec: int = 900,  # IMP-STUCK-001: 15 min default
    ):
        """Initialize watchdog.

        Args:
            max_run_wall_clock_sec: Maximum run duration in seconds (default: 2 hours)
            max_phase_wall_clock_sec: Maximum phase duration in seconds (default: 15 min)
        """
        self.max_duration = max_run_wall_clock_sec
        self.max_phase_duration = max_phase_wall_clock_sec
        self.start_time: Optional[float] = None
        self.phase_timers: Dict[str, float] = {}  # IMP-STUCK-001: Track phase start times

    def start(self) -> None:
        """Start tracking run time."""
        self.start_time = time.time()

    def check(self) -> tuple[bool, float]:
        """Check if run has exceeded time limit.

        Returns:
            Tuple of (exceeded: bool, elapsed_sec: float)
        """
        if self.start_time is None:
            return False, 0.0

        elapsed = time.time() - self.start_time
        exceeded = elapsed > self.max_duration

        return exceeded, elapsed

    def get_remaining_sec(self) -> float:
        """Get remaining time before timeout.

        Returns:
            Remaining seconds (negative if already exceeded)
        """
        if self.start_time is None:
            return self.max_duration

        elapsed = time.time() - self.start_time
        return self.max_duration - elapsed

    def format_elapsed(self, elapsed_sec: float) -> str:
        """Format elapsed time as human-readable string.

        Args:
            elapsed_sec: Elapsed time in seconds

        Returns:
            Formatted string (e.g., "1h 23m 45s")
        """
        hours = int(elapsed_sec // 3600)
        minutes = int((elapsed_sec % 3600) // 60)
        seconds = int(elapsed_sec % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return " ".join(parts)

    # IMP-STUCK-001: Per-phase timeout tracking
    def track_phase_start(self, phase_id: str) -> None:
        """Start tracking time for a specific phase.

        Args:
            phase_id: Unique identifier for the phase
        """
        self.phase_timers[phase_id] = time.time()

    def check_phase_timeout(
        self, phase_id: str, custom_timeout_sec: Optional[int] = None
    ) -> tuple[bool, float, bool]:
        """Check if a phase has exceeded its time limit.

        Args:
            phase_id: Unique identifier for the phase
            custom_timeout_sec: Optional custom timeout (uses default if None)

        Returns:
            Tuple of (exceeded: bool, elapsed_sec: float, soft_warning: bool)
            - exceeded: True if phase exceeded timeout
            - elapsed_sec: Elapsed time for this phase
            - soft_warning: True if >50% of timeout used (warning threshold)
        """
        if phase_id not in self.phase_timers:
            return False, 0.0, False

        elapsed = time.time() - self.phase_timers[phase_id]
        timeout = custom_timeout_sec if custom_timeout_sec is not None else self.max_phase_duration

        exceeded = elapsed > timeout
        soft_warning = elapsed > (timeout * 0.5) and not exceeded

        return exceeded, elapsed, soft_warning

    def get_phase_remaining_sec(
        self, phase_id: str, custom_timeout_sec: Optional[int] = None
    ) -> float:
        """Get remaining time for a phase before timeout.

        Args:
            phase_id: Unique identifier for the phase
            custom_timeout_sec: Optional custom timeout (uses default if None)

        Returns:
            Remaining seconds (negative if already exceeded)
        """
        timeout = custom_timeout_sec if custom_timeout_sec is not None else self.max_phase_duration

        if phase_id not in self.phase_timers:
            return timeout

        elapsed = time.time() - self.phase_timers[phase_id]
        return timeout - elapsed

    def clear_phase_timer(self, phase_id: str) -> None:
        """Clear timer for completed phase to free memory.

        Args:
            phase_id: Unique identifier for the phase
        """
        self.phase_timers.pop(phase_id, None)
