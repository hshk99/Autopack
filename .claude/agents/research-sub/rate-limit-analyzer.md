---
name: rate-limit-analyzer
description: Analyze rate limits and quotas
tools: [WebSearch, WebFetch]
model: haiku
---

# Rate Limit Analyzer Sub-Agent

Analyze rate limits for: {{apis}}

Usage patterns: {{usage_patterns}}

## Search Strategy

### Rate Limit Documentation
```
WebFetch: {{api}}/docs/rate-limits
WebSearch: "{{api}}" rate limits
WebSearch: "{{api}}" API limits quotas
```

### Limit Experiences
```
WebSearch: "{{api}}" rate limit exceeded
WebSearch: "{{api}}" throttling issues
WebSearch: "{{api}}" 429 error
```

### Limit Increases
```
WebSearch: "{{api}}" increase rate limit
WebSearch: "{{api}}" enterprise limits
WebSearch: "{{api}}" higher tier limits
```

## Rate Limit Types

### Time-Based Limits
- Per second
- Per minute
- Per hour
- Per day
- Per month

### Resource-Based Limits
- Concurrent connections
- Payload size
- Response size
- File upload limits

### Token-Based Limits
- Tokens per minute (TPM)
- Tokens per day (TPD)
- Context window limits

### Account-Based Limits
- Per API key
- Per account
- Per organization
- Per IP address

## Analysis Framework

### Usage Pattern Mapping
- Peak usage times
- Burst patterns
- Sustained usage
- Geographic distribution

### Bottleneck Identification
- Which limit hits first?
- What blocks scaling?
- What causes degradation?

### Mitigation Strategies
- Caching
- Request batching
- Queue management
- Load balancing
- Tier upgrades

## Output Format

Return JSON to parent agent:
```json
{
  "rate_limit_summary": {
    "apis_analyzed": 5,
    "potential_bottlenecks": 2,
    "critical_limits": 1,
    "overall_feasibility": "feasible_with_planning"
  },
  "by_api": [
    {
      "api": "Anthropic Claude API",
      "documentation_url": "https://docs.anthropic.com/rate-limits",
      "tiers": {
        "current_tier": "default",
        "limits": {
          "requests_per_minute": {
            "limit": 60,
            "type": "sliding_window",
            "scope": "per_api_key"
          },
          "tokens_per_minute": {
            "limit": 100000,
            "type": "sliding_window",
            "scope": "per_api_key"
          },
          "tokens_per_day": {
            "limit": null,
            "notes": "No daily limit on default tier"
          }
        },
        "upgrade_path": {
          "tier": "Scale tier",
          "limits": {
            "requests_per_minute": 1000,
            "tokens_per_minute": 1000000
          },
          "how_to_upgrade": "Contact sales",
          "requirements": "Demonstrated usage, enterprise agreement"
        }
      },
      "usage_analysis": {
        "expected_usage": {
          "mvp": {
            "requests_per_minute_peak": 10,
            "tokens_per_minute_peak": 20000,
            "headroom": "6x under limit"
          },
          "growth": {
            "requests_per_minute_peak": 50,
            "tokens_per_minute_peak": 80000,
            "headroom": "Close to limit during peaks",
            "concern_level": "medium"
          },
          "scale": {
            "requests_per_minute_peak": 200,
            "tokens_per_minute_peak": 400000,
            "headroom": "Exceeds default limits",
            "concern_level": "high",
            "action_required": "Tier upgrade required"
          }
        }
      },
      "error_handling": {
        "rate_limit_response": "HTTP 429",
        "retry_after_header": true,
        "backoff_recommendation": "Exponential with jitter"
      },
      "bottleneck_risk": "medium",
      "mitigation_strategies": [
        {
          "strategy": "Response caching",
          "effectiveness": "high",
          "implementation": "Cache common queries for 1 hour",
          "reduction": "30-50% fewer requests"
        },
        {
          "strategy": "Request queuing",
          "effectiveness": "medium",
          "implementation": "Redis queue with rate limiter",
          "benefit": "Smooth out bursts"
        },
        {
          "strategy": "Tier upgrade",
          "effectiveness": "high",
          "implementation": "Contact Anthropic sales",
          "timeline": "1-2 weeks"
        }
      ]
    },
    {
      "api": "Twitter API v2",
      "tiers": {
        "current_tier": "Basic",
        "limits": {
          "tweets_per_month": {
            "limit": 1500,
            "type": "monthly_cap",
            "scope": "per_app"
          },
          "requests_per_15_min": {
            "limit": 50,
            "type": "fixed_window",
            "scope": "per_user"
          }
        }
      },
      "usage_analysis": {
        "expected_usage": {
          "mvp": {
            "tweets_per_month": 500,
            "headroom": "3x under limit"
          },
          "growth": {
            "tweets_per_month": 5000,
            "headroom": "Exceeds Basic tier",
            "concern_level": "high"
          }
        }
      },
      "bottleneck_risk": "high",
      "mitigation_strategies": [
        {
          "strategy": "Upgrade to Pro tier",
          "effectiveness": "high",
          "cost": "$100/month",
          "new_limits": "300K tweets/month"
        },
        {
          "strategy": "Reduce scope",
          "effectiveness": "medium",
          "implementation": "Focus on high-value tweets only"
        }
      ]
    }
  ],
  "aggregate_analysis": {
    "primary_bottleneck": {
      "api": "Anthropic Claude",
      "limit": "requests_per_minute",
      "when": "Growth phase peak hours",
      "severity": "medium"
    },
    "secondary_bottlenecks": [
      {
        "api": "Twitter API",
        "limit": "monthly tweet cap",
        "severity": "high for growth"
      }
    ]
  },
  "architectural_recommendations": [
    {
      "recommendation": "Implement request queue from day 1",
      "rationale": "Essential for rate limit management",
      "components": ["Redis", "Bull/BullMQ"],
      "effort": "medium"
    },
    {
      "recommendation": "Build caching layer",
      "rationale": "Reduce API calls significantly",
      "components": ["Redis cache", "Cache invalidation logic"],
      "effort": "medium"
    },
    {
      "recommendation": "Circuit breaker pattern",
      "rationale": "Graceful degradation when limits hit",
      "components": ["Circuit breaker library", "Fallback responses"],
      "effort": "low-medium"
    }
  ],
  "monitoring_recommendations": [
    {
      "metric": "Rate limit utilization %",
      "alert_threshold": "80%",
      "action": "Scale mitigation or upgrade tier"
    },
    {
      "metric": "429 error rate",
      "alert_threshold": ">1%",
      "action": "Investigate and adjust"
    },
    {
      "metric": "Queue depth",
      "alert_threshold": ">100 items",
      "action": "Scale workers or reduce intake"
    }
  ],
  "tier_upgrade_timeline": {
    "phase": "growth",
    "apis_requiring_upgrade": ["Anthropic", "Twitter"],
    "estimated_cost_increase": "$200-500/month",
    "lead_time": "1-2 weeks for enterprise tiers"
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Check current rate limit documentation
- Map limits to expected usage patterns
- Identify bottlenecks early
- Provide concrete mitigation strategies
