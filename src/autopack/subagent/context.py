"""
Context file management for sub-agent handoffs.

The context file (handoff/context.md) is the canonical "single source of current context"
for all sub-agents operating on a run. It contains:
- Intention anchor summary (what the run is trying to accomplish)
- Current gaps (what still needs to be done)
- Selected plan (current execution approach)
- Constraints/guardrails (what sub-agents must NOT do)
- Links to artifacts (files sub-agents should read)

BUILD-197: Claude Code sub-agent glue work
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class SubagentFinding:
    """A finding reported by a sub-agent."""

    topic: str
    summary: str
    confidence: float  # 0.0 to 1.0
    file_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """Convert finding to markdown format."""
        lines = [
            f"### {self.topic}",
            "",
            f"**Confidence**: {self.confidence:.0%}",
            "",
            self.summary,
        ]
        if self.file_references:
            lines.extend(["", "**References**:"])
            for ref in self.file_references:
                lines.append(f"- `{ref}`")
        return "\n".join(lines)


@dataclass
class SubagentProposal:
    """A proposed action from a sub-agent."""

    action: str
    rationale: str
    priority: str  # P0, P1, P2
    estimated_effort: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert proposal to markdown format."""
        lines = [
            f"### {self.action}",
            "",
            f"**Priority**: {self.priority}",
        ]
        if self.estimated_effort:
            lines.append(f"**Effort**: {self.estimated_effort}")
        lines.extend(["", "**Rationale**:", self.rationale])
        if self.dependencies:
            lines.extend(["", "**Dependencies**:"])
            for dep in self.dependencies:
                lines.append(f"- {dep}")
        if self.risks:
            lines.extend(["", "**Risks**:"])
            for risk in self.risks:
                lines.append(f"- {risk}")
        return "\n".join(lines)


@dataclass
class ContextFile:
    """
    Represents the canonical context file for a run.

    Path: .autonomous_runs/<project>/runs/<family>/<run_id>/handoff/context.md
    """

    # Core context
    run_id: str
    project_id: str
    family: str

    # Intention
    objective: str
    success_criteria: list[str] = field(default_factory=list)

    # Current state
    current_phase: Optional[str] = None
    gaps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    # Plan
    selected_plan: Optional[str] = None
    plan_rationale: Optional[str] = None

    # Constraints (guardrails for sub-agents)
    constraints: list[str] = field(default_factory=list)

    # Artifact links
    artifact_paths: dict[str, str] = field(default_factory=dict)

    # Sub-agent contributions
    findings: list[SubagentFinding] = field(default_factory=list)
    proposals: list[SubagentProposal] = field(default_factory=list)
    subagent_history: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: int = 1

    def to_markdown(self) -> str:
        """Serialize context to markdown format."""
        lines = [
            "# Run Context",
            "",
            f"**Run ID**: `{self.run_id}`",
            f"**Project**: `{self.project_id}`",
            f"**Family**: `{self.family}`",
            f"**Updated**: {self.updated_at.isoformat()}",
            f"**Version**: {self.version}",
            "",
            "---",
            "",
            "## Objective",
            "",
            self.objective,
            "",
        ]

        if self.success_criteria:
            lines.extend(["### Success Criteria", ""])
            for criterion in self.success_criteria:
                lines.append(f"- [ ] {criterion}")
            lines.append("")

        lines.extend(["---", "", "## Current State", ""])
        if self.current_phase:
            lines.append(f"**Current Phase**: {self.current_phase}")
            lines.append("")

        if self.gaps:
            lines.extend(["### Gaps", ""])
            for gap in self.gaps:
                lines.append(f"- {gap}")
            lines.append("")

        if self.blockers:
            lines.extend(["### Blockers", ""])
            for blocker in self.blockers:
                lines.append(f"- :warning: {blocker}")
            lines.append("")

        if self.selected_plan:
            lines.extend(["---", "", "## Selected Plan", "", self.selected_plan, ""])
            if self.plan_rationale:
                lines.extend(["### Rationale", "", self.plan_rationale, ""])

        if self.constraints:
            lines.extend(["---", "", "## Constraints (Sub-agent Guardrails)", ""])
            for constraint in self.constraints:
                lines.append(f"- {constraint}")
            lines.append("")

        if self.artifact_paths:
            lines.extend(["---", "", "## Artifacts", ""])
            for name, path in sorted(self.artifact_paths.items()):
                lines.append(f"- **{name}**: `{path}`")
            lines.append("")

        if self.findings:
            lines.extend(["---", "", "## Findings (from sub-agents)", ""])
            for finding in self.findings:
                lines.append(finding.to_markdown())
                lines.append("")

        if self.proposals:
            lines.extend(["---", "", "## Proposals (from sub-agents)", ""])
            for proposal in self.proposals:
                lines.append(proposal.to_markdown())
                lines.append("")

        if self.subagent_history:
            lines.extend(["---", "", "## Sub-agent History", ""])
            for entry in self.subagent_history:
                ts = entry.get("timestamp", "unknown")
                agent = entry.get("agent_type", "unknown")
                action = entry.get("action", "unknown")
                output = entry.get("output_file", "none")
                lines.append(f"- `{ts}` | **{agent}** | {action} | Output: `{output}`")
            lines.append("")

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Serialize context to JSON-compatible dict."""
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "family": self.family,
            "objective": self.objective,
            "success_criteria": self.success_criteria,
            "current_phase": self.current_phase,
            "gaps": self.gaps,
            "blockers": self.blockers,
            "selected_plan": self.selected_plan,
            "plan_rationale": self.plan_rationale,
            "constraints": self.constraints,
            "artifact_paths": self.artifact_paths,
            "findings": [
                {
                    "topic": f.topic,
                    "summary": f.summary,
                    "confidence": f.confidence,
                    "file_references": f.file_references,
                    "metadata": f.metadata,
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in self.findings
            ],
            "proposals": [
                {
                    "action": p.action,
                    "rationale": p.rationale,
                    "priority": p.priority,
                    "estimated_effort": p.estimated_effort,
                    "dependencies": p.dependencies,
                    "risks": p.risks,
                }
                for p in self.proposals
            ],
            "subagent_history": self.subagent_history,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ContextFile":
        """Deserialize context from JSON dict."""
        findings = [
            SubagentFinding(
                topic=f["topic"],
                summary=f["summary"],
                confidence=f["confidence"],
                file_references=f.get("file_references", []),
                metadata=f.get("metadata", {}),
                timestamp=datetime.fromisoformat(f["timestamp"]),
            )
            for f in data.get("findings", [])
        ]
        proposals = [
            SubagentProposal(
                action=p["action"],
                rationale=p["rationale"],
                priority=p["priority"],
                estimated_effort=p.get("estimated_effort"),
                dependencies=p.get("dependencies", []),
                risks=p.get("risks", []),
            )
            for p in data.get("proposals", [])
        ]
        return cls(
            run_id=data["run_id"],
            project_id=data["project_id"],
            family=data["family"],
            objective=data["objective"],
            success_criteria=data.get("success_criteria", []),
            current_phase=data.get("current_phase"),
            gaps=data.get("gaps", []),
            blockers=data.get("blockers", []),
            selected_plan=data.get("selected_plan"),
            plan_rationale=data.get("plan_rationale"),
            constraints=data.get("constraints", []),
            artifact_paths=data.get("artifact_paths", {}),
            findings=findings,
            proposals=proposals,
            subagent_history=data.get("subagent_history", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            version=data.get("version", 1),
        )


class ContextFileManager:
    """
    Manages context files for runs.

    Canonical path: .autonomous_runs/<project>/runs/<family>/<run_id>/handoff/context.md
    JSON backup:    .autonomous_runs/<project>/runs/<family>/<run_id>/handoff/context.json
    """

    DEFAULT_CONSTRAINTS = [
        "DO NOT execute any code changes - research and planning only",
        "DO NOT access or log any secrets, tokens, or credentials",
        "DO NOT perform any external API calls or side effects",
        "DO produce deterministic, traceable outputs (named files only)",
        "DO update context.md with findings and proposals",
    ]

    def __init__(self, runs_dir: Path):
        """
        Initialize context file manager.

        Args:
            runs_dir: Root directory for autonomous runs
                      (typically .autonomous_runs)
        """
        self.runs_dir = Path(runs_dir)

    def _get_context_dir(self, project_id: str, family: str, run_id: str) -> Path:
        """Get the handoff directory for a run."""
        return self.runs_dir / project_id / "runs" / family / run_id / "handoff"

    def _get_context_md_path(self, project_id: str, family: str, run_id: str) -> Path:
        """Get the context.md path for a run."""
        return self._get_context_dir(project_id, family, run_id) / "context.md"

    def _get_context_json_path(self, project_id: str, family: str, run_id: str) -> Path:
        """Get the context.json path for a run."""
        return self._get_context_dir(project_id, family, run_id) / "context.json"

    def create_context(
        self,
        project_id: str,
        family: str,
        run_id: str,
        objective: str,
        success_criteria: Optional[list[str]] = None,
        constraints: Optional[list[str]] = None,
        artifact_paths: Optional[dict[str, str]] = None,
    ) -> ContextFile:
        """
        Create a new context file for a run.

        Args:
            project_id: Project identifier
            family: Run family (e.g., "build", "research")
            run_id: Unique run identifier
            objective: What the run is trying to accomplish
            success_criteria: List of success criteria
            constraints: Additional constraints (merged with defaults)
            artifact_paths: Initial artifact paths

        Returns:
            Created ContextFile
        """
        # Merge default constraints with custom ones
        all_constraints = list(self.DEFAULT_CONSTRAINTS)
        if constraints:
            all_constraints.extend(constraints)

        context = ContextFile(
            run_id=run_id,
            project_id=project_id,
            family=family,
            objective=objective,
            success_criteria=success_criteria or [],
            constraints=all_constraints,
            artifact_paths=artifact_paths or {},
        )

        self.save_context(context)
        return context

    def load_context(self, project_id: str, family: str, run_id: str) -> Optional[ContextFile]:
        """
        Load an existing context file.

        Tries JSON first (canonical data), falls back to parsing markdown.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier

        Returns:
            ContextFile if found, None otherwise
        """
        json_path = self._get_context_json_path(project_id, family, run_id)
        if json_path.exists():
            with open(json_path) as f:
                data = json.load(f)
            return ContextFile.from_json(data)
        return None

    def save_context(self, context: ContextFile) -> Path:
        """
        Save a context file.

        Writes both markdown (human-readable) and JSON (machine-readable).

        Args:
            context: ContextFile to save

        Returns:
            Path to the saved context.md file
        """
        context.updated_at = datetime.now()
        context.version += 1

        context_dir = self._get_context_dir(context.project_id, context.family, context.run_id)
        context_dir.mkdir(parents=True, exist_ok=True)

        # Write markdown (human-readable)
        md_path = context_dir / "context.md"
        with open(md_path, "w") as f:
            f.write(context.to_markdown())

        # Write JSON (machine-readable backup)
        json_path = context_dir / "context.json"
        with open(json_path, "w") as f:
            json.dump(context.to_json(), f, indent=2)

        return md_path

    def add_finding(
        self,
        project_id: str,
        family: str,
        run_id: str,
        finding: SubagentFinding,
    ) -> ContextFile:
        """
        Add a finding to the context file.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            finding: Finding to add

        Returns:
            Updated ContextFile
        """
        context = self.load_context(project_id, family, run_id)
        if not context:
            raise ValueError(f"No context file found for run {run_id}")

        context.findings.append(finding)
        self.save_context(context)
        return context

    def add_proposal(
        self,
        project_id: str,
        family: str,
        run_id: str,
        proposal: SubagentProposal,
    ) -> ContextFile:
        """
        Add a proposal to the context file.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            proposal: Proposal to add

        Returns:
            Updated ContextFile
        """
        context = self.load_context(project_id, family, run_id)
        if not context:
            raise ValueError(f"No context file found for run {run_id}")

        context.proposals.append(proposal)
        self.save_context(context)
        return context

    def record_subagent_action(
        self,
        project_id: str,
        family: str,
        run_id: str,
        agent_type: str,
        action: str,
        output_file: Optional[str] = None,
    ) -> ContextFile:
        """
        Record a sub-agent action in the history.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            agent_type: Type of sub-agent (e.g., "researcher", "planner")
            action: What the sub-agent did
            output_file: Path to output file, if any

        Returns:
            Updated ContextFile
        """
        context = self.load_context(project_id, family, run_id)
        if not context:
            raise ValueError(f"No context file found for run {run_id}")

        context.subagent_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "agent_type": agent_type,
                "action": action,
                "output_file": output_file,
            }
        )
        self.save_context(context)
        return context

    def update_phase(
        self,
        project_id: str,
        family: str,
        run_id: str,
        phase: str,
        gaps: Optional[list[str]] = None,
        blockers: Optional[list[str]] = None,
    ) -> ContextFile:
        """
        Update the current phase and optionally gaps/blockers.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            phase: New current phase
            gaps: Updated gaps list (replaces existing)
            blockers: Updated blockers list (replaces existing)

        Returns:
            Updated ContextFile
        """
        context = self.load_context(project_id, family, run_id)
        if not context:
            raise ValueError(f"No context file found for run {run_id}")

        context.current_phase = phase
        if gaps is not None:
            context.gaps = gaps
        if blockers is not None:
            context.blockers = blockers

        self.save_context(context)
        return context

    def set_plan(
        self,
        project_id: str,
        family: str,
        run_id: str,
        plan: str,
        rationale: Optional[str] = None,
    ) -> ContextFile:
        """
        Set the selected plan for the run.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            plan: Plan content
            rationale: Why this plan was selected

        Returns:
            Updated ContextFile
        """
        context = self.load_context(project_id, family, run_id)
        if not context:
            raise ValueError(f"No context file found for run {run_id}")

        context.selected_plan = plan
        context.plan_rationale = rationale
        self.save_context(context)
        return context

    def add_artifact(
        self,
        project_id: str,
        family: str,
        run_id: str,
        name: str,
        path: str,
    ) -> ContextFile:
        """
        Add an artifact path to the context.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            name: Human-readable artifact name
            path: Path to artifact (relative to run dir)

        Returns:
            Updated ContextFile
        """
        context = self.load_context(project_id, family, run_id)
        if not context:
            raise ValueError(f"No context file found for run {run_id}")

        context.artifact_paths[name] = path
        self.save_context(context)
        return context

    def exists(self, project_id: str, family: str, run_id: str) -> bool:
        """Check if a context file exists for a run."""
        json_path = self._get_context_json_path(project_id, family, run_id)
        return json_path.exists()
