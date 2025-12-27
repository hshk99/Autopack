"""File layout utilities for .autonomous_runs/{run_id}/ structure (Chunk A)

Per §3 and §5 of v7 playbook, Supervisor maintains persistent artefacts:
- run_summary.md
- tiers/tier_{idx}_{name}.md
- phases/phase_{idx}_{phase_id}.md
"""

import os
from pathlib import Path
from typing import Optional, List, Sequence

from .config import settings


def collapse_consecutive_duplicates(parts: List[str]) -> List[str]:
    """Remove consecutive duplicate folder names from path parts.

    This prevents path nesting bugs like:
        test-run/test-run/file.md
    from becoming:
        test-run/file.md

    Args:
        parts: List of path components

    Returns:
        List with consecutive duplicates removed
    """
    if not parts:
        return parts

    collapsed: List[str] = [parts[0]]
    for i in range(1, len(parts)):
        if parts[i] != parts[i-1]:
            collapsed.append(parts[i])

    return collapsed


class RunFileLayout:
    """Manages file layout for a single autonomous run"""

    def __init__(self, run_id: str, project_id: Optional[str] = None, base_dir: Optional[Path] = None):
        self.run_id = run_id
        self.project_id = project_id or self._detect_project(run_id)
        self.family = self._extract_family(run_id)

        if base_dir is not None:
            # Build path parts and remove consecutive duplicates to prevent
            # test-run-001/test-run-001/ nesting bugs
            parts = [str(base_dir), self.project_id, "runs", self.family, run_id]
            collapsed = collapse_consecutive_duplicates(parts)
            self.base_dir = Path(collapsed[0])
            for part in collapsed[1:]:
                self.base_dir = self.base_dir / part
        else:
            # New structure: .autonomous_runs/{project}/runs/{family}/{run_id}/
            base = Path(settings.autonomous_runs_dir)
            parts = [str(base), self.project_id, "runs", self.family, run_id]
            collapsed = collapse_consecutive_duplicates(parts)
            self.base_dir = Path(collapsed[0])
            for part in collapsed[1:]:
                self.base_dir = self.base_dir / part

    def ensure_directories(self) -> None:
        """Create all required directories for the run"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "tiers").mkdir(exist_ok=True)
        (self.base_dir / "phases").mkdir(exist_ok=True)
        (self.base_dir / "issues").mkdir(exist_ok=True)

    def get_run_summary_path(self) -> Path:
        """Get path to run_summary.md"""
        return self.base_dir / "run_summary.md"

    def get_tier_summary_path(self, tier_index: int, tier_name: str) -> Path:
        """Get path to tier summary file"""
        safe_name = tier_name.replace(" ", "_").replace("/", "_")
        return self.base_dir / "tiers" / f"tier_{tier_index:02d}_{safe_name}.md"

    def get_phase_summary_path(self, phase_index: int, phase_id: str) -> Path:
        """Get path to phase summary file"""
        safe_id = phase_id.replace(" ", "_").replace("/", "_")
        return self.base_dir / "phases" / f"phase_{phase_index:02d}_{safe_id}.md"

    def get_diagnostics_dir(self) -> Path:
        """Directory for diagnostic artifacts."""
        return self.base_dir / "diagnostics"

    def ensure_diagnostics_dirs(self) -> None:
        """Create diagnostics directories (commands, sandbox)."""
        diag = self.get_diagnostics_dir()
        (diag / "commands").mkdir(parents=True, exist_ok=True)
        (diag / "sandbox").mkdir(parents=True, exist_ok=True)

    def write_run_summary(
        self,
        run_id: str,
        state: str,
        safety_profile: str,
        run_scope: str,
        created_at: str,
        tier_count: int = 0,
        phase_count: int = 0,
        tokens_used: int = 0,
        phases_complete: int = 0,
        phases_failed: int = 0,
        failure_reason: str = None,
        completed_at: str = None,
    ) -> None:
        """Write or update run_summary.md"""
        # Build status section
        status_lines = [
            f"- **State:** {state}",
            f"- **Safety Profile:** {safety_profile}",
            f"- **Run Scope:** {run_scope}",
            f"- **Created:** {created_at}",
        ]
        if completed_at:
            status_lines.append(f"- **Completed:** {completed_at}")

        # Build progress section
        progress_lines = [
            f"- **Tiers:** {tier_count}",
            f"- **Phases:** {phase_count}",
            f"- **Phases Complete:** {phases_complete}",
            f"- **Phases Failed:** {phases_failed}",
        ]

        # Build budgets section
        budgets_section = f"- **Tokens Used:** {tokens_used:,}" if tokens_used > 0 else "(To be populated as run progresses)"

        # Build issues section
        issues_section = ""
        if failure_reason:
            issues_section = f"**Failure Reason:** {failure_reason}"
        elif state.startswith("DONE_FAILED"):
            issues_section = "(Run failed - see phase logs for details)"
        elif state == "DONE_SUCCESS":
            issues_section = "No issues - run completed successfully."
        else:
            issues_section = "(To be populated as run progresses)"

        content = f"""# Run Summary: {run_id}

## Status
{chr(10).join(status_lines)}

## Progress
{chr(10).join(progress_lines)}

## Budgets
{budgets_section}

## Issues
{issues_section}
"""
        path = self.get_run_summary_path()
        path.write_text(content, encoding="utf-8")

    def write_tier_summary(
        self,
        tier_index: int,
        tier_id: str,
        tier_name: str,
        state: str,
        phase_count: int = 0,
    ) -> None:
        """Write or update tier summary file"""
        content = f"""# Tier Summary: {tier_id} - {tier_name}

## Status
- **State:** {state}
- **Tier ID:** {tier_id}
- **Index:** {tier_index}

## Phases
- **Total:** {phase_count}

## Issues
(To be populated as phases execute)

## Cleanliness
(To be determined after all phases complete)
"""
        path = self.get_tier_summary_path(tier_index, tier_name)
        path.write_text(content, encoding="utf-8")

    def write_phase_summary(
        self,
        phase_index: int,
        phase_id: str,
        phase_name: str,
        state: str,
        task_category: Optional[str] = None,
        complexity: Optional[str] = None,
        execution_lines: Optional[Sequence[str]] = None,
        issues_lines: Optional[Sequence[str]] = None,
    ) -> None:
        """Write or update phase summary file"""
        execution_section = (
            "\n".join(f"- {line}" for line in execution_lines)
            if execution_lines
            else "(To be populated as phase executes)"
        )
        issues_section = (
            "\n".join(f"- {line}" for line in issues_lines)
            if issues_lines
            else "(To be populated if issues arise)"
        )
        content = f"""# Phase Summary: {phase_id} - {phase_name}

## Status
- **State:** {state}
- **Phase ID:** {phase_id}
- **Index:** {phase_index}

## Classification
- **Task Category:** {task_category or 'N/A'}
- **Complexity:** {complexity or 'N/A'}

## Execution
{execution_section}

## Issues
{issues_section}
"""
        path = self.get_phase_summary_path(phase_index, phase_id)
        path.write_text(content, encoding="utf-8")

    def _detect_project(self, run_id: str) -> str:
        """Detect project from run_id prefix

        Args:
            run_id: Run identifier (e.g., 'fileorg-country-uk-20251205-132826')

        Returns:
            Project identifier (e.g., 'file-organizer-app-v1', 'autopack')
        """
        if run_id.startswith("fileorg-"):
            return "file-organizer-app-v1"
        elif run_id.startswith("backlog-"):
            return "file-organizer-app-v1"
        elif run_id.startswith("maintenance-"):
            return "file-organizer-app-v1"
        else:
            return "autopack"

    def _extract_family(self, run_id: str) -> str:
        """Extract family name from run_id (prefix before timestamp)

        Family groups related runs together (e.g., all 'fileorg-country-uk' runs).

        Args:
            run_id: Run identifier (e.g., 'fileorg-country-uk-20251205-132826')

        Returns:
            Family name (e.g., 'fileorg-country-uk') or full run_id if no pattern match
        """
        import re
        # Match pattern: prefix-YYYYMMDD-HHMMSS or prefix-10+digit-timestamp
        match = re.match(r"(.+?)-(?:\d{8}-\d{6}|\d{10,})", run_id)
        if match:
            return match.group(1)
        # Fallback to full run_id as family
        return run_id
