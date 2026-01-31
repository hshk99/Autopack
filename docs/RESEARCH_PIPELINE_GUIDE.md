# Research Pipeline User Guide

**Version**: 1.0
**Last Updated**: 2026-01-31
**Status**: Complete

This guide provides comprehensive documentation for using the Autopack Research Pipeline, including API usage, result interpretation, and practical examples.

---

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [API Modes](#api-modes)
4. [Bootstrap Research Sessions](#bootstrap-research-sessions)
5. [Full Research Sessions](#full-research-sessions)
6. [Analysis Results](#analysis-results)
7. [Practical Examples](#practical-examples)
8. [Interpreting Analysis Results](#interpreting-analysis-results)
9. [Leveraging Artifacts](#leveraging-artifacts)
10. [Troubleshooting](#troubleshooting)
11. [FAQ](#faq)

---

## Overview

The Autopack Research Pipeline is a comprehensive research system that analyzes project ideas and generates strategic guidance. It provides:

- **Idea Parsing**: Parse raw project ideas into structured intent
- **Bootstrap Research**: Rapid research with market, competitive, and technical analysis
- **Advanced Analysis**: Cost-effectiveness, build-vs-buy, research state tracking, and followup trigger identification
- **Artifact Generation**: Auto-generated deployment configs, CI/CD pipelines, and runbooks
- **Caching**: 24-hour TTL caching to avoid redundant research

### Key Components

| Component | Purpose |
|-----------|---------|
| **Orchestrator** | Coordinates research workflows and analysis |
| **Idea Parser** | Converts raw text into structured project intent |
| **Bootstrap Session** | Runs parallel research phases (market, competitive, technical) |
| **Analysis Modules** | Cost, build-vs-buy, research state, followup triggers |
| **Cache** | 24-hour TTL caching with idea-based hashing |
| **API Router** | REST API with tri-state mode system |

---

## Getting Started

### Prerequisites

- Autopack server running (typically `http://localhost:8000`)
- Research API enabled (check `/research/mode` endpoint)
- API key or authentication token (if required)

### Quick Start

The simplest way to use the research pipeline is through the Bootstrap API:

```bash
# 1. Start a bootstrap research session
curl -X POST http://localhost:8000/api/research/bootstrap \
  -H "Content-Type: application/json" \
  -d '{
    "idea_text": "Build an AI-powered code review tool for GitHub repositories",
    "use_cache": true,
    "parallel": true
  }'

# Response:
{
  "session_id": "abc-123-def",
  "status": "in_progress",
  "message": "Bootstrap session started. Research phases in progress."
}

# 2. Check bootstrap status
curl http://localhost:8000/api/research/bootstrap/abc-123-def/status

# 3. Get draft anchor when complete
curl http://localhost:8000/api/research/bootstrap/abc-123-def/draft_anchor
```

---

## API Modes

The Research API uses a tri-state mode system for controlled access:

### Mode: DISABLED (Default in Production)

- All endpoints return `503 Service Unavailable`
- No research functionality available
- **Set via**: `RESEARCH_API_MODE=disabled`

### Mode: BOOTSTRAP_ONLY (Limited Production)

- Only bootstrap endpoints accessible
- Safe for production with limited scope
- Accessible endpoints:
  - `POST /research/bootstrap` - Start bootstrap research
  - `GET /research/bootstrap/{id}/status` - Check status
  - `GET /research/bootstrap/{id}/draft_anchor` - Get results
- **Set via**: `RESEARCH_API_MODE=bootstrap_only`

### Mode: FULL (Development Only)

- All endpoints accessible
- Includes advanced analysis and cache management
- Safety gates enforce:
  - Rate limiting (30 requests/minute by default)
  - Request size limits (10KB default)
  - Audit logging
- **Set via**: `RESEARCH_API_MODE=full`

### Configuration

```bash
# Set via environment variable
export RESEARCH_API_MODE=bootstrap_only

# Or programmatically in code
os.environ['RESEARCH_API_MODE'] = 'full'

# Check current mode
curl http://localhost:8000/api/research/mode
```

Response:
```json
{
  "mode": "bootstrap_only",
  "bootstrap_endpoints_enabled": true,
  "full_endpoints_enabled": false,
  "safety_gates": {
    "rate_limit_requests_per_minute": 30,
    "max_request_size_bytes": 10240,
    "audit_logging_enabled": true
  }
}
```

---

## Bootstrap Research Sessions

Bootstrap sessions are the primary entry point for the research pipeline. They run parallel research phases and are cacheable.

### Starting a Bootstrap Session

**Endpoint**: `POST /research/bootstrap`

**Request**:
```json
{
  "idea_text": "Build a SaaS platform for automated content management",
  "use_cache": true,
  "parallel": true
}
```

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `idea_text` | string | required | Raw idea text (min 10 chars) |
| `use_cache` | boolean | true | Use cached results if available |
| `parallel` | boolean | true | Execute phases in parallel |

**Response** (201 Created):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "in_progress",
  "message": "Bootstrap session started. Research phases in progress."
}
```

**Possible Status Values**:
- `in_progress` - Research phases executing
- `completed` - All phases completed successfully
- `partial` - Some phases failed but completed overall

### Checking Bootstrap Status

**Endpoint**: `GET /research/bootstrap/{session_id}/status`

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "current_phase": "market_research",
  "is_complete": true,
  "completed_phases": ["market_research", "competitive_analysis", "technical_feasibility"],
  "failed_phases": [],
  "synthesis": {
    "market_size": "$2.5B TAM",
    "key_competitors": ["Contentful", "Strapi"],
    "technical_complexity": "medium"
  }
}
```

### Getting Draft Anchor

**Endpoint**: `GET /research/bootstrap/{session_id}/draft_anchor`

Once bootstrap is complete, get the structured anchor for next steps:

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "anchor": {
    "project_type": "SaaS",
    "primary_market": "content_teams",
    "revenue_model": "subscription",
    "key_differentiators": ["AI-powered recommendations", "Content versioning"]
  },
  "clarifying_questions": [
    "What's your target team size?",
    "Budget for development?"
  ],
  "confidence_report": {
    "market_research": {
      "score": 0.85,
      "reasoning": "Strong market demand signals"
    },
    "competitive_analysis": {
      "score": 0.72,
      "reasoning": "Several competitors but differentiation possible"
    }
  }
}
```

---

## Full Research Sessions

Full mode provides advanced analysis capabilities (requires `RESEARCH_API_MODE=full`).

### Creating a Full Session

**Endpoint**: `POST /research/full/session`

**Request**:
```json
{
  "title": "AI Code Review Platform",
  "description": "An intelligent platform for automated code review using AI models with GitHub integration",
  "objectives": [
    "Understand market demand for AI code review",
    "Identify key technical challenges",
    "Evaluate build vs buy options for ML models"
  ]
}
```

**Response** (201 Created):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "message": "Full research session started. Use /full/session/{session_id}/validate to validate."
}
```

### Validating a Session

**Endpoint**: `POST /research/full/session/{session_id}/validate`

Runs validation checks including evidence, recency, and quality validation:

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "validation_status": "validated",
  "message": "Session validated successfully",
  "checks_passed": ["evidence_validation", "recency_validation", "quality_validation"],
  "checks_failed": []
}
```

### Publishing a Session

**Endpoint**: `POST /research/full/session/{session_id}/publish`

Publish validated research findings:

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "published": true,
  "message": "Research session published successfully."
}
```

---

## Analysis Results

Full mode unlocks detailed analysis across multiple dimensions.

### Cost Effectiveness Analysis

**Endpoint**: `GET /research/full/session/{session_id}/analysis/cost-effectiveness`

Provides comprehensive cost projections and optimization strategies.

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "executive_summary": {
    "total_year_1_cost": 450000,
    "total_year_3_cost": 1200000,
    "total_year_5_cost": 2100000,
    "primary_cost_drivers": ["AI model API costs", "Infrastructure", "Development"],
    "key_recommendations": [
      "Use tiered AI model strategy",
      "Implement caching to reduce API calls",
      "Start with managed infrastructure, migrate to Kubernetes at scale"
    ],
    "cost_confidence": "high"
  },
  "component_analysis": [
    {
      "component": "AI Model API",
      "decision": "BUY",
      "service": "OpenAI API + fallback to open-source",
      "year_1_cost": 120000,
      "year_5_cost": 250000,
      "vs_build_savings": 180000,
      "rationale": "Faster time-to-market, reduce training complexity"
    },
    {
      "component": "Infrastructure",
      "decision": "HYBRID",
      "service": "AWS managed services + custom optimization",
      "year_1_cost": 180000,
      "year_5_cost": 450000,
      "vs_build_savings": 80000,
      "rationale": "Balance between managed services and custom optimization"
    }
  ],
  "cost_optimization_roadmap": [
    {
      "phase": "Year 1",
      "optimizations": ["Implement caching layer", "Auto-scaling policies"],
      "potential_savings": "15%"
    },
    {
      "phase": "Year 2",
      "optimizations": ["Custom model fine-tuning", "Regional deployment"],
      "potential_savings": "25%"
    }
  ],
  "generated_at": "2026-01-31T12:00:00Z"
}
```

**Key Fields**:
- `executive_summary` - High-level cost overview and recommendations
- `component_analysis` - Detailed build vs buy decisions per component
- `cost_optimization_roadmap` - Phased cost reduction strategies
- `infrastructure_projection` - Long-term infrastructure cost trajectory
- `risk_adjusted_costs` - Costs accounting for technical and market risks

### Build vs Buy Analysis

**Endpoint**: `GET /research/full/session/{session_id}/analysis/build-vs-buy`

Component-level build vs buy decisions:

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "decisions": [
    {
      "component": "Authentication",
      "recommendation": "BUY",
      "confidence": 0.95,
      "build_cost": {
        "initial_cost": 50000,
        "monthly_recurring": 2000,
        "year_1_total": 74000
      },
      "buy_cost": {
        "initial_cost": 0,
        "monthly_recurring": 500,
        "year_1_total": 6000
      },
      "build_time_weeks": 12,
      "buy_integration_time_weeks": 1,
      "risks": [
        "Security vulnerabilities if implemented incorrectly",
        "Ongoing maintenance burden"
      ],
      "rationale": "Auth0 or similar providers offer battle-tested solutions",
      "strategic_importance": "supporting",
      "key_factors": ["security_critical", "commodity_service"]
    }
  ],
  "overall_recommendation": "HYBRID",
  "total_build_cost": 500000,
  "total_buy_cost": 250000,
  "generated_at": "2026-01-31T12:00:00Z"
}
```

**Decision Framework**:
- `BUY`: External solution is more cost-effective or specialized
- `BUILD`: Internal development provides strategic advantage
- `HYBRID`: Combination approach (use vendor for some, build custom for others)

### Research State

**Endpoint**: `GET /research/full/session/{session_id}/analysis/research-state`

Track research coverage and identified gaps:

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "gaps": [
    {
      "gap_id": "gap-001",
      "gap_type": "coverage",
      "category": "market_sizing",
      "description": "Need more granular TAM breakdown by customer segment",
      "priority": "high",
      "suggested_queries": [
        "enterprise content management market size 2026",
        "SMB content tools market growth"
      ],
      "identified_at": "2026-01-31T12:00:00Z",
      "status": "open"
    }
  ],
  "gap_count": 3,
  "critical_gaps": 1,
  "coverage_metrics": {
    "market_coverage": 0.85,
    "competitive_coverage": 0.72,
    "technical_coverage": 0.90
  },
  "completed_queries": 24,
  "discovered_sources": 18,
  "research_depth": "MEDIUM",
  "generated_at": "2026-01-31T12:00:00Z"
}
```

### Followup Research Triggers

**Endpoint**: `GET /research/full/session/{session_id}/analysis/followup-triggers`

Identify uncertainties requiring additional research:

**Response**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "triggers": [
    {
      "trigger_id": "trigger-001",
      "trigger_type": "gap",
      "priority": "critical",
      "reason": "Regulatory landscape unclear for AI-powered code analysis",
      "source_finding": "GDPR compliance concerns mentioned in 3 sources",
      "research_plan": {
        "focus_areas": ["data_privacy", "compliance_frameworks"],
        "estimated_time_minutes": 120,
        "suggested_agents": ["legal_policy_agent", "compliance_checker"]
      },
      "created_at": "2026-01-31T12:00:00Z",
      "addressed": false
    }
  ],
  "should_research": true,
  "triggers_selected": 1,
  "total_estimated_time": 120,
  "generated_at": "2026-01-31T12:00:00Z"
}
```

### Aggregated Analysis

**Endpoint**: `GET /research/full/session/{session_id}/analysis`

Get all analysis results in a single call:

```bash
curl "http://localhost:8000/api/research/full/session/abc-123/analysis?include_cost_effectiveness=true&include_build_vs_buy=true&include_followup_triggers=true&include_research_state=true"
```

---

## Practical Examples

### Example 1: Evaluating a SaaS Idea

```bash
#!/bin/bash

# Step 1: Start research
SESSION=$(curl -s -X POST http://localhost:8000/api/research/bootstrap \
  -H "Content-Type: application/json" \
  -d '{
    "idea_text": "A workflow automation platform for marketing teams to manage social media scheduling, content calendars, and team collaboration",
    "use_cache": true,
    "parallel": true
  }' | jq -r '.session_id')

echo "Session ID: $SESSION"

# Step 2: Wait for completion
sleep 30

# Step 3: Check status
curl -s http://localhost:8000/api/research/bootstrap/$SESSION/status | jq '.'

# Step 4: Get draft anchor
curl -s http://localhost:8000/api/research/bootstrap/$SESSION/draft_anchor | jq '.'
```

### Example 2: Deep Cost Analysis

```bash
#!/bin/bash

SESSION=$1

# Get cost analysis
curl -s "http://localhost:8000/api/research/full/session/$SESSION/analysis/cost-effectiveness?include_optimization_roadmap=true" \
  | jq '{
    "year_1_cost": .executive_summary.total_year_1_cost,
    "year_5_cost": .executive_summary.total_year_5_cost,
    "primary_drivers": .executive_summary.primary_cost_drivers,
    "recommendations": .executive_summary.key_recommendations
  }'
```

### Example 3: Component-Level Build vs Buy

```bash
#!/bin/bash

SESSION=$1

# Get build vs buy analysis filtered for critical components
curl -s "http://localhost:8000/api/research/full/session/$SESSION/analysis/build-vs-buy" \
  | jq '.decisions[] | select(.strategic_importance == "core") | {
    component: .component,
    recommendation: .recommendation,
    year_1_cost_buy: .buy_cost.year_1_total,
    year_1_cost_build: .build_cost.year_1_total,
    savings: (.build_cost.year_1_total - .buy_cost.year_1_total)
  }'
```

---

## Interpreting Analysis Results

### Cost Effectiveness Analysis

**What it tells you**:
- Total cost of ownership (Year 1, 3, 5)
- Component-level cost drivers
- Build vs buy recommendations per component
- Long-term optimization strategies

**How to use it**:
1. Review `executive_summary` for high-level costs
2. Identify primary cost drivers
3. Focus on components with highest build vs buy savings potential
4. Plan phased cost optimization per roadmap

**Confidence levels**:
- `high` (0.8+): Market data is abundant and consistent
- `medium` (0.5-0.8): Mixed signals or limited data
- `low` (<0.5): Significant uncertainty, needs more research

### Build vs Buy Analysis

**Understanding recommendations**:

| Recommendation | Meaning | Consider If |
|---|---|---|
| **BUY** | Buy from external vendor | Cost-effective, non-differentiating |
| **BUILD** | Build in-house | Strategic advantage, core capability |
| **HYBRID** | Use vendor + custom development | Some parts commodity, others strategic |

**Key decision factors**:
- **Cost differential**: 3-5x difference usually favors BUY
- **Time-to-market**: BUILD takes longer but provides flexibility
- **Strategic importance**: Core capabilities → BUILD, supporting → BUY
- **Maintenance burden**: Consider long-term TCO, not just initial cost

### Research State

**Gap priority guidance**:
- **Critical**: Must address before proceeding (affects core assumptions)
- **High**: Should address if time permits (improves confidence)
- **Medium**: Nice to have (increases detail, not critical)
- **Low**: Exploratory (bonus learning)

**Coverage metrics interpretation**:
- `0.9+`: Comprehensive research, high confidence
- `0.7-0.9`: Good coverage, minor gaps
- `0.5-0.7`: Moderate coverage, some uncertainty
- `<0.5`: Preliminary research, needs more work

**Research depth levels**:
- `SHALLOW`: Quick overview, 5-10 queries
- `MEDIUM`: Balanced coverage, 15-25 queries
- `DEEP`: Comprehensive analysis, 40+ queries

### Followup Triggers

**Trigger types**:
- `gap`: Missing information needed for decision-making
- `uncertainty`: Conflicting signals or unclear trends
- `risk`: Potential problems requiring investigation
- `opportunity`: Upside potential worth exploring

**Priority**: Use to schedule follow-up research cycles:
1. Address `critical` triggers immediately
2. Schedule `high` triggers for next cycle
3. Monitor `medium` triggers
4. Consider `low` triggers for long-term research

---

## Leveraging Artifacts

The research pipeline generates multiple artifact types for downstream use:

### Deployment Configurations

Post-build artifact generator creates:
- Docker configurations
- Kubernetes manifests
- Infrastructure-as-Code (Terraform, CloudFormation)
- Environment variable templates

**Usage**:
```bash
# Export deployment configs to file
curl http://localhost:8000/api/research/full/session/{id}/artifacts/deployment \
  > deployment-config.tar.gz

# Extract and review
tar -xzf deployment-config.tar.gz
cat deployment/docker/Dockerfile
cat deployment/k8s/deployment.yaml
```

### CI/CD Pipelines

Auto-generated GitHub Actions, GitLab CI, or Jenkins pipelines:

**Usage**:
```bash
# Get CI/CD pipeline artifact
curl http://localhost:8000/api/research/full/session/{id}/artifacts/cicd \
  > cicd-pipeline.yaml

# Review generated workflow
cat cicd-pipeline.yaml

# Copy to your repo
cp cicd-pipeline.yaml .github/workflows/pipeline.yml
git add .github/workflows/pipeline.yml
git commit -m "Add AI-generated CI/CD pipeline"
```

### Operational Runbooks

Auto-generated runbooks for:
- Deployment procedures
- Troubleshooting guides
- Scaling strategies
- Monitoring dashboards

**Usage**:
```bash
# Get runbooks
curl http://localhost:8000/api/research/full/session/{id}/artifacts/runbooks \
  > runbooks.md

# Review and customize
cat runbooks.md
# Edit with your specific procedures
```

### SOT (Source of Truth) Summaries

Integrated BUILD_HISTORY.md and ARCHITECTURE_DECISIONS.md summaries:

**Usage**:
1. Review extracted insights
2. Validate against actual implementation
3. Update if project decisions have changed

---

## Troubleshooting

### Bootstrap Session Stuck in Progress

**Symptoms**: Session status stays `in_progress` for more than 5 minutes

**Solutions**:
1. Check server logs for errors
2. Verify all research phases are responding
3. Increase timeout if network is slow
4. Try without parallel execution: `"parallel": false`

```bash
# Restart with sequential execution
curl -X POST http://localhost:8000/api/research/bootstrap \
  -H "Content-Type: application/json" \
  -d '{
    "idea_text": "...",
    "parallel": false
  }'
```

### Cache Not Working

**Symptoms**: Getting fresh results for identical ideas instead of cached results

**Troubleshooting**:
```bash
# Check cache status
curl http://localhost:8000/api/research/full/cache/status

# Verify caching is enabled
# {
#   "cache_enabled": true,
#   "cached_sessions": 5,
#   "cache_ttl_hours": 24
# }

# Clear cache if stale data
curl -X DELETE http://localhost:8000/api/research/full/cache
```

### API Returns 503 Service Unavailable

**Cause**: Research API is disabled or in wrong mode

**Solution**:
```bash
# Check current mode
curl http://localhost:8000/api/research/mode

# Enable appropriate mode
export RESEARCH_API_MODE=bootstrap_only
# or
export RESEARCH_API_MODE=full
```

### Rate Limiting

**Symptoms**: Getting 429 Too Many Requests

**Information**:
- Default limit: 30 requests/minute
- Per-endpoint rate limiting
- Respects HTTP `Retry-After` header

**Solution**:
```bash
# Add delay between requests
for i in {1..5}; do
  curl http://localhost:8000/api/research/bootstrap/{id}/status
  sleep 3  # 3 second delay
done

# Or adjust rate limit in code:
export RESEARCH_API_RATE_LIMIT=60  # 60 req/min
```

### Analysis Endpoints Return Incomplete Data

**Cause**: Session not complete or analysis not run

**Solution**:
```bash
# Verify session is complete
curl http://localhost:8000/api/research/bootstrap/{id}/status | jq '.is_complete'

# If complete, try aggregated endpoint to get all at once
curl "http://localhost:8000/api/research/full/session/{id}/analysis"
```

---

## FAQ

### Q: Can I use the research pipeline for any project type?

**A**: Yes! The pipeline auto-detects project type (SaaS, web app, mobile, CLI tool, library, etc.) and tailors research accordingly.

### Q: How long does bootstrap research take?

**A**: Typically 2-5 minutes depending on:
- Idea complexity
- Network latency
- Available compute resources
- Cache hit vs miss

Enable `parallel: true` for faster results.

### Q: Is my data cached? How long?

**A**: Yes, bootstrap sessions are cached for 24 hours based on idea hash. Identical ideas return cached results within 24 hours. Clear cache if you need fresh results.

```bash
curl -X DELETE http://localhost:8000/api/research/full/cache
```

### Q: Can I run research without caching?

**A**: Yes, set `use_cache: false` when starting:
```json
{
  "idea_text": "...",
  "use_cache": false
}
```

### Q: What's the difference between bootstrap and full sessions?

**A**:
| Aspect | Bootstrap | Full |
|--------|-----------|------|
| **Speed** | Fast (2-5 min) | Slower (as needed) |
| **Analysis** | Basic | Advanced |
| **Available in** | bootstrap_only, full modes | full mode only |
| **Cache** | Yes | Optional |
| **Use case** | Quick validation | Deep analysis |

### Q: Can I export analysis results?

**A**: Yes, all responses are JSON. Export easily:
```bash
curl http://localhost:8000/api/research/full/session/{id}/analysis/cost-effectiveness \
  > cost-analysis.json
```

### Q: How do I interpret confidence scores?

**A**: Confidence represents how certain the analysis is:
- `0.9-1.0`: Very confident, market data abundant
- `0.7-0.9`: Confident, good signal
- `0.5-0.7`: Moderate, mixed signals
- `<0.5`: Low confidence, needs more research

Lower confidence suggests followup research needed.

### Q: Can I integrate research results into my CI/CD?

**A**: Yes! Export artifacts and use in pipelines:
```bash
# In your CI script
ANALYSIS=$(curl http://localhost:8000/api/research/full/session/{id}/analysis)
COST=$(echo $ANALYSIS | jq '.cost_effectiveness.executive_summary.total_year_1_cost')

if [ $COST -gt 500000 ]; then
  echo "High cost project - flagging for review"
fi
```

### Q: What happens if research fails?

**A**: Bootstrap status shows `partial` with `failed_phases`:
```json
{
  "status": "partial",
  "completed_phases": ["market_research"],
  "failed_phases": ["technical_feasibility"]
}
```

Retry with `parallel: false` or check server logs for specific errors.

### Q: Can I use the API programmatically in Python?

**A**: Yes, here's a simple client:
```python
import requests
import json
import time

BASE_URL = "http://localhost:8000/api/research"

class ResearchClient:
    def start_bootstrap(self, idea_text):
        response = requests.post(f"{BASE_URL}/bootstrap", json={
            "idea_text": idea_text,
            "use_cache": True,
            "parallel": True
        })
        return response.json()["session_id"]

    def get_status(self, session_id):
        response = requests.get(f"{BASE_URL}/bootstrap/{session_id}/status")
        return response.json()

    def wait_for_completion(self, session_id, timeout=300):
        start = time.time()
        while time.time() - start < timeout:
            status = self.get_status(session_id)
            if status["is_complete"]:
                return status
            time.sleep(5)
        raise TimeoutError(f"Research did not complete within {timeout}s")

# Usage
client = ResearchClient()
session_id = client.start_bootstrap("Build an AI chatbot for customer support")
result = client.wait_for_completion(session_id)
print(result)
```

### Q: Is there a JavaScript client?

**A**: The API is REST JSON, so you can use any HTTP client:
```javascript
async function startResearch(ideaText) {
  const response = await fetch('http://localhost:8000/api/research/bootstrap', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      idea_text: ideaText,
      use_cache: true,
      parallel: true
    })
  });
  return response.json();
}

async function waitForCompletion(sessionId, maxWaitMs = 300000) {
  const startTime = Date.now();
  while (Date.now() - startTime < maxWaitMs) {
    const response = await fetch(
      `http://localhost:8000/api/research/bootstrap/${sessionId}/status`
    );
    const status = await response.json();
    if (status.is_complete) return status;
    await new Promise(r => setTimeout(r, 5000));
  }
  throw new Error('Research timeout');
}
```

---

## Additional Resources

- [Architecture Documentation](../ARCHITECTURE.md)
- [API Reference](./API_REFERENCE.md)
- [Research System CI/CD Guide](../guides/RESEARCH_CI_FIX_CHECKLIST.md)
- [Troubleshooting Deep Dive](./TROUBLESHOOTING.md)
- [Build vs Buy Analysis Framework](./decision_frameworks.md)

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review server logs: `tail -f logs/autopack.log`
3. Check [Research API Mode](../guides/RESEARCH_QUARANTINE.md) documentation
4. File an issue with session ID and error details

---

**Last Updated**: 2026-01-31
**Maintained by**: Autopack Development Team
