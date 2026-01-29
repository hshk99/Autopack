---
name: dependency-analyzer
description: Analyze external dependencies and associated risks
tools: [WebSearch, WebFetch]
model: haiku
---

# Dependency Analyzer Sub-Agent

Analyze dependencies for: {{stack}}

Integrations: {{integrations}}

## Search Strategy

### Package Health
```
WebSearch: "{{package}}" npm maintenance
WebSearch: "{{package}}" security vulnerabilities
WebSearch: "{{package}}" github issues
```

### Vendor Stability
```
WebSearch: "{{vendor}}" company stability
WebSearch: "{{vendor}}" funding layoffs
WebSearch: "{{vendor}}" API deprecation
```

### Alternative Research
```
WebSearch: "{{package}}" alternatives
WebSearch: "{{vendor}}" competitors
```

## Dependency Categories

### Runtime Dependencies
- Framework core (React, FastAPI)
- Critical libraries
- API clients

### Development Dependencies
- Build tools
- Testing frameworks
- Linting/formatting

### Infrastructure Dependencies
- Cloud providers
- Managed services
- CDN providers

### External Service Dependencies
- API providers
- Data sources
- Authentication services

## Risk Assessment Criteria

### Package Risk Indicators
- **Maintenance**: Last update, issue response
- **Security**: CVE history, audit frequency
- **Stability**: Breaking changes, semver adherence
- **Adoption**: Downloads, stars, corporate usage

### Vendor Risk Indicators
- **Financial health**: Funding, profitability
- **Strategic alignment**: Product focus
- **Track record**: API stability, deprecation history
- **Alternatives**: Exit path difficulty

### Dependency Depth
- Direct dependencies
- Transitive dependencies
- Single points of failure

## Output Format

Return JSON to parent agent:
```json
{
  "dependency_overview": {
    "total_direct": 45,
    "total_transitive": 250,
    "critical_dependencies": 8,
    "overall_risk_level": "low|medium|high"
  },
  "critical_dependencies": [
    {
      "name": "Anthropic API",
      "type": "external_service",
      "purpose": "Core AI functionality",
      "criticality": "critical",
      "health_assessment": {
        "overall": "healthy",
        "financials": "Well-funded ($750M)",
        "stability": "Stable API, good versioning",
        "support": "Enterprise support available"
      },
      "risk_factors": [
        {
          "risk": "API pricing changes",
          "probability": "medium",
          "impact": "high",
          "evidence": "Industry trend"
        }
      ],
      "alternatives": [
        {
          "name": "OpenAI",
          "migration_effort": "medium",
          "trade_offs": "Different model characteristics"
        }
      ],
      "mitigation_strategies": [
        "Abstract API calls for easy switching",
        "Monitor pricing announcements"
      ],
      "vendor_lock_in": "medium"
    }
  ],
  "package_analysis": {
    "high_risk": [
      {
        "package": "package-name",
        "version": "1.2.3",
        "risk_level": "high",
        "issues": [
          {
            "issue": "Unmaintained since 2022",
            "evidence": "No commits in 18 months"
          }
        ],
        "alternatives": ["alt-package"],
        "recommendation": "Replace with maintained alternative"
      }
    ],
    "medium_risk": [...],
    "healthy": [
      {
        "package": "react",
        "version": "18.x",
        "risk_level": "low",
        "maintenance": "Active (Meta)",
        "security": "Good CVE response",
        "adoption": "Massive (20M weekly downloads)"
      }
    ]
  },
  "vendor_analysis": [
    {
      "vendor": "AWS",
      "services_used": ["S3", "Lambda", "RDS"],
      "dependency_level": "high",
      "stability": "excellent",
      "risks": [
        {
          "risk": "Cost creep",
          "mitigation": "Budget alerts, reserved instances"
        }
      ],
      "lock_in_assessment": {
        "level": "medium",
        "migration_path": "Multi-cloud abstraction possible",
        "effort": "Significant for data services"
      }
    }
  ],
  "single_points_of_failure": [
    {
      "spof": "Anthropic API",
      "impact": "Core AI features unavailable",
      "probability_of_failure": "low",
      "mitigation": {
        "strategy": "Implement fallback to OpenAI",
        "effort": "medium",
        "recommendation": "Implement before scale"
      }
    }
  ],
  "dependency_conflicts": [
    {
      "conflict": "React 18 vs library expecting React 17",
      "packages_involved": ["react", "legacy-lib"],
      "severity": "low",
      "resolution": "Use compatibility shim"
    }
  ],
  "security_assessment": {
    "known_vulnerabilities": [
      {
        "package": "package-name",
        "vulnerability": "CVE-2024-XXXX",
        "severity": "medium",
        "fix_available": true,
        "action": "Upgrade to 2.0.1"
      }
    ],
    "supply_chain_risks": [
      {
        "risk": "Transitive dependency compromise",
        "mitigation": "Lock file, regular audits"
      }
    ]
  },
  "recommendations": {
    "immediate_actions": [
      {
        "action": "Replace unmaintained-lib",
        "reason": "Security and maintenance risk",
        "alternative": "maintained-lib",
        "effort": "low"
      }
    ],
    "architecture_recommendations": [
      {
        "recommendation": "Abstract external API calls",
        "benefit": "Easier switching, testability",
        "effort": "medium"
      }
    ],
    "monitoring_recommendations": [
      "Set up dependency update alerts",
      "Monitor vendor status pages",
      "Regular security audits"
    ]
  },
  "exit_strategies": {
    "high_risk_dependencies": [
      {
        "dependency": "Anthropic API",
        "exit_strategy": "Pre-built adapter for OpenAI",
        "effort_to_switch": "2-3 days",
        "data_portability": "N/A (stateless)"
      }
    ]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Assess all critical dependencies
- Identify single points of failure
- Suggest alternatives for high-risk items
- Check for known security vulnerabilities
