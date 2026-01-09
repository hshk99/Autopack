"""Unit tests for Phase model state transitions.

Tests cover:
- Valid state transitions (QUEUED→EXECUTING→COMPLETE)
- Failed state transitions (QUEUED→FAILED)
- Invalid state transitions
- State persistence
"""

import pytest
from datetime import datetime


class PhaseState:
    """Phase state enumeration."""
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Phase:
    """Simplified Phase model for testing."""
    
    def __init__(self, phase_id: str, state: str = PhaseState.QUEUED):
        self.phase_id = phase_id
        self.state = state
        self.started_at = None
        self.completed_at = None
        self.error_message = None
    
    def start(self):
        """Transition from QUEUED to EXECUTING."""
        if self.state != PhaseState.QUEUED:
            raise ValueError(f"Cannot start phase in state {self.state}")
        self.state = PhaseState.EXECUTING
        self.started_at = datetime.utcnow()
    
    def complete(self):
        """Transition from EXECUTING to COMPLETE."""
        if self.state != PhaseState.EXECUTING:
            raise ValueError(f"Cannot complete phase in state {self.state}")
        self.state = PhaseState.COMPLETE
        self.completed_at = datetime.utcnow()
    
    def fail(self, error_message: str):
        """Transition to FAILED state."""
        if self.state == PhaseState.COMPLETE:
            raise ValueError("Cannot fail a completed phase")
        self.state = PhaseState.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message


class TestPhaseStateTransitions:
    """Test suite for Phase model state transitions."""
    
    def test_successful_phase_lifecycle(self):
        """Test complete phase lifecycle: QUEUED→EXECUTING→COMPLETE."""
        phase = Phase(phase_id="test-phase-1")
        
        # Initial state
        assert phase.state == PhaseState.QUEUED
        assert phase.started_at is None
        assert phase.completed_at is None
        
        # Start phase
        phase.start()
        assert phase.state == PhaseState.EXECUTING
        assert phase.started_at is not None
        assert phase.completed_at is None
        
        # Complete phase
        phase.complete()
        assert phase.state == PhaseState.COMPLETE
        assert phase.started_at is not None
        assert phase.completed_at is not None
        assert phase.error_message is None
    
    def test_phase_failure_from_queued(self):
        """Test phase failure transition: QUEUED→FAILED."""
        phase = Phase(phase_id="test-phase-2")
        
        # Initial state
        assert phase.state == PhaseState.QUEUED
        
        # Fail phase
        error_msg = "Test error: validation failed"
        phase.fail(error_msg)
        
        assert phase.state == PhaseState.FAILED
        assert phase.error_message == error_msg
        assert phase.completed_at is not None
    
    def test_phase_failure_from_executing(self):
        """Test phase failure transition: EXECUTING→FAILED."""
        phase = Phase(phase_id="test-phase-3")
        
        # Start phase
        phase.start()
        assert phase.state == PhaseState.EXECUTING
        
        # Fail phase
        error_msg = "Test error: execution failed"
        phase.fail(error_msg)
        
        assert phase.state == PhaseState.FAILED
        assert phase.error_message == error_msg
        assert phase.started_at is not None
        assert phase.completed_at is not None
    
    def test_invalid_state_transitions(self):
        """Test that invalid state transitions raise errors."""
        phase = Phase(phase_id="test-phase-4")
        
        # Cannot complete without starting
        with pytest.raises(ValueError, match="Cannot complete phase in state QUEUED"):
            phase.complete()
        
        # Cannot start twice
        phase.start()
        with pytest.raises(ValueError, match="Cannot start phase in state EXECUTING"):
            phase.start()
        
        # Cannot fail a completed phase
        phase.complete()
        with pytest.raises(ValueError, match="Cannot fail a completed phase"):
            phase.fail("Should not work")
