"""Deploy Phase Implementation for Autonomous Build System.

This module implements the DEPLOY phase type, which enables the autonomous
executor to orchestrate deployment configuration generation for multiple platforms
and CI/CD systems.

Deploy phases are used when:
- A project needs deployment configuration for production
- Multiple deployment platforms need to be supported (AWS, GCP, Azure, Docker)
- CI/CD pipelines require generation and configuration
- Monitoring and health checks need to be set up

Design Principles:
- Deploy phases leverage existing deployment guidance infrastructure
- Artifacts are generated to workspace in phase-specific subdirectory
- Results are cached and reusable across phases
- Clear success/failure criteria for deployment readiness
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeployStatus(Enum):
    """Status of a deployment phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DeployConfig:
    """Configuration for a deployment phase."""

    providers: List[str] = field(default_factory=lambda: ["docker"])
    guidance_types: List[str] = field(default_factory=lambda: ["containerization"])
    enable_cicd: bool = True
    cicd_platform: str = "github_actions"
    enable_monitoring: bool = True
    health_check_path: str = "/health"
    save_to_history: bool = True
    max_duration_minutes: Optional[int] = None


@dataclass
class DeployInput:
    """Input data for deployment phase."""

    project_name: str
    tech_stack: Dict[str, Any]
    project_requirements: Optional[Dict[str, Any]] = None


@dataclass
class DeployOutput:
    """Output from deployment phase."""

    deployment_guide_path: Optional[str] = None
    docker_config_path: Optional[str] = None
    cicd_config_path: Optional[str] = None
    monitoring_config_path: Optional[str] = None
    providers_configured: List[str] = field(default_factory=list)
    artifacts_generated: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class DeployPhase:
    """Represents a deployment phase with its configuration and state."""

    phase_id: str
    description: str
    config: DeployConfig
    input_data: Optional[DeployInput] = None
    status: DeployStatus = DeployStatus.PENDING
    output: Optional[DeployOutput] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation."""
        output_dict = None
        if self.output:
            output_dict = {
                "deployment_guide_path": self.output.deployment_guide_path,
                "docker_config_path": self.output.docker_config_path,
                "cicd_config_path": self.output.cicd_config_path,
                "monitoring_config_path": self.output.monitoring_config_path,
                "providers_configured": self.output.providers_configured,
                "artifacts_generated": self.output.artifacts_generated,
                "warnings": self.output.warnings,
                "recommendations": self.output.recommendations,
            }

        input_dict = None
        if self.input_data:
            input_dict = {
                "project_name": self.input_data.project_name,
                "tech_stack": self.input_data.tech_stack,
                "project_requirements": self.input_data.project_requirements,
            }

        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "providers": self.config.providers,
                "guidance_types": self.config.guidance_types,
                "enable_cicd": self.config.enable_cicd,
                "cicd_platform": self.config.cicd_platform,
                "enable_monitoring": self.config.enable_monitoring,
                "health_check_path": self.config.health_check_path,
                "save_to_history": self.config.save_to_history,
                "max_duration_minutes": self.config.max_duration_minutes,
            },
            "input_data": input_dict,
            "output": output_dict,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class DeployPhaseExecutor:
    """Executor for deployment phases."""

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

    def execute(self, phase: DeployPhase) -> DeployPhase:
        """Execute a deployment phase.

        Args:
            phase: The phase to execute

        Returns:
            The updated phase with results
        """
        logger.info(f"Executing deployment phase: {phase.phase_id}")

        phase.status = DeployStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        phase.output = DeployOutput()
        phase.error = None

        try:
            # Validate input
            if not phase.input_data:
                phase.status = DeployStatus.FAILED
                phase.error = "No input data provided for deployment phase"
                return phase

            # Generate deployment artifacts
            self._generate_deployment_artifacts(phase)

            # Mark as completed if not already failed
            if phase.status == DeployStatus.IN_PROGRESS:
                phase.status = DeployStatus.COMPLETED

            # Save to history if configured
            if phase.config.save_to_history and self.build_history_path:
                self._save_to_history(phase)

        except Exception as e:
            logger.error(f"Phase execution failed: {e}", exc_info=True)
            phase.status = DeployStatus.FAILED
            phase.error = str(e)

        finally:
            phase.completed_at = datetime.now()

        return phase

    def _generate_deployment_artifacts(self, phase: DeployPhase) -> None:
        """Generate deployment artifacts for configured providers.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        # Validate providers
        valid_providers = [
            "docker",
            "aws",
            "gcp",
            "azure",
            "heroku",
            "kubernetes",
        ]
        providers = [p for p in phase.config.providers if p in valid_providers]
        if not providers:
            phase.output.warnings.append(
                f"No valid providers specified. Valid providers: {valid_providers}"
            )
            providers = ["docker"]

        # Generate deployment guide (multi-platform)
        try:
            from autopack.artifact_generators.deployment_guide import DeploymentGuide

            guide_generator = DeploymentGuide()
            guide_content = guide_generator.generate(
                project_name=phase.input_data.project_name,
                tech_stack=phase.input_data.tech_stack,
                platforms=providers,
                project_requirements=phase.input_data.project_requirements,
            )

            # Write deployment guide to workspace
            deploy_dir = self.workspace_path / "deployment"
            deploy_dir.mkdir(parents=True, exist_ok=True)
            guide_path = deploy_dir / "DEPLOYMENT_GUIDE.md"
            guide_path.write_text(guide_content, encoding="utf-8")

            phase.output.deployment_guide_path = str(guide_path)
            phase.output.artifacts_generated.append(str(guide_path))
            logger.info(f"Generated deployment guide: {guide_path}")

        except Exception as e:
            logger.warning(f"Failed to generate deployment guide: {e}")
            phase.output.warnings.append(f"Deployment guide generation failed: {str(e)}")

        # Generate Docker configuration if Docker is a provider
        if "docker" in providers:
            try:
                self._generate_docker_config(phase)
            except Exception as e:
                logger.warning(f"Failed to generate Docker config: {e}")
                phase.output.warnings.append(f"Docker config generation failed: {str(e)}")

        # Generate CI/CD configuration if enabled
        if phase.config.enable_cicd:
            try:
                self._generate_cicd_config(phase)
            except Exception as e:
                logger.warning(f"Failed to generate CI/CD config: {e}")
                phase.output.warnings.append(f"CI/CD config generation failed: {str(e)}")

        # Generate monitoring configuration if enabled
        if phase.config.enable_monitoring:
            try:
                self._generate_monitoring_config(phase)
            except Exception as e:
                logger.warning(f"Failed to generate monitoring config: {e}")
                phase.output.warnings.append(f"Monitoring config generation failed: {str(e)}")

        # Update providers configured
        phase.output.providers_configured = providers

    def _generate_docker_config(self, phase: DeployPhase) -> None:
        """Generate Docker configuration files.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        # Create Dockerfile template
        tech_stack = phase.input_data.tech_stack
        language = tech_stack.get("language", "python").lower()

        dockerfile_content = f"""# Dockerfile for {phase.input_data.project_name}
# Generated by Autopack deployment phase

FROM {self._get_base_image(language)}

WORKDIR /app

# Copy dependency files
COPY requirements.txt .

# Install dependencies
RUN {self._get_install_command(language)}

# Copy application code
COPY . .

# Expose port (adjust as needed)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD [{self._get_run_command(language)}]
"""

        deploy_dir = self.workspace_path / "deployment"
        deploy_dir.mkdir(parents=True, exist_ok=True)
        dockerfile_path = deploy_dir / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

        if phase.output:
            phase.output.docker_config_path = str(dockerfile_path)
            phase.output.artifacts_generated.append(str(dockerfile_path))
            logger.info(f"Generated Dockerfile: {dockerfile_path}")

    def _generate_cicd_config(self, phase: DeployPhase) -> None:
        """Generate CI/CD configuration files.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        platform = phase.config.cicd_platform.lower()

        if platform == "github_actions":
            cicd_content = self._generate_github_actions_config(phase.input_data)
        elif platform == "gitlab_ci":
            cicd_content = self._generate_gitlab_ci_config(phase.input_data)
        else:
            logger.warning(f"Unsupported CI/CD platform: {platform}")
            return

        deploy_dir = self.workspace_path / "deployment"
        deploy_dir.mkdir(parents=True, exist_ok=True)

        if platform == "github_actions":
            ci_dir = deploy_dir / ".github" / "workflows"
            ci_dir.mkdir(parents=True, exist_ok=True)
            ci_path = ci_dir / "deploy.yml"
        else:
            ci_path = deploy_dir / ".gitlab-ci.yml"

        ci_path.write_text(cicd_content, encoding="utf-8")

        if phase.output:
            phase.output.cicd_config_path = str(ci_path)
            phase.output.artifacts_generated.append(str(ci_path))
            logger.info(f"Generated CI/CD config: {ci_path}")

    def _generate_github_actions_config(self, input_data: DeployInput) -> str:
        """Generate GitHub Actions workflow configuration.

        Args:
            input_data: Deployment input data

        Returns:
            YAML content for GitHub Actions workflow
        """
        return f"""name: Deploy {input_data.project_name}

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run tests
        run: pytest

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - uses: actions/checkout@v3
      - name: Build and push Docker image
        run: |
          docker build -t {input_data.project_name}:latest .
          # Add push commands for your registry
"""

    def _generate_gitlab_ci_config(self, input_data: DeployInput) -> str:
        """Generate GitLab CI configuration.

        Args:
            input_data: Deployment input data

        Returns:
            YAML content for GitLab CI
        """
        return f"""stages:
  - test
  - deploy

test:
  stage: test
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - pytest

deploy:
  stage: deploy
  image: docker:latest
  script:
    - docker build -t {input_data.project_name}:latest .
    # Add deployment script
  only:
    - main
"""

    def _generate_monitoring_config(self, phase: DeployPhase) -> None:
        """Generate monitoring configuration.

        Args:
            phase: The phase being executed
        """
        if not phase.output:
            return

        monitoring_content = """# Monitoring Configuration

## Prometheus Configuration

Create a prometheus.yml file in your deployment directory:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'application'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s
```

## Health Check Endpoint

Implement a health check endpoint in your application:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
```

## Alerts Configuration

Configure alerts in your monitoring system to watch for:
- Application downtime (health check failures)
- High error rates (>1%)
- Slow response times (>500ms)
- Memory/CPU usage spikes
"""

        deploy_dir = self.workspace_path / "deployment"
        deploy_dir.mkdir(parents=True, exist_ok=True)
        monitoring_path = deploy_dir / "MONITORING.md"
        monitoring_path.write_text(monitoring_content, encoding="utf-8")

        phase.output.monitoring_config_path = str(monitoring_path)
        phase.output.artifacts_generated.append(str(monitoring_path))
        logger.info(f"Generated monitoring config: {monitoring_path}")

    def _get_base_image(self, language: str) -> str:
        """Get Docker base image for language.

        Args:
            language: Programming language

        Returns:
            Docker image tag
        """
        images = {
            "python": "python:3.11-slim",
            "javascript": "node:18-alpine",
            "typescript": "node:18-alpine",
            "go": "golang:1.20-alpine",
            "java": "openjdk:21-jdk-slim",
            "rust": "rust:1.70",
        }
        return images.get(language, "python:3.11-slim")

    def _get_install_command(self, language: str) -> str:
        """Get install command for language.

        Args:
            language: Programming language

        Returns:
            Installation command
        """
        commands = {
            "python": "pip install --no-cache-dir -r requirements.txt",
            "javascript": "npm ci",
            "typescript": "npm ci",
            "go": "go mod download && go mod verify",
            "java": "mvn clean install -DskipTests",
            "rust": "cargo build --release",
        }
        return commands.get(language, "pip install --no-cache-dir -r requirements.txt")

    def _get_run_command(self, language: str) -> str:
        """Get run command for language.

        Args:
            language: Programming language

        Returns:
            Run command
        """
        commands = {
            "python": '"python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0"',
            "javascript": '"npm", "start"',
            "typescript": '"npm", "start"',
            "go": '"/app/bin/app"',
            "java": '"java", "-jar", "target/app.jar"',
            "rust": '"/app/target/release/app"',
        }
        return commands.get(language, '"python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0"')

    def _save_to_history(self, phase: DeployPhase) -> None:
        """Save phase results to BUILD_HISTORY.

        Args:
            phase: The phase to save
        """
        if not self.build_history_path:
            return

        entry = self._format_history_entry(phase)

        try:
            with open(self.build_history_path, "a", encoding="utf-8") as f:
                f.write("\n" + entry + "\n")
        except Exception as e:
            logger.warning(f"Failed to save to build history: {e}")

    def _format_history_entry(self, phase: DeployPhase) -> str:
        """Format phase as BUILD_HISTORY entry.

        Args:
            phase: The phase to format

        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Deploy Phase: {phase.phase_id}",
            f"**Description**: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at}",
            f"**Completed**: {phase.completed_at}",
            "",
        ]

        if phase.output:
            lines.append("### Deployment Artifacts")
            if phase.output.providers_configured:
                lines.append(
                    f"- **Providers Configured**: {', '.join(phase.output.providers_configured)}"
                )
            if phase.output.artifacts_generated:
                lines.append("- **Artifacts Generated**:")
                for artifact in phase.output.artifacts_generated:
                    lines.append(f"  - {artifact}")
            if phase.output.warnings:
                lines.append("- **Warnings**:")
                for warning in phase.output.warnings:
                    lines.append(f"  - {warning}")
            lines.append("")

        if phase.error:
            lines.append(f"**Error**: {phase.error}")
            lines.append("")

        return "\n".join(lines)


def create_deploy_phase(
    phase_id: str, project_name: str, tech_stack: Dict[str, Any], **kwargs
) -> DeployPhase:
    """Factory function to create a deployment phase.

    Args:
        phase_id: Unique phase identifier
        project_name: Name of the project
        tech_stack: Technology stack configuration
        **kwargs: Additional configuration options

    Returns:
        Configured DeployPhase instance
    """
    config = DeployConfig(**kwargs)
    input_data = DeployInput(
        project_name=project_name,
        tech_stack=tech_stack,
    )

    return DeployPhase(
        phase_id=phase_id,
        description=f"Deploy phase: {phase_id}",
        config=config,
        input_data=input_data,
    )
