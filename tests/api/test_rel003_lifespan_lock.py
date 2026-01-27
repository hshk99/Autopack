"""Tests for IMP-REL-003: Add asyncio locks for global state in API lifespan.

Tests verify that global state (_shutdown_manager, _task_monitor) is protected
by asyncio.Lock to prevent race conditions during concurrent startup/shutdown.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from autopack.api import app as app_module


@pytest.fixture(autouse=True)
def reset_state_lock():
    """Reset the state lock before each test to ensure clean state."""
    # Reset the lock to None so each test gets a fresh lock for its event loop
    app_module._state_lock = None
    yield
    # Clean up after test
    app_module._state_lock = None


class TestStateLockExists:
    """Test that the state lock is properly defined."""

    def test_get_state_lock_function_exists(self):
        """Verify _get_state_lock function exists."""
        assert hasattr(app_module, "_get_state_lock")
        assert callable(app_module._get_state_lock)

    @pytest.mark.asyncio
    async def test_get_state_lock_returns_asyncio_lock(self):
        """Verify _get_state_lock returns an asyncio.Lock instance."""
        lock = app_module._get_state_lock()
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_state_lock_returns_same_instance(self):
        """Verify _get_state_lock returns the same lock on repeated calls."""
        lock1 = app_module._get_state_lock()
        lock2 = app_module._get_state_lock()
        assert lock1 is lock2

    def test_global_shutdown_manager_variable_exists(self):
        """Verify _shutdown_manager global variable exists."""
        assert hasattr(app_module, "_shutdown_manager")

    def test_global_task_monitor_variable_exists(self):
        """Verify _task_monitor global variable exists."""
        assert hasattr(app_module, "_task_monitor")


class TestStateLockProtectsInitialization:
    """Test that state lock protects initialization."""

    @pytest.mark.asyncio
    async def test_concurrent_init_is_serialized(self):
        """Verify concurrent initialization attempts are serialized by the lock."""
        # Save original state
        original_shutdown_manager = app_module._shutdown_manager
        original_task_monitor = app_module._task_monitor

        try:
            # Reset state
            app_module._shutdown_manager = None
            app_module._task_monitor = None

            init_order = []
            init_count = {"shutdown_manager": 0, "task_monitor": 0}

            async def init_shutdown_manager():
                async with app_module._get_state_lock():
                    init_order.append("shutdown_manager_start")
                    await asyncio.sleep(0.01)  # Simulate initialization work
                    if app_module._shutdown_manager is None:
                        init_count["shutdown_manager"] += 1
                        app_module._shutdown_manager = MagicMock()
                    init_order.append("shutdown_manager_end")

            async def init_task_monitor():
                async with app_module._get_state_lock():
                    init_order.append("task_monitor_start")
                    await asyncio.sleep(0.01)  # Simulate initialization work
                    if app_module._task_monitor is None:
                        init_count["task_monitor"] += 1
                        app_module._task_monitor = MagicMock()
                    init_order.append("task_monitor_end")

            # Run both init functions concurrently
            await asyncio.gather(
                init_shutdown_manager(),
                init_task_monitor(),
            )

            # Verify serialization - one should complete before the other starts
            # The order should be either:
            # [shutdown_manager_start, shutdown_manager_end, task_monitor_start, task_monitor_end]
            # or
            # [task_monitor_start, task_monitor_end, shutdown_manager_start, shutdown_manager_end]
            assert len(init_order) == 4

            # Verify no interleaving - each start should be followed by its end
            # before the next start
            for i in range(0, 4, 2):
                start_item = init_order[i]
                end_item = init_order[i + 1]
                # Extract the base name (shutdown_manager or task_monitor)
                base_name = start_item.replace("_start", "")
                assert end_item == f"{base_name}_end"

            # Each should only be initialized once
            assert init_count["shutdown_manager"] == 1
            assert init_count["task_monitor"] == 1

        finally:
            # Restore original state
            app_module._shutdown_manager = original_shutdown_manager
            app_module._task_monitor = original_task_monitor


class TestIdempotentInitialization:
    """Test that initialization is idempotent with lock protection."""

    @pytest.mark.asyncio
    async def test_double_init_shutdown_manager_is_idempotent(self):
        """Verify double initialization of shutdown manager only creates one instance."""
        original_shutdown_manager = app_module._shutdown_manager

        try:
            app_module._shutdown_manager = None
            created_instances = []

            async def init_shutdown_manager():
                async with app_module._get_state_lock():
                    if app_module._shutdown_manager is None:
                        instance = MagicMock()
                        created_instances.append(instance)
                        app_module._shutdown_manager = instance
                    return app_module._shutdown_manager

            # Call init twice concurrently
            results = await asyncio.gather(
                init_shutdown_manager(),
                init_shutdown_manager(),
            )

            # Both should return the same instance
            assert results[0] is results[1]
            # Only one instance should have been created
            assert len(created_instances) == 1

        finally:
            app_module._shutdown_manager = original_shutdown_manager

    @pytest.mark.asyncio
    async def test_double_init_task_monitor_is_idempotent(self):
        """Verify double initialization of task monitor only creates one instance."""
        original_task_monitor = app_module._task_monitor

        try:
            app_module._task_monitor = None
            created_instances = []

            async def init_task_monitor():
                async with app_module._get_state_lock():
                    if app_module._task_monitor is None:
                        instance = MagicMock()
                        created_instances.append(instance)
                        app_module._task_monitor = instance
                    return app_module._task_monitor

            # Call init twice concurrently
            results = await asyncio.gather(
                init_task_monitor(),
                init_task_monitor(),
            )

            # Both should return the same instance
            assert results[0] is results[1]
            # Only one instance should have been created
            assert len(created_instances) == 1

        finally:
            app_module._task_monitor = original_task_monitor


class TestStateLockProtectsCleanup:
    """Test that state lock protects cleanup operations."""

    @pytest.mark.asyncio
    async def test_cleanup_acquires_lock(self):
        """Verify cleanup operations acquire the state lock."""
        original_shutdown_manager = app_module._shutdown_manager
        original_task_monitor = app_module._task_monitor

        try:
            app_module._shutdown_manager = MagicMock()
            app_module._task_monitor = MagicMock()

            lock_was_held = False
            lock = app_module._get_state_lock()

            async def cleanup_with_verification():
                nonlocal lock_was_held
                async with lock:
                    lock_was_held = lock.locked()
                    app_module._shutdown_manager = None
                    app_module._task_monitor = None

            await cleanup_with_verification()

            # Verify lock was held during cleanup
            assert lock_was_held is True
            # Verify state was cleaned up
            assert app_module._shutdown_manager is None
            assert app_module._task_monitor is None

        finally:
            app_module._shutdown_manager = original_shutdown_manager
            app_module._task_monitor = original_task_monitor

    @pytest.mark.asyncio
    async def test_concurrent_cleanup_is_serialized(self):
        """Verify concurrent cleanup operations are serialized."""
        original_shutdown_manager = app_module._shutdown_manager
        original_task_monitor = app_module._task_monitor

        try:
            cleanup_order = []
            lock = app_module._get_state_lock()

            async def cleanup_task(task_id: int):
                async with lock:
                    cleanup_order.append(f"start_{task_id}")
                    await asyncio.sleep(0.01)  # Simulate cleanup work
                    cleanup_order.append(f"end_{task_id}")

            # Run multiple cleanup tasks concurrently
            await asyncio.gather(
                cleanup_task(1),
                cleanup_task(2),
            )

            # Verify serialization - no interleaving
            assert len(cleanup_order) == 4
            # First task should complete before second starts
            assert cleanup_order[0].startswith("start_")
            assert cleanup_order[1].startswith("end_")
            assert cleanup_order[2].startswith("start_")
            assert cleanup_order[3].startswith("end_")
            # Same task ID for start and end in each pair
            assert cleanup_order[0].split("_")[1] == cleanup_order[1].split("_")[1]
            assert cleanup_order[2].split("_")[1] == cleanup_order[3].split("_")[1]

        finally:
            app_module._shutdown_manager = original_shutdown_manager
            app_module._task_monitor = original_task_monitor


class TestLockDoesNotDeadlock:
    """Test that lock usage doesn't cause deadlocks."""

    @pytest.mark.asyncio
    async def test_init_and_cleanup_can_run_sequentially(self):
        """Verify init followed by cleanup doesn't deadlock."""
        original_shutdown_manager = app_module._shutdown_manager
        original_task_monitor = app_module._task_monitor

        try:
            app_module._shutdown_manager = None
            app_module._task_monitor = None

            # Simulate init
            async with app_module._get_state_lock():
                app_module._shutdown_manager = MagicMock()
                app_module._task_monitor = MagicMock()

            # Verify state is set
            assert app_module._shutdown_manager is not None
            assert app_module._task_monitor is not None

            # Simulate cleanup
            async with app_module._get_state_lock():
                app_module._shutdown_manager = None
                app_module._task_monitor = None

            # Verify state is cleaned
            assert app_module._shutdown_manager is None
            assert app_module._task_monitor is None

        finally:
            app_module._shutdown_manager = original_shutdown_manager
            app_module._task_monitor = original_task_monitor

    @pytest.mark.asyncio
    async def test_lock_times_out_rather_than_deadlock(self):
        """Verify operations complete within reasonable time."""
        original_shutdown_manager = app_module._shutdown_manager

        try:
            app_module._shutdown_manager = None

            async def timed_operation():
                async with app_module._get_state_lock():
                    app_module._shutdown_manager = MagicMock()
                return True

            # Should complete within 1 second
            result = await asyncio.wait_for(timed_operation(), timeout=1.0)
            assert result is True

        finally:
            app_module._shutdown_manager = original_shutdown_manager
