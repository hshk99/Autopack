"""Tests for health monitoring."""

import asyncio

import pytest

from autopack.generative.health_monitor import HealthMonitor


class TestHealthMonitor:
    """Test health monitoring."""

    def test_monitor_creation(self):
        """Test creating a health monitor."""
        monitor = HealthMonitor()
        assert len(monitor.get_all_health_status()) == 0

    def test_initialize_provider(self):
        """Test initializing provider health tracking."""
        monitor = HealthMonitor()
        monitor.initialize_provider("test_provider")

        assert "test_provider" in monitor.get_all_health_status()
        assert monitor.is_healthy("test_provider")

    def test_mark_success(self):
        """Test marking a provider as successful."""
        monitor = HealthMonitor()
        monitor.mark_success("test_provider")

        health = monitor.get_health_status("test_provider")
        assert health.is_healthy
        assert health.consecutive_failures == 0
        assert health.last_error is None

    def test_mark_failure(self):
        """Test marking a provider as failed."""
        monitor = HealthMonitor()
        monitor.mark_failure("test_provider", "Connection timeout")

        health = monitor.get_health_status("test_provider")
        assert health.consecutive_failures == 1
        assert health.last_error == "Connection timeout"
        assert health.is_healthy  # Not yet unhealthy (threshold is 3)

    def test_mark_multiple_failures(self):
        """Test that provider becomes unhealthy after threshold failures."""
        monitor = HealthMonitor()

        # Mark failures up to threshold
        for i in range(3):
            monitor.mark_failure("test_provider", f"Error {i+1}")

        health = monitor.get_health_status("test_provider")
        assert health.consecutive_failures == 3
        assert not health.is_healthy  # Now unhealthy

    def test_recovery_after_success(self):
        """Test that success resets failure counter."""
        monitor = HealthMonitor()

        # Create failures
        monitor.mark_failure("test_provider", "Error 1")
        monitor.mark_failure("test_provider", "Error 2")
        assert monitor.get_health_status("test_provider").consecutive_failures == 2

        # Mark success
        monitor.mark_success("test_provider")
        assert monitor.get_health_status("test_provider").consecutive_failures == 0
        assert monitor.is_healthy("test_provider")

    def test_get_recovery_wait_time(self):
        """Test calculating recovery wait time (exponential backoff)."""
        monitor = HealthMonitor()
        health = monitor.get_health_status("test_provider")

        # No recovery attempts yet
        wait_time = monitor.get_recovery_wait_time("test_provider")
        assert wait_time == 5  # Base wait time

        # After some recovery attempts
        health.recovery_attempts = 1
        wait_time = monitor.get_recovery_wait_time("test_provider")
        assert wait_time == 10  # 5 * 2^1

        health.recovery_attempts = 2
        wait_time = monitor.get_recovery_wait_time("test_provider")
        assert wait_time == 20  # 5 * 2^2

        # Check max limit
        health.recovery_attempts = 10
        wait_time = monitor.get_recovery_wait_time("test_provider")
        assert wait_time == HealthMonitor.RECOVERY_WAIT_MAX

    @pytest.mark.asyncio
    async def test_wait_for_recovery(self):
        """Test async wait for recovery."""
        monitor = HealthMonitor()

        # Should wait approximately 5 seconds (base time)
        start = asyncio.get_event_loop().time()
        await monitor.wait_for_recovery("test_provider")
        elapsed = asyncio.get_event_loop().time() - start

        # Allow some tolerance for timing variations
        assert 4.9 < elapsed < 6.0

    @pytest.mark.asyncio
    async def test_check_provider_health_success(self):
        """Test health check with successful result."""
        monitor = HealthMonitor()

        async def health_check():
            return True

        result = await monitor.check_provider_health("test_provider", health_check)
        assert result
        assert monitor.is_healthy("test_provider")

    @pytest.mark.asyncio
    async def test_check_provider_health_failure(self):
        """Test health check with failure."""
        monitor = HealthMonitor()

        async def health_check():
            return False

        result = await monitor.check_provider_health("test_provider", health_check)
        assert not result
        # Provider is not unhealthy after 1 failure (threshold is 3)
        health = monitor.get_health_status("test_provider")
        assert health.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_check_provider_health_timeout(self):
        """Test health check with timeout."""
        monitor = HealthMonitor()

        async def slow_health_check():
            await asyncio.sleep(20)  # Longer than timeout
            return True

        result = await monitor.check_provider_health("test_provider", slow_health_check)
        assert not result
        # Provider is not unhealthy after 1 failure (threshold is 3)
        health = monitor.get_health_status("test_provider")
        assert health.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_check_provider_health_exception(self):
        """Test health check with exception."""
        monitor = HealthMonitor()

        async def failing_health_check():
            raise ValueError("Connection failed")

        result = await monitor.check_provider_health("test_provider", failing_health_check)
        assert not result
        health = monitor.get_health_status("test_provider")
        assert "Connection failed" in health.last_error

    def test_reset_provider(self):
        """Test resetting provider health."""
        monitor = HealthMonitor()

        # Create unhealthy state
        for _ in range(3):
            monitor.mark_failure("test_provider", "Error")
        assert not monitor.is_healthy("test_provider")

        # Reset
        monitor.reset_provider("test_provider")
        health = monitor.get_health_status("test_provider")
        assert health.is_healthy
        assert health.consecutive_failures == 0
        assert health.recovery_attempts == 0

    def test_increment_recovery_attempts(self):
        """Test incrementing recovery attempt counter."""
        monitor = HealthMonitor()
        health = monitor.get_health_status("test_provider")

        assert health.recovery_attempts == 0
        monitor.increment_recovery_attempts("test_provider")
        assert health.recovery_attempts == 1

    def test_get_healthy_providers(self):
        """Test getting list of healthy providers."""
        monitor = HealthMonitor()

        monitor.mark_success("provider1")
        monitor.mark_success("provider2")

        for _ in range(3):
            monitor.mark_failure("provider3", "Error")

        healthy = monitor.get_healthy_providers()
        assert "provider1" in healthy
        assert "provider2" in healthy
        assert "provider3" not in healthy

    def test_get_unhealthy_providers(self):
        """Test getting list of unhealthy providers."""
        monitor = HealthMonitor()

        monitor.mark_success("provider1")

        for _ in range(3):
            monitor.mark_failure("provider2", "Error")

        unhealthy = monitor.get_unhealthy_providers()
        assert "provider1" not in unhealthy
        assert "provider2" in unhealthy
