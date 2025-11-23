"""Issue tracking system for Autopack (Chunk B implementation)

Per §5 of v7 playbook:
- Phase-level issue files
- Run-level issue index for de-duplication
- Project-level issue backlog with aging
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import settings
from .issue_schemas import (
    Issue,
    PhaseIssueFile,
    ProjectBacklogEntry,
    ProjectIssueBacklog,
    RunIssueIndex,
    RunIssueIndexEntry,
)


class IssueTracker:
    """Manages issue tracking at phase, run, and project levels"""

    def __init__(self, run_id: str, project_id: str = "Autopack"):
        self.run_id = run_id
        self.project_id = project_id
        self.base_dir = Path(settings.autonomous_runs_dir) / run_id / "issues"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_phase_issue_path(self, phase_index: int, phase_id: str) -> Path:
        """Get path to phase issue file"""
        safe_id = phase_id.replace(" ", "_").replace("/", "_")
        return self.base_dir / f"phase_{phase_index:02d}_{safe_id}_issues.json"

    def get_run_issue_index_path(self) -> Path:
        """Get path to run issue index"""
        return self.base_dir / "run_issue_index.json"

    def get_project_backlog_path(self) -> Path:
        """Get path to project issue backlog (at repo root level)"""
        return Path(settings.autonomous_runs_dir).parent / "project_issue_backlog.json"

    # Phase-level operations

    def load_phase_issues(self, phase_index: int, phase_id: str) -> PhaseIssueFile:
        """Load phase issue file or create new one"""
        path = self.get_phase_issue_path(phase_index, phase_id)
        if path.exists():
            return PhaseIssueFile.model_validate_json(path.read_text())
        return PhaseIssueFile(phase_id=phase_id, tier_id="unknown")

    def save_phase_issues(self, phase_index: int, issue_file: PhaseIssueFile) -> None:
        """Save phase issue file"""
        path = self.get_phase_issue_path(phase_index, issue_file.phase_id)
        path.write_text(issue_file.model_dump_json(indent=2))

    def add_phase_issue(
        self,
        phase_index: int,
        phase_id: str,
        tier_id: str,
        issue: Issue,
    ) -> PhaseIssueFile:
        """Add issue to phase file"""
        issue_file = self.load_phase_issues(phase_index, phase_id)
        issue_file.tier_id = tier_id

        # Check if issue already exists
        existing = next((i for i in issue_file.issues if i.issue_key == issue.issue_key), None)
        if existing:
            existing.occurrence_count += 1
            existing.last_seen_run = issue.last_seen_run
        else:
            issue_file.issues.append(issue)

        # Update counts (based on distinct issue_keys, not occurrences per §5.2)
        issue_file.minor_issue_count = len(
            [i for i in issue_file.issues if i.effective_severity == "minor"]
        )
        issue_file.major_issue_count = len(
            [i for i in issue_file.issues if i.effective_severity == "major"]
        )

        # Update issue state
        if issue_file.major_issue_count > 0:
            issue_file.issue_state = "has_major_issues"
        elif issue_file.minor_issue_count > 0:
            issue_file.issue_state = "has_minor_issues"
        else:
            issue_file.issue_state = "no_issues"

        self.save_phase_issues(phase_index, issue_file)
        return issue_file

    # Run-level operations

    def load_run_issue_index(self) -> RunIssueIndex:
        """Load run issue index or create new one"""
        path = self.get_run_issue_index_path()
        if path.exists():
            return RunIssueIndex.model_validate_json(path.read_text())
        return RunIssueIndex(run_id=self.run_id)

    def save_run_issue_index(self, index: RunIssueIndex) -> None:
        """Save run issue index"""
        path = self.get_run_issue_index_path()
        path.write_text(index.model_dump_json(indent=2))

    def update_run_issue_index(
        self, issue: Issue, phase_index: int, phase_id: str, tier_id: str
    ) -> RunIssueIndex:
        """Update run issue index with issue (de-duplication per §5.2)"""
        index = self.load_run_issue_index()

        if issue.issue_key in index.issues_by_key:
            # Update existing entry
            entry = index.issues_by_key[issue.issue_key]
            entry.last_phase_index = phase_index
            entry.occurrence_count += 1
            if tier_id not in entry.seen_in_tiers:
                entry.seen_in_tiers.append(tier_id)
            if phase_id not in entry.seen_in_phases:
                entry.seen_in_phases.append(phase_id)
        else:
            # Create new entry
            index.issues_by_key[issue.issue_key] = RunIssueIndexEntry(
                category=issue.category,
                severity=issue.severity,
                effective_severity=issue.effective_severity,
                first_phase_index=phase_index,
                last_phase_index=phase_index,
                occurrence_count=1,
                seen_in_tiers=[tier_id],
                seen_in_phases=[phase_id],
            )

        self.save_run_issue_index(index)
        return index

    # Project-level operations

    def load_project_backlog(self) -> ProjectIssueBacklog:
        """Load project issue backlog or create new one"""
        path = self.get_project_backlog_path()
        if path.exists():
            return ProjectIssueBacklog.model_validate_json(path.read_text())
        return ProjectIssueBacklog(project_id=self.project_id)

    def save_project_backlog(self, backlog: ProjectIssueBacklog) -> None:
        """Save project issue backlog"""
        path = self.get_project_backlog_path()
        path.write_text(backlog.model_dump_json(indent=2))

    def update_project_backlog(
        self, issue: Issue, tier_id: str, aging_config: Optional[Dict] = None
    ) -> ProjectIssueBacklog:
        """Update project backlog with issue and apply aging (§5.3)"""
        backlog = self.load_project_backlog()

        # Default aging thresholds per §5.3
        if aging_config is None:
            aging_config = {
                "minor_issue_aging_runs_threshold": 3,
                "minor_issue_aging_tiers_threshold": 2,
            }

        if issue.issue_key in backlog.issues_by_key:
            # Update existing entry
            entry = backlog.issues_by_key[issue.issue_key]
            entry.age_in_runs += 1
            entry.last_seen_run_id = self.run_id
            entry.last_seen_at = datetime.utcnow()

            # Check if this is a new tier
            # (simplified: would need to track tiers per run in full implementation)
            entry.age_in_tiers += 1

            # Apply aging rules per §5.3
            if entry.base_severity == "minor":
                if (
                    entry.age_in_runs >= aging_config["minor_issue_aging_runs_threshold"]
                    or entry.age_in_tiers >= aging_config["minor_issue_aging_tiers_threshold"]
                ):
                    entry.status = "needs_cleanup"
        else:
            # Create new entry
            backlog.issues_by_key[issue.issue_key] = ProjectBacklogEntry(
                category=issue.category,
                base_severity=issue.severity,
                age_in_runs=1,
                age_in_tiers=1,
                first_seen_run_id=self.run_id,
                last_seen_run_id=self.run_id,
                last_seen_at=datetime.utcnow(),
                seen_in_tiers=[],
            )

        self.save_project_backlog(backlog)
        return backlog

    def record_issue(
        self,
        phase_index: int,
        phase_id: str,
        tier_id: str,
        issue_key: str,
        severity: str,
        source: str,
        category: str,
        task_category: Optional[str] = None,
        complexity: Optional[str] = None,
        evidence_refs: Optional[List[str]] = None,
    ) -> tuple[PhaseIssueFile, RunIssueIndex, ProjectIssueBacklog]:
        """
        Record an issue at all three levels: phase, run, and project.

        Returns tuple of (phase_file, run_index, project_backlog)
        """
        issue = Issue(
            issue_key=issue_key,
            severity=severity,
            effective_severity=severity,  # May be upgraded by aging later
            source=source,
            category=category,
            task_category=task_category,
            complexity=complexity,
            first_seen_run=self.run_id,
            last_seen_run=self.run_id,
            evidence_refs=evidence_refs or [],
        )

        # Record at phase level
        phase_file = self.add_phase_issue(phase_index, phase_id, tier_id, issue)

        # Update run index
        run_index = self.update_run_issue_index(issue, phase_index, phase_id, tier_id)

        # Update project backlog
        project_backlog = self.update_project_backlog(issue, tier_id)

        return phase_file, run_index, project_backlog
