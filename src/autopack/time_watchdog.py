"""Simple Time Watchdog - Coarse kill switch for runaway executions

Following GPT consensus: No heavy time budget system, just a simple
run-level wall-clock timeout to prevent infinite loops or stuck phases.

Philosophy:
- Token caps handle 95%+ of execution time (LLM calls dominate)
- This is a last-resort safety net for edge cases
- ~20 lines of code, not a full BudgetController
"""

import time
from typing import Optional


class TimeWatchdog:
    """Simple wall-clock timeout watchdog for runs.

    Provides coarse kill switch without complex time budget system.
    """

    def __init__(self, max_run_wall_clock_sec: int = 7200):
        """Initialize watchdog.

        Args:
            max_run_wall_clock_sec: Maximum run duration in seconds (default: 2 hours)
        """
        self.max_duration = max_run_wall_clock_sec
        self.start_time: Optional[float] = None

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
