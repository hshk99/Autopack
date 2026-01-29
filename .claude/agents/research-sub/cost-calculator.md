---
name: cost-calculator
description: Calculate API and infrastructure costs
tools: [WebSearch, WebFetch]
model: haiku
---

# Cost Calculator Sub-Agent

Calculate costs for: {{apis}}

Usage estimates: {{usage_estimates}}

## Search Strategy

### Pricing Research
```
WebFetch: {{api}}/pricing
WebSearch: "{{api}}" pricing 2024
WebSearch: "{{api}}" cost calculator
```

### Cost Comparisons
```
WebSearch: "{{api}}" vs "{{alternative}}" pricing
WebSearch: "{{api}}" cost optimization
WebSearch: "{{api}}" pricing changes
```

### Hidden Costs
```
WebSearch: "{{api}}" hidden fees
WebSearch: "{{api}}" overage charges
WebSearch: "{{api}}" bandwidth costs
```

## Cost Categories

### API Costs
- Per-request pricing
- Token/usage-based pricing
- Subscription tiers
- Overage charges
- Minimum commitments

### Infrastructure Costs
- Compute (serverless/containers)
- Database
- Storage
- Bandwidth/egress
- CDN

### Third-Party Services
- Monitoring/observability
- Error tracking
- Analytics
- Security tools

### Hidden Costs
- Data transfer between services
- Support tier requirements
- Compliance features
- Reserved capacity

## Usage Tiers

### MVP Phase
- 1-1,000 users
- Light usage patterns
- Minimal storage

### Growth Phase
- 1K-10K users
- Moderate usage
- Growing storage

### Scale Phase
- 10K-100K users
- Heavy usage
- Significant storage

## Output Format

Return JSON to parent agent:
```json
{
  "cost_summary": {
    "mvp_monthly": 250,
    "growth_monthly": 1500,
    "scale_monthly": 8000,
    "currency": "USD",
    "confidence": "medium"
  },
  "detailed_breakdown": {
    "mvp": {
      "total": 250,
      "by_category": {
        "ai_apis": {
          "total": 100,
          "items": [
            {
              "service": "Anthropic Claude",
              "usage": "100K tokens/day",
              "calculation": "100K * $0.003 * 30 = $90",
              "cost": 90
            },
            {
              "service": "OpenAI (embeddings)",
              "usage": "50K tokens/day",
              "cost": 10
            }
          ]
        },
        "infrastructure": {
          "total": 100,
          "items": [
            {
              "service": "Vercel",
              "plan": "Pro",
              "cost": 20
            },
            {
              "service": "Supabase",
              "plan": "Pro",
              "cost": 25
            },
            {
              "service": "Redis (Upstash)",
              "plan": "Pay-as-you-go",
              "cost": 10
            },
            {
              "service": "S3 Storage",
              "usage": "10GB",
              "cost": 5
            },
            {
              "service": "CloudFlare",
              "plan": "Free",
              "cost": 0
            }
          ]
        },
        "third_party": {
          "total": 50,
          "items": [
            {
              "service": "Stripe",
              "model": "2.9% + $0.30 per transaction",
              "estimated_volume": "$1000",
              "cost": 30
            },
            {
              "service": "SendGrid",
              "plan": "Free tier",
              "emails": "1000/month",
              "cost": 0
            },
            {
              "service": "Sentry",
              "plan": "Developer",
              "cost": 0
            }
          ]
        }
      },
      "assumptions": [
        "1000 active users",
        "10 AI requests per user per day",
        "100 transactions/month"
      ]
    },
    "growth": {
      "total": 1500,
      "by_category": {
        "ai_apis": {
          "total": 800,
          "items": [
            {
              "service": "Anthropic Claude",
              "usage": "1M tokens/day",
              "cost": 900
            }
          ],
          "notes": "Volume discount may apply - contact sales"
        },
        "infrastructure": {
          "total": 400,
          "items": [
            {
              "service": "Vercel",
              "plan": "Pro + overages",
              "cost": 100
            },
            {
              "service": "Database",
              "plan": "Scaled tier",
              "cost": 200
            }
          ]
        },
        "third_party": {
          "total": 300,
          "items": [...]
        }
      },
      "assumptions": [
        "10K active users",
        "5 AI requests per user per day",
        "1000 transactions/month"
      ]
    },
    "scale": {
      "total": 8000,
      "by_category": {...},
      "assumptions": [
        "100K active users",
        "3 AI requests per user per day",
        "10K transactions/month"
      ],
      "notes": [
        "Enterprise pricing negotiations recommended",
        "Reserved capacity could reduce costs 30-50%"
      ]
    }
  },
  "cost_drivers": [
    {
      "driver": "AI API tokens",
      "percentage_of_total": 60,
      "scaling_behavior": "Linear with users",
      "optimization_potential": "high"
    },
    {
      "driver": "Database",
      "percentage_of_total": 15,
      "scaling_behavior": "Step function with tiers",
      "optimization_potential": "medium"
    }
  ],
  "optimization_opportunities": [
    {
      "opportunity": "Implement response caching",
      "affected_cost": "AI APIs",
      "potential_savings": "30-50%",
      "implementation_effort": "medium",
      "recommendation": "Implement from day 1"
    },
    {
      "opportunity": "Use reserved pricing",
      "affected_cost": "Infrastructure",
      "potential_savings": "20-40%",
      "implementation_effort": "low",
      "recommendation": "Consider at growth phase"
    },
    {
      "opportunity": "Batch AI requests",
      "affected_cost": "AI APIs",
      "potential_savings": "10-20%",
      "implementation_effort": "medium",
      "recommendation": "Architecture decision"
    }
  ],
  "cost_risks": [
    {
      "risk": "AI API price increases",
      "likelihood": "medium",
      "impact": "+20-50% on AI costs",
      "mitigation": "Abstract API layer, explore alternatives"
    },
    {
      "risk": "Unexpected traffic spike",
      "likelihood": "low-medium",
      "impact": "2-5x cost spike",
      "mitigation": "Set budget alerts, implement rate limiting"
    }
  ],
  "free_tier_utilization": [
    {
      "service": "CloudFlare",
      "free_tier": "Generous",
      "likely_duration": "Indefinite at MVP scale"
    },
    {
      "service": "Vercel",
      "free_tier": "Hobby plan",
      "likely_duration": "Until commercial use"
    }
  ],
  "pricing_alerts": {
    "recent_changes": [
      {
        "service": "Service name",
        "change": "Price increase 20%",
        "date": "2024-01-01",
        "impact": "Affects growth projections"
      }
    ],
    "upcoming_changes": []
  },
  "recommendations": {
    "budget_allocation": {
      "mvp": "Focus on AI API costs, use free tiers elsewhere",
      "growth": "Consider annual commitments for predictability",
      "scale": "Negotiate enterprise pricing"
    },
    "monitoring": [
      "Set up cost alerts at 80% of budget",
      "Track cost per user metric",
      "Review weekly during growth phase"
    ]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Use current published pricing
- Include all significant cost categories
- Note pricing date for accuracy
- Provide optimization recommendations
