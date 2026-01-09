"""
Task brief generation for sub-agents.

Generates structured "task briefs" that tell sub-agents:
- What to do (objective)
- What to read (context.md + specific artifacts)
- What to produce (filename + schema)
- What NOT to do (constraints)

BUILD-197: Claude Code sub-agent glue work
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from autopack.subagent.context import ContextFileManager
from autopack.subagent.output_contract import OutputContract, OutputType


class TaskConstraint(Enum):
    """Standard constraints for sub-agent tasks."""

    NO_CODE_CHANGES = "no_code_changes"
    NO_SECRETS = "no_secrets"
    NO_SIDE_EFFECTS = "no_side_effects"
    READ_ONLY = "read_only"
    BOUNDED_SCOPE = "bounded_scope"
    DETERMINISTIC_OUTPUT = "deterministic_output"


# Human-readable constraint descriptions
CONSTRAINT_DESCRIPTIONS = {
    TaskConstraint.NO_CODE_CHANGES: (
        "DO NOT modify any code files. This is a research/planning task only."
    ),
    TaskConstraint.NO_SECRETS: (
        "DO NOT access, log, or include any secrets, tokens, API keys, or credentials "
        "in your output. Redact any sensitive values you encounter."
    ),
    TaskConstraint.NO_SIDE_EFFECTS: (
        "DO NOT perform any external API calls, file writes outside the handoff directory, "
        "or any other operations that could have side effects."
    ),
    TaskConstraint.READ_ONLY: (
        "This is a read-only task. You may only read files and produce output artifacts."
    ),
    TaskConstraint.BOUNDED_SCOPE: (
        "Stay within the defined scope. Do not expand into tangential topics or areas "
        "not explicitly requested."
    ),
    TaskConstraint.DETERMINISTIC_OUTPUT: (
        "Produce deterministic, traceable outputs. All outputs must be named files "
        "in the handoff directory with stable, predictable names."
    ),
}


@dataclass
class TaskBrief:
    """
    A structured task brief for a sub-agent.

    Contains everything the sub-agent needs to perform its task.
    """

    # Task identity
    task_id: str
    run_id: str
    project_id: str
    family: str

    # Objective
    objective: str
    success_criteria: list[str] = field(default_factory=list)

    # What to read
    context_file: str = "handoff/context.md"
    required_reads: list[str] = field(default_factory=list)  # Files that MUST be read
    optional_reads: list[str] = field(default_factory=list)  # Files that MAY be read

    # What to produce
    output_contract: Optional[OutputContract] = None
    output_filename: Optional[str] = None
    output_schema: Optional[dict[str, Any]] = None

    # Constraints
    constraints: list[TaskConstraint] = field(default_factory=list)
    additional_constraints: list[str] = field(default_factory=list)

    # Context
    background: Optional[str] = None
    prior_findings: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    timeout_minutes: int = 30

    def to_markdown(self) -> str:
        """Generate markdown task brief for the sub-agent."""
        lines = [
            "# Task Brief",
            "",
            f"**Task ID**: `{self.task_id}`",
            f"**Run ID**: `{self.run_id}`",
            f"**Project**: `{self.project_id}`",
            f"**Family**: `{self.family}`",
            f"**Created**: {self.created_at.isoformat()}",
            f"**Timeout**: {self.timeout_minutes} minutes",
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

        if self.background:
            lines.extend(
                [
                    "---",
                    "",
                    "## Background",
                    "",
                    self.background,
                    "",
                ]
            )

        if self.prior_findings:
            lines.extend(["### Prior Findings", ""])
            for finding in self.prior_findings:
                lines.append(f"- {finding}")
            lines.append("")

        # What to read
        lines.extend(
            [
                "---",
                "",
                "## What to Read",
                "",
                "### Required Reading",
                "",
                f"1. **Context File**: `{self.context_file}` (always read this first)",
            ]
        )
        for i, path in enumerate(self.required_reads, start=2):
            lines.append(f"{i}. `{path}`")
        lines.append("")

        if self.optional_reads:
            lines.extend(["### Optional Reading (if relevant)", ""])
            for path in self.optional_reads:
                lines.append(f"- `{path}`")
            lines.append("")

        # What to produce
        lines.extend(
            [
                "---",
                "",
                "## What to Produce",
                "",
            ]
        )

        if self.output_filename:
            lines.append(f"**Output File**: `handoff/{self.output_filename}`")
            lines.append("")

        if self.output_contract:
            lines.extend(
                [
                    "### Output Requirements",
                    "",
                    f"- **Type**: {self.output_contract.output_type.value}",
                    f"- **Topic**: {self.output_contract.topic}",
                    f"- **Max Length**: {self.output_contract.max_length_chars:,} characters",
                    "",
                    "### Required Sections",
                    "",
                ]
            )
            for section in self.output_contract.required_sections:
                lines.append(f"- `## {section}`")
            lines.append("")

            if self.output_contract.optional_sections:
                lines.extend(["### Optional Sections", ""])
                for section in self.output_contract.optional_sections:
                    lines.append(f"- `## {section}`")
                lines.append("")

            lines.extend(
                [
                    "### Additional Requirements",
                    "",
                ]
            )
            if self.output_contract.require_file_references:
                lines.append("- **Must include**: List of file paths referenced")
            if self.output_contract.require_confidence_scores:
                lines.append("- **Must include**: Confidence scores for findings")
            lines.append("- **Must include**: Key findings summary (for context.md update)")
            lines.append("- **Must include**: Proposed next actions (for context.md update)")
            lines.append("")

        if self.output_schema:
            lines.extend(
                [
                    "### Output Schema (JSON)",
                    "",
                    "```json",
                    json.dumps(self.output_schema, indent=2),
                    "```",
                    "",
                ]
            )

        # Constraints
        lines.extend(
            [
                "---",
                "",
                "## Constraints (MUST FOLLOW)",
                "",
            ]
        )

        for constraint in self.constraints:
            lines.append(f"### {constraint.value.replace('_', ' ').title()}")
            lines.append("")
            lines.append(CONSTRAINT_DESCRIPTIONS[constraint])
            lines.append("")

        if self.additional_constraints:
            lines.extend(["### Additional Constraints", ""])
            for constraint in self.additional_constraints:
                lines.append(f"- {constraint}")
            lines.append("")

        # Footer
        lines.extend(
            [
                "---",
                "",
                "## Reminder",
                "",
                "After completing this task:",
                "",
                "1. Save your output to `handoff/{filename}`".format(
                    filename=(
                        self.output_filename or self.output_contract.get_filename()
                        if self.output_contract
                        else "output.md"
                    )
                ),
                "2. The parent agent will update `handoff/context.md` with your findings",
                "3. DO NOT modify any files outside the handoff directory",
                "",
            ]
        )

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "family": self.family,
            "objective": self.objective,
            "success_criteria": self.success_criteria,
            "context_file": self.context_file,
            "required_reads": self.required_reads,
            "optional_reads": self.optional_reads,
            "output_contract": self.output_contract.get_schema() if self.output_contract else None,
            "output_filename": self.output_filename,
            "output_schema": self.output_schema,
            "constraints": [c.value for c in self.constraints],
            "additional_constraints": self.additional_constraints,
            "background": self.background,
            "prior_findings": self.prior_findings,
            "created_at": self.created_at.isoformat(),
            "timeout_minutes": self.timeout_minutes,
        }


class TaskBriefGenerator:
    """
    Generates task briefs for sub-agents.

    Uses run context and artifacts to produce comprehensive briefs.
    """

    # Default constraints for all sub-agent tasks
    DEFAULT_CONSTRAINTS = [
        TaskConstraint.NO_CODE_CHANGES,
        TaskConstraint.NO_SECRETS,
        TaskConstraint.NO_SIDE_EFFECTS,
        TaskConstraint.DETERMINISTIC_OUTPUT,
    ]

    def __init__(self, runs_dir: Path):
        """
        Initialize task brief generator.

        Args:
            runs_dir: Root directory for autonomous runs
        """
        self.runs_dir = Path(runs_dir)
        self.context_manager = ContextFileManager(runs_dir)

    def _get_run_dir(self, project_id: str, family: str, run_id: str) -> Path:
        """Get the run directory path."""
        return self.runs_dir / project_id / "runs" / family / run_id

    def _discover_artifacts(self, run_dir: Path) -> list[str]:
        """Discover available artifacts in a run directory."""
        artifacts = []
        if run_dir.exists():
            # Check handoff directory
            handoff_dir = run_dir / "handoff"
            if handoff_dir.exists():
                for path in handoff_dir.glob("*.md"):
                    artifacts.append(f"handoff/{path.name}")
                for path in handoff_dir.glob("*.json"):
                    if path.name != "context.json":  # Skip context JSON
                        artifacts.append(f"handoff/{path.name}")

            # Check phases directory
            phases_dir = run_dir / "phases"
            if phases_dir.exists():
                for path in phases_dir.glob("phase_*.md"):
                    artifacts.append(f"phases/{path.name}")

            # Check diagnostics directory
            diag_dir = run_dir / "diagnostics"
            if diag_dir.exists():
                for path in diag_dir.glob("*.md"):
                    artifacts.append(f"diagnostics/{path.name}")
                for path in diag_dir.glob("*.json"):
                    artifacts.append(f"diagnostics/{path.name}")

        return artifacts

    def generate_research_brief(
        self,
        project_id: str,
        family: str,
        run_id: str,
        topic: str,
        objective: str,
        required_reads: Optional[list[str]] = None,
        success_criteria: Optional[list[str]] = None,
        additional_constraints: Optional[list[str]] = None,
    ) -> TaskBrief:
        """
        Generate a research task brief.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            topic: Research topic
            objective: What the research should accomplish
            required_reads: Additional files to read
            success_criteria: Success criteria for the research
            additional_constraints: Extra constraints

        Returns:
            TaskBrief for research sub-agent
        """
        from autopack.subagent.output_contract import OutputType, create_contract

        run_dir = self._get_run_dir(project_id, family, run_id)
        context = self.context_manager.load_context(project_id, family, run_id)

        # Build output contract
        contract = create_contract(
            output_type=OutputType.RESEARCH,
            topic=topic,
            require_refs=True,
            require_confidence=True,
        )

        # Build task brief
        brief = TaskBrief(
            task_id=f"research-{topic}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            run_id=run_id,
            project_id=project_id,
            family=family,
            objective=objective,
            success_criteria=success_criteria or [],
            required_reads=required_reads or [],
            optional_reads=self._discover_artifacts(run_dir),
            output_contract=contract,
            output_filename=contract.get_filename(),
            constraints=list(self.DEFAULT_CONSTRAINTS),
            additional_constraints=additional_constraints or [],
            background=context.objective if context else None,
            prior_findings=[f.summary for f in context.findings] if context else [],
        )

        return brief

    def generate_planning_brief(
        self,
        project_id: str,
        family: str,
        run_id: str,
        topic: str,
        objective: str,
        required_reads: Optional[list[str]] = None,
        success_criteria: Optional[list[str]] = None,
        additional_constraints: Optional[list[str]] = None,
    ) -> TaskBrief:
        """
        Generate a planning task brief.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            topic: Planning topic
            objective: What the plan should accomplish
            required_reads: Additional files to read
            success_criteria: Success criteria for the plan
            additional_constraints: Extra constraints

        Returns:
            TaskBrief for planning sub-agent
        """
        from autopack.subagent.output_contract import OutputType, create_contract

        run_dir = self._get_run_dir(project_id, family, run_id)
        context = self.context_manager.load_context(project_id, family, run_id)

        contract = create_contract(
            output_type=OutputType.PLAN,
            topic=topic,
            require_refs=True,
        )

        brief = TaskBrief(
            task_id=f"plan-{topic}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            run_id=run_id,
            project_id=project_id,
            family=family,
            objective=objective,
            success_criteria=success_criteria
            or [
                "Plan has clear, actionable steps",
                "Each step has acceptance criteria",
                "Dependencies are identified",
                "Risks are documented",
            ],
            required_reads=required_reads or [],
            optional_reads=self._discover_artifacts(run_dir),
            output_contract=contract,
            output_filename=contract.get_filename(),
            constraints=list(self.DEFAULT_CONSTRAINTS),
            additional_constraints=additional_constraints or [],
            background=context.objective if context else None,
            prior_findings=[f.summary for f in context.findings] if context else [],
        )

        return brief

    def generate_analysis_brief(
        self,
        project_id: str,
        family: str,
        run_id: str,
        topic: str,
        objective: str,
        required_reads: Optional[list[str]] = None,
        success_criteria: Optional[list[str]] = None,
        additional_constraints: Optional[list[str]] = None,
    ) -> TaskBrief:
        """
        Generate an analysis task brief.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            topic: Analysis topic
            objective: What the analysis should accomplish
            required_reads: Additional files to read
            success_criteria: Success criteria
            additional_constraints: Extra constraints

        Returns:
            TaskBrief for analysis sub-agent
        """
        from autopack.subagent.output_contract import OutputType, create_contract

        run_dir = self._get_run_dir(project_id, family, run_id)
        context = self.context_manager.load_context(project_id, family, run_id)

        contract = create_contract(
            output_type=OutputType.ANALYSIS,
            topic=topic,
            require_refs=True,
            require_confidence=True,
        )

        brief = TaskBrief(
            task_id=f"analysis-{topic}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            run_id=run_id,
            project_id=project_id,
            family=family,
            objective=objective,
            success_criteria=success_criteria
            or [
                "Analysis methodology is documented",
                "Results include confidence scores",
                "Conclusions are supported by evidence",
            ],
            required_reads=required_reads or [],
            optional_reads=self._discover_artifacts(run_dir),
            output_contract=contract,
            output_filename=contract.get_filename(),
            constraints=list(self.DEFAULT_CONSTRAINTS),
            additional_constraints=additional_constraints or [],
            background=context.objective if context else None,
            prior_findings=[f.summary for f in context.findings] if context else [],
        )

        return brief

    def generate_from_context(
        self,
        project_id: str,
        family: str,
        run_id: str,
        output_type: OutputType,
        topic: str,
        phase_id: Optional[str] = None,
    ) -> TaskBrief:
        """
        Generate a task brief from existing run context.

        This is the main "command to generate sub-agent task briefs from existing artifacts"
        mentioned in the gap analysis.

        Args:
            project_id: Project identifier
            family: Run family
            run_id: Run identifier
            output_type: Type of output expected (research, plan, analysis)
            topic: Topic for the task
            phase_id: Optional phase ID for phase-specific briefs

        Returns:
            TaskBrief populated from context
        """
        context = self.context_manager.load_context(project_id, family, run_id)
        if not context:
            raise ValueError(f"No context file found for run {run_id}")

        run_dir = self._get_run_dir(project_id, family, run_id)

        # Build required reads from context artifact paths
        required_reads = list(context.artifact_paths.values())

        # Add phase-specific artifacts if phase_id provided
        if phase_id:
            phase_file = f"phases/{phase_id}.md"
            if (run_dir / phase_file).exists():
                required_reads.insert(0, phase_file)

        # Determine objective from context
        objective = f"Produce {output_type.value} for: {context.objective}"

        # Map output type to generator
        if output_type == OutputType.RESEARCH:
            return self.generate_research_brief(
                project_id=project_id,
                family=family,
                run_id=run_id,
                topic=topic,
                objective=objective,
                required_reads=required_reads,
                success_criteria=context.success_criteria,
            )
        elif output_type == OutputType.PLAN:
            return self.generate_planning_brief(
                project_id=project_id,
                family=family,
                run_id=run_id,
                topic=topic,
                objective=objective,
                required_reads=required_reads,
                success_criteria=context.success_criteria,
            )
        elif output_type == OutputType.ANALYSIS:
            return self.generate_analysis_brief(
                project_id=project_id,
                family=family,
                run_id=run_id,
                topic=topic,
                objective=objective,
                required_reads=required_reads,
                success_criteria=context.success_criteria,
            )
        else:
            # Generic brief for other types
            from autopack.subagent.output_contract import create_contract

            contract = create_contract(output_type=output_type, topic=topic)

            return TaskBrief(
                task_id=f"{output_type.value}-{topic}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                run_id=run_id,
                project_id=project_id,
                family=family,
                objective=objective,
                success_criteria=context.success_criteria,
                required_reads=required_reads,
                optional_reads=self._discover_artifacts(run_dir),
                output_contract=contract,
                output_filename=contract.get_filename(),
                constraints=list(self.DEFAULT_CONSTRAINTS),
                background=context.objective,
                prior_findings=[f.summary for f in context.findings],
            )

    def save_brief(
        self,
        brief: TaskBrief,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Save a task brief to disk.

        Args:
            brief: TaskBrief to save
            output_dir: Directory to save to (defaults to run's handoff dir)

        Returns:
            Path to saved brief
        """
        if output_dir is None:
            output_dir = self._get_run_dir(brief.project_id, brief.family, brief.run_id) / "handoff"

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save markdown version
        md_path = output_dir / f"task_brief_{brief.task_id}.md"
        with open(md_path, "w") as f:
            f.write(brief.to_markdown())

        # Save JSON version
        json_path = output_dir / f"task_brief_{brief.task_id}.json"
        with open(json_path, "w") as f:
            json.dump(brief.to_json(), f, indent=2)

        return md_path
