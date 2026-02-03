"""
V2 Telemetry Logger

Tracks all V2 decisions for tuning: agent state detection, nudges sent,
escalations, provider usage, timing metrics. Output to v2_telemetry.json.

Provides structured logging for system optimization and analysis.
"""

import json
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict, field


class EventType(Enum):
    """Types of telemetry events for V2 autonomous loop."""
    AGENT_STATE_DETECTED = "agent_state_detected"
    NUDGE_SENT = "nudge_sent"
    NUDGE_RESPONSE = "nudge_response"
    ESCALATION = "escalation"
    MODEL_USAGE = "model_usage"
    PHASE_START = "phase_start"
    PHASE_COMPLETE = "phase_complete"
    CI_EVENT = "ci_event"
    RESOURCE_ALERT = "resource_alert"
    NETWORK_STATUS = "network_status"
    TELEMETRY_ROTATED = "telemetry_rotated"
    WAVE_COMPLETE = "wave_complete"
    PROJECT_COMPLETE = "project_complete"


class AgentState(Enum):
    """Agent states for telemetry tracking."""
    IDLE = "idle"
    THINKING = "thinking"
    ASKING_USER = "asking_user"
    TASK_DONE = "task_done"
    ERROR_STUCK = "error_stuck"
    CI_FAILURE = "ci_failure"
    WORKING = "working"


class EscalationLevel(Enum):
    """Escalation levels for tracking."""
    HAIKU_NUDGE = "haiku_nudge"
    OPUS_ESCALATION = "opus_escalation"
    HUMAN_FLAG = "human_flag"


class ModelProvider(Enum):
    """Model providers for usage tracking."""
    CLAUDE_MAX = "claude_max"
    CLAUDE_API = "claude_api"
    GLM_SUBSCRIPTION = "glm_subscription"
    GLM_API = "glm_api"


@dataclass
class TelemetryEvent:
    """Structured telemetry event."""
    timestamp: str
    event_type: str
    wave: Optional[int] = None
    phase_id: Optional[str] = None
    agent_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStateEvent:
    """Agent state detection telemetry."""
    previous_state: str
    current_state: str
    idle_duration_sec: Optional[float] = None
    last_output: Optional[str] = None
    thinking_indicators: List[str] = field(default_factory=list)
    tool_calls_in_progress: int = 0


@dataclass
class NudgeEvent:
    """Nudge sent telemetry."""
    nudge_number: int
    nudge_type: str
    content: str
    escalation_level: Optional[str] = None
    model_used: Optional[str] = None
    previous_nudges: int = 0
    response_status: Optional[str] = None


@dataclass
class EscalationEvent:
    """Escalation telemetry."""
    escalation_type: str
    from_level: Optional[str] = None
    to_level: str = None
    reason: str = ""
    previous_attempts: int = 0
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelUsageEvent:
    """Model usage telemetry."""
    provider: str
    model: str
    task_type: str  # critical, non_critical
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_sec: Optional[float] = None
    success: bool = True
    error_type: Optional[str] = None


@dataclass
class TimingMetric:
    """Timing metrics for events."""
    event_name: str
    start_time: str
    end_time: str
    duration_sec: float
    wave: Optional[int] = None
    phase_id: Optional[str] = None


class TelemetryLogger:
    """V2 Telemetry Logger for system optimization and analysis.

    Tracks all V2 decisions including:
    - Agent state detection events
    - Nudges sent and responses
    - Escalations
    - Model usage by provider
    - Timing metrics

    Output: v2_telemetry.json with structured JSON for analysis.
    """

    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        rotation_hours: int = 24,
        max_events_per_file: int = 10000
    ):
        """Initialize telemetry logger.

        Args:
            logs_dir: Directory for telemetry files. Defaults to ../logs from src.
            rotation_hours: Hours between log rotations.
            max_events_per_file: Maximum events before forced rotation.
        """
        self._write_lock = threading.Lock()
        
        # Set up logs directory
        if logs_dir is None:
            # Default to ../logs relative to this file
            self.logs_dir = Path(__file__).parent.parent.parent / "logs"
        else:
            self.logs_dir = Path(logs_dir)
        
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.rotation_hours = rotation_hours
        self.max_events_per_file = max_events_per_file
        
        # Current telemetry file
        self.current_telemetry_file = self._get_current_telemetry_path()
        self.last_rotation = datetime.now()
        self.event_count = 0
        
        # Initialize telemetry file
        self._init_telemetry_file()
        
        # In-memory buffer for fast access
        self._events_buffer: List[TelemetryEvent] = []
    
    def _get_current_telemetry_path(self) -> Path:
        """Get path to current telemetry file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.logs_dir / f"v2_telemetry_{timestamp}.json"
    
    def _init_telemetry_file(self):
        """Initialize telemetry file with metadata."""
        telemetry_data = {
            "metadata": {
                "version": "2.0",
                "created_at": datetime.now().isoformat(),
                "rotation_hours": self.rotation_hours,
                "max_events_per_file": self.max_events_per_file
            },
            "events": []
        }
        with open(self.current_telemetry_file, 'w', encoding='utf-8') as f:
            json.dump(telemetry_data, f, indent=2)
    
    def _should_rotate(self) -> bool:
        """Check if telemetry file should be rotated."""
        now = datetime.now()
        hours_since_rotation = (now - self.last_rotation).total_seconds() / 3600
        return (hours_since_rotation >= self.rotation_hours or 
                self.event_count >= self.max_events_per_file)
    
    def _rotate_telemetry(self):
        """Rotate telemetry file to new file."""
        # Archive current file
        old_file = self.current_telemetry_file
        archived_name = old_file.name.replace(".json", "_archived.json")
        archived_path = old_file.parent / archived_name
        old_file.rename(archived_path)
        
        # Create new file
        self.current_telemetry_file = self._get_current_telemetry_path()
        self.last_rotation = datetime.now()
        self.event_count = 0
        self._init_telemetry_file()
        
        # Log rotation event
        self.log_event(
            event_type=EventType.TELEMETRY_ROTATED,
            data={
                "archived_file": str(archived_path),
                "new_file": str(self.current_telemetry_file),
                "events_in_file": len(self._events_buffer)
            }
        )
    
    def log_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        wave: Optional[int] = None,
        phase_id: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> None:
        """Log a telemetry event.

        Thread-safe with write lock. Supports automatic rotation.

        Args:
            event_type: Type of telemetry event.
            data: Event-specific data dictionary.
            wave: Optional wave number.
            phase_id: Optional phase identifier.
            agent_id: Optional agent identifier.
        """
        with self._write_lock:
            # Check for rotation
            if self._should_rotate():
                self._rotate_telemetry()
            
            # Create event
            event = TelemetryEvent(
                timestamp=datetime.now().isoformat(),
                event_type=event_type.value,
                wave=wave,
                phase_id=phase_id,
                agent_id=agent_id,
                data=data
            )
            
            # Add to buffer
            self._events_buffer.append(event)
            self.event_count += 1
            
            # Write to file
            self._write_event_to_file(event)
    
    def _write_event_to_file(self, event: TelemetryEvent):
        """Append event to telemetry file."""
        try:
            # Read current data
            with open(self.current_telemetry_file, 'r', encoding='utf-8') as f:
                telemetry_data = json.load(f)
            
            # Append event
            telemetry_data["events"].append(asdict(event))
            
            # Update metadata
            telemetry_data["metadata"]["last_updated"] = datetime.now().isoformat()
            telemetry_data["metadata"]["event_count"] = len(telemetry_data["events"])
            
            # Write back
            with open(self.current_telemetry_file, 'w', encoding='utf-8') as f:
                json.dump(telemetry_data, f, indent=2)
        except (json.JSONDecodeError, KeyError) as e:
            # File corruption or invalid format - reinitialize
            self._init_telemetry_file()
            self.log_event(
                event_type=EventType.TELEMETRY_ROTATED,
                data={
                    "reason": "file_corruption",
                    "error": str(e)
                }
            )
    
    def log_agent_state(
        self,
        agent_id: str,
        previous_state: AgentState,
        current_state: AgentState,
        phase_id: Optional[str] = None,
        wave: Optional[int] = None,
        idle_duration_sec: Optional[float] = None,
        last_output: Optional[str] = None,
        thinking_indicators: Optional[List[str]] = None,
        tool_calls_in_progress: int = 0
    ) -> None:
        """Log agent state detection event.

        Args:
            agent_id: Agent identifier.
            previous_state: Previous agent state.
            current_state: Current agent state.
            phase_id: Optional phase identifier.
            wave: Optional wave number.
            idle_duration_sec: Optional duration of idle state.
            last_output: Optional last agent output.
            thinking_indicators: List of thinking indicators detected.
            tool_calls_in_progress: Number of tool calls in progress.
        """
        state_event = AgentStateEvent(
            previous_state=previous_state.value,
            current_state=current_state.value,
            idle_duration_sec=idle_duration_sec,
            last_output=last_output,
            thinking_indicators=thinking_indicators or [],
            tool_calls_in_progress=tool_calls_in_progress
        )
        
        self.log_event(
            event_type=EventType.AGENT_STATE_DETECTED,
            data=asdict(state_event),
            wave=wave,
            phase_id=phase_id,
            agent_id=agent_id
        )
    
    def log_nudge(
        self,
        agent_id: str,
        nudge_number: int,
        nudge_type: str,
        content: str,
        escalation_level: Optional[EscalationLevel] = None,
        model_used: Optional[ModelProvider] = None,
        previous_nudges: int = 0,
        phase_id: Optional[str] = None,
        wave: Optional[int] = None
    ) -> None:
        """Log nudge sent event.

        Args:
            agent_id: Agent identifier.
            nudge_number: Sequential nudge number for this agent.
            nudge_type: Type of nudge.
            content: Nudge content.
            escalation_level: Optional escalation level.
            model_used: Optional model used to generate nudge.
            previous_nudges: Number of previous nudges sent.
            phase_id: Optional phase identifier.
            wave: Optional wave number.
        """
        nudge_event = NudgeEvent(
            nudge_number=nudge_number,
            nudge_type=nudge_type,
            content=content,
            escalation_level=escalation_level.value if escalation_level else None,
            model_used=model_used.value if model_used else None,
            previous_nudges=previous_nudges,
            response_status=None
        )
        
        self.log_event(
            event_type=EventType.NUDGE_SENT,
            data=asdict(nudge_event),
            wave=wave,
            phase_id=phase_id,
            agent_id=agent_id
        )
    
    def log_nudge_response(
        self,
        agent_id: str,
        nudge_number: int,
        response_status: str,
        response_time_sec: Optional[float] = None,
        phase_id: Optional[str] = None,
        wave: Optional[int] = None
    ) -> None:
        """Log nudge response event.

        Args:
            agent_id: Agent identifier.
            nudge_number: Nudge number being responded to.
            response_status: Status of agent response (e.g., "acknowledged", "completed").
            response_time_sec: Time to respond to nudge.
            phase_id: Optional phase identifier.
            wave: Optional wave number.
        """
        self.log_event(
            event_type=EventType.NUDGE_RESPONSE,
            data={
                "nudge_number": nudge_number,
                "response_status": response_status,
                "response_time_sec": response_time_sec
            },
            wave=wave,
            phase_id=phase_id,
            agent_id=agent_id
        )
    
    def log_escalation(
        self,
        agent_id: str,
        escalation_type: EscalationLevel,
        from_level: Optional[EscalationLevel] = None,
        reason: str = "",
        previous_attempts: int = 0,
        phase_id: Optional[str] = None,
        wave: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log escalation event.

        Args:
            agent_id: Agent identifier.
            escalation_type: Type of escalation.
            from_level: Previous escalation level (if any).
            reason: Reason for escalation.
            previous_attempts: Number of previous nudges/attempts.
            phase_id: Optional phase identifier.
            wave: Optional wave number.
            context: Additional context about escalation.
        """
        escalation_event = EscalationEvent(
            escalation_type=escalation_type.value,
            from_level=from_level.value if from_level else None,
            to_level=escalation_type.value,
            reason=reason,
            previous_attempts=previous_attempts,
            context=context or {}
        )
        
        self.log_event(
            event_type=EventType.ESCALATION,
            data=asdict(escalation_event),
            wave=wave,
            phase_id=phase_id,
            agent_id=agent_id
        )
    
    def log_model_usage(
        self,
        provider: ModelProvider,
        model: str,
        task_type: str,
        tokens_used: Optional[int] = None,
        cost_usd: Optional[float] = None,
        duration_sec: Optional[float] = None,
        success: bool = True,
        error_type: Optional[str] = None,
        phase_id: Optional[str] = None,
        wave: Optional[int] = None
    ) -> None:
        """Log model usage event.

        Args:
            provider: Model provider used.
            model: Model name.
            task_type: Type of task (critical, non_critical).
            tokens_used: Optional token count.
            cost_usd: Optional cost in USD.
            duration_sec: Optional duration of request.
            success: Whether request was successful.
            error_type: Optional error type if failed.
            phase_id: Optional phase identifier.
            wave: Optional wave number.
        """
        usage_event = ModelUsageEvent(
            provider=provider.value,
            model=model,
            task_type=task_type,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            duration_sec=duration_sec,
            success=success,
            error_type=error_type
        )
        
        self.log_event(
            event_type=EventType.MODEL_USAGE,
            data=asdict(usage_event),
            wave=wave,
            phase_id=phase_id
        )
    
    def log_timing_metric(
        self,
        event_name: str,
        start_time: datetime,
        end_time: datetime,
        phase_id: Optional[str] = None,
        wave: Optional[int] = None
    ) -> None:
        """Log timing metric for an event.

        Args:
            event_name: Name of the timed event.
            start_time: Start datetime.
            end_time: End datetime.
            phase_id: Optional phase identifier.
            wave: Optional wave number.
        """
        duration_sec = (end_time - start_time).total_seconds()
        
        timing_metric = TimingMetric(
            event_name=event_name,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_sec=duration_sec,
            wave=wave,
            phase_id=phase_id
        )
        
        self.log_event(
            event_type=EventType.PHASE_COMPLETE if "phase" in event_name.lower() else EventType.MODEL_USAGE,
            data=asdict(timing_metric),
            wave=wave,
            phase_id=phase_id
        )
    
    def log_phase_start(
        self,
        phase_id: str,
        wave: int,
        phase_title: str,
        worktree_path: Optional[str] = None
    ) -> None:
        """Log phase start event.

        Args:
            phase_id: Phase identifier.
            wave: Wave number.
            phase_title: Human-readable phase title.
            worktree_path: Optional path to phase worktree.
        """
        self.log_event(
            event_type=EventType.PHASE_START,
            data={
                "phase_id": phase_id,
                "phase_title": phase_title,
                "worktree_path": worktree_path
            },
            wave=wave,
            phase_id=phase_id
        )
    
    def log_phase_complete(
        self,
        phase_id: str,
        wave: int,
        phase_title: str,
        pr_number: Optional[int] = None,
        duration_sec: Optional[float] = None
    ) -> None:
        """Log phase complete event.

        Args:
            phase_id: Phase identifier.
            wave: Wave number.
            phase_title: Human-readable phase title.
            pr_number: Optional PR number for this phase.
            duration_sec: Optional duration of phase execution.
        """
        self.log_event(
            event_type=EventType.PHASE_COMPLETE,
            data={
                "phase_id": phase_id,
                "phase_title": phase_title,
                "pr_number": pr_number,
                "duration_sec": duration_sec
            },
            wave=wave,
            phase_id=phase_id
        )
    
    def log_ci_event(
        self,
        pr_number: int,
        event_type: str,  # e.g., "failed", "succeeded", "rerun"
        failure_category: Optional[str] = None,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        wave: Optional[int] = None
    ) -> None:
        """Log CI event.

        Args:
            pr_number: PR number.
            event_type: Type of CI event.
            failure_category: Optional failure category.
            run_id: Optional CI run ID.
            phase_id: Optional phase identifier.
            wave: Optional wave number.
        """
        self.log_event(
            event_type=EventType.CI_EVENT,
            data={
                "pr_number": pr_number,
                "ci_event_type": event_type,
                "failure_category": failure_category,
                "run_id": run_id
            },
            wave=wave,
            phase_id=phase_id
        )
    
    def log_wave_complete(
        self,
        wave: int,
        total_phases: int,
        completed_phases: int,
        duration_sec: float
    ) -> None:
        """Log wave completion event.

        Args:
            wave: Wave number.
            total_phases: Total phases in wave.
            completed_phases: Number of completed phases.
            duration_sec: Duration of wave execution.
        """
        self.log_event(
            event_type=EventType.WAVE_COMPLETE,
            data={
                "wave": wave,
                "total_phases": total_phases,
                "completed_phases": completed_phases,
                "duration_sec": duration_sec
            },
            wave=wave
        )
    
    def get_recent_events(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent telemetry events from buffer.

        Args:
            event_type: Optional event type filter.
            limit: Maximum number of events to return.

        Returns:
            List of recent events (as dicts).
        """
        events = self._events_buffer
        if event_type:
            events = [e for e in events if e.event_type == event_type.value]
        return [asdict(e) for e in events[-limit:]]
    
    def get_event_count(self) -> int:
        """Get total number of events logged."""
        return len(self._events_buffer)
    
    def get_current_file_path(self) -> Path:
        """Get path to current telemetry file."""
        return self.current_telemetry_file


# Global telemetry logger instance
_telemetry_logger: Optional[TelemetryLogger] = None
_logger_lock = threading.Lock()


def get_telemetry_logger(
    logs_dir: Optional[Path] = None,
    rotation_hours: int = 24,
    max_events_per_file: int = 10000
) -> TelemetryLogger:
    """Get or create global telemetry logger instance.

    Thread-safe singleton pattern with double-check locking.

    Args:
        logs_dir: Optional directory for telemetry files.
        rotation_hours: Hours between log rotations.
        max_events_per_file: Maximum events before forced rotation.

    Returns:
        The TelemetryLogger instance.
    """
    global _telemetry_logger
    if _telemetry_logger is None or logs_dir is not None:
        with _logger_lock:
            # Double-check pattern
            if _telemetry_logger is None or logs_dir is not None:
                _telemetry_logger = TelemetryLogger(
                    logs_dir=logs_dir,
                    rotation_hours=rotation_hours,
                    max_events_per_file=max_events_per_file
                )
    return _telemetry_logger
