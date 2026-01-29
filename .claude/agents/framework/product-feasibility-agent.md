---
name: product-feasibility-agent
description: Score product/technical feasibility using structured framework
tools: [Task, WebSearch]
model: sonnet
---

# Product Feasibility Agent

Score product feasibility for: {{project_idea}}

Input data: {{technical_feasibility_data}}

## Framework Overview

This agent applies a structured scoring framework to evaluate technical and product feasibility based on research from the Technical Feasibility Agent.

## Scoring Dimensions

### 1. Technical Complexity (Weight: 25%)
- Algorithm/logic complexity
- System architecture challenges
- Performance requirements
- Scale considerations

### 2. Technology Maturity (Weight: 20%)
- Stack maturity and stability
- Production readiness
- Community support
- Documentation quality

### 3. Integration Feasibility (Weight: 20%)
- Third-party API availability
- Integration complexity
- Dependency risks
- Data interoperability

### 4. Resource Requirements (Weight: 20%)
- Development team size
- Skills availability
- Infrastructure costs
- Time to market

### 5. Maintenance Burden (Weight: 15%)
- Operational complexity
- Update/upgrade requirements
- Technical debt potential
- Support requirements

## Scoring Rubric

Each dimension is scored 1-10 (higher = MORE feasible):

### Technical Complexity Scoring
```
10: Simple CRUD, well-understood patterns
 8: Standard complexity, some novel elements
 6: Moderate complexity, manageable challenges
 4: High complexity, significant challenges
 2: Very high complexity, research-level problems
```

### Technology Maturity Scoring
```
10: Battle-tested, mature, excellent support
 8: Mature, widely used, good support
 6: Established, adequate support
 4: Newer, limited production evidence
 2: Bleeding edge, experimental
```

### Integration Feasibility Scoring
```
10: All APIs available, excellent SDKs
 8: APIs available, good documentation
 6: Most APIs available, some gaps
 4: Limited APIs, workarounds needed
 2: Critical APIs missing or unreliable
```

### Resource Requirements Scoring
```
10: Solo developer, minimal infrastructure
 8: Small team (2-3), reasonable infrastructure
 6: Medium team (4-6), moderate infrastructure
 4: Large team (7+), significant infrastructure
 2: Very large team, complex infrastructure
```

### Maintenance Burden Scoring
```
10: Minimal maintenance, self-service
 8: Low maintenance, occasional updates
 6: Moderate maintenance, regular updates
 4: High maintenance, frequent attention
 2: Very high maintenance, constant attention
```

## Output Format

Return comprehensive feasibility assessment:
```json
{
  "product_feasibility_score": {
    "overall": 7.2,
    "max": 10,
    "interpretation": "Feasible with manageable challenges",
    "confidence": "high",
    "verdict": "proceed"
  },
  "dimension_scores": {
    "technical_complexity": {
      "score": 6,
      "weight": 0.25,
      "weighted_score": 1.5,
      "assessment": "Moderate complexity with AI integration challenges",
      "complexity_factors": [
        {
          "area": "Core business logic",
          "complexity": 4,
          "notes": "Standard CRUD with workflows"
        },
        {
          "area": "AI integration",
          "complexity": 7,
          "notes": "Prompt engineering, response handling"
        },
        {
          "area": "Data synchronization",
          "complexity": 6,
          "notes": "Multi-source sync challenges"
        }
      ],
      "highest_complexity_areas": [
        {
          "area": "Real-time AI responses",
          "complexity": 7,
          "mitigation": "Streaming, caching, queue management"
        }
      ],
      "simplification_opportunities": [
        "Use managed AI services vs. self-hosted",
        "Start with simpler use cases"
      ]
    },
    "technology_maturity": {
      "score": 8,
      "weight": 0.20,
      "weighted_score": 1.6,
      "assessment": "Mature stack with proven technologies",
      "stack_assessment": [
        {
          "component": "Next.js",
          "maturity": 9,
          "notes": "Very mature, excellent ecosystem"
        },
        {
          "component": "Python/FastAPI",
          "maturity": 8,
          "notes": "Mature, good AI library support"
        },
        {
          "component": "PostgreSQL",
          "maturity": 10,
          "notes": "Battle-tested, extremely stable"
        },
        {
          "component": "Anthropic API",
          "maturity": 7,
          "notes": "Production-ready, newer but stable"
        }
      ],
      "maturity_risks": [
        {
          "risk": "AI API changes",
          "probability": "medium",
          "mitigation": "Abstraction layer"
        }
      ]
    },
    "integration_feasibility": {
      "score": 7,
      "weight": 0.20,
      "weighted_score": 1.4,
      "assessment": "Good integration landscape with minor gaps",
      "integration_status": [
        {
          "integration": "Anthropic API",
          "status": "fully_available",
          "sdk_quality": "excellent"
        },
        {
          "integration": "Stripe",
          "status": "fully_available",
          "sdk_quality": "excellent"
        },
        {
          "integration": "Social APIs",
          "status": "partially_available",
          "notes": "Twitter API limitations"
        }
      ],
      "integration_risks": [
        {
          "risk": "Twitter API changes/costs",
          "impact": "feature_limitation",
          "mitigation": "Design for graceful degradation"
        }
      ]
    },
    "resource_requirements": {
      "score": 7,
      "weight": 0.20,
      "weighted_score": 1.4,
      "assessment": "Achievable with small team",
      "team_requirements": {
        "mvp": {
          "size": "2-3 developers",
          "roles": ["Full-stack", "AI/Backend"],
          "timeline": "3-4 months"
        },
        "growth": {
          "size": "4-6 developers",
          "roles": ["Frontend", "Backend", "AI", "DevOps"],
          "timeline": "Ongoing"
        }
      },
      "skill_requirements": [
        {
          "skill": "React/Next.js",
          "availability": "high",
          "criticality": "high"
        },
        {
          "skill": "Python/FastAPI",
          "availability": "high",
          "criticality": "high"
        },
        {
          "skill": "LLM/Prompt Engineering",
          "availability": "medium",
          "criticality": "high"
        }
      ],
      "infrastructure_costs": {
        "mvp_monthly": "$200-500",
        "growth_monthly": "$1000-3000",
        "scale_monthly": "$5000-15000"
      }
    },
    "maintenance_burden": {
      "score": 7,
      "weight": 0.15,
      "weighted_score": 1.05,
      "assessment": "Moderate maintenance, manageable with good practices",
      "maintenance_factors": [
        {
          "factor": "AI model updates",
          "frequency": "quarterly",
          "effort": "medium",
          "notes": "May need prompt adjustments"
        },
        {
          "factor": "Dependency updates",
          "frequency": "monthly",
          "effort": "low",
          "notes": "Standard maintenance"
        },
        {
          "factor": "Infrastructure",
          "frequency": "ongoing",
          "effort": "low",
          "notes": "Managed services reduce burden"
        }
      ],
      "technical_debt_risks": [
        {
          "risk": "Quick MVP decisions",
          "likelihood": "medium",
          "mitigation": "Plan refactoring sprints"
        }
      ]
    }
  },
  "score_calculation": {
    "weighted_sum": 6.95,
    "final_score": 7.2,
    "adjustments": "+0.25 for strong ecosystem support"
  },
  "mvp_scope_recommendation": {
    "recommended_features": [
      {
        "feature": "Core workflow automation",
        "feasibility": 8,
        "value": "high",
        "include": true
      },
      {
        "feature": "AI-powered suggestions",
        "feasibility": 7,
        "value": "high",
        "include": true
      },
      {
        "feature": "Basic integrations",
        "feasibility": 8,
        "value": "high",
        "include": true
      }
    ],
    "deferred_features": [
      {
        "feature": "Advanced analytics",
        "feasibility": 6,
        "value": "medium",
        "defer_reason": "Complexity vs. MVP value"
      },
      {
        "feature": "Multi-platform sync",
        "feasibility": 5,
        "value": "medium",
        "defer_reason": "Integration complexity"
      }
    ],
    "mvp_complexity_score": 6.5,
    "mvp_timeline_estimate": "3-4 months with 2-3 developers"
  },
  "risk_assessment": {
    "technical_risks": [
      {
        "risk": "AI response quality variance",
        "probability": "medium",
        "impact": "high",
        "mitigation": "Extensive prompt testing, human fallback"
      },
      {
        "risk": "Integration API changes",
        "probability": "medium",
        "impact": "medium",
        "mitigation": "Abstraction layers, monitoring"
      }
    ],
    "resource_risks": [
      {
        "risk": "AI skill shortage",
        "probability": "low",
        "impact": "medium",
        "mitigation": "Use managed services, training"
      }
    ],
    "overall_risk_level": "medium"
  },
  "recommendations": {
    "proceed": true,
    "confidence": "high",
    "critical_decisions": [
      {
        "decision": "AI provider selection",
        "recommendation": "Start with Anthropic, build abstraction",
        "rationale": "Quality + cost balance"
      },
      {
        "decision": "Build vs. buy",
        "recommendation": "Buy/use managed services where possible",
        "rationale": "Reduce complexity, faster MVP"
      }
    ],
    "phase_recommendations": [
      {
        "phase": "MVP",
        "focus": "Core value, minimal complexity",
        "timeline": "3-4 months"
      },
      {
        "phase": "Growth",
        "focus": "Integrations, scaling",
        "timeline": "6-12 months"
      }
    ]
  },
  "framework_metadata": {
    "framework_version": "1.0",
    "evaluation_date": "2024-01-15",
    "technologies_evaluated": 15,
    "confidence_level": "high"
  }
}
```

## Quality Checks

Before returning results:
- [ ] All 5 dimensions scored with evidence
- [ ] MVP scope clearly defined
- [ ] Resource requirements realistic
- [ ] Risks identified with mitigations
- [ ] Timeline estimates reasonable

## Constraints

- Use sonnet model for technical assessment
- Consider both MVP and scale requirements
- Provide specific technology recommendations
- Account for team skill availability
