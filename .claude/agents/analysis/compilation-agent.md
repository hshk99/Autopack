---
name: compilation-agent
description: Compile research into structured formats for downstream use
tools: [Task]
model: sonnet
---

# Compilation Agent

Compile research from: {{all_research_outputs}}

## Purpose

This agent compiles all research findings into structured, standardized formats that can be consumed by Autopack for project setup and intention anchor generation.

## Compilation Outputs

### 1. Research Summary Document
Executive summary for human review

### 2. Structured Data Export
Machine-readable format for Autopack

### 3. Intention Anchor Inputs
Pre-formatted data for anchor generation

### 4. Decision Matrix
Key decisions and recommendations

## Output Formats

### Research Summary (Human-Readable)
```json
{
  "project_overview": {
    "project_idea": "{{project_idea}}",
    "one_liner": "A tool that helps X do Y to achieve Z",
    "research_date": "2024-01-15",
    "confidence_level": "high"
  },
  "executive_summary": {
    "opportunity_assessment": "Strong opportunity in growing market with clear demand and achievable technical requirements",
    "key_strengths": [
      "Large, growing market ($50B TAM, 15% CAGR)",
      "Validated demand through multiple channels",
      "Favorable technology timing with AI maturity",
      "Underserved SMB segment"
    ],
    "key_risks": [
      "Competitive market with well-funded players",
      "Low barriers to entry for fast followers",
      "Dependency on third-party AI APIs"
    ],
    "recommendation": "Proceed with SMB-focused, AI-native approach",
    "confidence": "High - strong cross-domain support"
  },
  "market_summary": {
    "tam": "$50B",
    "sam": "$5B",
    "som_3yr": "$50M",
    "growth_rate": "15% CAGR",
    "market_stage": "Growth",
    "key_trends": [
      "AI automation adoption accelerating",
      "SMB segment growing faster than enterprise",
      "Consolidation in legacy solutions"
    ]
  },
  "competitive_summary": {
    "direct_competitors": 15,
    "market_leader": "Competitor A (30% share)",
    "competitive_intensity": "Medium-high",
    "key_differentiators": [
      "AI-native architecture",
      "SMB pricing",
      "Ease of use"
    ],
    "moat_strategy": "Data + integrations"
  },
  "technical_summary": {
    "feasibility_score": "7.2/10",
    "recommended_stack": {
      "frontend": "Next.js",
      "backend": "Python/FastAPI",
      "database": "PostgreSQL + Redis",
      "ai": "Anthropic Claude API"
    },
    "mvp_timeline": "3-4 months",
    "team_size": "2-3 developers"
  },
  "go_to_market_summary": {
    "target_segment": "SMB (10-200 employees)",
    "primary_channel": "Product-led growth",
    "secondary_channel": "Content marketing",
    "pricing_strategy": "Freemium + $29-79/mo tiers",
    "launch_strategy": "Community-first soft launch"
  }
}
```

### Structured Data Export (Autopack Format)
```json
{
  "autopack_research_export": {
    "version": "1.0",
    "export_date": "2024-01-15T10:30:00Z",
    "project_id": "{{project_id}}",

    "market_data": {
      "size": {
        "tam_usd": 50000000000,
        "sam_usd": 5000000000,
        "som_usd": 50000000,
        "som_timeline_years": 3
      },
      "growth": {
        "cagr_percent": 15,
        "stage": "growth",
        "trajectory": "accelerating"
      },
      "scores": {
        "attractiveness": 7.5,
        "confidence": "high"
      }
    },

    "competitive_data": {
      "landscape": {
        "direct_count": 15,
        "indirect_count": 10,
        "intensity_score": 6.5
      },
      "top_competitors": [
        {
          "name": "Competitor A",
          "market_share_percent": 30,
          "funding_usd": 150000000,
          "strengths": ["Brand", "Features"],
          "weaknesses": ["Price", "UX"]
        }
      ],
      "positioning": {
        "recommended": "SMB-focused, ease-of-use leader",
        "differentiators": ["AI-native", "Price", "UX"]
      }
    },

    "technical_data": {
      "feasibility_score": 7.2,
      "complexity_score": 6.5,
      "stack": {
        "frontend": {"tech": "Next.js", "version": "14.x"},
        "backend": {"tech": "FastAPI", "version": "0.100+"},
        "database": {"primary": "PostgreSQL", "cache": "Redis"},
        "ai": {"provider": "Anthropic", "model": "claude-3-sonnet"}
      },
      "integrations": {
        "required": ["Stripe", "SendGrid", "Anthropic"],
        "optional": ["Slack", "Zapier"]
      },
      "estimates": {
        "mvp_months": 4,
        "team_size": 3,
        "monthly_cost_usd": 300
      }
    },

    "legal_data": {
      "risk_level": "low",
      "regulations": ["GDPR", "CCPA"],
      "tos_compliant": true,
      "ip_clear": true,
      "actions_required": [
        {"item": "Privacy policy", "timing": "before_launch"},
        {"item": "Cookie consent", "timing": "before_launch"}
      ]
    },

    "social_data": {
      "sentiment_score": 0.45,
      "demand_strength": "strong",
      "communities": {
        "count": 15,
        "top_communities": ["r/subreddit1", "Discord X"]
      },
      "influencers": {
        "count": 30,
        "potential_advocates": 10
      }
    },

    "framework_scores": {
      "market_attractiveness": 7.5,
      "competitive_intensity": 6.5,
      "product_feasibility": 7.2,
      "adoption_readiness": 7.0,
      "overall_score": 7.1
    }
  }
}
```

### Intention Anchor Inputs
```json
{
  "intention_anchor_inputs": {
    "north_star": {
      "primary_goal": "Build AI-powered automation tool for SMB market",
      "success_metrics": [
        {"metric": "MAU", "target": 1000, "timeline": "6 months"},
        {"metric": "MRR", "target": 10000, "timeline": "12 months"},
        {"metric": "NPS", "target": 50, "timeline": "6 months"}
      ],
      "constraints": [
        "Bootstrap-friendly resource usage",
        "SMB-focused pricing",
        "AI-native architecture"
      ]
    },

    "safety_risk": {
      "technical_risks": [
        {
          "risk": "AI API dependency",
          "probability": "medium",
          "impact": "high",
          "mitigation": "Multi-provider abstraction"
        }
      ],
      "business_risks": [
        {
          "risk": "Competitive response",
          "probability": "high",
          "impact": "medium",
          "mitigation": "Speed + differentiation"
        }
      ],
      "legal_risks": [
        {
          "risk": "GDPR compliance",
          "probability": "certain",
          "impact": "medium",
          "mitigation": "Built-in compliance features"
        }
      ]
    },

    "scope_boundaries": {
      "in_scope": [
        "Core automation workflows",
        "AI-powered suggestions",
        "Basic integrations (3-5)",
        "Web application",
        "SMB pricing tiers"
      ],
      "out_of_scope": [
        "Enterprise features (SSO, audit logs)",
        "Mobile applications",
        "On-premise deployment",
        "White-label solutions"
      ],
      "future_scope": [
        "Advanced analytics",
        "More integrations",
        "Team collaboration features"
      ]
    },

    "budget_cost": {
      "development": {
        "team_cost_monthly": 15000,
        "infrastructure_monthly": 300,
        "tools_monthly": 200
      },
      "operations": {
        "api_costs_monthly": 500,
        "hosting_monthly": 100,
        "support_monthly": 0
      },
      "mvp_total": {
        "timeline_months": 4,
        "estimated_total": 62400
      }
    },

    "evidence_verification": {
      "key_claims": [
        {
          "claim": "Market size is $50B",
          "sources": 3,
          "confidence": "high"
        },
        {
          "claim": "SMB segment underserved",
          "sources": 5,
          "confidence": "high"
        }
      ],
      "validation_needed": [
        {
          "hypothesis": "Users will pay $29-79/mo",
          "validation_method": "Early user interviews"
        }
      ]
    }
  }
}
```

### Decision Matrix
```json
{
  "decision_matrix": {
    "critical_decisions": [
      {
        "decision": "Target market segment",
        "options": ["SMB", "Mid-market", "Enterprise"],
        "recommendation": "SMB",
        "rationale": "Underserved, lower CAC, faster sales cycle",
        "confidence": "high",
        "reversibility": "medium"
      },
      {
        "decision": "Primary AI provider",
        "options": ["Anthropic", "OpenAI", "Google"],
        "recommendation": "Anthropic",
        "rationale": "Quality + cost balance, good SDK",
        "confidence": "high",
        "reversibility": "high"
      },
      {
        "decision": "Go-to-market strategy",
        "options": ["PLG", "Sales-led", "Hybrid"],
        "recommendation": "PLG",
        "rationale": "Fits SMB target, lower CAC",
        "confidence": "medium",
        "reversibility": "medium"
      }
    ],
    "open_questions": [
      {
        "question": "Optimal pricing tiers",
        "status": "Needs validation",
        "recommended_action": "A/B test with early users"
      },
      {
        "question": "Feature prioritization for MVP",
        "status": "Draft complete",
        "recommended_action": "Validate with target users"
      }
    ]
  }
}
```

## Compilation Process

1. **Aggregate** all research outputs
2. **Normalize** data formats
3. **Validate** cross-references
4. **Generate** each output format
5. **Quality check** completeness

## Output File Generation

Generate the following files:
- `research_summary.json` - Human-readable summary
- `autopack_export.json` - Machine-readable for Autopack
- `intention_inputs.json` - Pre-formatted for anchor generation
- `decision_matrix.json` - Key decisions and recommendations

## Quality Checks

Before returning results:
- [ ] All data fields populated
- [ ] Cross-references validated
- [ ] Formats match specifications
- [ ] No missing critical data
- [ ] Ready for Autopack consumption

## Constraints

- Use sonnet model for synthesis
- Maintain data traceability
- Generate all output formats
- Validate data completeness
