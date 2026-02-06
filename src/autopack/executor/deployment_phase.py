"""Deployment phase support for the phase orchestrator.

This module provides guidance generation for the deployment phase, including:
- Container/Docker guidance
- Cloud deployment (AWS/GCP/Azure)
- CI/CD pipeline generation
- Monitoring setup

Architectural foundation for Wave 6 deployment phase extensions (IMP-HIGH-003).

ART-005 Enhancement: Integration with comprehensive DeploymentGuide generator for
generating full deployment documentation including platform-specific instructions,
environment configuration, security checklists, and troubleshooting guides.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeploymentProvider(str, Enum):
    """Supported deployment platforms."""

    DOCKER = "docker"
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    KUBERNETES = "kubernetes"


class GuidanceType(str, Enum):
    """Types of deployment guidance to generate."""

    CONTAINERIZATION = "containerization"
    CLOUD_DEPLOYMENT = "cloud_deployment"
    CI_CD_PIPELINE = "ci_cd_pipeline"
    MONITORING = "monitoring"


@dataclass
class DeploymentTemplate:
    """Template for deployment guidance generation."""

    name: str
    provider: DeploymentProvider
    guidance_type: GuidanceType
    template_content: str
    requirements: List[str] = field(default_factory=list)
    variables: Dict[str, str] = field(default_factory=dict)


class DeploymentTemplateRegistry:
    """Registry of deployment templates for guidance generation."""

    def __init__(self):
        """Initialize template registry with default templates."""
        self.templates: Dict[str, DeploymentTemplate] = {}
        self._register_default_templates()

    def _register_default_templates(self) -> None:
        """Register default deployment templates."""
        # Docker templates
        self.register_template(
            DeploymentTemplate(
                name="docker_basic",
                provider=DeploymentProvider.DOCKER,
                guidance_type=GuidanceType.CONTAINERIZATION,
                template_content="""# Basic Docker Configuration

## Dockerfile (Multi-stage build)
```dockerfile
# Build stage
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
    CMD python -c "import http.client; conn = http.client.HTTPConnection('localhost', 8000); conn.request('GET', '/health'); exit(0 if conn.getresponse().status == 200 else 1)"

CMD ["python", "-m", "app.main"]
```

## .dockerignore
```
__pycache__
*.pyc
*.pyo
*.egg-info/
.git
.gitignore
.env
.venv
node_modules
dist
build
.pytest_cache
.coverage
```

## Best Practices
- Use specific base image versions (not latest)
- Run as non-root user for security
- Minimize layer count and image size
- Use multi-stage builds for production
""",
                requirements=["docker", "docker-compose"],
            )
        )

        # AWS templates
        self.register_template(
            DeploymentTemplate(
                name="aws_ecs_deployment",
                provider=DeploymentProvider.AWS,
                guidance_type=GuidanceType.CLOUD_DEPLOYMENT,
                template_content="""# AWS ECS Deployment Guide

## Prerequisites
- AWS CLI configured with credentials
- ECR (Elastic Container Registry) repository created
- ECS cluster created
- IAM roles configured

## Steps

### 1. Build and Push Docker Image
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
docker build -t my-app .
docker tag my-app:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:latest
```

### 2. Create Task Definition
```json
{
  "family": "my-app",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "my-app",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/my-app",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### 3. Create Service
```bash
aws ecs create-service \\
  --cluster my-cluster \\
  --service-name my-app \\
  --task-definition my-app \\
  --desired-count 2 \\
  --launch-type FARGATE \\
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx]}"
```
""",
                requirements=["aws-cli", "docker"],
            )
        )

        # CI/CD templates
        self.register_template(
            DeploymentTemplate(
                name="github_actions_ci_cd",
                provider=DeploymentProvider.DOCKER,
                guidance_type=GuidanceType.CI_CD_PIPELINE,
                template_content="""# GitHub Actions CI/CD Pipeline

## .github/workflows/deploy.yml

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/ -v --cov

      - name: Run linting
        run: |
          pip install black flake8
          black --check .
          flake8 .

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3

      - name: Build Docker image
        run: docker build -t my-app:${{ github.sha }} .

      - name: Login to ECR
        env:
          AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
        run: |
          aws ecr get-login-password | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

      - name: Push to ECR
        env:
          AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
        run: |
          docker tag my-app:${{ github.sha }} $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/my-app:latest
          docker push $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/my-app:latest

      - name: Deploy to ECS
        env:
          AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
        run: |
          aws ecs update-service \\
            --cluster my-cluster \\
            --service my-app \\
            --force-new-deployment
```

## Key Features
- Automated testing on every push
- Code quality checks (linting, formatting)
- Docker image build and push to ECR
- Automatic deployment to ECS on main branch
- PR checks prevent deployment of failing code
""",
                requirements=["github-actions", "docker"],
            )
        )

        # Monitoring templates
        self.register_template(
            DeploymentTemplate(
                name="prometheus_monitoring",
                provider=DeploymentProvider.DOCKER,
                guidance_type=GuidanceType.MONITORING,
                template_content="""# Prometheus Monitoring Setup

## Prometheus Configuration

### prometheus.yml
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'my-app'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'

  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
```

## Application Instrumentation

### Python (using prometheus_client)
```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from flask import Response

# Define metrics
request_count = Counter('app_requests_total', 'Total requests', ['method', 'endpoint'])
request_duration = Histogram('app_request_duration_seconds', 'Request duration')
active_connections = Gauge('app_active_connections', 'Active connections')

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype='text/plain')

@app.before_request
def before_request():
    request.start_time = time.time()
    active_connections.inc()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time
    request_duration.observe(duration)
    request_count.labels(
        method=request.method,
        endpoint=request.path
    ).inc()
    active_connections.dec()
    return response
```

## Docker Compose Stack

```yaml
version: '3'
services:
  app:
    build: .
    ports:
      - "8000:8000"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

## Alert Rules (prometheus-alerts.yml)
```yaml
groups:
  - name: app_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(app_errors_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate on {{ $labels.instance }}"

      - alert: HighResponseTime
        expr: histogram_quantile(0.95, app_request_duration_seconds_bucket) > 1
        for: 5m
        annotations:
          summary: "High response time on {{ $labels.instance }}"
```
""",
                requirements=["prometheus", "grafana", "prometheus-client"],
            )
        )

    def register_template(self, template: DeploymentTemplate) -> None:
        """Register a deployment template.

        Args:
            template: Template to register
        """
        self.templates[template.name] = template

    def get_template(self, name: str) -> Optional[DeploymentTemplate]:
        """Get a registered template by name.

        Args:
            name: Template name

        Returns:
            Template if found, None otherwise
        """
        return self.templates.get(name)

    def get_templates_by_provider(self, provider: DeploymentProvider) -> List[DeploymentTemplate]:
        """Get all templates for a provider.

        Args:
            provider: Deployment provider

        Returns:
            List of templates for the provider
        """
        return [t for t in self.templates.values() if t.provider == provider]

    def get_templates_by_guidance_type(
        self, guidance_type: GuidanceType
    ) -> List[DeploymentTemplate]:
        """Get all templates for a guidance type.

        Args:
            guidance_type: Type of guidance

        Returns:
            List of templates for the guidance type
        """
        return [t for t in self.templates.values() if t.guidance_type == guidance_type]


class DeploymentPhaseHandler:
    """Handler for deployment phase execution and guidance generation.

    Coordinates deployment phase execution by:
    - Selecting appropriate templates based on project requirements
    - Generating comprehensive deployment guidance using DeploymentGuide
    - Creating necessary configuration files

    ART-005: Integrated with comprehensive DeploymentGuide generator for
    generating full deployment documentation.
    """

    def __init__(self):
        """Initialize deployment phase handler."""
        self.template_registry = DeploymentTemplateRegistry()
        self._deployment_guide = None  # Lazy-loaded DeploymentGuide instance

    def generate_deployment_guidance(self, providers: List[str], guidance_types: List[str]) -> str:
        """Generate deployment guidance for the phase.

        Args:
            providers: List of deployment providers to include
            guidance_types: List of guidance types to generate

        Returns:
            Combined deployment guidance as string
        """
        guidance_sections = []

        for provider_name in providers:
            try:
                provider = DeploymentProvider(provider_name)
                templates = self.template_registry.get_templates_by_provider(provider)

                if templates:
                    guidance_sections.append(f"## {provider.value.upper()} Deployment\n")
                    for template in templates:
                        guidance_sections.append(f"\n### {template.name}\n")
                        guidance_sections.append(template.template_content)
            except ValueError:
                continue

        for guidance_name in guidance_types:
            try:
                guidance_type = GuidanceType(guidance_name)
                templates = self.template_registry.get_templates_by_guidance_type(guidance_type)

                if templates:
                    guidance_sections.append(f"## {guidance_type.value.upper()}\n")
                    for template in templates:
                        guidance_sections.append(f"\n### {template.name}\n")
                        guidance_sections.append(template.template_content)
            except ValueError:
                continue

        return (
            "\n".join(guidance_sections)
            if guidance_sections
            else "No deployment guidance available"
        )

    def create_deployment_phase_config(
        self, providers: Optional[List[str]] = None, guidance_types: Optional[List[str]] = None
    ) -> Dict:
        """Create deployment phase configuration.

        Args:
            providers: List of deployment providers
            guidance_types: List of guidance types

        Returns:
            Deployment configuration dictionary
        """
        return {
            "providers": providers or [DeploymentProvider.DOCKER.value],
            "guidance_types": guidance_types or [GuidanceType.CONTAINERIZATION.value],
            "templates": [
                t.name
                for t in self.template_registry.templates.values()
                if (not providers or t.provider.value in providers)
                and (not guidance_types or t.guidance_type.value in guidance_types)
            ],
        }

    def _get_deployment_guide(self) -> Any:
        """Get or lazily load DeploymentGuide instance.

        Returns:
            DeploymentGuide instance or None if import fails
        """
        if self._deployment_guide is None:
            try:
                from autopack.artifact_generators.deployment_guide import DeploymentGuide
                self._deployment_guide = DeploymentGuide()
                logger.debug("[ART-005] DeploymentGuide loaded successfully")
            except ImportError as e:
                logger.warning(
                    f"[ART-005] Failed to import DeploymentGuide: {e}. "
                    "Template-based guidance will be used instead."
                )
                return None
        return self._deployment_guide

    def generate_comprehensive_deployment_guide(
        self,
        project_name: str,
        tech_stack: Dict[str, Any],
        platforms: Optional[List[str]] = None,
        project_requirements: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate comprehensive deployment guide using DeploymentGuide generator.

        This method provides full deployment documentation including:
        - Platform-specific deployment instructions (AWS, GCP, Azure, Heroku, Self-hosted)
        - Environment configuration guides
        - Security checklists
        - Troubleshooting sections
        - Monitoring and maintenance setup

        ART-005: Wires comprehensive deployment guide generation into deploy phase.

        Args:
            project_name: Name of the project
            tech_stack: Technology stack configuration
            platforms: List of platforms to generate guides for
            project_requirements: Optional project requirements and constraints

        Returns:
            Comprehensive deployment guide as string
        """
        logger.info(
            f"[ART-005] Generating comprehensive deployment guide for {project_name} "
            f"with platforms: {platforms or 'all'}"
        )

        guide_generator = self._get_deployment_guide()
        if guide_generator is not None:
            try:
                return guide_generator.generate(
                    project_name=project_name,
                    tech_stack=tech_stack,
                    platforms=platforms,
                    project_requirements=project_requirements,
                )
            except Exception as e:
                logger.warning(
                    f"[ART-005] Failed to generate comprehensive guide: {e}. "
                    "Falling back to template-based guidance."
                )

        # Fallback to template-based guidance if comprehensive guide fails
        logger.debug("[ART-005] Using fallback template-based guidance")
        return self.generate_deployment_guidance(
            providers=platforms or ["docker"],
            guidance_types=["containerization", "cloud_deployment", "ci_cd_pipeline", "monitoring"],
        )
