"""Schemas for Builder and Auditor integration (Chunk D)

Per §2.2 and §2.3 of v7 playbook:
- Builder results (diffs, logs, issue suggestions)
- Auditor requests and results
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class BuilderProbeResult(BaseModel):
    """Result from a Builder probe (local test run)"""

    probe_type: str = Field(..., description="pytest, lint, script, etc.")
    exit_code: int
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    duration_seconds: float = Field(default=0.0)


class BuilderSuggestedIssue(BaseModel):
    """Issue suggested by Builder"""

    issue_key: str
    severity: str
    source: str = Field(default="cursor_self_doubt")
    category: str
    evidence_refs: List[str] = Field(default_factory=list)
    description: str = Field(default="")


class BuilderResult(BaseModel):
    """Builder result submitted after phase execution"""

    phase_id: str
    run_id: str
    run_type: str = Field(default="project_build", description="Run type context (project_build, autopack_maintenance, etc.)")
    allowed_paths: List[str] = Field(default_factory=list, description="Explicitly allowed path prefixes")

    # Patch/diff information
    patch_content: Optional[str] = Field(None, description="Git diff or patch content")
    files_changed: List[str] = Field(default_factory=list)
    lines_added: int = Field(default=0)
    lines_removed: int = Field(default=0)

    # Execution details
    builder_attempts: int = Field(default=1)
    tokens_used: int = Field(default=0)
    duration_minutes: float = Field(default=0.0)

    # Probe results
    probe_results: List[BuilderProbeResult] = Field(default_factory=list)

    # Issue suggestions
    suggested_issues: List[BuilderSuggestedIssue] = Field(default_factory=list)

    # Status
    status: str = Field(..., description="success, failed, needs_review")
    notes: str = Field(default="")


class AuditorRequest(BaseModel):
    """Request for Auditor review"""

    phase_id: str
    run_id: str
    tier_id: str

    # Context for review
    builder_result: Optional[BuilderResult] = None
    failure_context: str = Field(default="")
    review_focus: str = Field(default="general", description="general, security, schema, etc.")

    # Auditor profile to use
    auditor_profile: Optional[str] = Field(None)


class AuditorSuggestedPatch(BaseModel):
    """Minimal patch suggested by Auditor"""

    description: str
    patch_content: str
    files_affected: List[str] = Field(default_factory=list)


class AuditorResult(BaseModel):
    """Auditor result after review"""

    phase_id: str
    run_id: str

    # Review findings
    review_notes: str
    issues_found: List[BuilderSuggestedIssue] = Field(default_factory=list)

    # Suggested patches (if any)
    suggested_patches: List[AuditorSuggestedPatch] = Field(default_factory=list)

    # Execution details
    auditor_attempts: int = Field(default=1)
    tokens_used: int = Field(default=0)

    # Recommendation
    recommendation: str = Field(..., description="approve, revise, escalate")
    confidence: str = Field(default="medium", description="low, medium, high")
