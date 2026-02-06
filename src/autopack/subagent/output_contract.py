"""
Standard sub-agent output contract.

Every sub-agent must produce:
1. Exactly one primary output file (e.g., handoff/research_<topic>.md)
2. Update to handoff/context.md with:
   - What it did
   - Key findings
   - Proposed next actions
   - File paths created

BUILD-197: Claude Code sub-agent glue work
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class OutputType(Enum):
    """Types of sub-agent outputs."""

    RESEARCH = "research"  # Research findings (e.g., research_codebase.md)
    PLAN = "plan"  # Implementation plan (e.g., plan_feature_x.md)
    ANALYSIS = "analysis"  # Code/data analysis (e.g., analysis_performance.md)
    REVIEW = "review"  # Code review findings (e.g., review_pr_123.md)
    SUMMARY = "summary"  # Summary/digest (e.g., summary_changes.md)
    REPORT = "report"  # Structured report (e.g., report_compliance.md)


@dataclass
class OutputContract:
    """
    Defines what a sub-agent must produce.

    This is the "agreement" between the parent agent and sub-agent.
    """

    output_type: OutputType
    topic: str  # e.g., "codebase", "performance", "compliance"
    required_sections: list[str] = field(default_factory=list)
    optional_sections: list[str] = field(default_factory=list)
    max_length_chars: int = 50000  # Reasonable limit for context
    require_file_references: bool = True
    require_confidence_scores: bool = False

    def get_filename(self) -> str:
        """Generate canonical filename for this output."""
        # Sanitize topic for filename
        safe_topic = re.sub(r"[^a-z0-9_]", "_", self.topic.lower())
        return f"{self.output_type.value}_{safe_topic}.md"

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema representation of the contract."""
        return {
            "output_type": self.output_type.value,
            "topic": self.topic,
            "filename": self.get_filename(),
            "required_sections": self.required_sections,
            "optional_sections": self.optional_sections,
            "max_length_chars": self.max_length_chars,
            "require_file_references": self.require_file_references,
            "require_confidence_scores": self.require_confidence_scores,
        }


# Pre-defined contracts for common sub-agent tasks
RESEARCH_CONTRACT = OutputContract(
    output_type=OutputType.RESEARCH,
    topic="generic",
    required_sections=[
        "Objective",
        "Methodology",
        "Findings",
        "Recommendations",
    ],
    optional_sections=[
        "Limitations",
        "Further Research",
    ],
    require_file_references=True,
)

PLAN_CONTRACT = OutputContract(
    output_type=OutputType.PLAN,
    topic="generic",
    required_sections=[
        "Objective",
        "Approach",
        "Implementation Steps",
        "Acceptance Criteria",
    ],
    optional_sections=[
        "Risks",
        "Dependencies",
        "Alternatives Considered",
    ],
    require_file_references=True,
)

ANALYSIS_CONTRACT = OutputContract(
    output_type=OutputType.ANALYSIS,
    topic="generic",
    required_sections=[
        "Scope",
        "Methodology",
        "Results",
        "Conclusions",
    ],
    optional_sections=[
        "Data Sources",
        "Limitations",
    ],
    require_file_references=True,
    require_confidence_scores=True,
)


@dataclass
class SubagentOutput:
    """
    Represents the actual output from a sub-agent.

    This is what gets validated against the contract.
    """

    # Identity
    output_type: OutputType
    topic: str
    agent_type: str  # e.g., "researcher", "planner"
    run_id: str

    # Content
    title: str
    content: str  # Full markdown content
    sections: dict[str, str] = field(default_factory=dict)

    # Metadata
    file_references: list[str] = field(default_factory=list)
    findings_summary: list[str] = field(default_factory=list)
    proposed_actions: list[str] = field(default_factory=list)
    confidence_scores: dict[str, float] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    content_hash: Optional[str] = None  # SHA-256 of content

    def __post_init__(self):
        """Compute content hash if not provided."""
        if self.content_hash is None:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()

    def get_filename(self) -> str:
        """Generate canonical filename."""
        safe_topic = re.sub(r"[^a-z0-9_]", "_", self.topic.lower())
        return f"{self.output_type.value}_{safe_topic}.md"

    def to_markdown(self) -> str:
        """Generate full markdown output."""
        lines = [
            f"# {self.title}",
            "",
            f"**Type**: {self.output_type.value}",
            f"**Topic**: {self.topic}",
            f"**Agent**: {self.agent_type}",
            f"**Run**: {self.run_id}",
            f"**Created**: {self.created_at.isoformat()}",
            f"**Content Hash**: `{self.content_hash[:12]}...`",
            "",
            "---",
            "",
        ]

        # Main content
        lines.append(self.content)
        lines.append("")

        # Summary section (for context.md update)
        lines.extend(
            [
                "---",
                "",
                "## Context Update Summary",
                "",
                "### What This Agent Did",
                "",
            ]
        )
        lines.append(f"- Analyzed: {self.topic}")
        lines.append(f"- Output type: {self.output_type.value}")
        lines.append(f"- Files referenced: {len(self.file_references)}")
        lines.append("")

        if self.findings_summary:
            lines.extend(["### Key Findings", ""])
            for finding in self.findings_summary:
                lines.append(f"- {finding}")
            lines.append("")

        if self.proposed_actions:
            lines.extend(["### Proposed Next Actions", ""])
            for action in self.proposed_actions:
                lines.append(f"- {action}")
            lines.append("")

        if self.file_references:
            lines.extend(["### File References", ""])
            for ref in self.file_references:
                lines.append(f"- `{ref}`")
            lines.append("")

        if self.confidence_scores:
            lines.extend(["### Confidence Scores", ""])
            for key, score in self.confidence_scores.items():
                lines.append(f"- {key}: {score:.0%}")
            lines.append("")

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "output_type": self.output_type.value,
            "topic": self.topic,
            "agent_type": self.agent_type,
            "run_id": self.run_id,
            "title": self.title,
            "content": self.content,
            "sections": self.sections,
            "file_references": self.file_references,
            "findings_summary": self.findings_summary,
            "proposed_actions": self.proposed_actions,
            "confidence_scores": self.confidence_scores,
            "created_at": self.created_at.isoformat(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SubagentOutput":
        """Deserialize from JSON dict."""
        return cls(
            output_type=OutputType(data["output_type"]),
            topic=data["topic"],
            agent_type=data["agent_type"],
            run_id=data["run_id"],
            title=data["title"],
            content=data["content"],
            sections=data.get("sections", {}),
            file_references=data.get("file_references", []),
            findings_summary=data.get("findings_summary", []),
            proposed_actions=data.get("proposed_actions", []),
            confidence_scores=data.get("confidence_scores", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            content_hash=data.get("content_hash"),
        )


@dataclass
class ValidationResult:
    """Result of validating sub-agent output against contract."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)


class SubagentOutputValidator:
    """Validates sub-agent output against contracts."""

    def validate(self, output: SubagentOutput, contract: OutputContract) -> ValidationResult:
        """
        Validate sub-agent output against a contract.

        Args:
            output: The sub-agent output to validate
            contract: The contract to validate against

        Returns:
            ValidationResult with errors and warnings
        """
        errors: list[str] = []
        warnings: list[str] = []
        missing_sections: list[str] = []

        # Check output type matches
        if output.output_type != contract.output_type:
            errors.append(
                f"Output type mismatch: expected {contract.output_type.value}, "
                f"got {output.output_type.value}"
            )

        # Check content length
        if len(output.content) > contract.max_length_chars:
            errors.append(
                f"Content exceeds max length: {len(output.content)} > {contract.max_length_chars}"
            )

        # Check required sections
        content_lower = output.content.lower()
        for section in contract.required_sections:
            # Look for section header in content
            section_pattern = f"## {section.lower()}"
            alt_pattern = f"### {section.lower()}"
            if section_pattern not in content_lower and alt_pattern not in content_lower:
                # Also check if in sections dict
                if section.lower() not in {s.lower() for s in output.sections}:
                    missing_sections.append(section)
                    errors.append(f"Missing required section: {section}")

        # Check file references
        if contract.require_file_references and not output.file_references:
            errors.append("Contract requires file references but none provided")

        # Check confidence scores
        if contract.require_confidence_scores and not output.confidence_scores:
            errors.append("Contract requires confidence scores but none provided")

        # Check for recommended sections
        for section in contract.optional_sections:
            section_pattern = f"## {section.lower()}"
            alt_pattern = f"### {section.lower()}"
            if section_pattern not in content_lower and alt_pattern not in content_lower:
                warnings.append(f"Optional section not found: {section}")

        # Check that findings summary is provided (for context update)
        if not output.findings_summary:
            warnings.append("No findings summary provided for context update")

        # Check that proposed actions are provided
        if not output.proposed_actions:
            warnings.append("No proposed actions provided for context update")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            missing_sections=missing_sections,
        )

    def save_output(
        self,
        output: SubagentOutput,
        handoff_dir: Path,
        update_context: bool = True,
    ) -> Path:
        """
        Save validated output to the handoff directory.

        Args:
            output: The sub-agent output to save
            handoff_dir: Path to the handoff directory
            update_context: Whether to update context.json with the output info

        Returns:
            Path to the saved output file
        """
        handoff_dir = Path(handoff_dir)
        handoff_dir.mkdir(parents=True, exist_ok=True)

        # Save markdown output
        md_path = handoff_dir / output.get_filename()
        with open(md_path, "w") as f:
            f.write(output.to_markdown())

        # Save JSON backup
        json_path = handoff_dir / f"{output.get_filename()}.json"
        with open(json_path, "w") as f:
            json.dump(output.to_json(), f, indent=2)

        # Update context.json if requested
        if update_context:
            context_json_path = handoff_dir / "context.json"
            if context_json_path.exists():
                with open(context_json_path) as f:
                    context_data = json.load(f)

                # Add to subagent history
                if "subagent_history" not in context_data:
                    context_data["subagent_history"] = []

                context_data["subagent_history"].append(
                    {
                        "timestamp": output.created_at.isoformat(),
                        "agent_type": output.agent_type,
                        "action": f"Produced {output.output_type.value} on {output.topic}",
                        "output_file": output.get_filename(),
                    }
                )

                # Add artifact path
                if "artifact_paths" not in context_data:
                    context_data["artifact_paths"] = {}
                context_data["artifact_paths"][
                    f"{output.output_type.value}_{output.topic}"
                ] = output.get_filename()

                # Update version and timestamp
                context_data["version"] = context_data.get("version", 0) + 1
                context_data["updated_at"] = datetime.now().isoformat()

                with open(context_json_path, "w") as f:
                    json.dump(context_data, f, indent=2)

        return md_path


def create_contract(
    output_type: OutputType,
    topic: str,
    required_sections: Optional[list[str]] = None,
    optional_sections: Optional[list[str]] = None,
    max_length: int = 50000,
    require_refs: bool = True,
    require_confidence: bool = False,
) -> OutputContract:
    """
    Factory function to create output contracts.

    Args:
        output_type: Type of output (research, plan, analysis, etc.)
        topic: Topic being addressed
        required_sections: List of required section headers
        optional_sections: List of optional section headers
        max_length: Maximum content length in characters
        require_refs: Whether file references are required
        require_confidence: Whether confidence scores are required

    Returns:
        Configured OutputContract
    """
    # Use defaults based on output type if not provided
    if required_sections is None:
        if output_type == OutputType.RESEARCH:
            required_sections = ["Objective", "Methodology", "Findings", "Recommendations"]
        elif output_type == OutputType.PLAN:
            required_sections = [
                "Objective",
                "Approach",
                "Implementation Steps",
                "Acceptance Criteria",
            ]
        elif output_type == OutputType.ANALYSIS:
            required_sections = ["Scope", "Methodology", "Results", "Conclusions"]
        elif output_type == OutputType.REVIEW:
            required_sections = ["Scope", "Findings", "Severity Assessment", "Recommendations"]
        else:
            required_sections = ["Summary", "Details"]

    return OutputContract(
        output_type=output_type,
        topic=topic,
        required_sections=required_sections,
        optional_sections=optional_sections or [],
        max_length_chars=max_length,
        require_file_references=require_refs,
        require_confidence_scores=require_confidence,
    )
