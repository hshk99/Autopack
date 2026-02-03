"""
Demo script for V2 Telemetry Logger

Shows how to use the telemetry logger to track various events.
"""

import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

import time
from datetime import datetime

# Import telemetry logger
from monitoring.telemetry_logger import (
    TelemetryLogger,
    get_telemetry_logger,
    EventType,
    AgentState,
    EscalationLevel,
    ModelProvider
)


def demo_telemetry_logger():
    """Demonstrate telemetry logger functionality."""
    print("V2 Telemetry Logger Demo")
    print("=" * 60)
    
    # Initialize telemetry logger
    logs_dir = Path(__file__).parent.parent.parent / "logs"
    telemetry = TelemetryLogger(logs_dir=logs_dir, rotation_hours=1)
    
    print(f"\nTelemetry file: {telemetry.get_current_file_path()}")
    print(f"Logs directory: {logs_dir}")
    
    # Demo: Log phase start
    print("\n1. Logging phase start...")
    telemetry.log_phase_start(
        phase_id="telemetry001",
        wave=2,
        phase_title="Telemetry Logger",
        worktree_path="C:\\dev\\autopack_loop_v2_c1_w2_telemetry001"
    )
    
    # Demo: Log agent state detection
    print("2. Logging agent state detection...")
    telemetry.log_agent_state(
        agent_id="agent_001",
        previous_state=AgentState.WORKING,
        current_state=AgentState.IDLE,
        phase_id="telemetry001",
        wave=2,
        idle_duration_sec=35.5,
        last_output="Task completed successfully",
        thinking_indicators=[],
        tool_calls_in_progress=0
    )
    
    # Demo: Log nudge sent
    print("3. Logging nudge sent...")
    telemetry.log_nudge(
        agent_id="agent_001",
        nudge_number=1,
        nudge_type="IDLE_DETECTED",
        content="Agent appears to be idle. Please continue with the task.",
        escalation_level=EscalationLevel.HAIKU_NUDGE,
        model_used=ModelProvider.CLAUDE_API,
        previous_nudges=0,
        phase_id="telemetry001",
        wave=2
    )
    
    # Demo: Log model usage
    print("4. Logging model usage...")
    telemetry.log_model_usage(
        provider=ModelProvider.CLAUDE_API,
        model="claude-3-haiku-20240307",
        task_type="non_critical",
        tokens_used=1250,
        cost_usd=0.00125,
        duration_sec=2.5,
        success=True,
        phase_id="telemetry001",
        wave=2
    )
    
    # Demo: Log escalation
    print("5. Logging escalation...")
    telemetry.log_escalation(
        agent_id="agent_001",
        escalation_type=EscalationLevel.OPUS_ESCALATION,
        from_level=EscalationLevel.HAIKU_NUDGE,
        reason="Agent did not respond to Haiku nudge within timeout",
        previous_attempts=2,
        phase_id="telemetry001",
        wave=2,
        context={"nudge_number": 2, "timeout_sec": 300}
    )
    
    # Demo: Log timing metric
    print("6. Logging timing metric...")
    start_time = datetime.now()
    time.sleep(0.1)  # Simulate work
    end_time = datetime.now()
    telemetry.log_timing_metric(
        event_name="phase_telemetry001_execution",
        start_time=start_time,
        end_time=end_time,
        phase_id="telemetry001",
        wave=2
    )
    
    # Demo: Log phase complete
    print("7. Logging phase complete...")
    telemetry.log_phase_complete(
        phase_id="telemetry001",
        wave=2,
        phase_title="Telemetry Logger",
        pr_number=42,
        duration_sec=180.0
    )
    
    # Demo: Log CI event
    print("8. Logging CI event...")
    telemetry.log_ci_event(
        pr_number=42,
        event_type="succeeded",
        failure_category=None,
        run_id="gh-run-12345",
        phase_id="telemetry001",
        wave=2
    )
    
    # Demo: Log wave complete
    print("9. Logging wave complete...")
    telemetry.log_wave_complete(
        wave=2,
        total_phases=11,
        completed_phases=11,
        duration_sec=86400.0
    )
    
    # Get recent events
    print("\n10. Retrieving recent events...")
    recent_events = telemetry.get_recent_events(limit=5)
    print(f"Found {len(recent_events)} recent events:")
    for event in recent_events:
        print(f"  - {event['event_type']}: {event['timestamp']}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"Total events logged: {telemetry.get_event_count()}")
    print(f"Telemetry file: {telemetry.get_current_file_path()}")
    print("\nCheck the logs directory for v2_telemetry_*.json files.")


def demo_global_logger():
    """Demonstrate global logger pattern."""
    print("\n\nGlobal Logger Pattern Demo")
    print("=" * 60)
    
    # Get global logger instance
    telemetry = get_telemetry_logger()
    
    print(f"Using global logger: {telemetry.get_current_file_path()}")
    
    # Log some events
    telemetry.log_event(
        event_type=EventType.MODEL_USAGE,
        data={"test": "global_pattern"},
        wave=2
    )
    
    print(f"Event logged. Total events: {telemetry.get_event_count()}")


if __name__ == "__main__":
    demo_telemetry_logger()
    demo_global_logger()
