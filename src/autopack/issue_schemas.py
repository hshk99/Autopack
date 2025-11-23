"""Pydantic schemas for issue tracking (Chunk B implementation)

Per §5 of v7 playbook:
- Phase-level issue files
- Run-level issue index (de-duplication)
- Project-level issue backlog with aging
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Issue(BaseModel):
    """Individual issue entry"""

    issue_key: str = Field(..., description="Stable identifier for the issue")
    severity: str = Field(..., description="minor or major")
    effective_severity: str = Field(..., description="May be upgraded by aging or rules")
    source: str = Field(..., description="test, probe, ci, static_check, cursor_self_doubt")
    category: str = Field(..., description="High-level failure type")
    task_category: Optional[str] = Field(None, description="Task category of the phase")
    complexity: Optional[str] = Field(None, description="Complexity of the phase")
    expected_fail: bool = Field(default=False, description="Whether this failure was expected")
    occurrence_count: int = Field(default=1, description="Times seen in this context")
    first_seen_run: str = Field(..., description="First run where this issue appeared")
    last_seen_run: str = Field(..., description="Most recent run with this issue")
    evidence_refs: List[str] = Field(default_factory=list, description="References to evidence")


class PhaseIssueFile(BaseModel):
    """Phase-level issue file schema (§5.1 of v7 playbook)"""

    phase_id: str
    tier_id: str
    issues: List[Issue] = Field(default_factory=list)
    minor_issue_count: int = Field(default=0, description="Count of distinct minor issues")
    major_issue_count: int = Field(default=0, description="Count of distinct major issues")
    issue_state: str = Field(
        default="no_issues", description="no_issues, has_minor_issues, has_major_issues"
    )


class RunIssueIndexEntry(BaseModel):
    """Entry in run-level issue index"""

    category: str
    severity: str
    effective_severity: str
    first_phase_index: int
    last_phase_index: int
    occurrence_count: int
    seen_in_tiers: List[str] = Field(default_factory=list)
    seen_in_phases: List[str] = Field(default_factory=list)


class RunIssueIndex(BaseModel):
    """Run-level issue index (§5.2 of v7 playbook)"""

    run_id: str
    issues_by_key: dict[str, RunIssueIndexEntry] = Field(default_factory=dict)


class ProjectBacklogEntry(BaseModel):
    """Entry in project-level issue backlog"""

    category: str
    base_severity: str
    age_in_runs: int = Field(default=0, description="Number of runs this issue has persisted")
    age_in_tiers: int = Field(default=0, description="Number of tiers this issue has affected")
    last_seen_run_id: str
    last_seen_at: datetime
    status: str = Field(default="open", description="open, needs_cleanup, resolved")


class ProjectIssueBacklog(BaseModel):
    """Project-level issue backlog (§5.3 of v7 playbook)"""

    project_id: str
    issues_by_key: dict[str, ProjectBacklogEntry] = Field(default_factory=dict)
