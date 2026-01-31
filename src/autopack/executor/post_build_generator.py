"""Post-Build Artifact Generator for generating deployment artifacts after successful builds.

This module generates post-build artifacts including:
- Deployment configurations (Docker, Kubernetes, serverless)
- Operational runbooks for day-to-day operations
- Monitoring and alerting templates
- Infrastructure configuration files

Implements IMP-INT-003: Post-Build Artifact Generation.
Depends on: IMP-RES-003 (Deployment Guidance Generator), IMP-RES-004 (CI/CD Pipeline Generator)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ArtifactType(str, Enum):
    """Types of post-build artifacts."""

    DEPLOYMENT_CONFIG = "deployment_config"
    RUNBOOK = "runbook"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    INFRASTRUCTURE = "infrastructure"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    CICD = "cicd"


class RunbookCategory(str, Enum):
    """Categories of operational runbooks."""

    DEPLOYMENT = "deployment"
    TROUBLESHOOTING = "troubleshooting"
    SCALING = "scaling"
    BACKUP_RESTORE = "backup_restore"
    INCIDENT_RESPONSE = "incident_response"
    MAINTENANCE = "maintenance"


@dataclass
class BuildCharacteristics:
    """Captured characteristics of a successful build."""

    project_name: str
    tech_stack: Dict[str, Any] = field(default_factory=dict)
    language: str = "unknown"
    framework: str = "unknown"
    build_tool: str = "unknown"
    test_framework: Optional[str] = None
    has_database: bool = False
    has_api: bool = False
    is_containerized: bool = False
    port: int = 3000
    environment_variables: List[str] = field(default_factory=list)
    build_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    build_duration_seconds: float = 0.0
    test_coverage_percent: Optional[float] = None


@dataclass
class PostBuildArtifact:
    """A generated post-build artifact."""

    artifact_type: ArtifactType
    name: str
    content: str
    file_extension: str = "md"
    metadata: Dict[str, Any] = field(default_factory=dict)


class PostBuildArtifactGenerator:
    """Generator for post-build deployment artifacts.

    Generates deployment configurations, operational runbooks, and monitoring
    templates after successful project builds.
    """

    def __init__(
        self,
        deployment_analyzer: Optional[Any] = None,
        cicd_generator: Optional[Any] = None,
    ):
        """Initialize the post-build artifact generator.

        Args:
            deployment_analyzer: Optional DeploymentAnalyzer instance for deployment configs
            cicd_generator: Optional CI/CD generator for pipeline configs
        """
        self._deployment_analyzer = deployment_analyzer
        self._cicd_generator = cicd_generator
        self._generated_artifacts: List[PostBuildArtifact] = []

    def generate_all_artifacts(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Optional[Dict[str, Any]] = None,
    ) -> List[PostBuildArtifact]:
        """Generate all post-build artifacts for a successful build.

        Args:
            build_characteristics: Captured build characteristics
            tech_stack: Optional tech stack configuration

        Returns:
            List of generated PostBuildArtifact objects
        """
        logger.info(
            f"[PostBuildArtifactGenerator] Generating artifacts for: {build_characteristics.project_name}"
        )

        tech_stack = tech_stack or build_characteristics.tech_stack
        artifacts: List[PostBuildArtifact] = []

        # Generate deployment config
        deployment_config = self.generate_deployment_config(
            build_characteristics, tech_stack
        )
        artifacts.append(deployment_config)

        # Generate operational runbooks
        runbooks = self.generate_runbooks(build_characteristics, tech_stack)
        artifacts.extend(runbooks)

        # Generate monitoring templates
        monitoring = self.generate_monitoring_templates(
            build_characteristics, tech_stack
        )
        artifacts.append(monitoring)

        # Generate alerting rules
        alerting = self.generate_alerting_rules(build_characteristics, tech_stack)
        artifacts.append(alerting)

        # Generate Docker config if containerized
        if build_characteristics.is_containerized:
            docker_config = self.generate_docker_config(
                build_characteristics, tech_stack
            )
            artifacts.append(docker_config)

        self._generated_artifacts = artifacts
        logger.info(
            f"[PostBuildArtifactGenerator] Generated {len(artifacts)} artifacts"
        )

        return artifacts

    def generate_deployment_config(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate deployment configuration for the built project.

        Args:
            build_characteristics: Build characteristics
            tech_stack: Tech stack configuration

        Returns:
            Deployment configuration artifact
        """
        logger.info("[PostBuildArtifactGenerator] Generating deployment configuration")

        content = self._generate_deployment_config_content(
            build_characteristics, tech_stack
        )

        return PostBuildArtifact(
            artifact_type=ArtifactType.DEPLOYMENT_CONFIG,
            name="DEPLOYMENT_CONFIG",
            content=content,
            file_extension="md",
            metadata={
                "project_name": build_characteristics.project_name,
                "language": build_characteristics.language,
                "framework": build_characteristics.framework,
            },
        )

    def _generate_deployment_config_content(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> str:
        """Generate deployment configuration markdown content."""
        sections = [
            f"# Deployment Configuration: {build_characteristics.project_name}",
            "",
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Tech Stack**: {build_characteristics.language} / {build_characteristics.framework}",
            f"**Build Tool**: {build_characteristics.build_tool}",
            "",
            "---",
            "",
            "## Overview",
            "",
            "This document provides deployment configuration for the project based on the successful build.",
            "",
            "## Environment Configuration",
            "",
            "### Required Environment Variables",
            "",
        ]

        # Add environment variables
        if build_characteristics.environment_variables:
            for env_var in build_characteristics.environment_variables:
                sections.append(f"- `{env_var}`")
        else:
            sections.append("- `NODE_ENV` or `PYTHON_ENV` (production)")
            sections.append("- `PORT` (default: {})".format(build_characteristics.port))

        sections.extend(
            [
                "",
                "### Recommended Configuration",
                "",
                "```bash",
                f"# Application port",
                f"PORT={build_characteristics.port}",
                "",
                "# Environment",
                "NODE_ENV=production",
                "",
                "# Logging",
                "LOG_LEVEL=info",
                "```",
                "",
                "## Deployment Strategy",
                "",
            ]
        )

        # Add deployment strategy based on tech stack
        if build_characteristics.is_containerized:
            sections.extend(self._get_container_deployment_strategy())
        else:
            sections.extend(
                self._get_standard_deployment_strategy(build_characteristics)
            )

        sections.extend(
            [
                "",
                "## Health Checks",
                "",
                "### Readiness Probe",
                "```yaml",
                "readinessProbe:",
                "  httpGet:",
                "    path: /health",
                f"    port: {build_characteristics.port}",
                "  initialDelaySeconds: 5",
                "  periodSeconds: 10",
                "```",
                "",
                "### Liveness Probe",
                "```yaml",
                "livenessProbe:",
                "  httpGet:",
                "    path: /health",
                f"    port: {build_characteristics.port}",
                "  initialDelaySeconds: 15",
                "  periodSeconds: 20",
                "```",
                "",
                "## Resource Limits",
                "",
                "### Recommended Limits",
                "",
                "| Resource | Request | Limit |",
                "|----------|---------|-------|",
                "| CPU | 100m | 500m |",
                "| Memory | 128Mi | 512Mi |",
                "",
            ]
        )

        return "\n".join(sections)

    def _get_container_deployment_strategy(self) -> List[str]:
        """Get container deployment strategy content."""
        return [
            "### Container Deployment",
            "",
            "1. **Build Docker Image**",
            "   ```bash",
            "   docker build -t app:latest .",
            "   ```",
            "",
            "2. **Push to Registry**",
            "   ```bash",
            "   docker tag app:latest registry.example.com/app:latest",
            "   docker push registry.example.com/app:latest",
            "   ```",
            "",
            "3. **Deploy to Kubernetes**",
            "   ```bash",
            "   kubectl apply -f k8s/",
            "   ```",
            "",
            "4. **Verify Deployment**",
            "   ```bash",
            "   kubectl rollout status deployment/app",
            "   ```",
        ]

    def _get_standard_deployment_strategy(
        self, build_characteristics: BuildCharacteristics
    ) -> List[str]:
        """Get standard deployment strategy content."""
        if build_characteristics.language == "node":
            return [
                "### Node.js Deployment",
                "",
                "1. **Install Dependencies**",
                "   ```bash",
                "   npm ci --production",
                "   ```",
                "",
                "2. **Build Application**",
                "   ```bash",
                "   npm run build",
                "   ```",
                "",
                "3. **Start Application**",
                "   ```bash",
                "   npm start",
                "   ```",
            ]
        elif build_characteristics.language == "python":
            return [
                "### Python Deployment",
                "",
                "1. **Create Virtual Environment**",
                "   ```bash",
                "   python -m venv venv",
                "   source venv/bin/activate",
                "   ```",
                "",
                "2. **Install Dependencies**",
                "   ```bash",
                "   pip install -r requirements.txt",
                "   ```",
                "",
                "3. **Start Application**",
                "   ```bash",
                "   gunicorn app:app --bind 0.0.0.0:8000",
                "   ```",
            ]
        else:
            return [
                "### Standard Deployment",
                "",
                "1. **Install Dependencies**",
                f"   - Install {build_characteristics.language} runtime",
                "   - Install project dependencies",
                "",
                "2. **Build Application**",
                "   - Run build command for your project",
                "",
                "3. **Start Application**",
                "   - Run start command for your project",
            ]

    def generate_runbooks(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> List[PostBuildArtifact]:
        """Generate operational runbooks.

        Args:
            build_characteristics: Build characteristics
            tech_stack: Tech stack configuration

        Returns:
            List of runbook artifacts
        """
        logger.info("[PostBuildArtifactGenerator] Generating operational runbooks")

        runbooks = []

        # Deployment runbook
        runbooks.append(
            self._generate_deployment_runbook(build_characteristics, tech_stack)
        )

        # Troubleshooting runbook
        runbooks.append(
            self._generate_troubleshooting_runbook(build_characteristics, tech_stack)
        )

        # Scaling runbook
        runbooks.append(
            self._generate_scaling_runbook(build_characteristics, tech_stack)
        )

        # Incident response runbook
        runbooks.append(
            self._generate_incident_response_runbook(build_characteristics, tech_stack)
        )

        return runbooks

    def _generate_deployment_runbook(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate deployment runbook."""
        content = f"""# Deployment Runbook: {build_characteristics.project_name}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Category**: Deployment Operations

---

## Pre-Deployment Checklist

- [ ] All tests passing in CI/CD pipeline
- [ ] Code review approved
- [ ] Environment variables configured
- [ ] Database migrations prepared (if applicable)
- [ ] Rollback plan documented

## Deployment Steps

### 1. Prepare Deployment

```bash
# Pull latest code
git pull origin main

# Verify build
{self._get_build_command(build_characteristics)}
```

### 2. Deploy to Staging

```bash
# Deploy to staging environment
./deploy.sh staging

# Run smoke tests
./scripts/smoke-test.sh staging
```

### 3. Deploy to Production

```bash
# Deploy to production
./deploy.sh production

# Verify deployment
./scripts/health-check.sh production
```

### 4. Post-Deployment Verification

- [ ] Application responding on health endpoint
- [ ] Key features functional
- [ ] No error spikes in logs
- [ ] Metrics within expected ranges

## Rollback Procedure

If issues are detected:

```bash
# Rollback to previous version
./scripts/rollback.sh production

# Verify rollback
./scripts/health-check.sh production
```

## Contacts

- **On-call Engineer**: See PagerDuty schedule
- **Platform Team**: #platform-support
- **Security Team**: #security-oncall
"""
        return PostBuildArtifact(
            artifact_type=ArtifactType.RUNBOOK,
            name="RUNBOOK_DEPLOYMENT",
            content=content,
            file_extension="md",
            metadata={"category": RunbookCategory.DEPLOYMENT.value},
        )

    def _generate_troubleshooting_runbook(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate troubleshooting runbook."""
        content = f"""# Troubleshooting Runbook: {build_characteristics.project_name}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Category**: Troubleshooting

---

## Common Issues

### 1. Application Not Starting

**Symptoms**:
- Container exits immediately
- Health check failing
- Port not responding

**Diagnosis**:
```bash
# Check container logs
docker logs <container_id>

# Check application logs
kubectl logs deployment/{build_characteristics.project_name.lower().replace(' ', '-')}

# Check environment variables
kubectl describe pod <pod_name>
```

**Resolution**:
1. Verify environment variables are set correctly
2. Check if required services (database, cache) are accessible
3. Verify port configuration matches deployment

### 2. High Memory Usage

**Symptoms**:
- OOM kills
- Slow response times
- Memory metrics climbing

**Diagnosis**:
```bash
# Check memory usage
kubectl top pods

# Get detailed metrics
kubectl describe pod <pod_name>
```

**Resolution**:
1. Check for memory leaks in application code
2. Increase memory limits if legitimate usage
3. Review recent code changes for memory-intensive operations

### 3. Database Connection Issues

**Symptoms**:
- Connection timeout errors
- "Too many connections" errors
- Slow queries

**Diagnosis**:
```bash
# Check database connectivity
nc -zv <db_host> <db_port>

# Check connection pool status
# (Application-specific command)
```

**Resolution**:
1. Verify database credentials
2. Check database server health
3. Review connection pool settings

### 4. High Latency

**Symptoms**:
- Slow API responses
- Request timeouts
- User complaints

**Diagnosis**:
```bash
# Check response times
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:{build_characteristics.port}/health

# Check external dependencies
# traceroute, ping, etc.
```

**Resolution**:
1. Identify slow endpoints using APM
2. Check database query performance
3. Review external API response times
4. Check for resource contention

## Escalation Path

1. **L1**: On-call engineer (first response)
2. **L2**: Senior engineer / Tech lead
3. **L3**: Platform team / Architecture team
"""
        return PostBuildArtifact(
            artifact_type=ArtifactType.RUNBOOK,
            name="RUNBOOK_TROUBLESHOOTING",
            content=content,
            file_extension="md",
            metadata={"category": RunbookCategory.TROUBLESHOOTING.value},
        )

    def _generate_scaling_runbook(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate scaling runbook."""
        content = f"""# Scaling Runbook: {build_characteristics.project_name}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Category**: Scaling Operations

---

## Horizontal Scaling

### Manual Scaling

```bash
# Scale up replicas
kubectl scale deployment/{build_characteristics.project_name.lower().replace(' ', '-')} --replicas=5

# Verify scaling
kubectl get pods -l app={build_characteristics.project_name.lower().replace(' ', '-')}
```

### Auto-Scaling Configuration

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {build_characteristics.project_name.lower().replace(' ', '-')}-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {build_characteristics.project_name.lower().replace(' ', '-')}
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## Vertical Scaling

### Increase Resource Limits

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "200m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

## Scaling Decision Matrix

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU > 70% | Sustained 5 min | Scale up horizontally |
| Memory > 80% | Sustained 5 min | Scale up vertically or horizontally |
| Request latency > 500ms | P95 | Investigate and scale if needed |
| Error rate > 1% | 5 min window | Investigate before scaling |

## Pre-Scaling Checklist

- [ ] Verify database can handle additional connections
- [ ] Check load balancer configuration
- [ ] Ensure sufficient cluster resources
- [ ] Review cost implications
"""
        return PostBuildArtifact(
            artifact_type=ArtifactType.RUNBOOK,
            name="RUNBOOK_SCALING",
            content=content,
            file_extension="md",
            metadata={"category": RunbookCategory.SCALING.value},
        )

    def _generate_incident_response_runbook(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate incident response runbook."""
        content = f"""# Incident Response Runbook: {build_characteristics.project_name}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Category**: Incident Response

---

## Incident Severity Levels

| Level | Description | Response Time | Example |
|-------|-------------|---------------|---------|
| SEV1 | Complete outage | 15 min | Service down, data loss |
| SEV2 | Major degradation | 30 min | >50% of requests failing |
| SEV3 | Minor degradation | 2 hours | Elevated latency, partial feature outage |
| SEV4 | Low impact | 24 hours | Non-critical bug, cosmetic issue |

## Incident Response Process

### 1. Acknowledge & Assess (First 5 minutes)

- [ ] Acknowledge alert in PagerDuty
- [ ] Join incident channel
- [ ] Assess severity level
- [ ] Communicate initial status

### 2. Triage & Diagnose (Next 10 minutes)

```bash
# Quick health check
curl -s http://localhost:{build_characteristics.port}/health | jq

# Check recent deployments
kubectl rollout history deployment/{build_characteristics.project_name.lower().replace(' ', '-')}

# Check error logs
kubectl logs -l app={build_characteristics.project_name.lower().replace(' ', '-')} --tail=100 | grep -i error
```

### 3. Mitigate (As soon as possible)

**Option A: Rollback**
```bash
kubectl rollout undo deployment/{build_characteristics.project_name.lower().replace(' ', '-')}
```

**Option B: Scale Up**
```bash
kubectl scale deployment/{build_characteristics.project_name.lower().replace(' ', '-')} --replicas=10
```

**Option C: Feature Flag Disable**
```bash
# Disable problematic feature via feature flag system
```

### 4. Resolve & Verify

- [ ] Confirm mitigation is effective
- [ ] Monitor for 15 minutes
- [ ] Update stakeholders
- [ ] Close incident if stable

### 5. Post-Incident

- [ ] Schedule post-mortem within 48 hours
- [ ] Document timeline
- [ ] Identify root cause
- [ ] Create action items

## Communication Templates

### Initial Status Update
> **[INCIDENT] {build_characteristics.project_name}**
>
> We are investigating an issue with [service]. Impact: [description].
> We will provide an update in 15 minutes.

### Resolution Update
> **[RESOLVED] {build_characteristics.project_name}**
>
> The issue has been resolved. Root cause: [description].
> A post-mortem will be scheduled.

## Emergency Contacts

- **On-call Primary**: See PagerDuty
- **On-call Secondary**: See PagerDuty
- **Engineering Manager**: @engineering-manager
- **VP Engineering**: @vp-engineering (SEV1 only)
"""
        return PostBuildArtifact(
            artifact_type=ArtifactType.RUNBOOK,
            name="RUNBOOK_INCIDENT_RESPONSE",
            content=content,
            file_extension="md",
            metadata={"category": RunbookCategory.INCIDENT_RESPONSE.value},
        )

    def generate_monitoring_templates(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate monitoring configuration templates.

        Args:
            build_characteristics: Build characteristics
            tech_stack: Tech stack configuration

        Returns:
            Monitoring configuration artifact
        """
        logger.info("[PostBuildArtifactGenerator] Generating monitoring templates")

        content = f"""# Monitoring Configuration: {build_characteristics.project_name}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Prometheus Configuration

### scrape_config.yml

```yaml
scrape_configs:
  - job_name: '{build_characteristics.project_name.lower().replace(' ', '-')}'
    static_configs:
      - targets: ['localhost:{build_characteristics.port}']
    metrics_path: '/metrics'
    scrape_interval: 15s

    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
        regex: '(.+):.+'
        replacement: '$1'
```

## Key Metrics to Monitor

### Application Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | Request latency |
| `http_requests_in_flight` | Gauge | Active requests |
| `errors_total` | Counter | Error count by type |

### Infrastructure Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `container_cpu_usage_seconds_total` | Counter | CPU usage |
| `container_memory_usage_bytes` | Gauge | Memory usage |
| `container_network_receive_bytes_total` | Counter | Network in |
| `container_network_transmit_bytes_total` | Counter | Network out |

## Grafana Dashboard JSON

```json
{{
  "dashboard": {{
    "title": "{build_characteristics.project_name} Overview",
    "panels": [
      {{
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {{
            "expr": "rate(http_requests_total[5m])"
          }}
        ]
      }},
      {{
        "title": "Error Rate",
        "type": "graph",
        "targets": [
          {{
            "expr": "rate(errors_total[5m])"
          }}
        ]
      }},
      {{
        "title": "Response Time (P95)",
        "type": "graph",
        "targets": [
          {{
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
          }}
        ]
      }},
      {{
        "title": "CPU Usage",
        "type": "graph",
        "targets": [
          {{
            "expr": "rate(container_cpu_usage_seconds_total[5m])"
          }}
        ]
      }},
      {{
        "title": "Memory Usage",
        "type": "graph",
        "targets": [
          {{
            "expr": "container_memory_usage_bytes"
          }}
        ]
      }}
    ]
  }}
}}
```

## Application Instrumentation

### Python (prometheus_client)

```python
from prometheus_client import Counter, Histogram, generate_latest
from flask import Response

REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype='text/plain')
```

### Node.js (prom-client)

```javascript
const client = require('prom-client');

const requestCounter = new client.Counter({{
  name: 'http_requests_total',
  help: 'Total HTTP requests',
  labelNames: ['method', 'path', 'status']
}});

const requestDuration = new client.Histogram({{
  name: 'http_request_duration_seconds',
  help: 'HTTP request latency',
  labelNames: ['method', 'path'],
  buckets: [0.1, 0.5, 1, 2, 5]
}});

app.get('/metrics', async (req, res) => {{
  res.set('Content-Type', client.register.contentType);
  res.end(await client.register.metrics());
}});
```

## Health Check Endpoints

### Recommended Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health` | Basic health check | `{{"status": "healthy"}}` |
| `/health/live` | Liveness probe | HTTP 200 |
| `/health/ready` | Readiness probe | HTTP 200 |
| `/metrics` | Prometheus metrics | Prometheus format |
"""
        return PostBuildArtifact(
            artifact_type=ArtifactType.MONITORING,
            name="MONITORING_CONFIG",
            content=content,
            file_extension="md",
            metadata={
                "project_name": build_characteristics.project_name,
                "port": build_characteristics.port,
            },
        )

    def generate_alerting_rules(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate alerting rules configuration.

        Args:
            build_characteristics: Build characteristics
            tech_stack: Tech stack configuration

        Returns:
            Alerting rules artifact
        """
        logger.info("[PostBuildArtifactGenerator] Generating alerting rules")

        app_name = build_characteristics.project_name.lower().replace(" ", "-")
        content = f"""# Alerting Rules: {build_characteristics.project_name}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Prometheus Alert Rules

### alerts.yml

```yaml
groups:
  - name: {app_name}-alerts
    rules:
      # High Error Rate
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{{status=~"5.."}}[5m])) /
          sum(rate(http_requests_total[5m])) > 0.01
        for: 5m
        labels:
          severity: critical
          service: {app_name}
        annotations:
          summary: "High error rate on {build_characteristics.project_name}"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 1%)"

      # High Latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 1
        for: 5m
        labels:
          severity: warning
          service: {app_name}
        annotations:
          summary: "High latency on {build_characteristics.project_name}"
          description: "P95 latency is {{ $value | humanizeDuration }} (threshold: 1s)"

      # Service Down
      - alert: ServiceDown
        expr: up{{job="{app_name}"}} == 0
        for: 1m
        labels:
          severity: critical
          service: {app_name}
        annotations:
          summary: "{build_characteristics.project_name} is down"
          description: "Service has been down for more than 1 minute"

      # High Memory Usage
      - alert: HighMemoryUsage
        expr: |
          container_memory_usage_bytes{{container="{app_name}"}} /
          container_spec_memory_limit_bytes{{container="{app_name}"}} > 0.9
        for: 5m
        labels:
          severity: warning
          service: {app_name}
        annotations:
          summary: "High memory usage on {build_characteristics.project_name}"
          description: "Memory usage is {{ $value | humanizePercentage }} of limit"

      # High CPU Usage
      - alert: HighCPUUsage
        expr: |
          rate(container_cpu_usage_seconds_total{{container="{app_name}"}}[5m]) > 0.9
        for: 5m
        labels:
          severity: warning
          service: {app_name}
        annotations:
          summary: "High CPU usage on {build_characteristics.project_name}"
          description: "CPU usage is {{ $value | humanizePercentage }}"

      # Pod Restart Loop
      - alert: PodRestartLoop
        expr: |
          increase(kube_pod_container_status_restarts_total{{container="{app_name}"}}[1h]) > 5
        for: 5m
        labels:
          severity: warning
          service: {app_name}
        annotations:
          summary: "Pod restart loop detected"
          description: "Pod has restarted {{ $value }} times in the last hour"

      # Deployment Replica Mismatch
      - alert: DeploymentReplicaMismatch
        expr: |
          kube_deployment_spec_replicas{{deployment="{app_name}"}} !=
          kube_deployment_status_replicas_available{{deployment="{app_name}"}}
        for: 10m
        labels:
          severity: warning
          service: {app_name}
        annotations:
          summary: "Deployment replica mismatch"
          description: "Deployment does not have expected number of replicas"
```

## PagerDuty Integration

### Alertmanager Configuration

```yaml
global:
  pagerduty_url: 'https://events.pagerduty.com/v2/enqueue'

route:
  receiver: 'pagerduty-critical'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty-critical'
    - match:
        severity: warning
      receiver: 'pagerduty-warning'

receivers:
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: '<your-pagerduty-integration-key>'
        severity: critical

  - name: 'pagerduty-warning'
    pagerduty_configs:
      - service_key: '<your-pagerduty-integration-key>'
        severity: warning
```

## Slack Integration

```yaml
receivers:
  - name: 'slack-notifications'
    slack_configs:
      - api_url: '<your-slack-webhook-url>'
        channel: '#alerts-{app_name}'
        title: '{{ .Status | toUpper }}: {{ .CommonAnnotations.summary }}'
        text: '{{ .CommonAnnotations.description }}'
```

## Alert Severity Matrix

| Severity | Response Time | Escalation | Notification |
|----------|---------------|------------|--------------|
| Critical | 15 min | Immediate | PagerDuty + Slack |
| Warning | 30 min | After 1 hour | Slack only |
| Info | Next business day | None | Slack only |
"""
        return PostBuildArtifact(
            artifact_type=ArtifactType.ALERTING,
            name="ALERTING_RULES",
            content=content,
            file_extension="md",
            metadata={"app_name": app_name},
        )

    def generate_docker_config(
        self,
        build_characteristics: BuildCharacteristics,
        tech_stack: Dict[str, Any],
    ) -> PostBuildArtifact:
        """Generate Docker configuration for containerized deployment.

        Args:
            build_characteristics: Build characteristics
            tech_stack: Tech stack configuration

        Returns:
            Docker configuration artifact
        """
        logger.info("[PostBuildArtifactGenerator] Generating Docker configuration")

        dockerfile = self._generate_dockerfile(build_characteristics)
        docker_compose = self._generate_docker_compose(build_characteristics)

        content = f"""# Docker Configuration: {build_characteristics.project_name}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Dockerfile

```dockerfile
{dockerfile}
```

## docker-compose.yml

```yaml
{docker_compose}
```

## .dockerignore

```
# Dependencies
node_modules
.venv
venv
__pycache__
*.pyc

# Build artifacts
dist
build
*.egg-info

# Version control
.git
.gitignore

# IDE
.idea
.vscode

# Environment
.env
.env.local
*.env

# Test and coverage
.pytest_cache
.coverage
coverage
htmlcov

# Logs
*.log
logs
```

## Build Commands

```bash
# Build image
docker build -t {build_characteristics.project_name.lower().replace(' ', '-')}:latest .

# Run container
docker run -d -p {build_characteristics.port}:{build_characteristics.port} \\
  --name {build_characteristics.project_name.lower().replace(' ', '-')} \\
  {build_characteristics.project_name.lower().replace(' ', '-')}:latest

# Using docker-compose
docker-compose up -d

# View logs
docker-compose logs -f
```
"""
        return PostBuildArtifact(
            artifact_type=ArtifactType.DOCKER,
            name="DOCKER_CONFIG",
            content=content,
            file_extension="md",
            metadata={
                "language": build_characteristics.language,
                "port": build_characteristics.port,
            },
        )

    def _generate_dockerfile(self, build_characteristics: BuildCharacteristics) -> str:
        """Generate Dockerfile content based on build characteristics."""
        if build_characteristics.language == "node":
            return f"""# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package*.json ./

ENV NODE_ENV=production
ENV PORT={build_characteristics.port}
EXPOSE {build_characteristics.port}

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
  CMD wget --no-verbose --tries=1 --spider http://localhost:{build_characteristics.port}/health || exit 1

CMD ["node", "dist/index.js"]"""

        elif build_characteristics.language == "python":
            return f"""# Build stage
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PORT={build_characteristics.port}
EXPOSE {build_characteristics.port}

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
  CMD python -c "import http.client; conn = http.client.HTTPConnection('localhost', {build_characteristics.port}); conn.request('GET', '/health'); exit(0 if conn.getresponse().status == 200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:{build_characteristics.port}", "app:app"]"""

        else:
            return f"""FROM alpine:latest
WORKDIR /app
COPY . .

ENV PORT={build_characteristics.port}
EXPOSE {build_characteristics.port}

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
  CMD wget --no-verbose --tries=1 --spider http://localhost:{build_characteristics.port}/health || exit 1

CMD ["./start.sh"]"""

    def _generate_docker_compose(
        self, build_characteristics: BuildCharacteristics
    ) -> str:
        """Generate docker-compose.yml content."""
        app_name = build_characteristics.project_name.lower().replace(" ", "-")
        return f"""version: '3.8'

services:
  {app_name}:
    build: .
    ports:
      - "{build_characteristics.port}:{build_characteristics.port}"
    environment:
      - NODE_ENV=production
      - PORT={build_characteristics.port}
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:{build_characteristics.port}/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    depends_on:
      - {app_name}

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - prometheus"""

    def _get_build_command(self, build_characteristics: BuildCharacteristics) -> str:
        """Get build command based on language."""
        commands = {
            "node": "npm ci && npm run build",
            "python": "pip install -e . && pytest",
            "go": "go build ./...",
            "rust": "cargo build --release",
        }
        return commands.get(build_characteristics.language, "./build.sh")

    def get_generated_artifacts(self) -> List[PostBuildArtifact]:
        """Get list of previously generated artifacts.

        Returns:
            List of generated PostBuildArtifact objects
        """
        return self._generated_artifacts

    def export_artifacts_to_markdown(
        self, output_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """Export all generated artifacts to markdown files.

        Args:
            output_dir: Optional output directory path

        Returns:
            Dictionary mapping artifact names to file paths
        """
        file_paths = {}
        for artifact in self._generated_artifacts:
            filename = f"{artifact.name}.{artifact.file_extension}"
            file_paths[artifact.name] = filename
            logger.info(f"[PostBuildArtifactGenerator] Would write: {filename}")

        return file_paths


def capture_build_characteristics(
    project_name: str,
    tech_stack: Dict[str, Any],
    build_result: Optional[Dict[str, Any]] = None,
) -> BuildCharacteristics:
    """Capture characteristics from a successful build.

    Args:
        project_name: Name of the project
        tech_stack: Technology stack configuration
        build_result: Optional build result data

    Returns:
        BuildCharacteristics instance
    """
    build_result = build_result or {}

    # Detect language from tech stack
    stack_name = tech_stack.get("name", "").lower()
    category = tech_stack.get("category", "").lower()
    combined = f"{stack_name} {category}"

    language = "node"  # Default
    # Check for node/javascript first to avoid "java" matching in "javascript"
    if any(
        lang in combined
        for lang in ["node", "next.js", "react", "vue", "angular", "express", "javascript", "typescript"]
    ):
        language = "node"
    elif any(lang in combined for lang in ["python", "django", "fastapi", "flask"]):
        language = "python"
    elif any(lang in combined for lang in ["go", "golang"]):
        language = "go"
    elif any(lang in combined for lang in ["rust"]):
        language = "rust"
    elif any(lang in combined for lang in ["ruby", "rails"]):
        language = "ruby"
    elif any(lang in combined for lang in ["java", "spring"]):
        # Ensure we don't match "javascript" when looking for "java"
        if "javascript" not in combined and "java" in combined:
            language = "java"

    # Detect framework
    framework = "unknown"
    framework_mapping = {
        "next.js": "next",
        "react": "react",
        "vue": "vue",
        "angular": "angular",
        "django": "django",
        "fastapi": "fastapi",
        "flask": "flask",
        "express": "express",
        "spring": "spring",
    }
    for key, value in framework_mapping.items():
        if key in combined:
            framework = value
            break

    # Detect build tool
    build_tool = "npm" if language == "node" else "pip" if language == "python" else "unknown"

    # Detect database and API
    has_database = any(
        db in combined
        for db in ["postgres", "mysql", "mongo", "redis", "supabase", "firebase", "database"]
    )
    has_api = any(api in combined for api in ["api", "rest", "graphql", "backend", "server"])

    # Detect containerization
    is_containerized = any(
        c in combined for c in ["docker", "kubernetes", "k8s", "container"]
    )

    # Default port based on language
    port_mapping = {
        "node": 3000,
        "python": 8000,
        "go": 8080,
        "rust": 8080,
        "ruby": 3000,
        "java": 8080,
    }
    port = port_mapping.get(language, 3000)

    return BuildCharacteristics(
        project_name=project_name,
        tech_stack=tech_stack,
        language=language,
        framework=framework,
        build_tool=build_tool,
        has_database=has_database,
        has_api=has_api,
        is_containerized=is_containerized,
        port=port,
        build_duration_seconds=build_result.get("duration_seconds", 0.0),
        test_coverage_percent=build_result.get("test_coverage_percent"),
    )


def generate_post_build_artifacts(
    project_name: str,
    tech_stack: Dict[str, Any],
    build_result: Optional[Dict[str, Any]] = None,
) -> List[PostBuildArtifact]:
    """Convenience function to generate post-build artifacts.

    Args:
        project_name: Name of the project
        tech_stack: Technology stack configuration
        build_result: Optional build result data

    Returns:
        List of generated PostBuildArtifact objects
    """
    characteristics = capture_build_characteristics(
        project_name=project_name,
        tech_stack=tech_stack,
        build_result=build_result,
    )

    generator = PostBuildArtifactGenerator()
    return generator.generate_all_artifacts(characteristics, tech_stack)
