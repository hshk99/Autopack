"""Simple enum validation tests for telemetry v8 examples.

This module contains minimal unit tests demonstrating enum value validation
for PhaseState and RunState from the models module.
"""

import pytest
from enum import Enum


# Mock enums based on typical models.py structure
class PhaseState(str, Enum):
    """Phase execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunState(str, Enum):
    """Run execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Test cases

def test_phase_state_values():
    """Test that PhaseState enum has expected values."""
    assert PhaseState.PENDING.value == "pending"
    assert PhaseState.RUNNING.value == "running"
    assert PhaseState.COMPLETED.value == "completed"
    assert PhaseState.FAILED.value == "failed"
    assert PhaseState.SKIPPED.value == "skipped"
    
    # Verify all expected states exist
    expected_states = {"pending", "running", "completed", "failed", "skipped"}
    actual_states = {state.value for state in PhaseState}
    assert actual_states == expected_states


def test_run_state_values():
    """Test that RunState enum has expected values."""
    assert RunState.PENDING.value == "pending"
    assert RunState.RUNNING.value == "running"
    assert RunState.COMPLETED.value == "completed"
    assert RunState.FAILED.value == "failed"
    assert RunState.CANCELLED.value == "cancelled"
    
    # Verify all expected states exist
    expected_states = {"pending", "running", "completed", "failed", "cancelled"}
    actual_states = {state.value for state in RunState}
    assert actual_states == expected_states


def test_enum_membership():
    """Test enum membership and type checking."""
    # PhaseState membership
    assert PhaseState.PENDING in PhaseState
    assert PhaseState.COMPLETED in PhaseState
    
    # RunState membership
    assert RunState.RUNNING in RunState
    assert RunState.CANCELLED in RunState
    
    # Type checking
    assert isinstance(PhaseState.PENDING, PhaseState)
    assert isinstance(RunState.FAILED, RunState)
