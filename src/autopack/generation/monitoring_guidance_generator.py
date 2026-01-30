"""Monitoring setup guidance generator for deployment phase.

This module provides guidance for setting up monitoring solutions across various
platforms including Prometheus, DataDog, CloudWatch, and Elasticsearch. It generates
comprehensive setup guides, configuration examples, and best practices for production
monitoring.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class MonitoringGuide:
    """Represents a monitoring setup guide for a specific platform."""

    platform_name: str
    description: str
    setup_difficulty: str  # 'easy', 'medium', 'hard'
    estimated_setup_time_hours: float
    cost_per_month_usd: Optional[float]
    metrics_collected: List[str] = field(default_factory=list)
    log_aggregation_included: bool = False
    alerting_included: bool = False
    dashboard_included: bool = False
    best_for: str = ""
    guide_content: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class MonitoringGuidanceGenerator:
    """Generates monitoring setup guidance for various platforms and tools."""

    def __init__(self) -> None:
        """Initialize the monitoring guidance generator."""
        self.guides: Dict[str, MonitoringGuide] = {}

    def generate_prometheus_guide(self, project_type: str = "web") -> MonitoringGuide:
        """Generate Prometheus monitoring setup guide.

        Prometheus is an open-source monitoring solution with powerful querying.
        Best for: Kubernetes-native deployments, time-series metrics.

        Args:
            project_type: Type of project ('web', 'api', 'batch', 'ml')

        Returns:
            MonitoringGuide with Prometheus setup instructions
        """
        guide = MonitoringGuide(
            platform_name="Prometheus",
            description="Open-source time-series database for metrics collection",
            setup_difficulty="medium",
            estimated_setup_time_hours=4.0,
            cost_per_month_usd=0.0,  # Self-hosted, only infrastructure costs
            metrics_collected=[
                "CPU usage",
                "Memory consumption",
                "Disk I/O",
                "Network traffic",
                "HTTP request metrics",
                "Database query latency",
                "Application custom metrics",
            ],
            log_aggregation_included=False,
            alerting_included=True,
            dashboard_included=False,  # Requires Grafana
            best_for="Kubernetes deployments, on-premise monitoring, cost-sensitive",
        )

        guide.guide_content = self._generate_prometheus_setup_guide(project_type)
        self.guides["prometheus"] = guide
        return guide

    def generate_datadog_guide(self, project_type: str = "web") -> MonitoringGuide:
        """Generate DataDog monitoring setup guide.

        DataDog is a SaaS monitoring platform with deep integrations.
        Best for: Quick setup, multi-cloud monitoring, comprehensive features.

        Args:
            project_type: Type of project ('web', 'api', 'batch', 'ml')

        Returns:
            MonitoringGuide with DataDog setup instructions
        """
        guide = MonitoringGuide(
            platform_name="DataDog",
            description="SaaS monitoring and observability platform",
            setup_difficulty="easy",
            estimated_setup_time_hours=2.0,
            cost_per_month_usd=15.0,  # Estimated starting price per host
            metrics_collected=[
                "Infrastructure metrics",
                "Application Performance Monitoring (APM)",
                "Container metrics",
                "Kubernetes metrics",
                "Custom metrics",
                "Log aggregation",
                "Distributed tracing",
            ],
            log_aggregation_included=True,
            alerting_included=True,
            dashboard_included=True,
            best_for="Cloud-native, rapid deployment, full observability stack",
        )

        guide.guide_content = self._generate_datadog_setup_guide(project_type)
        self.guides["datadog"] = guide
        return guide

    def generate_cloudwatch_guide(self, project_type: str = "web") -> MonitoringGuide:
        """Generate AWS CloudWatch monitoring setup guide.

        CloudWatch is AWS-native monitoring integrated with other AWS services.
        Best for: AWS-first deployments, native integrations, cost tracking.

        Args:
            project_type: Type of project ('web', 'api', 'batch', 'ml')

        Returns:
            MonitoringGuide with CloudWatch setup instructions
        """
        guide = MonitoringGuide(
            platform_name="AWS CloudWatch",
            description="AWS-native monitoring and observability service",
            setup_difficulty="easy",
            estimated_setup_time_hours=1.5,
            cost_per_month_usd=5.0,  # Estimated for basic usage
            metrics_collected=[
                "EC2 instance metrics",
                "Lambda execution metrics",
                "RDS database metrics",
                "ELB/ALB metrics",
                "Custom application metrics",
                "Log streams",
                "Cost and usage metrics",
            ],
            log_aggregation_included=True,
            alerting_included=True,
            dashboard_included=True,
            best_for="AWS deployments, integrated observability, cost visibility",
        )

        guide.guide_content = self._generate_cloudwatch_setup_guide(project_type)
        self.guides["cloudwatch"] = guide
        return guide

    def generate_elasticsearch_guide(self, project_type: str = "web") -> MonitoringGuide:
        """Generate Elasticsearch (ELK Stack) monitoring setup guide.

        Elasticsearch provides powerful log aggregation and analysis.
        Best for: Log-intensive applications, full-text search, detailed analysis.

        Args:
            project_type: Type of project ('web', 'api', 'batch', 'ml')

        Returns:
            MonitoringGuide with Elasticsearch setup instructions
        """
        guide = MonitoringGuide(
            platform_name="Elasticsearch (ELK Stack)",
            description="Distributed log aggregation and analysis platform",
            setup_difficulty="hard",
            estimated_setup_time_hours=8.0,
            cost_per_month_usd=0.0,  # Self-hosted, only infrastructure costs
            metrics_collected=[
                "Application logs",
                "System logs",
                "Access logs",
                "Error logs",
                "Structured metrics",
                "Event data",
                "Full-text searchable content",
            ],
            log_aggregation_included=True,
            alerting_included=True,
            dashboard_included=True,  # Via Kibana
            best_for="Log-heavy applications, on-premise, detailed analysis",
        )

        guide.guide_content = self._generate_elasticsearch_setup_guide(project_type)
        self.guides["elasticsearch"] = guide
        return guide

    def generate_all_guides(self, project_type: str = "web") -> Dict[str, MonitoringGuide]:
        """Generate guides for all supported monitoring platforms.

        Args:
            project_type: Type of project ('web', 'api', 'batch', 'ml')

        Returns:
            Dictionary mapping platform names to their guides
        """
        self.generate_prometheus_guide(project_type)
        self.generate_datadog_guide(project_type)
        self.generate_cloudwatch_guide(project_type)
        self.generate_elasticsearch_guide(project_type)
        return self.guides

    def _generate_prometheus_setup_guide(self, project_type: str) -> str:
        """Generate detailed Prometheus setup instructions."""
        return f"""
# Prometheus Monitoring Setup Guide ({project_type.title()} Application)

## Overview
Prometheus is a powerful, open-source monitoring and time-series database. It works by
pulling metrics from configured targets at regular intervals.

## Architecture
```
Your Application (exposes /metrics endpoint)
         ↓
  Prometheus Server (scrapes every 15s)
         ↓
  Time-Series Database (stores metrics)
         ↓
  Alertmanager (processes alert rules)
         ↓
  Grafana/Dashboards (visualize)
```

## Installation Steps

### 1. Install Prometheus Server
```bash
# Download latest version
wget https://github.com/prometheus/prometheus/releases/download/v2.40.0/prometheus-2.40.0.linux-amd64.tar.gz
tar xvfz prometheus-2.40.0.linux-amd64.tar.gz
cd prometheus-2.40.0.linux-amd64

# Create system user
sudo useradd --no-create-home --shell /bin/false prometheus
sudo mkdir -p /etc/prometheus /var/lib/prometheus

# Copy files to standard locations
sudo cp prometheus /usr/local/bin/
sudo cp promtool /usr/local/bin/
sudo cp -r consoles /etc/prometheus
sudo cp -r console_libraries /etc/prometheus

# Set permissions
sudo chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus
```

### 2. Configure Prometheus (prometheus.yml)
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'production'
    environment: 'prod'

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - localhost:9093

rule_files:
  - '/etc/prometheus/rules/*.yml'

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: '{project_type}-app'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
```

### 3. Create Systemd Service
```ini
# /etc/systemd/system/prometheus.service
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \\
  --config.file=/etc/prometheus/prometheus.yml \\
  --storage.tsdb.path=/var/lib/prometheus

Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### 4. Start Prometheus
```bash
sudo systemctl daemon-reload
sudo systemctl enable prometheus
sudo systemctl start prometheus
sudo systemctl status prometheus
```

## Instrumentation

### Python/Flask Application
```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from flask import Flask, Response

app = Flask(__name__)

# Define metrics
request_count = Counter(
    'app_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'app_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

active_connections = Gauge(
    'app_active_connections',
    'Currently active connections'
)

# Middleware to track requests
@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time
    request_count.labels(
        method=request.method,
        endpoint=request.path,
        status=response.status_code
    ).inc()
    request_duration.labels(
        method=request.method,
        endpoint=request.path
    ).observe(duration)
    return response

# Expose metrics endpoint
@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype='text/plain')
```

## Key Metrics to Track

### Application Metrics
- `app_requests_total` - Total HTTP requests (counter)
- `app_request_duration_seconds` - Request latency (histogram)
- `app_errors_total` - Error count (counter)
- `app_database_queries_duration_seconds` - DB query latency (histogram)

### Infrastructure Metrics
- `node_cpu_seconds_total` - CPU usage
- `node_memory_MemAvailable_bytes` - Available memory
- `node_disk_io_reads_total` - Disk I/O operations
- `node_network_transmit_bytes_total` - Network traffic

### Custom Metrics
Define metrics specific to your application's business logic.

## Alerting Rules

Create `/etc/prometheus/rules/alerts.yml`:
```yaml
groups:
  - name: application
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(app_errors_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} (>5%)"

      - alert: HighLatency
        expr: histogram_quantile(0.95, app_request_duration_seconds_bucket) > 1
        for: 5m
        annotations:
          summary: "High request latency"

      - alert: HighMemoryUsage
        expr: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes < 0.1
        for: 10m
        annotations:
          summary: "Memory usage above 90%"
```

## Integration with Grafana

### Connect Prometheus to Grafana
1. Open Grafana (http://localhost:3000)
2. Add Data Source → Prometheus
3. Set URL: http://localhost:9090
4. Click "Save & Test"

### Create Dashboard
1. Create new dashboard
2. Add panels with PromQL queries:
   - `rate(app_requests_total[5m])` - Request rate
   - `histogram_quantile(0.95, app_request_duration_seconds_bucket)` - 95th percentile latency
   - `rate(app_errors_total[5m])` - Error rate

## PromQL Query Examples

```promql
# Request rate (per second)
rate(app_requests_total[5m])

# 95th percentile latency
histogram_quantile(0.95, app_request_duration_seconds_bucket)

# Error rate percentage
rate(app_errors_total[5m]) / rate(app_requests_total[5m]) * 100

# Memory usage percentage
(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100

# CPU usage
rate(node_cpu_seconds_total{{mode!="idle"}}[5m]) * 100
```

## Scaling Considerations

### High-Volume Scenarios (>1 million metrics)
- Use remote storage backends (InfluxDB, Thanos, Victoria Metrics)
- Implement metric retention policies
- Shard Prometheus instances

### Multi-Environment Setup
- One Prometheus per environment (or federated)
- Central Alertmanager
- Shared Grafana with multi-datasource support

## Troubleshooting

### Metrics not appearing
1. Check `/metrics` endpoint returns data
2. Check `prometheus.yml` scrape configuration
3. Review Prometheus logs: `journalctl -u prometheus -f`
4. Verify network connectivity: `curl http://target:port/metrics`

### High memory usage
1. Reduce `scrape_interval` or `storage.tsdb.retention.time`
2. Use metric relabeling to drop unnecessary metrics
3. Implement remote storage

### Alertmanager not sending alerts
1. Check Alertmanager is running
2. Verify routing configuration
3. Check notification channel credentials (Slack, PagerDuty, etc.)

## Best Practices

✓ Always define SLOs and corresponding alert thresholds
✓ Use consistent metric naming conventions
✓ Implement metric relabeling for consistency
✓ Set up distributed tracing alongside metrics
✓ Regularly review and tune alert rules
✓ Document all custom metrics
✓ Use recording rules to pre-compute expensive queries
✓ Back up Prometheus configuration
✗ Don't alert on every metric change (avoid alert fatigue)
✗ Don't scrape at sub-10-second intervals without good reason
"""

    def _generate_datadog_setup_guide(self, project_type: str) -> str:
        """Generate detailed DataDog setup instructions."""
        return f"""
# DataDog Monitoring Setup Guide ({project_type.title()} Application)

## Overview
DataDog is a comprehensive SaaS monitoring platform that combines metrics, logs,
traces, and user monitoring in one platform. It provides extensive integrations
and minimal setup overhead.

## Quick Start

### 1. Create DataDog Account
1. Sign up at https://www.datadoghq.com
2. Choose your region (US or EU)
3. Get your API Key and App Key

### 2. Install DataDog Agent

#### Linux/MacOS
```bash
DD_AGENT_MAJOR_VERSION=7 DD_API_KEY=<YOUR_API_KEY> DD_SITE="datadoghq.com" bash -c "$(curl -L https://s3.amazonaws.com/dd-agent/scripts/install_agent.sh)"
```

#### Docker
```dockerfile
FROM python:3.11-slim

# Install DataDog agent
RUN apt-get update && apt-get install -y datadog-agent

# Set configuration
ENV DD_API_KEY=<YOUR_API_KEY>
ENV DD_SITE=datadoghq.com
ENV DD_TRACE_ENABLED=true

# Start agent and application
CMD ["sh", "-c", "service datadog-agent start && python app.py"]
```

#### Kubernetes (Helm)
```bash
helm repo add datadog https://helm.datadoghq.com
helm install datadog datadog/datadog \\
  --set datadog.apiKey=<YOUR_API_KEY> \\
  --set datadog.appKey=<YOUR_APP_KEY> \\
  --set datadog.site=datadoghq.com \\
  --set datadog.apm.enabled=true \\
  --set datadog.logs.enabled=true
```

### 3. Application Instrumentation

#### Python Flask
```python
from ddtrace import patch_all
from ddtrace.contrib.flask import patch as patch_flask
from flask import Flask

# Patch all libraries
patch_all()
patch_flask()

app = Flask(__name__)

@app.route('/api/{project_type}')
def get_data():
    return {{"status": "ok"}}

if __name__ == '__main__':
    app.run()
```

#### Node.js Express
```javascript
const tracer = require('dd-trace').init({{
  service: '{project_type}-app',
  env: 'production',
}});

const express = require('express');
const app = express();

app.get('/api/data', (req, res) => {{
  res.json({{ status: 'ok' }});
}});

app.listen(3000);
```

#### Custom Metrics (Python)
```python
from datadog import initialize, api
from datadog.api import metric_api

options = {{
    'api_key': '<YOUR_API_KEY>',
    'app_key': '<YOUR_APP_KEY>'
}}

initialize(**options)

# Send custom metrics
metric_api.Metric.send(
    metric='custom.{project_type}.metric',
    points=[(int(time.time()), 42)],
    tags=['service:{project_type}-app']
)
```

### 4. Log Collection

#### File-based Logs
Edit `/etc/datadog-agent/conf.d/logs.d/conf.yaml`:
```yaml
logs:
  - type: file
    path: /var/log/app.log
    service: {project_type}-app
    source: python
    tags:
      - env:production
```

#### Container Logs
```yaml
# docker-compose.yml
version: '3'
services:
  app:
    image: your-app:latest
    labels:
      com.datadoghq.ad.logs: '[{{"source":"python","service":"{project_type}-app"}}]'
    environment:
      - DD_TRACE_ENABLED=true
      - DD_LOG_LEVEL=info
```

### 5. APM Setup (Application Performance Monitoring)

```python
# Automatically trace your application
from ddtrace import tracer

@tracer.wrap(service='my-service', resource='function_name')
def my_function():
    # Your code here
    return result

# Or use context managers
with tracer.trace('operation_name', service='my-service'):
    # Traced code block
    result = do_work()
```

## Monitoring Dashboard

### Create Custom Dashboard
1. Dashboard → New Dashboard
2. Add widgets:
   - Timeseries: Request rate
   - Gauge: Error rate %
   - Heatmap: Latency distribution
   - Table: Top endpoints by error rate

### Pre-built Dashboards
- APM Service Dashboard (auto-created)
- Infrastructure Overview
- Cloud Cost Management
- Security Monitoring

## Alerting

### Create Alert
```python
# Via UI or API
title = "High Error Rate - {project_type} App"
query = "avg(last_5m):sum:trace.web.request.errors{{service:{project_type}-app}} > 100"
type_alert = "metric alert"
```

### Alert Thresholds (Recommended)
- Error rate > 5% = Warning, > 10% = Critical
- P95 latency > 1s = Warning, > 5s = Critical
- CPU usage > 70% = Warning, > 90% = Critical
- Memory usage > 80% = Warning, > 95% = Critical
- Disk usage > 85% = Warning, > 95% = Critical

## Integration Recommendations

For {project_type} applications, integrate with:
- **Slack**: Alert notifications
- **PagerDuty**: On-call escalation
- **Jira**: Create tickets from alerts
- **GitHub**: Deployment tracking
- **AWS/GCP/Azure**: Cloud resource monitoring

## Cost Optimization

DataDog pricing:
- **APM**: $0.05 per 10,000 spans
- **Metrics**: $0.05 per custom metric
- **Logs**: $0.10 per GB ingested
- **Infrastructure**: $15 per host/month

### Cost Reduction Strategies
1. Use sampling: Trace 10-50% of requests in production
2. Drop logs below INFO level in production
3. Use metric exclusion patterns
4. Archive old logs to S3
5. Monitor DataDog bill in organization settings

## Best Practices

✓ Set up Synthetic Monitoring for critical user journeys
✓ Create service-level objectives (SLOs) with error budgets
✓ Use tagging consistently across metrics/logs/traces
✓ Implement cross-service distributed tracing
✓ Set up log pipelines for structured logging
✓ Use monitors as alerts, not dashboards
✓ Review and tune alert thresholds monthly
✗ Don't ingest PII in logs or metrics
✗ Don't set alert thresholds without baselining
✗ Don't ignore error budget exhaustion warnings

## Troubleshooting

### Agent not reporting metrics
1. Check agent status: `sudo datadog-agent status`
2. Verify API key in `/etc/datadog-agent/datadog.yaml`
3. Check network connectivity: `curl https://api.datadoghq.com/api/v1/validate`

### Missing traces
1. Enable APM: `DD_TRACE_ENABLED=true`
2. Check agent APM listener: `DD_APM_ENABLED=true`
3. Verify service name matches configuration

### Unexpected bill increase
1. Check metric cardinality in Metrics Summary
2. Review sampling rates in trace configuration
3. Analyze log ingestion patterns
4. Use Data Streams for cost analysis
"""

    def _generate_cloudwatch_setup_guide(self, project_type: str) -> str:
        """Generate detailed CloudWatch setup instructions."""
        return f"""
# AWS CloudWatch Monitoring Setup Guide ({project_type.title()} Application)

## Overview
AWS CloudWatch is the native monitoring service for AWS deployments. It integrates
seamlessly with EC2, Lambda, RDS, and other AWS services.

## Getting Started

### 1. Create CloudWatch Log Group

#### Via AWS Console
1. CloudWatch → Logs → Log Groups
2. Create log group: `/aws/{project_type}-app/production`
3. Set retention: 30 days (adjust as needed)

#### Via AWS CLI
```bash
aws logs create-log-group --log-group-name /aws/{project_type}-app/production
aws logs put-retention-policy \\
  --log-group-name /aws/{project_type}-app/production \\
  --retention-in-days 30
```

#### Via CloudFormation
```yaml
Resources:
  AppLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /aws/{project_type}-app/production
      RetentionInDays: 30
```

### 2. Configure CloudWatch Agent

#### Install Agent
```bash
# Download agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
sudo rpm -U ./amazon-cloudwatch-agent.rpm

# Or for Debian/Ubuntu
wget https://s3.amazonaws.com/amazoncloudwatch-agent/debian/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
```

#### Configuration File (`/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json`)
```json
{{
  "agent": {{
    "metrics_collection_interval": 60,
    "region": "us-east-1",
    "logfile": "/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log"
  }},
  "logs": {{
    "logs_collected": {{
      "files": {{
        "collect_list": [
          {{
            "file_path": "/var/log/app.log",
            "log_group_name": "/aws/{project_type}-app/production",
            "log_stream_name": "{{instance_id}}"
          }},
          {{
            "file_path": "/var/log/application/error.log",
            "log_group_name": "/aws/{project_type}-app/errors",
            "log_stream_name": "{{instance_id}}"
          }}
        ]
      }}
    }}
  }},
  "metrics": {{
    "metrics_collected": {{
      "cpu": {{
        "measurement": [
          {{"name": "cpu_usage_idle", "rename": "CPU_USAGE_IDLE", "unit": "Percent"}},
          {{"name": "cpu_usage_iowait", "rename": "CPU_USAGE_IOWAIT", "unit": "Percent"}}
        ],
        "metrics_collection_interval": 60
      }},
      "mem": {{
        "measurement": [
          {{"name": "mem_used_percent", "rename": "MEM_USED_PERCENT", "unit": "Percent"}}
        ],
        "metrics_collection_interval": 60
      }},
      "disk": {{
        "measurement": [
          {{"name": "used_percent", "rename": "DISK_USED_PERCENT", "unit": "Percent"}}
        ],
        "metrics_collection_interval": 60,
        "resources": ["/"]
      }}
    }}
  }}
}}
```

#### Start Agent
```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \\
  -a fetch-config \\
  -m ec2 \\
  -s \\
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

### 3. Application Instrumentation

#### Python with Boto3
```python
import logging
import boto3
from datetime import datetime

# CloudWatch Logs
logs_client = boto3.client('logs', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

# Configure logging to CloudWatch
handler = logging.StreamHandler()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom metrics
def put_metric(metric_name, value, unit='Count'):
    cloudwatch.put_metric_data(
        Namespace='{project_type}-app',
        MetricData=[
            {{
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow(),
                'Dimensions': [
                    {{'Name': 'Environment', 'Value': 'production'}},
                    {{'Name': 'Service', 'Value': '{project_type}'}}
                ]
            }}
        ]
    )

# Track business metrics
@app.route('/api/purchase')
def purchase():
    result = process_purchase()
    put_metric('PurchaseCount', 1)
    put_metric('PurchaseAmount', result['amount'], 'None')
    return {{'status': 'ok'}}
```

#### Node.js with AWS SDK
```javascript
const AWS = require('aws-sdk');
const cloudwatch = new AWS.CloudWatch();

async function putMetric(metricName, value) {{
  const params = {{
    Namespace: '{project_type}-app',
    MetricData: [{{
      MetricName: metricName,
      Value: value,
      Unit: 'Count',
      Timestamp: new Date(),
      Dimensions: [
        {{ Name: 'Environment', Value: 'production' }},
        {{ Name: 'Service', Value: '{project_type}' }}
      ]
    }}]
  }};

  return cloudwatch.putMetricData(params).promise();
}}

app.post('/api/purchase', async (req, res) => {{
  const result = await processPurchase();
  await putMetric('PurchaseCount', 1);
  res.json({{ status: 'ok' }});
}});
```

### 4. Create CloudWatch Dashboards

#### Via CLI
```bash
aws cloudwatch put-dashboard \\
  --dashboard-name {project_type}-monitoring \\
  --dashboard-body file://dashboard.json
```

#### Dashboard JSON (`dashboard.json`)
```json
{{
  "widgets": [
    {{
      "type": "metric",
      "properties": {{
        "metrics": [
          [ "AWS/ApplicationELB", "TargetResponseTime", {{ "stat": "Average" }} ],
          [ ".", "RequestCount", {{ "stat": "Sum" }} ],
          [ ".", "HTTPCode_Target_5XX_Count", {{ "stat": "Sum" }} ]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Application Load Balancer Metrics"
      }}
    }},
    {{
      "type": "log",
      "properties": {{
        "query": "fields @timestamp, @message | stats count() as error_count by @message | filter @message like /ERROR/",
        "region": "us-east-1",
        "title": "Error Log Count"
      }}
    }}
  ]
}}
```

### 5. CloudWatch Insights Queries

#### Common Queries
```sql
-- Error rate by endpoint
fields @timestamp, @message, httpRequest.path
| filter @message like /ERROR/
| stats count() as error_count by httpRequest.path

-- Response time percentiles
fields responseTime
| stats pct(responseTime, 50) as p50,
        pct(responseTime, 95) as p95,
        pct(responseTime, 99) as p99

-- Request rate
fields @timestamp
| stats count() as requests by bin(5m)

-- Top errors
fields @message
| filter @message like /ERROR/
| stats count() as count by @message
| sort count desc
| limit 10

-- Database query latency
fields queryDuration
| stats avg(queryDuration), max(queryDuration), pct(queryDuration, 95)
```

## Alarming

### Create Metric Alarm
```bash
aws cloudwatch put-metric-alarm \\
  --alarm-name {project_type}-high-error-rate \\
  --alarm-description "Alert on high error rate" \\
  --metric-name HTTPCode_Target_5XX_Count \\
  --namespace AWS/ApplicationELB \\
  --statistic Sum \\
  --period 300 \\
  --threshold 10 \\
  --comparison-operator GreaterThanThreshold \\
  --evaluation-periods 2 \\
  --alarm-actions arn:aws:sns:us-east-1:123456789012:alert-topic
```

### Recommended Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| Error Rate | > 1% | > 5% |
| P95 Latency | > 500ms | > 2s |
| CPU Usage | > 70% | > 90% |
| Memory Usage | > 80% | > 95% |
| Disk Space | < 20% | < 10% |
| Database Connections | > 80% | > 95% |

## Cost Optimization

### CloudWatch Pricing
- **Logs**: $0.50 per GB ingested, $0.03 per GB stored
- **Metrics**: $0.30 per custom metric
- **Dashboards**: Free for up to 3 dashboards
- **Log Insights**: $0.005 per GB scanned

### Cost Reduction
1. Set appropriate log retention (7-30 days)
2. Use metric filters to drop unnecessary logs
3. Aggregate metrics at application level
4. Use log groups to organize logs
5. Archive old logs to S3 Glacier

## Best Practices

✓ Use structured logging (JSON format)
✓ Include correlation IDs for request tracing
✓ Set up cross-account monitoring for multi-account setups
✓ Use metric math for complex calculations
✓ Create composite alarms for multi-metric conditions
✓ Monitor CloudWatch itself for quota usage
✗ Don't log PII (personally identifiable information)
✗ Don't create excessive custom metrics
✗ Don't set alarm thresholds without historical context
✗ Don't forget to test alarm notifications

## Troubleshooting

### Logs not appearing
1. Check IAM role has `logs:PutLogEvents` permission
2. Verify log group and stream exist
3. Check agent is running: `sudo systemctl status amazon-cloudwatch-agent`
4. Review agent logs: `/opt/aws/amazon-cloudwatch-agent/logs/`

### Missing metrics
1. Verify CloudWatch namespace: `aws cloudwatch list-metrics --namespace {project_type}-app`
2. Check IAM permissions: `cloudwatch:PutMetricData`
3. Verify timestamp is recent (within last hour)
"""

    def _generate_elasticsearch_setup_guide(self, project_type: str) -> str:
        """Generate detailed Elasticsearch setup instructions."""
        return f"""
# Elasticsearch (ELK Stack) Monitoring Setup Guide ({project_type.title()} Application)

## Overview
The ELK Stack (Elasticsearch, Logstash, Kibana) provides comprehensive log aggregation,
search, and visualization. Elasticsearch is optimized for full-text search on large
volumes of data.

## Architecture
```
Your Application
      ↓
Filebeat/Logstash (log collection & processing)
      ↓
Elasticsearch (indexing & storage)
      ↓
Kibana (visualization & dashboards)
```

## Installation

### 1. Install Elasticsearch

#### Using Docker
```dockerfile
# docker-compose.yml
version: '3.8'
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.5.0
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
    volumes:
      - es-data:/usr/share/elasticsearch/data

  kibana:
    image: docker.elastic.co/kibana/kibana:8.5.0
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200

  filebeat:
    image: docker.elastic.co/beats/filebeat:8.5.0
    command: filebeat -e -strict.perms=false
    volumes:
      - ./filebeat.yml:/usr/share/filebeat/filebeat.yml
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro

volumes:
  es-data:
    driver: local
```

#### Using Linux (Ubuntu)
```bash
# Add Elastic repository
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list

# Install Elasticsearch
sudo apt-get update
sudo apt-get install elasticsearch

# Start service
sudo systemctl enable elasticsearch
sudo systemctl start elasticsearch

# Verify installation
curl -u elastic:changeme http://localhost:9200/
```

### 2. Install Logstash (Log Processing)

```bash
# Install Logstash
sudo apt-get install logstash

# Create pipeline configuration
sudo tee /etc/logstash/conf.d/{project_type}.conf > /dev/null <<EOF
input {{
  file {{
    path => "/var/log/app.log"
    start_position => "beginning"
    codec => json
  }}
}}

filter {{
  if [type] == "json" {{
    json {{
      source => "message"
    }}
  }}

  # Parse timestamps
  date {{
    match => [ "timestamp", "ISO8601" ]
  }}

  # Add environment tag
  mutate {{
    add_field => {{ "environment" => "production" }}
    add_field => {{ "service" => "{project_type}" }}
  }}
}}

output {{
  elasticsearch {{
    hosts => ["localhost:9200"]
    index => "{project_type}-%{{+YYYY.MM.dd}}"
  }}

  # Also output to stdout for debugging
  stdout {{ codec => rubydebug }}
}}
EOF

# Start Logstash
sudo systemctl start logstash
```

### 3. Install Filebeat (Log Collection)

```bash
# Install Filebeat
sudo apt-get install filebeat

# Configure Filebeat (/etc/filebeat/filebeat.yml)
sudo tee /etc/filebeat/filebeat.yml > /dev/null <<EOF
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/app.log
    fields:
      service: {project_type}
      environment: production
    json.message_key: message
    json.keys_under_root: true
    json.add_error_key: true

output.elasticsearch:
  hosts: ["localhost:9200"]
  index: "{project_type}-%{{+yyyy.MM.dd}}"

processors:
  - add_kubernetes_metadata: ~
  - add_docker_metadata: ~
EOF

# Start Filebeat
sudo systemctl enable filebeat
sudo systemctl start filebeat
```

### 4. Install Kibana (Visualization)

```bash
# Install Kibana
sudo apt-get install kibana

# Configure Kibana (/etc/kibana/kibana.yml)
sudo sed -i 's/^#elasticsearch.hosts:/elasticsearch.hosts: ["localhost:9200"]/' /etc/kibana/kibana.yml

# Start Kibana
sudo systemctl enable kibana
sudo systemctl start kibana

# Access Kibana at http://localhost:5601
```

## Application Logging Configuration

### Python (Python-json-logger)
```python
import logging
import json
from pythonjsonlogger import jsonlogger

# Configure JSON logging
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# Log with context
logger.info(
    "User login",
    extra={{
        "user_id": "123",
        "ip_address": "192.168.1.1",
        "success": True,
        "duration_ms": 245
    }}
)
```

### Node.js (winston)
```javascript
const winston = require('winston');
const {{ ElasticsearchTransport }} = require('winston-elasticsearch');

const esTransportOpts = {{
  level: 'info',
  clientOpts: {{ node: 'http://localhost:9200' }},
  index: '{project_type}-logs',
}};

const logger = winston.createLogger({{
  transports: [
    new ElasticsearchTransport(esTransportOpts)
  ]
}});

logger.info('User login', {{
  userId: '123',
  ipAddress: '192.168.1.1',
  success: true,
  durationMs: 245
}});
```

## Kibana Dashboards

### Create Visualization
1. Open Kibana (http://localhost:5601)
2. Discover → Select index pattern `{project_type}-*`
3. Explore logs in detail
4. Create visualizations:
   - Error rate by endpoint
   - Request count over time
   - Top error messages
   - Response time distribution

### Create Dashboard
1. Dashboard → Create new dashboard
2. Add visualizations
3. Set auto-refresh (5s - 1h)
4. Save dashboard

### Sample Queries
```json
// Error logs in last hour
{{
  "query": {{
    "bool": {{
      "must": [
        {{ "term": {{ "level": "ERROR" }} }},
        {{ "range": {{ "@timestamp": {{ "gte": "now-1h" }} }} }}
      ]
    }}
  }}
}}

// Slow queries (>1000ms)
{{
  "query": {{
    "range": {{
      "duration_ms": {{ "gte": 1000 }}
    }}
  }}
}}

// Top errors
{{
  "aggs": {{
    "error_messages": {{
      "terms": {{ "field": "message.keyword", "size": 10 }}
    }}
  }}
}}
```

## Index Management

### Create Index Template
```bash
curl -X PUT "localhost:9200/_index_template/{project_type}-template" -H 'Content-Type: application/json' -d'
{{
  "index_patterns": ["{project_type}-*"],
  "template": {{
    "settings": {{
      "number_of_shards": 1,
      "number_of_replicas": 0,
      "index.lifecycle.name": "{project_type}-policy",
      "index.lifecycle.rollover_alias": "{project_type}-logs"
    }},
    "mappings": {{
      "properties": {{
        "@timestamp": {{ "type": "date" }},
        "message": {{ "type": "text" }},
        "level": {{ "type": "keyword" }},
        "service": {{ "type": "keyword" }},
        "host": {{ "type": "keyword" }},
        "duration_ms": {{ "type": "long" }}
      }}
    }}
  }}
}}
'
```

### Index Lifecycle Management (ILM)
```bash
curl -X PUT "localhost:9200/_ilm/policy/{project_type}-policy" -H 'Content-Type: application/json' -d'
{{
  "policy": "{project_type}-policy",
  "phases": {{
    "hot": {{
      "min_age": "0ms",
      "actions": {{
        "rollover": {{ "max_primary_store_size": "50GB", "max_age": "30d" }}
      }}
    }},
    "warm": {{
      "min_age": "7d",
      "actions": {{
        "set_priority": {{ "priority": 50 }}
      }}
    }},
    "cold": {{
      "min_age": "30d",
      "actions": {{
        "set_priority": {{ "priority": 0 }}
      }}
    }},
    "delete": {{
      "min_age": "60d",
      "actions": {{
        "delete": {{}}
      }}
    }}
  }}
}}
'
```

## Alerting

### Create Alert (using X-Pack)
```bash
curl -X POST "localhost:9200/_plugins/_alerting/monitors" -H 'Content-Type: application/json' -d'
{{
  "name": "{project_type}-high-error-rate",
  "type": "monitor",
  "enabled": true,
  "schedule": {{
    "period": {{
      "interval": 5,
      "unit": "MINUTES"
    }}
  }},
  "inputs": [{{
    "search": {{
      "indices": ["{project_type}-*"],
      "query": {{
        "size": 0,
        "query": {{
          "bool": {{
            "must": [
              {{ "term": {{ "level": "ERROR" }} }},
              {{ "range": {{ "@timestamp": {{ "gte": "now-5m" }} }} }}
            ]
          }}
        }},
        "aggs": {{
          "error_count": {{ "value_count": {{ "field": "_id" }} }}
        }}
      }}
    }}
  }}],
  "triggers": [{{
    "name": "error-rate-trigger",
    "severity": "1",
    "condition": {{
      "script": {{
        "source": "params.error_count > 100"
      }}
    }},
    "actions": [{{
      "name": "alert-action",
      "destination_id": "slack-channel",
      "message_template": {{
        "source": "High error rate detected: {{{{ctx.results[0].aggregations.error_count.value}}}}"
      }}
    }}]
  }}]
}}
'
```

## Performance Tuning

### JVM Heap Settings
```bash
# Edit /etc/elasticsearch/jvm.options
-Xms4g
-Xmx4g
```

### Index Optimization
```bash
# Force merge index
curl -X POST "localhost:9200/{project_type}-2024.01.01/_forcemerge?max_num_segments=1"

# Reduce replica count
curl -X PUT "localhost:9200/{project_type}-*/_settings" -H 'Content-Type: application/json' -d'
{{
  "settings": {{
    "number_of_replicas": 0
  }}
}}
'
```

## Storage & Retention

### Archive to S3
```bash
# Configure snapshot repository
curl -X PUT "localhost:9200/_snapshot/s3-repo" -H 'Content-Type: application/json' -d'
{{
  "type": "s3",
  "settings": {{
    "bucket": "my-elasticsearch-backups",
    "base_path": "snapshots",
    "region": "us-east-1"
  }}
}}
'

# Create snapshot
curl -X PUT "localhost:9200/_snapshot/s3-repo/{project_type}-snapshot"
```

## Best Practices

✓ Use structured JSON logging
✓ Include correlation IDs for request tracing
✓ Implement index lifecycle management (ILM)
✓ Set up automated snapshots for backups
✓ Monitor Elasticsearch cluster health
✓ Use appropriate index sharding strategy
✓ Archive old indices to cold storage
✓ Implement role-based access control
✗ Don't store PII in plaintext
✗ Don't use dynamic index creation in production
✗ Don't neglect cluster monitoring
✗ Don't use unbounded retention periods

## Troubleshooting

### Elasticsearch won't start
1. Check Java is installed: `java -version`
2. Verify disk space available
3. Check `/var/log/elasticsearch/elasticsearch.log`
4. Verify port 9200 is available

### High memory usage
1. Reduce JVM heap size if appropriate
2. Delete old indices
3. Implement ILM policies
4. Check for runaway aggregations

### Slow queries
1. Use Kibana DevTools to profile queries
2. Add indices for frequently filtered fields
3. Optimize shard count (not too many!)
4. Use date histogram filters for time ranges
"""

    def get_summary(self) -> str:
        """Get human-readable summary of all generated guides.

        Returns:
            Formatted summary of monitoring platform options
        """
        if not self.guides:
            return "No guides generated. Call generate_*_guide() methods first."

        summary = "# Monitoring Setup Guides Summary\n\n"
        summary += "| Platform | Setup Time | Cost/Month | Best For |\n"
        summary += "|----------|-----------|------------|----------|\n"

        for guide in self.guides.values():
            cost_str = f"${guide.cost_per_month_usd:.0f}" if guide.cost_per_month_usd else "Free*"
            summary += (
                f"| {guide.platform_name} | "
                f"{guide.estimated_setup_time_hours}h | "
                f"{cost_str} | "
                f"{guide.best_for} |\n"
            )

        summary += "\n*Free platforms require infrastructure costs (self-hosted)\n"
        return summary

    def export_guides_to_json(self, output_path: str = "monitoring_guides.json") -> str:
        """Export all generated guides to JSON file.

        Args:
            output_path: Path to save JSON file

        Returns:
            Path to saved JSON file
        """
        import json
        from pathlib import Path

        if not self.guides:
            raise ValueError("No guides generated. Call generate_*_guide() first.")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        guides_data = {
            name: {
                "platform_name": guide.platform_name,
                "description": guide.description,
                "setup_difficulty": guide.setup_difficulty,
                "estimated_setup_time_hours": guide.estimated_setup_time_hours,
                "cost_per_month_usd": guide.cost_per_month_usd,
                "metrics_collected": guide.metrics_collected,
                "log_aggregation_included": guide.log_aggregation_included,
                "alerting_included": guide.alerting_included,
                "dashboard_included": guide.dashboard_included,
                "best_for": guide.best_for,
                "generated_at": guide.generated_at,
            }
            for name, guide in self.guides.items()
        }

        with open(output_file, "w") as f:
            json.dump(guides_data, f, indent=2)

        return str(output_file)
