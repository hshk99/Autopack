"""Autopilot session models (Pydantic-based, validates against autopilot_session_v1.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..schema_validation import validate_autopilot_session_v1


class ExecutionSummary(BaseModel):
    """Execution statistics."""

    model_config = ConfigDict(extra="forbid")

    total_actions: int = 0
    auto_approved_actions: int = 0
    executed_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    blocked_actions: int = 0


class ApprovalRequest(BaseModel):
    """Action requiring human approval."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    approval_status: Literal["requires_approval", "blocked"]
    reason: str


class ErrorLogEntry(BaseModel):
    """Error encountered during execution."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    action_id: Optional[str] = None
    error_type: str
    error_message: str


class AutopilotMetadata(BaseModel):
    """Optional metadata for autopilot session."""

    model_config = ConfigDict(extra="forbid")

    autopilot_version: Optional[str] = None
    session_duration_ms: Optional[int] = None
    enabled_explicitly: Optional[bool] = None


class AutopilotSessionV1(BaseModel):
    """Autopilot Session v1: Log of autonomous execution attempts.

    This model captures what autopilot tried to do, what it executed,
    and where it stopped (if blocked by approval gates).

    All artifacts validate against docs/schemas/autopilot_session_v1.schema.json.
    """

    model_config = ConfigDict(extra="forbid")

    format_version: Literal["v1"] = "v1"
    project_id: str
    run_id: str
    session_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Literal["running", "completed", "blocked_approval_required", "failed", "aborted"]
    anchor_id: str
    gap_report_id: str
    plan_proposal_id: str
    execution_summary: Optional[ExecutionSummary] = None
    executed_action_ids: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    approval_requests: List[ApprovalRequest] = Field(default_factory=list)
    error_log: List[ErrorLogEntry] = Field(default_factory=list)
    metadata: Optional[AutopilotMetadata] = None

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict with ISO datetime formatting.

        Returns:
            Dictionary ready for JSON serialization
        """
        data = self.model_dump(mode="json", exclude_none=True)
        # Ensure datetimes are ISO strings
        if isinstance(data.get("started_at"), datetime):
            data["started_at"] = data["started_at"].isoformat()
        if isinstance(data.get("completed_at"), datetime):
            data["completed_at"] = data["completed_at"].isoformat()
        # Handle error_log timestamps
        if "error_log" in data:
            for entry in data["error_log"]:
                if isinstance(entry.get("timestamp"), datetime):
                    entry["timestamp"] = entry["timestamp"].isoformat()
        return data

    def validate_against_schema(self) -> None:
        """Validate this session against the JSON schema.

        Raises:
            SchemaValidationError: If validation fails
        """
        data = self.to_json_dict()
        validate_autopilot_session_v1(data)

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> AutopilotSessionV1:
        """Create AutopilotSessionV1 from JSON dict.

        Args:
            data: JSON dictionary

        Returns:
            AutopilotSessionV1 instance

        Raises:
            SchemaValidationError: If data doesn't match schema
        """
        # Validate first
        validate_autopilot_session_v1(data)
        return cls.model_validate(data)

    def save_to_file(self, path: Path) -> None:
        """Save autopilot session to JSON file.

        Args:
            path: Path to save to
        """
        self.validate_against_schema()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_json_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: Path) -> AutopilotSessionV1:
        """Load autopilot session from JSON file.

        Args:
            path: Path to load from

        Returns:
            AutopilotSessionV1 instance
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_json_dict(data)
