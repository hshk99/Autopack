"""Documentation Phase Implementation for Autonomous Build System.

This module implements the DOCUMENTATION phase type, which enables the autonomous
executor to generate comprehensive documentation artifacts for a project.

Documentation phases are used when:
- API documentation needs to be generated
- Architecture diagrams and guides are required
- User guides and tutorials need to be created
- Onboarding flows need to be defined
- Developer documentation needs to be established

Design Principles:
- Documentation phases leverage existing documentation generation infrastructure
- Artifacts are generated to workspace in phase-specific subdirectory
- Results are cached and reusable across phases
- Clear success/failure criteria for documentation completeness
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DocumentationStatus(Enum):
    """Status of a documentation phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DocumentationConfig:
    """Configuration for a documentation phase."""

    documentation_types: List[str] = field(
        default_factory=lambda: ["api", "architecture", "user_guide", "onboarding"]
    )
    output_format: str = "markdown"
    include_diagrams: bool = True
    include_examples: bool = True
    save_to_history: bool = True
    max_duration_minutes: Optional[int] = None


@dataclass
class DocumentationInput:
    """Input data for documentation phase."""

    project_name: str
    project_description: str
    tech_stack: Dict[str, Any]
    api_endpoints: Optional[List[Dict[str, Any]]] = None
    architecture: Optional[Dict[str, Any]] = None
    target_audience: Optional[str] = None
    additional_context: Optional[Dict[str, Any]] = None


@dataclass
class DocumentationArtifact:
    """Represents a generated documentation artifact."""

    artifact_type: str
    file_path: str
    title: str
    description: str
    generated_at: Optional[datetime] = None
    size_bytes: Optional[int] = None
    sections_count: Optional[int] = None


@dataclass
class DocumentationOutput:
    """Output from documentation phase."""

    api_docs_path: Optional[str] = None
    architecture_guide_path: Optional[str] = None
    user_guide_path: Optional[str] = None
    onboarding_guide_path: Optional[str] = None
    artifacts_generated: List[DocumentationArtifact] = field(default_factory=list)
    total_pages_estimated: int = 0
    documentation_coverage: float = 0.0
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class DocumentationPhase:
    """Represents a documentation phase with its configuration and state."""

    phase_id: str
    description: str
    config: DocumentationConfig
    input_data: Optional[DocumentationInput] = None
    status: DocumentationStatus = DocumentationStatus.PENDING
    output: Optional[DocumentationOutput] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation."""
        output_dict = None
        if self.output:
            artifacts_list = [
                {
                    "artifact_type": a.artifact_type,
                    "file_path": a.file_path,
                    "title": a.title,
                    "description": a.description,
                    "generated_at": a.generated_at.isoformat() if a.generated_at else None,
                    "size_bytes": a.size_bytes,
                    "sections_count": a.sections_count,
                }
                for a in self.output.artifacts_generated
            ]
            output_dict = {
                "api_docs_path": self.output.api_docs_path,
                "architecture_guide_path": self.output.architecture_guide_path,
                "user_guide_path": self.output.user_guide_path,
                "onboarding_guide_path": self.output.onboarding_guide_path,
                "artifacts_generated": artifacts_list,
                "total_pages_estimated": self.output.total_pages_estimated,
                "documentation_coverage": self.output.documentation_coverage,
                "warnings": self.output.warnings,
                "recommendations": self.output.recommendations,
            }

        input_dict = None
        if self.input_data:
            input_dict = {
                "project_name": self.input_data.project_name,
                "project_description": self.input_data.project_description,
                "tech_stack": self.input_data.tech_stack,
                "api_endpoints": self.input_data.api_endpoints,
                "architecture": self.input_data.architecture,
                "target_audience": self.input_data.target_audience,
                "additional_context": self.input_data.additional_context,
            }

        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "documentation_types": self.config.documentation_types,
                "output_format": self.config.output_format,
                "include_diagrams": self.config.include_diagrams,
                "include_examples": self.config.include_examples,
                "save_to_history": self.config.save_to_history,
                "max_duration_minutes": self.config.max_duration_minutes,
            },
            "input_data": input_dict,
            "output": output_dict,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class DocumentationPhaseExecutor:
    """Executor for documentation phases."""

    def __init__(
        self,
        workspace_path: Optional[Path] = None,
        build_history_path: Optional[Path] = None,
    ):
        """Initialize the executor.

        Args:
            workspace_path: Optional path to workspace for artifact generation
            build_history_path: Optional path to BUILD_HISTORY.md
        """
        self.workspace_path = workspace_path or Path.cwd()
        self.build_history_path = build_history_path

    def execute(self, phase: DocumentationPhase) -> DocumentationPhase:
        """Execute a documentation phase.

        Args:
            phase: The phase to execute

        Returns:
            The updated phase with results
        """
        logger.info(f"Executing documentation phase: {phase.phase_id}")

        phase.status = DocumentationStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        phase.output = DocumentationOutput()
        phase.error = None

        try:
            # Validate input
            if not phase.input_data:
                phase.status = DocumentationStatus.FAILED
                phase.error = "No input data provided for documentation phase"
                return phase

            # Generate documentation artifacts
            self._generate_documentation_artifacts(phase)

            # Calculate coverage metrics
            self._calculate_coverage_metrics(phase)

            # Mark as completed if not already failed
            if phase.status == DocumentationStatus.IN_PROGRESS:
                phase.status = DocumentationStatus.COMPLETED

            # Save to history if configured
            if phase.config.save_to_history and self.build_history_path:
                self._save_to_history(phase)

        except Exception as e:
            logger.error(f"Phase execution failed: {e}", exc_info=True)
            phase.status = DocumentationStatus.FAILED
            phase.error = str(e)

        finally:
            phase.completed_at = datetime.now()

        return phase

    def _generate_documentation_artifacts(self, phase: DocumentationPhase) -> None:
        """Generate documentation artifacts based on configuration.

        Args:
            phase: The phase to execute
        """
        if not phase.output:
            return

        # Create workspace subdirectory for documentation
        doc_workspace = self.workspace_path / "documentation" / phase.phase_id
        doc_workspace.mkdir(parents=True, exist_ok=True)

        # Generate each configured documentation type
        for doc_type in phase.config.documentation_types:
            try:
                if doc_type == "api":
                    self._generate_api_documentation(phase, doc_workspace)
                elif doc_type == "architecture":
                    self._generate_architecture_guide(phase, doc_workspace)
                elif doc_type == "user_guide":
                    self._generate_user_guide(phase, doc_workspace)
                elif doc_type == "onboarding":
                    self._generate_onboarding_flow(phase, doc_workspace)
                else:
                    phase.output.warnings.append(f"Unknown documentation type: {doc_type}")
            except Exception as e:
                logger.error(f"Failed to generate {doc_type} documentation: {e}")
                phase.output.warnings.append(f"Failed to generate {doc_type}: {str(e)}")

    def _generate_api_documentation(self, phase: DocumentationPhase, workspace: Path) -> None:
        """Generate API documentation.

        Args:
            phase: The phase being executed
            workspace: Path to documentation workspace
        """
        api_path = workspace / "API.md"

        content = [
            f"# API Documentation - {phase.input_data.project_name}",
            "",
            "## Overview",
            f"{phase.input_data.project_description}",
            "",
        ]

        if phase.input_data.api_endpoints:
            content.extend(["## Endpoints", ""])
            for endpoint in phase.input_data.api_endpoints:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "/")
                description = endpoint.get("description", "")
                content.append(f"### {method} {path}")
                content.append(f"{description}")
                content.append("")

        if phase.config.include_examples:
            content.extend(
                [
                    "## Usage Examples",
                    "",
                    "```python",
                    f"import {phase.input_data.project_name.lower().replace(' ', '_')}",
                    "```",
                    "",
                ]
            )

        content.extend(
            [
                "## Response Formats",
                "",
                "All endpoints return JSON responses with standard error handling.",
                "",
                "## Authentication",
                "",
                "API authentication details and required headers are documented below.",
                "",
            ]
        )

        # Write file
        try:
            api_path.write_text("\n".join(content), encoding="utf-8")
            artifact = DocumentationArtifact(
                artifact_type="api",
                file_path=str(api_path),
                title="API Documentation",
                description="Complete API reference including endpoints and examples",
                generated_at=datetime.now(),
                size_bytes=len("\n".join(content).encode("utf-8")),
                sections_count=4,
            )
            phase.output.artifacts_generated.append(artifact)
            phase.output.api_docs_path = str(api_path)
            logger.info(f"Generated API documentation at {api_path}")
        except Exception as e:
            logger.error(f"Failed to write API documentation: {e}")
            raise

    def _generate_architecture_guide(self, phase: DocumentationPhase, workspace: Path) -> None:
        """Generate architecture guide.

        Args:
            phase: The phase being executed
            workspace: Path to documentation workspace
        """
        arch_path = workspace / "ARCHITECTURE.md"

        content = [
            f"# Architecture Guide - {phase.input_data.project_name}",
            "",
            "## System Overview",
            phase.input_data.project_description or "System architecture and component design.",
            "",
        ]

        if phase.input_data.architecture:
            content.extend(
                [
                    "## Architecture Components",
                    "",
                ]
            )
            arch_data = phase.input_data.architecture
            if "components" in arch_data:
                for component in arch_data["components"]:
                    name = component.get("name", "Component")
                    description = component.get("description", "")
                    content.append(f"### {name}")
                    content.append(description)
                    content.append("")

        if phase.input_data.tech_stack:
            content.extend(
                [
                    "## Technology Stack",
                    "",
                ]
            )
            for tech_type, tech_list in phase.input_data.tech_stack.items():
                content.append(f"### {tech_type}")
                if isinstance(tech_list, list):
                    for tech in tech_list:
                        content.append(f"- {tech}")
                else:
                    content.append(f"- {tech_list}")
                content.append("")

        if phase.config.include_diagrams:
            content.extend(
                [
                    "## System Diagrams",
                    "",
                    "Architecture diagrams showing component relationships and data flow.",
                    "",
                ]
            )

        content.extend(
            [
                "## Design Principles",
                "",
                "- Modularity: Components are loosely coupled",
                "- Scalability: System can scale horizontally",
                "- Maintainability: Clear separation of concerns",
                "- Extensibility: Easy to add new features",
                "",
            ]
        )

        # Write file
        try:
            arch_path.write_text("\n".join(content), encoding="utf-8")
            artifact = DocumentationArtifact(
                artifact_type="architecture",
                file_path=str(arch_path),
                title="Architecture Guide",
                description="System architecture, components, and design principles",
                generated_at=datetime.now(),
                size_bytes=len("\n".join(content).encode("utf-8")),
                sections_count=5,
            )
            phase.output.artifacts_generated.append(artifact)
            phase.output.architecture_guide_path = str(arch_path)
            logger.info(f"Generated architecture guide at {arch_path}")
        except Exception as e:
            logger.error(f"Failed to write architecture guide: {e}")
            raise

    def _generate_user_guide(self, phase: DocumentationPhase, workspace: Path) -> None:
        """Generate user guide.

        Args:
            phase: The phase being executed
            workspace: Path to documentation workspace
        """
        user_path = workspace / "USER_GUIDE.md"

        content = [
            f"# User Guide - {phase.input_data.project_name}",
            "",
            "## Getting Started",
            "This guide helps users understand and use the system effectively.",
            "",
            "## Prerequisites",
            "",
            "- Basic understanding of the platform",
            "- Access credentials",
            "- Required software/dependencies",
            "",
        ]

        if phase.input_data.target_audience:
            content.extend(
                [
                    "## Target Audience",
                    phase.input_data.target_audience,
                    "",
                ]
            )

        content.extend(
            [
                "## Features",
                "",
                "### Core Features",
                "- Feature 1: Description of feature 1",
                "- Feature 2: Description of feature 2",
                "- Feature 3: Description of feature 3",
                "",
                "## Step-by-Step Instructions",
                "",
                "### Setting Up",
                "Follow these steps to set up and configure the system.",
                "",
                "### Common Tasks",
                "Guide users through common workflows and use cases.",
                "",
            ]
        )

        if phase.config.include_examples:
            content.extend(
                [
                    "## Examples",
                    "",
                    "Example 1: Basic usage scenario",
                    "Example 2: Advanced usage",
                    "Example 3: Integration patterns",
                    "",
                ]
            )

        content.extend(
            [
                "## Troubleshooting",
                "",
                "### Common Issues",
                "- Issue 1 and resolution",
                "- Issue 2 and resolution",
                "",
                "## Support and Resources",
                "",
                "Additional help and documentation resources available.",
                "",
            ]
        )

        # Write file
        try:
            user_path.write_text("\n".join(content), encoding="utf-8")
            artifact = DocumentationArtifact(
                artifact_type="user_guide",
                file_path=str(user_path),
                title="User Guide",
                description="Comprehensive guide for end users",
                generated_at=datetime.now(),
                size_bytes=len("\n".join(content).encode("utf-8")),
                sections_count=6,
            )
            phase.output.artifacts_generated.append(artifact)
            phase.output.user_guide_path = str(user_path)
            logger.info(f"Generated user guide at {user_path}")
        except Exception as e:
            logger.error(f"Failed to write user guide: {e}")
            raise

    def _generate_onboarding_flow(self, phase: DocumentationPhase, workspace: Path) -> None:
        """Generate onboarding flow documentation.

        Args:
            phase: The phase being executed
            workspace: Path to documentation workspace
        """
        onboarding_path = workspace / "ONBOARDING.md"

        content = [
            f"# Onboarding Guide - {phase.input_data.project_name}",
            "",
            "## Welcome",
            "Welcome to the onboarding program. This guide will help you get up to speed quickly.",
            "",
            "## Onboarding Checklist",
            "",
            "- [ ] Read the project overview",
            "- [ ] Understand the architecture",
            "- [ ] Set up development environment",
            "- [ ] Run first example",
            "- [ ] Review code conventions",
            "- [ ] Explore test suite",
            "- [ ] Get familiar with deployment process",
            "",
        ]

        content.extend(
            [
                "## Day 1: Project Overview",
                "",
                "### Learning Objectives",
                "- Understand project goals and scope",
                "- Learn about key stakeholders",
                "- Familiarize with documentation",
                "",
                "## Day 2-3: Environment Setup",
                "",
                "### Learning Objectives",
                "- Set up development environment",
                "- Clone and build project",
                "- Run existing tests",
                "",
                "## Day 4-5: Code Exploration",
                "",
                "### Learning Objectives",
                "- Understand codebase structure",
                "- Study design patterns used",
                "- Review coding standards",
                "",
                "## Week 2: First Contribution",
                "",
                "### Learning Objectives",
                "- Make your first code contribution",
                "- Participate in code review",
                "- Understand CI/CD pipeline",
                "",
                "## Resources",
                "",
                "- Internal Wiki",
                "- API Documentation",
                "- Architecture Diagrams",
                "- Code Examples",
                "- Team Contacts",
                "",
            ]
        )

        # Write file
        try:
            onboarding_path.write_text("\n".join(content), encoding="utf-8")
            artifact = DocumentationArtifact(
                artifact_type="onboarding",
                file_path=str(onboarding_path),
                title="Onboarding Flow",
                description="Structured onboarding program for new team members",
                generated_at=datetime.now(),
                size_bytes=len("\n".join(content).encode("utf-8")),
                sections_count=5,
            )
            phase.output.artifacts_generated.append(artifact)
            phase.output.onboarding_guide_path = str(onboarding_path)
            logger.info(f"Generated onboarding flow at {onboarding_path}")
        except Exception as e:
            logger.error(f"Failed to write onboarding flow: {e}")
            raise

    def _calculate_coverage_metrics(self, phase: DocumentationPhase) -> None:
        """Calculate documentation coverage metrics.

        Args:
            phase: The phase to calculate metrics for
        """
        if not phase.output:
            return

        # Count generated artifacts
        artifact_count = len(phase.output.artifacts_generated)
        total_configured = len(phase.config.documentation_types)

        # Calculate coverage percentage based on configured types
        # Coverage = (generated artifacts / configured types) * 100
        phase.output.documentation_coverage = (
            (artifact_count / total_configured * 100) if total_configured > 0 else 0.0
        )

        # Estimate pages (rough estimate based on artifact count)
        phase.output.total_pages_estimated = artifact_count * 5

        # Add recommendations based on coverage
        if phase.output.documentation_coverage < 100.0:
            phase.output.recommendations.append(
                f"Documentation coverage is {phase.output.documentation_coverage:.1f}%. "
                "Consider generating missing documentation types."
            )

    def _save_to_history(self, phase: DocumentationPhase) -> None:
        """Save phase results to BUILD_HISTORY.

        Args:
            phase: The phase to save
        """
        if not self.build_history_path:
            return

        entry = self._format_history_entry(phase)

        # Append to build history
        try:
            with open(self.build_history_path, "a", encoding="utf-8") as f:
                f.write("\n" + entry + "\n")
        except Exception as e:
            logger.warning(f"Failed to save to build history: {e}")

    def _format_history_entry(self, phase: DocumentationPhase) -> str:
        """Format phase as BUILD_HISTORY entry.

        Args:
            phase: The phase to format

        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Documentation Phase: {phase.phase_id}",
            f"**Description**: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at}",
            f"**Completed**: {phase.completed_at}",
            "",
        ]

        if phase.output:
            lines.append("### Generated Artifacts")
            for artifact in phase.output.artifacts_generated:
                lines.append(f"- **{artifact.title}** ({artifact.artifact_type})")
                lines.append(f"  - Path: {artifact.file_path}")
                lines.append(f"  - Description: {artifact.description}")
                if artifact.sections_count:
                    lines.append(f"  - Sections: {artifact.sections_count}")
                lines.append("")

            lines.append(f"**Coverage**: {phase.output.documentation_coverage:.1f}%")
            lines.append(f"**Estimated Pages**: {phase.output.total_pages_estimated}")
            lines.append("")

            if phase.output.recommendations:
                lines.append("### Recommendations")
                for rec in phase.output.recommendations:
                    lines.append(f"- {rec}")
                lines.append("")

        if phase.error:
            lines.append(f"**Error**: {phase.error}")
            lines.append("")

        return "\n".join(lines)


def create_documentation_phase(
    phase_id: str, project_name: str, project_description: str, **kwargs
) -> DocumentationPhase:
    """Factory function to create a documentation phase.

    Args:
        phase_id: Unique phase identifier
        project_name: Name of the project
        project_description: Description of the project
        **kwargs: Additional configuration options

    Returns:
        Configured DocumentationPhase instance
    """
    tech_stack = kwargs.get("tech_stack", {})
    api_endpoints = kwargs.get("api_endpoints")
    architecture = kwargs.get("architecture")
    target_audience = kwargs.get("target_audience")
    additional_context = kwargs.get("additional_context")

    input_data = DocumentationInput(
        project_name=project_name,
        project_description=project_description,
        tech_stack=tech_stack,
        api_endpoints=api_endpoints,
        architecture=architecture,
        target_audience=target_audience,
        additional_context=additional_context,
    )

    config_kwargs = {}
    if "documentation_types" in kwargs:
        config_kwargs["documentation_types"] = kwargs["documentation_types"]
    if "output_format" in kwargs:
        config_kwargs["output_format"] = kwargs["output_format"]
    if "include_diagrams" in kwargs:
        config_kwargs["include_diagrams"] = kwargs["include_diagrams"]
    if "include_examples" in kwargs:
        config_kwargs["include_examples"] = kwargs["include_examples"]
    if "save_to_history" in kwargs:
        config_kwargs["save_to_history"] = kwargs["save_to_history"]
    if "max_duration_minutes" in kwargs:
        config_kwargs["max_duration_minutes"] = kwargs["max_duration_minutes"]

    config = DocumentationConfig(**config_kwargs)

    return DocumentationPhase(
        phase_id=phase_id,
        description=f"Documentation phase: {project_name}",
        config=config,
        input_data=input_data,
    )


# Backward compatibility alias
DocumentationPhaseManager = DocumentationPhaseExecutor
