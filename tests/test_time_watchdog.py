"""Tests for TimeWatchdog (IMP-STUCK-001: Per-phase timeout enforcement)"""

import time
from autopack.time_watchdog import TimeWatchdog


class TestTimeWatchdogRunLevel:
    """Test run-level timeout functionality (existing behavior)"""

    def test_run_timeout_not_exceeded(self):
        """Test that run timeout check returns False when not exceeded"""
        watchdog = TimeWatchdog(max_run_wall_clock_sec=10)
        watchdog.start()

        exceeded, elapsed = watchdog.check()

        assert exceeded is False
        assert elapsed < 10

    def test_run_timeout_exceeded(self):
        """Test that run timeout check returns True when exceeded"""
        watchdog = TimeWatchdog(max_run_wall_clock_sec=1)
        watchdog.start()
        time.sleep(1.1)

        exceeded, elapsed = watchdog.check()

        assert exceeded is True
        assert elapsed >= 1.0

    def test_get_remaining_sec(self):
        """Test getting remaining time before run timeout"""
        watchdog = TimeWatchdog(max_run_wall_clock_sec=10)
        watchdog.start()

        remaining = watchdog.get_remaining_sec()

        assert 9.0 <= remaining <= 10.0

    def test_format_elapsed(self):
        """Test elapsed time formatting"""
        watchdog = TimeWatchdog()

        assert watchdog.format_elapsed(45) == "45s"
        assert watchdog.format_elapsed(90) == "1m 30s"
        assert watchdog.format_elapsed(3665) == "1h 1m 5s"


class TestTimeWatchdogPhaseLevel:
    """Test per-phase timeout functionality (IMP-STUCK-001)"""

    def test_phase_timeout_not_exceeded(self):
        """Test that phase timeout check returns False when not exceeded"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=10)
        phase_id = "test-phase-1"

        watchdog.track_phase_start(phase_id)
        exceeded, elapsed, soft_warning = watchdog.check_phase_timeout(phase_id)

        assert exceeded is False
        assert elapsed < 10
        assert soft_warning is False

    def test_phase_timeout_exceeded(self):
        """Test that phase timeout check returns True when exceeded"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=1)
        phase_id = "test-phase-timeout"

        watchdog.track_phase_start(phase_id)
        time.sleep(1.1)

        exceeded, elapsed, soft_warning = watchdog.check_phase_timeout(phase_id)

        assert exceeded is True
        assert elapsed >= 1.0
        assert soft_warning is False  # Hard timeout, not warning

    def test_phase_timeout_soft_warning(self):
        """Test soft warning at 50% threshold"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=2)
        phase_id = "test-phase-warning"

        watchdog.track_phase_start(phase_id)
        time.sleep(1.1)  # >50% but <100%

        exceeded, elapsed, soft_warning = watchdog.check_phase_timeout(phase_id)

        assert exceeded is False
        assert soft_warning is True
        assert 1.0 <= elapsed < 2.0

    def test_phase_timeout_custom_timeout(self):
        """Test custom timeout override"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=10)
        phase_id = "test-phase-custom"

        watchdog.track_phase_start(phase_id)
        time.sleep(0.6)

        # Use custom 1 second timeout
        exceeded, elapsed, soft_warning = watchdog.check_phase_timeout(
            phase_id, custom_timeout_sec=1
        )

        assert exceeded is False  # Not exceeded yet
        assert soft_warning is True  # >50% of custom timeout

    def test_get_phase_remaining_sec(self):
        """Test getting remaining time for phase"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=10)
        phase_id = "test-phase-remaining"

        watchdog.track_phase_start(phase_id)
        time.sleep(0.5)

        remaining = watchdog.get_phase_remaining_sec(phase_id)

        assert 9.0 <= remaining <= 9.5

    def test_get_phase_remaining_sec_custom_timeout(self):
        """Test getting remaining time with custom timeout"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=10)
        phase_id = "test-phase-remaining-custom"

        watchdog.track_phase_start(phase_id)
        time.sleep(0.5)

        remaining = watchdog.get_phase_remaining_sec(phase_id, custom_timeout_sec=5)

        assert 4.0 <= remaining <= 4.5

    def test_clear_phase_timer(self):
        """Test clearing phase timer after completion"""
        watchdog = TimeWatchdog()
        phase_id = "test-phase-clear"

        watchdog.track_phase_start(phase_id)
        assert phase_id in watchdog.phase_timers

        watchdog.clear_phase_timer(phase_id)
        assert phase_id not in watchdog.phase_timers

    def test_multiple_phases_tracked_independently(self):
        """Test tracking multiple phases independently"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=10)

        phase1 = "test-phase-multi-1"
        phase2 = "test-phase-multi-2"

        watchdog.track_phase_start(phase1)
        time.sleep(0.5)
        watchdog.track_phase_start(phase2)
        time.sleep(0.5)

        # Phase 1 should have ~1s elapsed
        _, elapsed1, _ = watchdog.check_phase_timeout(phase1)
        # Phase 2 should have ~0.5s elapsed
        _, elapsed2, _ = watchdog.check_phase_timeout(phase2)

        assert 0.9 <= elapsed1 <= 1.1
        assert 0.4 <= elapsed2 <= 0.6

    def test_phase_timeout_untracked_phase(self):
        """Test checking timeout for phase that wasn't tracked"""
        watchdog = TimeWatchdog()
        phase_id = "test-phase-untracked"

        exceeded, elapsed, soft_warning = watchdog.check_phase_timeout(phase_id)

        assert exceeded is False
        assert elapsed == 0.0
        assert soft_warning is False

    def test_get_remaining_sec_untracked_phase(self):
        """Test getting remaining time for untracked phase returns full timeout"""
        watchdog = TimeWatchdog(max_phase_wall_clock_sec=900)
        phase_id = "test-phase-untracked-remaining"

        remaining = watchdog.get_phase_remaining_sec(phase_id)

        assert remaining == 900


class TestTimeWatchdogIntegration:
    """Integration tests combining run and phase timeouts"""

    def test_run_and_phase_timeouts_independent(self):
        """Test that run and phase timeouts work independently"""
        watchdog = TimeWatchdog(max_run_wall_clock_sec=10, max_phase_wall_clock_sec=5)

        # Start run
        watchdog.start()

        # Start phase
        phase_id = "test-integration-phase"
        watchdog.track_phase_start(phase_id)
        time.sleep(0.5)

        # Check both
        run_exceeded, run_elapsed = watchdog.check()
        phase_exceeded, phase_elapsed, _ = watchdog.check_phase_timeout(phase_id)

        assert run_exceeded is False
        assert phase_exceeded is False
        assert 0.4 <= run_elapsed <= 0.6
        assert 0.4 <= phase_elapsed <= 0.6

    def test_phase_timeout_shorter_than_run_timeout(self):
        """Test that phase can timeout before run timeout"""
        watchdog = TimeWatchdog(max_run_wall_clock_sec=10, max_phase_wall_clock_sec=1)

        watchdog.start()
        phase_id = "test-short-phase"
        watchdog.track_phase_start(phase_id)

        time.sleep(1.1)

        run_exceeded, _ = watchdog.check()
        phase_exceeded, _, _ = watchdog.check_phase_timeout(phase_id)

        assert run_exceeded is False  # Run still OK
        assert phase_exceeded is True  # Phase timed out
