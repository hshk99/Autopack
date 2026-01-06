"""Gap report models (Pydantic-based, validates against gap_report_v1.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..schema_validation import validate_gap_report_v1


class GapExcerpt(BaseModel):
    """Evidence excerpt from a file."""

    model_config = ConfigDict(extra="forbid")

    source: str
    content_hash: Optional[str] = None
    preview: Optional[str] = None


class GapEvidence(BaseModel):
    """Evidence pointers for a gap."""

    model_config = ConfigDict(extra="forbid")

    file_paths: List[str] = Field(default_factory=list)
    test_names: List[str] = Field(default_factory=list)
    excerpts: List[GapExcerpt] = Field(default_factory=list)


class SafeRemediation(BaseModel):
    """Safe remediation approach for a gap."""

    model_config = ConfigDict(extra="forbid")

    approach: Optional[str] = None
    requires_approval: bool = True
    estimated_actions: Optional[int] = None


class Gap(BaseModel):
    """A detected gap in the workspace."""

    model_config = ConfigDict(extra="forbid")

    gap_id: str
    gap_type: Literal[
        "doc_drift",
        "root_clutter",
        "sot_duplicate",
        "test_infra_drift",
        "memory_budget_cap_issue",
        "windows_encoding_issue",
        "baseline_policy_drift",
        "protected_path_violation",
        "db_lock_contention",
        "git_state_corruption",
        "unknown",
    ]
    title: Optional[str] = None
    description: Optional[str] = None
    detection_signals: List[str]
    evidence: Optional[GapEvidence] = None
    risk_classification: Literal["critical", "high", "medium", "low", "info"]
    blocks_autopilot: bool
    safe_remediation: Optional[SafeRemediation] = None


class GapSummary(BaseModel):
    """Summary statistics for gap report."""

    model_config = ConfigDict(extra="forbid")

    total_gaps: int = 0
    critical_gaps: int = 0
    high_gaps: int = 0
    medium_gaps: int = 0
    low_gaps: int = 0
    autopilot_blockers: int = 0


class GapMetadata(BaseModel):
    """Optional metadata for gap report."""

    model_config = ConfigDict(extra="forbid")

    scanner_version: Optional[str] = None
    scan_duration_ms: Optional[int] = None


class GapReportV1(BaseModel):
    """Gap Report v1: Deterministic gap detection output.

    This model captures detected gaps in the workspace state,
    providing evidence, risk classification, and remediation guidance.

    All artifacts validate against docs/schemas/gap_report_v1.schema.json.
    """

    model_config = ConfigDict(extra="forbid")

    format_version: Literal["v1"] = "v1"
    project_id: str
    run_id: str
    generated_at: datetime
    workspace_state_digest: Optional[str] = None
    gaps: List[Gap] = Field(default_factory=list)
    summary: Optional[GapSummary] = None
    metadata: Optional[GapMetadata] = None

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict with ISO datetime formatting.

        Returns:
            Dictionary ready for JSON serialization
        """
        data = self.model_dump(mode="json", exclude_none=True)
        # Ensure datetimes are ISO strings
        if isinstance(data.get("generated_at"), datetime):
            data["generated_at"] = data["generated_at"].isoformat()
        return data

    def validate_against_schema(self) -> None:
        """Validate this report against the JSON schema.

        Raises:
            SchemaValidationError: If validation fails
        """
        data = self.to_json_dict()
        validate_gap_report_v1(data)

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> GapReportV1:
        """Create GapReportV1 from JSON dict.

        Args:
            data: JSON dictionary

        Returns:
            GapReportV1 instance

        Raises:
            SchemaValidationError: If data doesn't match schema
        """
        # Validate first
        validate_gap_report_v1(data)
        return cls.model_validate(data)

    def save_to_file(self, path: Path) -> None:
        """Save gap report to JSON file.

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
    def load_from_file(cls, path: Path) -> GapReportV1:
        """Load gap report from JSON file.

        Args:
            path: Path to load from

        Returns:
            GapReportV1 instance
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_json_dict(data)
