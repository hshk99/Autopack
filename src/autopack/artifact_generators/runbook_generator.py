"""RunbookGenerator artifact generator for operational runbooks.

Generates comprehensive operational runbooks including incident response,
maintenance procedures, scaling guides, and SLA/SLO definitions.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RunbookGenerator:
    """Generates structured operational runbooks for production support.

    Produces comprehensive runbook guidance including:
    - Incident response procedures (severity-based escalation)
    - Maintenance schedules and procedures
    - Scaling playbooks (horizontal and vertical)
    - SLA/SLO definitions and error budgets
    - On-call rotation and escalation paths
    - Monitoring and alerting setup
    """

    # Runbook types
    RUNBOOK_TYPES = {
        "incident_response": {
            "name": "Incident Response",
            "description": "Procedures for handling production incidents",
            "sections": ["Severity Levels", "Response Procedures", "Escalation Matrix"],
        },
        "maintenance": {
            "name": "Maintenance",
            "description": "Regular maintenance and upkeep procedures",
            "sections": ["Daily Checks", "Weekly Checks", "Monthly Checks"],
        },
        "scaling": {
            "name": "Scaling",
            "description": "Procedures for scaling application and infrastructure",
            "sections": ["Horizontal Scaling", "Vertical Scaling", "Auto-Scaling"],
        },
    }

    # Severity levels
    SEVERITY_LEVELS = {
        "critical": {
            "name": "Severity 1 - Critical",
            "impact": "Service completely unavailable or data at risk",
            "response_time": "15 minutes",
            "escalation_time": "Immediate",
        },
        "high": {
            "name": "Severity 2 - High",
            "impact": "Service severely degraded, multiple users affected",
            "response_time": "1 hour",
            "escalation_time": "30 minutes if unresolved",
        },
        "medium": {
            "name": "Severity 3 - Medium",
            "impact": "Limited functionality, some users affected",
            "response_time": "4 hours",
            "escalation_time": "Next standup",
        },
        "low": {
            "name": "Severity 4 - Low",
            "impact": "Cosmetic issues, edge cases",
            "response_time": "Next business day",
            "escalation_time": "Via ticket system",
        },
    }

    def __init__(self) -> None:
        """Initialize the RunbookGenerator."""
        logger.info("[RunbookGenerator] Initializing runbook generator")

    def generate(
        self,
        product_name: str,
        runbook_types: Optional[List[str]] = None,
        uptime_target: float = 99.9,
        response_time_target_ms: int = 500,
    ) -> Dict[str, str]:
        """Generate comprehensive operational runbooks.

        Args:
            product_name: Name of the product
            runbook_types: Types of runbooks to generate (defaults to all)
            uptime_target: Target uptime percentage
            response_time_target_ms: Target response time in milliseconds

        Returns:
            Dictionary of runbook names and content
        """
        logger.info(f"[RunbookGenerator] Generating runbooks for {product_name}")

        if runbook_types is None:
            runbook_types = list(self.RUNBOOK_TYPES.keys())
        else:
            # Validate runbook types
            runbook_types = [t for t in runbook_types if t in self.RUNBOOK_TYPES]
            if not runbook_types:
                runbook_types = list(self.RUNBOOK_TYPES.keys())
                logger.warning("[RunbookGenerator] No valid runbook types, using all")

        runbooks = {}

        for runbook_type in runbook_types:
            logger.info(f"[RunbookGenerator] Generating {runbook_type} runbook")

            if runbook_type == "incident_response":
                runbooks["incident_response.md"] = self._generate_incident_response(product_name)
            elif runbook_type == "maintenance":
                runbooks["maintenance.md"] = self._generate_maintenance(product_name)
            elif runbook_type == "scaling":
                runbooks["scaling.md"] = self._generate_scaling(product_name)

        # Always generate SLA document
        runbooks["sla_definition.md"] = self._generate_sla(
            product_name, uptime_target, response_time_target_ms
        )

        return runbooks

    def _generate_incident_response(self, product_name: str) -> str:
        """Generate incident response runbook.

        Args:
            product_name: Product name

        Returns:
            Markdown content
        """
        content = f"""# Incident Response Runbook - {product_name}

## Overview

This runbook provides procedures for responding to production incidents in {product_name}.
All times are in UTC. Follow this guide to minimize impact and customer disruption.

## Incident Severity Classification

"""
        for key, level in self.SEVERITY_LEVELS.items():
            content += f"""### {level["name"]}
- **Impact**: {level["impact"]}
- **Response Time**: Within {level["response_time"]}
- **Escalation**: {level["escalation_time"]}

"""

        content += """## Incident Response Process

### Phase 1: Detect & Acknowledge (0-5 minutes)

**Responsibilities**:
- On-call engineer: Acknowledge alert within 5 minutes
- Page escalation: Notify incident commander

**Steps**:
1. Receive alert notification (PagerDuty/monitoring system)
2. Acknowledge alert within 5 minutes
3. Create incident ticket with unique ID
4. Record: timestamp, alert details, initial severity assessment
5. For Severity 1-2: Open war room (Slack #incidents or Zoom)
6. For Severity 1: Immediately notify Engineering Lead

**Information to Gather**:
- Alert name and timestamp
- Affected services/components
- Initial metric readings
- Recent deployments or changes

### Phase 2: Assess & Triage (5-15 minutes)

**Responsibilities**:
- On-call engineer: Investigate
- Incident commander: Coordinate and communicate

**Steps**:
1. Review application logs for errors
   ```bash
   kubectl logs -f deployment/{product_name} -c app --tail=100
   ```

2. Check metrics dashboard
   - CPU and memory usage
   - Request rate and latency (p50, p95, p99)
   - Error rate
   - Database connection count
   - Disk space utilization

3. Identify affected systems
   - Application tier
   - Database tier
   - Cache layer
   - External dependencies

4. Determine root cause category
   - Application error (5xx errors)
   - Database issue (slow queries, unavailable)
   - Infrastructure issue (CPU, memory, disk)
   - External service dependency
   - Network/connectivity issue

5. Declare final severity level based on impact
   - Number of users affected
   - Duration of impact
   - Business criticality
   - Revenue impact

6. Update status page (incident.example.com) with initial assessment

### Phase 3: Mitigate (15-45 minutes)

**Responsibilities**:
- On-call engineer: Execute mitigation
- Incident commander: Monitor progress, communicate

**Steps Based on Root Cause**:

**If Application Error**:
```bash
# 1. Check error logs
kubectl logs -f deployment/{product_name} --all-containers=true | grep ERROR

# 2. Check for recent deployments
kubectl rollout history deployment/{product_name}

# 3. Check application health
curl -s https://api.example.com/health | jq

# 4. Potential fixes:
# - Restart pods
kubectl rollout restart deployment/{product_name}

# - Rollback recent deployment
kubectl rollout undo deployment/{product_name}

# - Scale up if resource-constrained
kubectl scale deployment/{product_name} --replicas=5
```

**If Database Issue**:
```bash
# 1. Check database connectivity
kubectl run -it --rm debug --image=postgres:15 -- \\
  psql -h postgres-service -U postgres -c "SELECT 1"

# 2. Check slow queries
SELECT pid, duration, query FROM pg_stat_statements \\
  WHERE duration > 1000 ORDER BY duration DESC LIMIT 10;

# 3. Check connection pool
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;

# 4. Potential fixes:
# - Kill long-running queries
SELECT pg_terminate_backend(pid) FROM pg_stat_activity \\
  WHERE duration > 300000;

# - Increase connection pool size
# - Scale database instance
```

**If Infrastructure Issue**:
```bash
# 1. Check node status
kubectl get nodes
kubectl describe node <node-name>

# 2. Check pod resource usage
kubectl top pods --all-namespaces | sort -k3 -rn | head -10

# 3. Check persistent volume
kubectl get pv
df -h /mnt/data

# 4. Potential fixes:
# - Evict pods from unhealthy node
kubectl drain <node-name> --ignore-daemonsets

# - Scale cluster
kubectl autoscale deployment {product_name} --min=3 --max=10 --cpu-percent=70

# - Expand persistent volume
# Update PVC and resize filesystem
```

### Phase 4: Communicate (Every 15 minutes)

**Responsibilities**: Incident commander

**Updates**:
- War room: Current status, next steps, ETA
- Slack #incidents: User-friendly status and timeline
- Status page: Public update
- Email: Critical updates to key stakeholders

**Message Template**:
```
We are investigating an issue affecting {product_name}.
Impact: {brief description}
Started: {time}
Current Status: {investigating / mitigating / monitoring recovery}
ETA: {estimated time to resolution}
Latest Update: {most recent action taken}
```

### Phase 5: Resolve & Monitor (Until stable)

**Responsibilities**:
- On-call engineer: Verify fix and stability
- Incident commander: Declare resolution

**Steps**:
1. Confirm metrics return to normal
   - Error rate < 0.01%
   - Latency < 500ms (p99)
   - CPU usage < 70%
   - Memory usage normal

2. Monitor for 15 minutes minimum
   - Watch for metric spikes
   - Check for customer reports
   - Verify no cascading issues

3. Update status page with resolution
4. Close war room when stable
5. Document incident conclusion

### Phase 6: Post-Incident (Within 24 hours)

**Responsibilities**: Incident commander + Engineering Lead

**Deliverables**:
1. Incident Summary Report
   - Timeline of events
   - Root cause analysis
   - Impact assessment
   - Resolution steps taken

2. Action Items
   - Preventive measures (monitoring, limits, redundancy)
   - Improvements to runbooks
   - Training needs

3. Post-Mortem Meeting (if Severity 1-2)
   - No-blame culture focus
   - 30-minute discussion
   - Document lessons learned

**Example Preventive Actions**:
- Add monitoring alert before threshold (e.g., when DB connections > 70%)
- Implement circuit breaker for flaky external service
- Increase resource limits based on incident
- Add automated scaling trigger

## Escalation Contacts

### By Role
- **On-Call Engineer**: PagerDuty rotation
- **Engineering Lead**: {product_name} Slack @engineering-lead
- **Database Admin**: @db-team
- **Infrastructure**: @ops-team
- **VP Engineering**: escalation@example.com

### By Time
- During business hours (9-5 UTC): Direct Slack
- Outside business hours: PagerDuty escalation
- Critical severity: Page all escalation levels

## Tools and Access

| Tool | Purpose | URL | Access |
|------|---------|-----|--------|
| Monitoring | Metrics/alerts | grafana.example.com | SSO |
| Logs | Application logs | kibana.example.com | SSO |
| Status Page | Public status | status.example.com | Update API |
| Database | Direct access | AWS Console | IAM role |
| Kubernetes | Container orchestration | kubectl configured | KUBECONFIG |
| PagerDuty | On-call management | pagerduty.com | Team account |

## Testing Incident Response

### Monthly Drill
- **When**: First Tuesday of month, 2 PM UTC
- **Participants**: On-call engineer + lead
- **Scenario**: Simulate actual incident
- **Duration**: 30 minutes
- **Debrief**: 15 minutes after

### Drill Scenarios
1. Database becomes unavailable
2. Application crashes (5xx errors)
3. Memory leak causes restart loop
4. External API dependency fails
5. DDoS attack (rate limiting)

"""
        return content

    def _generate_maintenance(self, product_name: str) -> str:
        """Generate maintenance runbook.

        Args:
            product_name: Product name

        Returns:
            Markdown content
        """
        return f"""# Maintenance Runbook - {product_name}

## Daily Maintenance (9 AM UTC)

### Health Checks
- [ ] Application responding to health checks
- [ ] Database connectivity verified
- [ ] All services in healthy state
- [ ] No untracked errors in logs
- [ ] Disk space < 80%

**Commands**:
```bash
curl https://api.example.com/health
kubectl get deployments
kubectl get pods --all-namespaces | grep -E "CrashLoop|Pending"
```

### Monitoring Review
- [ ] Check error rate (target: < 0.01%)
- [ ] Check latency p99 (target: < 500ms)
- [ ] Check active user count vs. baseline
- [ ] No unusual CPU/memory spikes

## Weekly Maintenance (Every Monday, 10 AM UTC)

### Backups Verification
- [ ] Most recent backup exists and is dated < 24 hours ago
- [ ] Backup size is reasonable (not 0 bytes)
- [ ] Test restore from backup (once per quarter)

**Commands**:
```bash
# AWS RDS backup check
aws rds describe-db-instances --db-instance-identifier prod \\
  --query 'DBInstances[0].LatestRestorableTime'

# Backup size verification
du -h /backups/prod_backup_latest.sql.gz
```

### Certificate Expiry Check
- [ ] SSL/TLS certificates valid
- [ ] Days until expiry > 30 days
- [ ] Renewal scheduled if < 90 days

**Commands**:
```bash
# Check certificate expiry
openssl s_client -connect api.example.com:443 \\
  -showcerts 2>/dev/null | \\
  openssl x509 -noout -dates
```

### Dependency Updates
- [ ] Check for security updates
- [ ] Review dependency changelogs
- [ ] Plan major upgrades if needed

**Commands**:
```bash
# Check npm/pip for updates
npm outdated
pip list --outdated
```

### Log Review
- [ ] Review error logs for patterns
- [ ] Check for repeated warnings
- [ ] Identify slow queries (> 1 second)
- [ ] Review access patterns for anomalies

## Monthly Maintenance (First day of month, 2 PM UTC)

### Security Scan
- [ ] Run vulnerability scanner
- [ ] Review security alerts
- [ ] Update security patches

**Tools**:
- npm audit
- OWASP Dependency Check
- Snyk

### Database Optimization
- [ ] Analyze query performance
- [ ] Add missing indexes if needed
- [ ] Run vacuum/analyze (PostgreSQL)

**PostgreSQL**:
```sql
-- Identify slow queries
SELECT query, mean_time, calls
FROM pg_stat_statements
ORDER BY mean_time DESC LIMIT 10;

-- Add missing index
CREATE INDEX idx_user_email ON users(email);

-- Optimize database
VACUUM ANALYZE;
```

### Capacity Planning
- [ ] Review storage growth rate
- [ ] Project 3-month storage needs
- [ ] Check CPU/memory utilization trends
- [ ] Identify scaling needs

**Metrics to Review**:
- Storage used vs. capacity
- Database table sizes
- Log retention needs
- Cache hit rates

### Documentation Review
- [ ] Update runbooks with recent changes
- [ ] Review architecture documentation
- [ ] Verify contact information current
- [ ] Check for broken links/outdated info

## Scheduled Maintenance Window

**When**: Second Tuesday, 2-3 AM UTC
**Notification**: Announce 1 week in advance

### Typical Maintenance Tasks
- Database schema migrations
- OS security patches
- Dependency updates
- Infrastructure maintenance
- Non-critical system upgrades

### Maintenance Checklist
1. [ ] Announce maintenance window (1 week prior)
2. [ ] Prepare and test changes in staging
3. [ ] Set status page to "Maintenance"
4. [ ] Execute planned changes
5. [ ] Verify all systems operational
6. [ ] Update status page to "Operational"
7. [ ] Notify team of completion

## Troubleshooting Common Issues

### Issue: Disk Space Critical (>95%)
1. Identify largest directories
2. Review old logs (cleanup if safe)
3. Clear temporary files
4. Expand volume if necessary

### Issue: Database Performance Degradation
1. Check slow query log
2. Analyze query execution plans
3. Add missing indexes
4. Consider query optimization

### Issue: Memory Usage Growing
1. Check for memory leaks in application
2. Review cache size settings
3. Restart service if needed
4. Investigate in development environment

### Issue: Certificate Expiry Warning
1. Generate new certificate
2. Configure renewal automation
3. Deploy new certificate to servers
4. Verify functionality

"""

    def _generate_scaling(self, product_name: str) -> str:
        """Generate scaling runbook.

        Args:
            product_name: Product name

        Returns:
            Markdown content
        """
        return f"""# Scaling Runbook - {product_name}

## Scaling Decision Tree

### When to Scale Horizontally (Add More Instances)
- **CPU Usage**: > 70% for 10 minutes
- **Memory Usage**: > 75% for sustained period
- **Request Latency**: p99 > 500ms
- **Request Rate**: > 1000 req/sec

**Action**: Add 1-2 more application instances

### When to Scale Vertically (Larger Instances)
- **All Metrics High**: CPU, Memory, Disk all elevated
- **Single Bottleneck**: One resource consistently maxed
- **Database CPU**: Database CPU-bound

**Action**: Upgrade to larger instance type (t3.medium → t3.large)

### When to Scale Database
- **Connections**: Connection pool near limit
- **CPU**: Database CPU > 80%
- **Storage**: Disk usage > 80%
- **Query Performance**: Slow queries increasing

**Action**: Scale database or add read replicas

## Horizontal Scaling

### Add Application Instances

**Option 1: Manual Scaling**
```bash
# Check current replicas
kubectl get deployments
kubectl get deployment {product_name} -o wide

# Scale up
kubectl scale deployment {product_name} --replicas=5

# Monitor scaling progress
kubectl rollout status deployment {product_name}
kubectl get pods -l app={product_name}

# Verify endpoints updated
kubectl get endpoints {product_name}
```

**Option 2: Automated Scaling (HPA)**
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
```

### Add Database Read Replicas

**AWS RDS**:
```bash
# Create read replica
aws rds create-db-instance-read-replica \\
  --db-instance-identifier prod-replica-1 \\
  --source-db-instance-identifier prod

# Monitor creation
aws rds describe-db-instances \\
  --db-instance-identifier prod-replica-1 \\
  --query 'DBInstances[0].DBInstanceStatus'

# Update connection string in application
# Database: prod-replica-1.xxxxxx.rds.amazonaws.com (read-only)
```

## Vertical Scaling

### Scale Application Instance

**Current**: t3.medium (2 vCPU, 4 GB RAM)
**Target**: t3.large (2 vCPU, 8 GB RAM)

```bash
# Update resource requests/limits
kubectl set resources deployment {product_name} \\
  --requests=cpu=1,memory=4Gi \\
  --limits=cpu=2,memory=8Gi

# Monitor pod rescheduling
kubectl get pods -o wide -l app={product_name}

# Verify new resources allocated
kubectl describe pod <pod-name> | grep -A 2 "Requests\\|Limits"
```

### Scale Database Instance

**AWS RDS**:
```bash
# Current: db.t3.medium
# Target: db.m5.large

aws rds modify-db-instance \\
  --db-instance-identifier prod \\
  --db-instance-class db.m5.large \\
  --apply-immediately \\
  --backup-retention-period 7

# Monitor scaling (involves brief downtime)
aws rds describe-db-instances \\
  --db-instance-identifier prod \\
  --query 'DBInstances[0].DBInstanceStatus'

# Estimated time: 5-10 minutes
```

## Auto-Scaling Setup

### Kubernetes HPA
```bash
# Create HPA
kubectl autoscale deployment {product_name} \\
  --min=2 --max=10 \\
  --cpu-percent=70

# Check HPA status
kubectl get hpa
kubectl describe hpa {product_name}-hpa

# View scaling history
kubectl get hpa {product_name}-hpa \\
  --watch  # real-time monitoring
```

### AWS RDS Auto Scaling (Aurora)
```bash
# Enable auto-scaling for read replicas
aws application-autoscaling register-scalable-target \\
  --service-namespace rds \\
  --resource-id cluster:prod-cluster \\
  --scalable-dimension rds:cluster:DesiredReadReplicaCount \\
  --min-capacity 1 \\
  --max-capacity 5

# Create scaling policy
aws application-autoscaling put-scaling-policy \\
  --policy-name scale-read-replicas \\
  --service-namespace rds \\
  --scalable-dimension rds:cluster:DesiredReadReplicaCount \\
  --policy-type TargetTrackingScaling \\
  --target-tracking-scaling-policy-configuration
```

## Capacity Planning

### Monthly Review Process
1. **Collect Metrics**: Last 30 days
   - CPU usage (peak and average)
   - Memory usage (peak and average)
   - Storage growth
   - Request count

2. **Calculate Growth Rate**
   - Current - 30 days ago = Growth
   - Growth / 30 = Daily growth rate

3. **Forecast 90 Days**
   - Current + (Daily growth rate × 90)
   - Identify when thresholds will exceed

4. **Plan Proactive Scaling**
   - Schedule scaling before hitting limits
   - Order new infrastructure if needed
   - Plan for peak season if applicable

### Example Forecast
```
CPU Usage:
- Current: 45%
- 30 days ago: 30%
- Daily growth: 0.5%/day
- 90-day forecast: 45% + (0.5% × 90) = 90% → SCALE NOW

Action: Increase target CPU threshold or add replicas
```

## Load Testing

### Pre-Deployment Load Test
```bash
# Tools: Apache JMeter, Locust, k6

# Example with k6
k6 run load_test.js \\
  --vus 100 \\  # 100 virtual users
  --duration 5m  # 5 minute test

# Success Criteria
# - p99 latency < 500ms
# - Error rate < 0.1%
# - Throughput > 1000 req/sec
```

### Chaos Engineering
```bash
# Simulated failure testing
# Kill random pods to test resilience
kubectl chaos daemon kill-pod \\
  --namespace default \\
  --label-selector app={product_name}

# Monitor application recovery time
# Target: < 30 seconds to detect and recover
```

## Scaling Policies

### CPU-Based Scaling
- Scale up when: CPU > 70% for 2 minutes
- Scale down when: CPU < 30% for 10 minutes
- Min replicas: 2, Max: 10

### Memory-Based Scaling
- Scale up when: Memory > 80% for 5 minutes
- Scale down when: Memory < 50% for 15 minutes
- Vertical: Increase instance size when > 90%

### Custom Metrics
- Scale on: Request queue length, DB connections
- Webhook-based for business metrics

"""

    def _generate_sla(self, product_name: str, uptime_target: float, response_time_ms: int) -> str:
        """Generate SLA definition.

        Args:
            product_name: Product name
            uptime_target: Target uptime percentage
            response_time_ms: Target response time in milliseconds

        Returns:
            Markdown content
        """
        error_budget = 100 - uptime_target
        downtime_per_month = (error_budget / 100) * 24 * 60 * 30

        return f"""# Service Level Agreement (SLA) - {product_name}

## Service Level Objectives (SLOs)

### Availability
- **Target Uptime**: {uptime_target}%
- **Error Budget**: {error_budget}% per month
- **Acceptable Downtime**: ~{downtime_per_month:.0f} minutes/month (~{downtime_per_month / 60:.1f} hours)

**Measured by**: Percentage of successful API responses from monitoring perspective
(external health checks, not internal)

### Performance
- **Response Time (p99)**: {response_time_ms}ms
- **Acceptable**: 95% of requests under {response_time_ms}ms
- **Measured by**: Application response latency from gateway

### Error Rate
- **Target**: < 0.01% errors
- **Acceptable**: 99.99% of requests succeed
- **Measured by**: 5xx errors / total requests

## Measurement Methodology

### Uptime Calculation
```
Uptime % = (Total time - Downtime) / Total time × 100

Example:
- Month = 43,200 minutes (30 days)
- Downtime = 22 minutes
- Uptime = (43,200 - 22) / 43,200 × 100 = 99.95%
```

### Exclusions from SLA
- Scheduled maintenance (30-day notice required)
- Force majeure (natural disasters, wars)
- Customer misconfiguration
- Third-party service failures (not owned by us)
- Beta or deprecated features
- DDoS attacks (mitigated but not part of SLA)

## Service Credits

If we fail to meet SLOs, service credits apply:

| Uptime Achieved | Monthly Service Credit |
|---|---|
| 99.0-99.89% | 10% monthly fee |
| 98.0-98.99% | 25% monthly fee |
| 95.0-97.99% | 50% monthly fee |
| < 95.0% | 100% monthly fee |

**Credit Conditions**:
- Must be claimed within 30 days of incident
- Credits applied to next invoice
- Credits do not entitle refund
- Total credits capped at monthly fee

## Support Response Times

| Severity | Support Channel | Response Time |
|---|---|---|
| Severity 1 (Critical) | Phone + Email | 15 minutes |
| Severity 2 (High) | Email + Slack | 1 hour |
| Severity 3 (Medium) | Email | 4 hours |
| Severity 4 (Low) | Ticket | 24 hours |

**Support Availability**:
- Emergency (24/7): P1/P2 incidents
- Business Hours (9-6 UTC): P3/P4 tickets
- Community Support: Best effort (no SLA)

## Escalation Procedure

1. **Tier 1**: Support team (initial response)
2. **Tier 2**: Engineering team (30 min if unresolved)
3. **Tier 3**: Engineering lead (4 hours if unresolved)
4. **Tier 4**: VP Engineering (8 hours if unresolved)

## Monitoring and Reporting

### Real-Time Monitoring
- Public status page: status.example.com
- Updated every 15 minutes during incidents
- Historical uptime stats publicly visible

### Monthly SLA Report
- Uptime percentage
- Incidents and impact
- Error budget consumption
- Trend analysis
- Recommendations

## Changes to SLA

- Changes require 30-day notice
- No reduction in service levels
- Annual review of SLA targets
- Customer feedback incorporated

---

**Last Updated**: {product_name} operations team
**Next Review**: Quarterly
"""
