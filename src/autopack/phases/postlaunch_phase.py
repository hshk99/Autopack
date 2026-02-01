"""Postlaunch Phase Implementation for Autonomous Build System.

This module implements the POSTLAUNCH phase type, which enables the autonomous
executor to generate operational runbooks, incident response playbooks, SLA/SLO
definitions, and monitoring/alerting configurations.

Postlaunch phases are used when:
- Operational runbooks are needed for production support
- Incident response procedures must be documented
- SLA/SLO definitions are required
- Monitoring and alerting setup is needed
- Scaling and maintenance guides are required
- On-call rotation and escalation paths need definition

Design Principles:
- Postlaunch phases leverage deployment and monetization phase outputs
- Runbooks are practical and executable by support team
- SLA/SLO definitions are measurable and achievable
- Monitoring setup is automated where possible
- Clear escalation paths for incident response
- Results are cached and reusable across phases
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PostlaunchStatus(Enum):
    """Status of a postlaunch phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PostlaunchConfig:
    """Configuration for a postlaunch phase."""

    runbook_types: List[str] = field(
        default_factory=lambda: ["incident_response", "maintenance", "scaling"]
    )
    define_sla: bool = True
    uptime_target: float = 99.9  # 99.9% uptime
    response_time_target_ms: int = 500
    error_rate_target: float = 0.01  # 1%
    monitoring_platform: str = "prometheus"
    alert_channels: List[str] = field(default_factory=lambda: ["email", "slack"])
    enable_oncall_rotation: bool = True
    save_to_history: bool = True
    max_duration_minutes: Optional[int] = None


@dataclass
class PostlaunchInput:
    """Input data for postlaunch phase."""

    product_name: str
    deployment_info: Optional[Dict[str, Any]] = None  # From deploy phase
    monetization_info: Optional[Dict[str, Any]] = None  # From monetization phase


@dataclass
class PostlaunchOutput:
    """Output from postlaunch phase."""

    runbook_dir_path: Optional[str] = None
    incident_response_path: Optional[str] = None
    sla_document_path: Optional[str] = None
    monitoring_setup_path: Optional[str] = None
    sla_definitions: List[Dict[str, Any]] = field(default_factory=list)
    alert_rules: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PostlaunchPhase:
    """Represents a postlaunch phase with its configuration and state."""

    phase_id: str
    description: str
    config: PostlaunchConfig
    input_data: Optional[PostlaunchInput] = None
    status: PostlaunchStatus = PostlaunchStatus.PENDING
    output: Optional[PostlaunchOutput] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation."""
        output_dict = None
        if self.output:
            output_dict = {
                "runbook_dir_path": self.output.runbook_dir_path,
                "incident_response_path": self.output.incident_response_path,
                "sla_document_path": self.output.sla_document_path,
                "monitoring_setup_path": self.output.monitoring_setup_path,
                "sla_definitions": self.output.sla_definitions,
                "alert_rules": self.output.alert_rules,
                "warnings": self.output.warnings,
            }

        input_dict = None
        if self.input_data:
            input_dict = {
                "product_name": self.input_data.product_name,
                "deployment_info": self.input_data.deployment_info,
                "monetization_info": self.input_data.monetization_info,
            }

        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "runbook_types": self.config.runbook_types,
                "define_sla": self.config.define_sla,
                "uptime_target": self.config.uptime_target,
                "response_time_target_ms": self.config.response_time_target_ms,
                "error_rate_target": self.config.error_rate_target,
                "monitoring_platform": self.config.monitoring_platform,
                "alert_channels": self.config.alert_channels,
                "enable_oncall_rotation": self.config.enable_oncall_rotation,
                "save_to_history": self.config.save_to_history,
                "max_duration_minutes": self.config.max_duration_minutes,
            },
            "input_data": input_dict,
            "output": output_dict,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class PostlaunchPhaseExecutor:
    """Executor for postlaunch phases."""

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

    def execute(self, phase: PostlaunchPhase) -> PostlaunchPhase:
        """Execute a postlaunch phase.

        Args:
            phase: The phase to execute

        Returns:
            The updated phase with results
        """
        logger.info(f"Executing postlaunch phase: {phase.phase_id}")

        phase.status = PostlaunchStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        phase.output = PostlaunchOutput()
        phase.error = None

        try:
            # Validate input
            if not phase.input_data:
                phase.status = PostlaunchStatus.FAILED
                phase.error = "No input data provided for postlaunch phase"
                return phase

            # Generate postlaunch artifacts
            self._generate_postlaunch_artifacts(phase)

            # Mark as completed if not already failed
            if phase.status == PostlaunchStatus.IN_PROGRESS:
                phase.status = PostlaunchStatus.COMPLETED

            # Save to history if configured
            if phase.config.save_to_history and self.build_history_path:
                self._save_to_history(phase)

        except Exception as e:
            logger.error(f"Phase execution failed: {e}", exc_info=True)
            phase.status = PostlaunchStatus.FAILED
            phase.error = str(e)

        finally:
            phase.completed_at = datetime.now()

        return phase

    def _generate_postlaunch_artifacts(self, phase: PostlaunchPhase) -> None:
        """Generate postlaunch artifacts.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        # Create runbooks directory
        runbook_dir = self.workspace_path / "runbooks"
        runbook_dir.mkdir(parents=True, exist_ok=True)
        phase.output.runbook_dir_path = str(runbook_dir)

        # Generate incident response runbooks
        if "incident_response" in phase.config.runbook_types:
            self._generate_incident_response_runbook(phase)

        # Generate maintenance runbooks
        if "maintenance" in phase.config.runbook_types:
            self._generate_maintenance_runbook(phase)

        # Generate scaling runbooks
        if "scaling" in phase.config.runbook_types:
            self._generate_scaling_runbook(phase)

        # Generate SLA/SLO document
        if phase.config.define_sla:
            self._generate_sla_document(phase)

        # Generate monitoring setup
        self._generate_monitoring_setup(phase)

    def _generate_incident_response_runbook(self, phase: PostlaunchPhase) -> None:
        """Generate incident response runbook.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        product_name = phase.input_data.product_name
        runbook_content = f"""# Incident Response Runbook for {product_name}

## Overview
This runbook provides procedures for responding to production incidents.
All times are in UTC unless otherwise specified.

## Incident Severity Levels

### Severity 1 (Critical)
- **Impact**: Service is completely unavailable or data is at risk
- **Response Time**: Within 15 minutes
- **Escalation**: Immediate escalation to Engineering Lead
- **Communication**: Update status page every 15 minutes

### Severity 2 (High)
- **Impact**: Service is severely degraded or affecting multiple users
- **Response Time**: Within 1 hour
- **Escalation**: Within 30 minutes if not resolved
- **Communication**: Update status page hourly

### Severity 3 (Medium)
- **Impact**: Limited functionality affecting some users
- **Response Time**: Within 4 hours
- **Escalation**: Daily standup unless resolved
- **Communication**: Update status page daily

### Severity 4 (Low)
- **Impact**: Cosmetic issues or minor bugs
- **Response Time**: Next business day
- **Escalation**: Via normal ticket system
- **Communication**: No status page update needed

## Response Procedures

### Step 1: Acknowledge and Assess (0-5 minutes)
1. On-call engineer acknowledges alert within 5 minutes
2. Review alert details in monitoring system
3. Determine severity level
4. Create incident ticket with timestamp and severity
5. Open war room (Slack channel or Zoom call)
6. Notify stakeholders if Severity 1-2

### Step 2: Investigate (5-15 minutes)
1. Check application logs for errors
   ```bash
   kubectl logs -f deployment/{product_name} --all-containers=true
   ```
2. Check metrics dashboard (Grafana/Prometheus)
3. Check recent deployments or infrastructure changes
4. Check database connectivity and performance
5. Document findings in incident ticket

### Step 3: Mitigate (15-45 minutes)
1. **If application error**:
   - Review error stack traces
   - Check for deployment issues
   - Consider rollback of recent changes
   - Restart affected services if needed

2. **If database issue**:
   - Check connection pool utilization
   - Check long-running queries
   - Review recent schema changes
   - Consider scaling if needed

3. **If infrastructure issue**:
   - Check node/pod status
   - Check resource utilization
   - Check networking connectivity
   - Scale up if capacity issue

4. **If external service issue**:
   - Check status page of external service
   - Implement fallback/caching if available
   - Route traffic to failover system

### Step 4: Communicate (Ongoing)
- Provide updates in war room every 15 minutes
- Post status updates to #incidents channel
- Update status page (incident.example.com)
- Notify affected customers if impact > 15 minutes

### Step 5: Resolve (Until stable)
- Monitor metrics for stability (at least 15 minutes)
- Confirm fix doesn't introduce new issues
- Deploy permanent fix if needed
- Update status page with resolution
- Close war room

### Step 6: Post-Incident (Within 24 hours)
- Write incident summary
- Document timeline
- Identify root cause
- Document action items
- Schedule post-mortem meeting (if Severity 1)

## Escalation Matrix

| Severity | On-Call | Lead | Manager | VP |
|----------|---------|------|---------|-----|
| 1        | Page    | Page | Page    | Notify |
| 2        | Page    | Notify | Notify | - |
| 3        | Create ticket | Notify if unresolved >4h | - | - |
| 4        | Create ticket | - | - | - |

## Contact Information
- On-Call Engineer: Pagerduty (pagerduty.com)
- Engineering Lead: {phase.input_data.product_name} Slack channel
- Database Admin: @db-team on Slack
- Ops Manager: ops-manager@example.com

## Tools and Access

- **Monitoring**: https://grafana.example.com
- **Logs**: https://kibana.example.com
- **Database**: Use AWS Console (SSO required)
- **Deployments**: kubectl configured with access to prod cluster
- **Status Page**: https://status.example.com (update via API)

## Common Issues and Solutions

### Issue: Service timeout
```
Diagnosis: Check response times in metrics
Solution:
1. Scale up instances: kubectl scale deployment/{product_name} --replicas=5
2. Check for slow database queries: SELECT * FROM slow_log
3. Clear cache if applicable: redis-cli FLUSHALL
```

### Issue: Database connection pool exhausted
```
Diagnosis: Check database connection count
Solution:
1. Restart connection pool service
2. Check for long-running connections: SHOW PROCESSLIST
3. Increase pool size if needed
```

### Issue: Memory leak
```
Diagnosis: Check memory usage trend
Solution:
1. Restart service: kubectl rollout restart deployment/{product_name}
2. Check for memory leaks in recent changes
3. Consider rolling back recent release
```

## Testing Incident Response

Schedule monthly incident response drills:
1. Declare a test incident
2. Page on-call engineer
3. Walk through response procedures
4. Evaluate response and communication
5. Document lessons learned
"""

        runbook_dir = self.workspace_path / "runbooks"
        runbook_dir.mkdir(parents=True, exist_ok=True)
        incident_path = runbook_dir / "INCIDENT_RESPONSE.md"
        incident_path.write_text(runbook_content, encoding="utf-8")

        phase.output.incident_response_path = str(incident_path)
        logger.info(f"Generated incident response runbook: {incident_path}")

    def _generate_maintenance_runbook(self, phase: PostlaunchPhase) -> None:
        """Generate maintenance runbook.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        product_name = phase.input_data.product_name
        runbook_content = f"""# Maintenance Runbook for {product_name}

## Regular Maintenance Tasks

### Daily Checks (Every morning, 9 AM UTC)
- [ ] Check application health: curl https://api.example.com/health
- [ ] Review error rate: Check error rate < 0.01% in Grafana
- [ ] Check disk space: kubectl exec deployment -c ls -h /data
- [ ] Review database size
- [ ] Verify all deployments are healthy: kubectl get deployments

### Weekly Checks (Every Monday)
- [ ] Backup verification: Check latest backup timestamp
- [ ] Review slow queries: Analyze database slow query log
- [ ] Check certificate expiry: openssl x509 -enddate -noout -in cert.pem
- [ ] Review access logs for anomalies
- [ ] Check third-party service integrations

### Monthly Checks (First day of month)
- [ ] Security scan: Run vulnerability scanner
- [ ] Dependency updates: Check for outdated packages
- [ ] Capacity planning: Review growth trends
- [ ] Database optimization: Run ANALYZE and VACUUM (if PostgreSQL)
- [ ] Review and rotate secrets if needed

## Backup and Recovery

### Database Backup
```bash
# Create backup
kubectl exec deployment -- pg_dump -U postgres dbname > backup.sql

# Verify backup
pg_restore -i -d postgres backup.sql --list

# Restore from backup
kubectl exec deployment -- psql -U postgres < backup.sql
```

### Point-in-Time Recovery
```bash
# List recovery points
aws rds describe-db-recovery-points --db-instance-identifier prod

# Restore to specific point in time
aws rds restore-db-instance-from-db-cluster-snapshot \\
  --db-instance-identifier {phase.input_data.product_name}-restore \\
  --db-cluster-snapshot-identifier {phase.input_data.product_name}-snapshot
```

## Rolling Updates

### Zero-Downtime Deployment
```bash
# 1. Create new deployment with new version
kubectl set image deployment/{product_name} \\
  app={product_name}:v2.0

# 2. Monitor rollout progress
kubectl rollout status deployment/{product_name}

# 3. If issues occur, rollback
kubectl rollout undo deployment/{product_name}

# 4. Verify new version
curl https://api.example.com/version
```

## Database Maintenance

### Regular Maintenance
```sql
-- PostgreSQL: Analyze query performance
ANALYZE;

-- PostgreSQL: Reclaim unused space
VACUUM FULL;

-- MySQL: Optimize tables
OPTIMIZE TABLE table_name;

-- Remove old logs (keep 7 days)
DELETE FROM logs WHERE created_at < NOW() - INTERVAL 7 DAY;
```

### Scaling Database
```bash
# If database disk approaching capacity:
# 1. Add more storage
aws rds modify-db-instance --db-instance-identifier prod \\
  --allocated-storage 1000 --apply-immediately

# 2. If CPU-bound, increase instance type
aws rds modify-db-instance --db-instance-identifier prod \\
  --db-instance-class db.r5.2xlarge --apply-immediately

# 3. Consider adding read replicas for scaling reads
aws rds create-db-instance-read-replica \\
  --db-instance-identifier prod-read-replica
```

## Troubleshooting Common Issues

### Issue: High Memory Usage
1. Check memory-intensive processes: top -b -n 1 | sort -k6 -nr
2. Check for memory leaks: valgrind or Node.js heap snapshot
3. Clear caches if applicable: redis-cli FLUSHALL
4. Restart service if needed

### Issue: Slow Database
1. Check slow query log
2. Analyze query execution plan: EXPLAIN ANALYZE
3. Add missing indexes: CREATE INDEX idx_name ON table(column)
4. Update statistics: ANALYZE table_name

### Issue: Disk Space Filling
1. Check largest directories: du -sh /*
2. Remove old logs: find /var/log -type f -mtime +30 -delete
3. Clear temporary files: rm -rf /tmp/*
4. Expand volume if needed
"""

        runbook_dir = self.workspace_path / "runbooks"
        runbook_dir.mkdir(parents=True, exist_ok=True)
        maintenance_path = runbook_dir / "MAINTENANCE.md"
        maintenance_path.write_text(runbook_content, encoding="utf-8")

        logger.info(f"Generated maintenance runbook: {maintenance_path}")

    def _generate_scaling_runbook(self, phase: PostlaunchPhase) -> None:
        """Generate scaling runbook.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        product_name = phase.input_data.product_name
        runbook_content = f"""# Scaling Runbook for {product_name}

## Scaling Decision Matrix

| Metric | Threshold | Action | Timeline |
|--------|-----------|--------|----------|
| CPU usage | >70% | Increase replicas | Immediately |
| Memory usage | >80% | Increase instance size | Within 1 hour |
| Database connections | >80% pool | Scale database | Within 4 hours |
| Request latency | >500ms p99 | Scale horizontally | Immediately |
| Disk usage | >80% | Expand volume | Within 1 hour |

## Horizontal Scaling (Add more instances)

### Add Application Instances
```bash
# Check current replicas
kubectl get deployment {product_name}

# Scale up
kubectl scale deployment {product_name} --replicas=5

# Monitor rollout
kubectl rollout status deployment {product_name}

# Verify traffic distribution
kubectl get endpoints {product_name}
```

### Add Database Read Replicas
```bash
# Create read replica
aws rds create-db-instance-read-replica \\
  --db-instance-identifier prod-read-replica-1 \\
  --source-db-instance-identifier prod

# Route read queries to replica
# Update connection string to use prod-read-replica-1.rds.amazonaws.com
```

## Vertical Scaling (Larger instances)

### Scale Application Instance Type
```bash
# Current: t3.medium
# Target: t3.large (2x CPU, 2x memory)

# Update deployment
kubectl set resources deployment {product_name} \\
  --limits=cpu=2,memory=4Gi \\
  --requests=cpu=1,memory=2Gi

# Monitor pod scheduling
kubectl get pods -o wide
```

### Scale Database
```bash
# Current: db.t3.medium
# Target: db.m5.large (more CPU cores)

# Modify database instance (causes brief downtime)
aws rds modify-db-instance \\
  --db-instance-identifier prod \\
  --db-instance-class db.m5.large \\
  --apply-immediately

# Monitor during maintenance window
aws rds describe-db-instances \\
  --db-instance-identifier prod \\
  --query 'DBInstances[0].DBInstanceStatus'
```

## Auto-Scaling Setup

### Kubernetes Horizontal Pod Autoscaler
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {product_name}-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {product_name}
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

### AWS RDS Auto Scaling
```bash
# Enable RDS auto-scaling
aws application-autoscaling register-scalable-target \\
  --service-namespace rds \\
  --resource-id cluster:prod-cluster \\
  --scalable-dimension rds:cluster:DesiredReadReplicaCount \\
  --min-capacity 1 \\
  --max-capacity 5
```

## Capacity Planning

### Monthly Capacity Review
1. Review usage trends: 30-day CPU, memory, and storage graphs
2. Calculate growth rate: (current - 30 days ago) / 30
3. Forecast 90-day needs: current + (growth rate * 90)
4. Identify when thresholds will be exceeded
5. Schedule proactive scaling before threshold

### Example Forecast
- Current CPU usage: 45%
- 30-day growth: +2% per day
- 90-day forecast: 45% + (2% * 90) = 225% → SCALE NOW
- Recommended action: Double instance count

## Load Testing

### Before Major Deployment
```bash
# Use Apache JMeter or similar
jmeter -n -t test_plan.jmx \\
  -l results.jtl \\
  -j jmeter.log

# Simulate peak load
# Target: 10,000 requests/second with <500ms latency
# Duration: 5 minutes sustained
```

### Capacity Test Results
- Document baseline performance
- Identify breaking points
- Update scaling thresholds based on results
- Share findings with team
"""

        runbook_dir = self.workspace_path / "runbooks"
        runbook_dir.mkdir(parents=True, exist_ok=True)
        scaling_path = runbook_dir / "SCALING.md"
        scaling_path.write_text(runbook_content, encoding="utf-8")

        logger.info(f"Generated scaling runbook: {scaling_path}")

    def _generate_sla_document(self, phase: PostlaunchPhase) -> None:
        """Generate SLA/SLO document.

        Args:
            phase: The phase being executed
        """
        if not phase.output:
            return

        sla_content = f"""# Service Level Agreement (SLA) for {phase.input_data.product_name}

## Service Level Objectives (SLOs)

### Availability
- **Target**: {phase.config.uptime_target}% uptime
- **Error budget**: {100 - phase.config.uptime_target}% per month
- **Acceptable downtime**: ~22 minutes/month
- **Measured by**: Percentage of successful API responses

### Performance
- **Target**: {phase.config.response_time_target_ms}ms response time (p99)
- **Acceptable**: 95% of requests under {phase.config.response_time_target_ms}ms
- **Measured by**: Application response time from monitoring

### Error Rate
- **Target**: {phase.config.error_rate_target * 100}% error rate (max)
- **Acceptable**: 99% of requests succeed
- **Measured by**: 5xx errors / total requests

## Measurement and Reporting

### Weekly Metrics Report
- Uptime percentage
- Average response time
- Error rate
- P50, P95, P99 latencies
- Peak concurrent users

### Monthly SLA Report
- Compliance with SLOs
- Incidents and impact
- Error budget consumption
- Trend analysis
- Recommendations

## Support Channels

### Emergency Support (Severity 1-2)
- **Phone**: +1-XXX-XXX-XXXX
- **Response Time**: Within 15 minutes
- **Availability**: 24/7

### Standard Support (Severity 3-4)
- **Email**: support@example.com
- **Response Time**: Within 4 hours
- **Availability**: Business hours (9 AM - 6 PM UTC)

### Community Support
- **Slack**: #support-channel
- **Forums**: community.example.com
- **Response Time**: Best effort (no SLA)

## Credits for SLA Violations

If we fail to meet SLOs, service credits apply:

| Availability | Credit |
|--------------|--------|
| 99.0 - 99.89% | 10% monthly fee |
| 98.0 - 98.99% | 25% monthly fee |
| 95.0 - 97.99% | 50% monthly fee |
| < 95.0% | 100% monthly fee |

## Exclusions

SLA does not apply to:
- Scheduled maintenance (announced 30 days in advance)
- Force majeure events (natural disasters, wars)
- Customer configuration errors
- Third-party service failures
- DDoS attacks

## Service Scope

This SLA applies to:
- API endpoints (api.example.com)
- Web dashboard (app.example.com)
- WebSocket connections for real-time updates

This SLA does NOT apply to:
- Email notifications (best effort)
- Third-party integrations
- Beta features
- Deprecated APIs

## Escalation Procedure

1. **Initial Response** (within 15 min): Acknowledge ticket, confirm issue
2. **Engineering Team** (within 1 hour): Assign engineer, begin investigation
3. **Lead Engineer** (after 4 hours): Escalate if not resolved
4. **VP Engineering** (after 8 hours): Executive escalation
5. **Customer Success** (after 24 hours): C-level notification

## Communication During Incidents

- **Status Page**: https://status.example.com (updated every 15 min)
- **Email**: Sent to all affected customers
- **Slack**: Real-time updates in #incidents
- **Twitter**: @examplestatus (for public incidents)
"""

        sla_path = self.workspace_path / "SLA.md"
        sla_path.write_text(sla_content, encoding="utf-8")

        # Store SLA definitions
        phase.output.sla_definitions = [
            {
                "metric": "Uptime",
                "target": f"{phase.config.uptime_target}%",
                "error_budget": f"{100 - phase.config.uptime_target}%",
            },
            {
                "metric": "Response Time (p99)",
                "target": f"{phase.config.response_time_target_ms}ms",
            },
            {
                "metric": "Error Rate",
                "target": f"<{phase.config.error_rate_target * 100}%",
            },
        ]

        phase.output.sla_document_path = str(sla_path)
        logger.info(f"Generated SLA document: {sla_path}")

    def _generate_monitoring_setup(self, phase: PostlaunchPhase) -> None:
        """Generate monitoring setup guide.

        Args:
            phase: The phase being executed
        """
        if not phase.output:
            return

        monitoring_content = f"""# Monitoring Setup for {phase.input_data.product_name}

## Alert Rules

### Critical Alerts (Severity 1)
"""

        phase.output.alert_rules = [
            {
                "name": "Service Unreachable",
                "condition": "Health check fails for 5 consecutive checks",
                "action": "Page on-call engineer immediately",
            },
            {
                "name": "High Error Rate",
                "condition": "Error rate > 5% for 5 minutes",
                "action": "Page on-call engineer, open war room",
            },
            {
                "name": "Database Unavailable",
                "condition": "DB connection pool exhausted or connection timeout",
                "action": "Page on-call + database team",
            },
            {
                "name": "Disk Space Critical",
                "condition": "Disk usage > 95%",
                "action": "Page ops engineer immediately",
            },
        ]

        monitoring_content += """
### High Priority Alerts (Severity 2)
- High memory usage (>85% for 10 minutes)
- High CPU usage (>80% for 15 minutes)
- Database slow query detected (>1000ms)
- High latency (p99 > 1000ms for 5 minutes)

### Medium Priority Alerts (Severity 3)
- Moderate error rate increase (error rate doubles previous hour)
- Certificate expiry warning (< 30 days)
- Backup failure detected
- API response time slightly elevated (500-1000ms)

### Low Priority Alerts (Severity 4)
- High memory usage (>70% for 5 minutes)
- Disk usage moderate (80-95%)
- Infrequent errors (< 0.1%)

## Grafana Dashboards

### Main Dashboard
- Service availability timeline
- Error rate trend
- Response time distribution (p50, p95, p99)
- CPU and memory usage
- Database connection count
- Active users/sessions

### Business Metrics
- Total requests/hour
- Revenue-impacting errors
- Top 10 error types
- Hourly/daily/monthly trends
- Capacity utilization

### Infrastructure Dashboard
- Kubernetes node health
- Pod restart count
- Network I/O
- Disk space utilization
- Database replication lag

## Prometheus Configuration

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    environment: 'production'
    team: 'backend'

scrape_configs:
  - job_name: 'application'
    static_configs:
      - targets: ['localhost:8000']
    scrape_interval: 10s

  - job_name: 'kubernetes'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_scrape]
        action: keep
        regex: true

rule_files:
  - '/etc/prometheus/alert_rules.yml'
```

## Log Aggregation Setup

### ELK Stack Configuration
```
Logs from all containers → Filebeat → Logstash → Elasticsearch → Kibana
```

### Important Log Queries
```
# Find all errors in last hour
level:error AND timestamp:[now-1h TO now]

# Find slow API calls
duration_ms:[500 TO *]

# Find authentication failures
event_type:auth_failure
```

## Alert Notification Channels
"""

        for channel in phase.config.alert_channels:
            monitoring_content += f"- {channel}\n"

        monitoring_path = self.workspace_path / "MONITORING_SETUP.md"
        monitoring_path.write_text(monitoring_content, encoding="utf-8")

        phase.output.monitoring_setup_path = str(monitoring_path)
        logger.info(f"Generated monitoring setup: {monitoring_path}")

    def _save_to_history(self, phase: PostlaunchPhase) -> None:
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

    def _format_history_entry(self, phase: PostlaunchPhase) -> str:
        """Format phase as BUILD_HISTORY entry.

        Args:
            phase: The phase to format

        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Postlaunch Phase: {phase.phase_id}",
            f"**Description**: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at}",
            f"**Completed**: {phase.completed_at}",
            "",
        ]

        if phase.output:
            lines.append("### Operational Artifacts")
            if phase.output.sla_definitions:
                lines.append("- **SLA Definitions**:")
                for sla in phase.output.sla_definitions:
                    lines.append(f"  - {sla.get('metric')}: {sla.get('target')}")
            if phase.output.alert_rules:
                lines.append(f"- **Alert Rules Configured**: {len(phase.output.alert_rules)}")
            lines.append("")

        if phase.error:
            lines.append(f"**Error**: {phase.error}")
            lines.append("")

        return "\n".join(lines)


def create_postlaunch_phase(
    phase_id: str,
    product_name: str,
    **kwargs,
) -> PostlaunchPhase:
    """Factory function to create a postlaunch phase.

    Args:
        phase_id: Unique phase identifier
        product_name: Name of the product
        **kwargs: Additional configuration options

    Returns:
        Configured PostlaunchPhase instance
    """
    config = PostlaunchConfig(**kwargs)
    input_data = PostlaunchInput(product_name=product_name)

    return PostlaunchPhase(
        phase_id=phase_id,
        description=f"Postlaunch phase: {phase_id}",
        config=config,
        input_data=input_data,
    )
