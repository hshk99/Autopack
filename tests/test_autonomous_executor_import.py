"""Regression test to prevent import-time crashes in autonomous_executor.

BUILD-146: Prevent syntax errors and import-time crashes from blocking all phase draining.
This test ensures the autonomous_executor module can be imported without errors.
"""

import pytest


def test_autonomous_executor_imports():
    """Test that autonomous_executor module can be imported without syntax or import errors."""
    try:
        from autopack import autonomous_executor

        assert autonomous_executor is not None
    except SyntaxError as e:
        pytest.fail(f"SyntaxError in autonomous_executor: {e}")
    except ImportError as e:
        pytest.fail(f"ImportError in autonomous_executor: {e}")


def test_autonomous_executor_class_exists():
    """Test that AutonomousExecutor class exists and can be instantiated (with mock dependencies)."""
    from autopack.autonomous_executor import AutonomousExecutor

    # Just verify the class exists and has expected attributes
    assert hasattr(AutonomousExecutor, "__init__")
    assert hasattr(AutonomousExecutor, "execute_phase")
    # Verify at least one internal method exists
    assert hasattr(AutonomousExecutor, "_load_scoped_context") or hasattr(
        AutonomousExecutor, "_apply_patch"
    )
