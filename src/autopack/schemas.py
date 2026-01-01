"""Pydantic schemas for API requests and responses"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class RunCreate(BaseModel):
    """Request to create a new run"""

    run_id: str = Field(..., description="Unique identifier for the run")
    safety_profile: str = Field(default="normal", description="normal or safety_critical")
    run_scope: str = Field(default="multi_tier", description="multi_tier or single_tier")
    token_cap: Optional[int] = Field(default=5_000_000, description="Maximum tokens for this run")
    max_phases: Optional[int] = Field(default=25, description="Maximum phases for this run")
    max_duration_minutes: Optional[int] = Field(default=120, description="Maximum duration in minutes")


class TierCreate(BaseModel):
    """Tier to be created within a run"""

    tier_id: str = Field(..., description="Tier identifier (e.g. T1, T2)")
    tier_index: int = Field(..., description="Order index for this tier")
    name: str = Field(..., description="Human-readable tier name")
    description: Optional[str] = Field(None, description="Tier description")


class PhaseCreate(BaseModel):
    """Phase to be created within a tier"""

    phase_id: str = Field(..., description="Phase identifier (e.g. F2.3)")
    phase_index: int = Field(..., description="Order index for this phase")
    tier_id: str = Field(..., description="Parent tier identifier")
    name: str = Field(..., description="Human-readable phase name")
    description: Optional[str] = Field(None, description="Phase description")
    task_category: Optional[str] = Field(None, description="Task category (e.g. schema_change)")
    complexity: Optional[str] = Field(None, description="Complexity: low, medium, or high")
    builder_mode: Optional[str] = Field(None, description="Builder mode (e.g. tweak_light)")
    scope: Optional[Dict[str, Any]] = Field(None, description="Scope configuration: paths and read_only_context")

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_read_only_context(cls, v: Any) -> Any:
        """Normalize read_only_context to canonical dict format at API boundary.

        BUILD-145 P0 Schema Normalization: Ensures all consumers receive canonical
        format even if legacy string format is provided.

        Supports two formats:
        - Legacy: ["path/to/file.py", ...]
        - New: [{"path": "path/to/file.py", "reason": "..."}, ...]

        Normalizes to canonical dict format: [{"path": "...", "reason": ""}, ...]
        """
        if v is None or not isinstance(v, dict):
            return v

        # Normalize read_only_context entries to canonical dict format
        read_only_context = v.get("read_only_context")
        if read_only_context and isinstance(read_only_context, list):
            normalized_entries = []
            for entry in read_only_context:
                if isinstance(entry, dict):
                    # Already in dict format - validate it has non-empty 'path'
                    path = entry.get("path")
                    if path:  # Skip if path is None, empty string, or missing
                        normalized_entries.append({
                            "path": path,
                            "reason": entry.get("reason", "")
                        })
                    # Skip invalid entries (missing 'path', empty path, None path)
                elif isinstance(entry, str):
                    # Legacy string format - normalize to dict
                    # Note: empty strings are still included (executor may handle them)
                    normalized_entries.append({
                        "path": entry,
                        "reason": ""
                    })
                # Skip invalid entry types (int, list, None, etc.)

            # Update scope with normalized entries
            v["read_only_context"] = normalized_entries

        return v


class RunStartRequest(BaseModel):
    """Request to start a run with tiers and phases"""

    run: RunCreate
    tiers: List[TierCreate] = Field(default_factory=list)
    phases: List[PhaseCreate] = Field(default_factory=list)


class PhaseStatusUpdate(BaseModel):
    """Request to update phase status"""

    state: str = Field(..., description="New phase state")
    builder_attempts: Optional[int] = Field(None)
    tokens_used: Optional[int] = Field(None)
    minor_issues_count: Optional[int] = Field(None)
    major_issues_count: Optional[int] = Field(None)
    quality_level: Optional[str] = Field(None, description="Quality level: ok, needs_review, blocked")
    quality_blocked: Optional[bool] = Field(None, description="Whether phase is blocked by quality gate")


class PhaseResponse(BaseModel):
    """Phase information response"""

    id: int
    phase_id: str
    run_id: str
    tier_id: int
    name: str
    description: Optional[str]
    state: str
    task_category: Optional[str]
    complexity: Optional[str]
    builder_mode: Optional[str]
    phase_index: int
    scope: Optional[Dict[str, Any]] = None

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_scope(cls, v: Any) -> Any:
        """Normalize legacy / malformed scope values into a dict.

        Some legacy runs persisted `Phase.scope` as a JSON string (or even a plain string),
        which can cause API serialization/validation to fail and surface as a 500 on
        `GET /runs/{run_id}`. We coerce these into a dict so executors can continue draining
        (typically triggering scope auto-fix because `scope.paths` is missing).
        """
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                loaded = json.loads(v)
            except Exception:
                return {"_legacy_text": v}
            if isinstance(loaded, dict):
                return loaded
            if isinstance(loaded, str):
                return {"_legacy_text": loaded}
            return {"_legacy_value": loaded}
        # e.g. list/bool/int from old JSON blobs
        return {"_legacy_value": v}

    model_config = ConfigDict(from_attributes=True)


class TierResponse(BaseModel):
    """Tier information response"""

    id: int
    tier_id: str
    name: str
    state: str
    tier_index: int
    cleanliness: str
    minor_issues_count: int
    major_issues_count: int
    phases: List[PhaseResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RunResponse(BaseModel):
    """Run information response"""

    id: str
    state: str
    safety_profile: str
    run_scope: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    tokens_used: int
    ci_runs_used: int
    minor_issues_count: int
    major_issues_count: int
    promotion_eligible_to_main: str
    debt_status: Optional[str]
    failure_reason: Optional[str]
    tiers: List[TierResponse] = Field(default_factory=list)
    # Some runs (e.g. patch-scoped or legacy) may not have Tier rows populated.
    # Include a top-level phases list so executors can still select queued work.
    phases: List[PhaseResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Storage Optimizer Schemas (BUILD-149 Phase 2)
# ==============================================================================

class StorageScanRequest(BaseModel):
    """Request to trigger a new storage scan"""

    scan_type: str = Field(..., description="Scan type: 'drive' or 'directory'")
    scan_target: str = Field(..., description="Target to scan (e.g., 'C:' or 'c:/dev/Autopack')")
    max_depth: Optional[int] = Field(3, description="Maximum directory depth to scan")
    max_items: Optional[int] = Field(1000, description="Maximum items to scan per directory")
    save_to_db: bool = Field(True, description="Whether to save scan results to database")
    created_by: Optional[str] = Field(None, description="User identifier for scan creator")


class CleanupCandidateResponse(BaseModel):
    """Cleanup candidate information"""

    id: int
    path: str
    size_bytes: int
    age_days: Optional[int]
    category: str
    reason: str
    requires_approval: bool
    approval_status: str
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    execution_status: Optional[str]
    compressed: bool
    compressed_path: Optional[str]
    compression_ratio: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class StorageScanResponse(BaseModel):
    """Storage scan information"""

    id: int
    timestamp: datetime
    scan_type: str
    scan_target: str
    total_items_scanned: int
    total_size_bytes: int
    cleanup_candidates_count: int
    potential_savings_bytes: int
    scan_duration_seconds: Optional[int]
    created_by: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class StorageScanDetailResponse(BaseModel):
    """Detailed storage scan with candidates"""

    scan: StorageScanResponse
    candidates: List[CleanupCandidateResponse]
    stats_by_category: Dict[str, Dict[str, Any]]


class ApprovalRequest(BaseModel):
    """Request to approve cleanup candidates"""

    candidate_ids: List[int] = Field(..., description="List of candidate IDs to approve/reject")
    approved_by: str = Field(..., description="User identifier (email, username, etc.)")
    decision: str = Field(..., description="Decision: 'approve', 'reject', or 'defer'")
    approval_method: str = Field(default='api', description="Method: 'cli_interactive', 'api', 'telegram', 'automated'")
    notes: Optional[str] = Field(None, description="Optional notes about the decision")


class ExecutionRequest(BaseModel):
    """Request to execute approved deletions"""

    dry_run: bool = Field(True, description="If true, preview actions without executing")
    compress_before_delete: bool = Field(False, description="Compress files before deletion")
    category: Optional[str] = Field(None, description="Optional category filter (e.g., 'dev_caches')")


class ExecutionResultResponse(BaseModel):
    """Result of executing cleanup on a single candidate"""

    candidate_id: int
    path: str
    status: str
    error: Optional[str]
    freed_bytes: Optional[int]
    compressed_path: Optional[str]


class BatchExecutionResponse(BaseModel):
    """Result of batch cleanup execution"""

    total_candidates: int
    successful: int
    failed: int
    skipped: int
    total_freed_bytes: int
    success_rate: float
    execution_duration_seconds: int
    results: List[ExecutionResultResponse]

class SteamGameResponse(BaseModel):
    """Steam game information for storage optimization"""

    app_id: Optional[str] = None
    name: str
    install_path: str
    size_bytes: int
    size_gb: float
    last_updated: Optional[str] = None  # ISO format datetime
    age_days: Optional[int] = None


class SteamGamesListResponse(BaseModel):
    """List of Steam games with totals"""

    total_games: int
    total_size_bytes: int
    total_size_gb: float
    games: List[SteamGameResponse]
    steam_available: bool
    steam_path: Optional[str] = None
