---
name: integration-checker
description: Verify third-party integration availability and quality
tools: [WebSearch, WebFetch]
model: haiku
---

# Integration Checker Sub-Agent

Check integrations for: {{required_integrations}}

Project context: {{project_context}}

## Search Strategy

### API Documentation
```
WebSearch: "{{service}}" API documentation
WebFetch: {{service_api_docs_url}}
WebSearch: "{{service}}" developer docs
```

### Integration Quality
```
WebSearch: "{{service}}" API reliability
WebSearch: "{{service}}" API issues problems
WebSearch: "{{service}}" integration example
```

### SDK Availability
```
WebSearch: "{{service}}" SDK Python
WebSearch: "{{service}}" SDK TypeScript JavaScript
WebSearch: "{{service}}" npm package
```

## Integration Categories

### Authentication
- OAuth providers (Google, GitHub, etc.)
- SSO providers (Okta, Auth0)
- Identity verification

### Payments
- Payment processing (Stripe, Square)
- Invoicing (FreshBooks, QuickBooks)
- Crypto payments

### Communication
- Email (SendGrid, Mailgun, SES)
- SMS (Twilio, MessageBird)
- Push notifications

### Storage
- File storage (S3, Cloudflare R2)
- Media processing (Cloudinary)
- CDN

### AI/ML
- Language models (Anthropic, OpenAI)
- Speech (Whisper, ElevenLabs)
- Vision (DALL-E, Stability)

### Data Sources
- Social media APIs
- E-commerce platforms
- Market data

## Evaluation Criteria

### API Quality
- Documentation completeness
- API design (REST, GraphQL, etc.)
- Versioning strategy
- Error handling

### Reliability
- Uptime history
- Rate limit generosity
- Status page availability
- Incident history

### Developer Experience
- SDK quality
- Code examples
- Sandbox/testing environment
- Support responsiveness

### Business Terms
- Pricing transparency
- TOS restrictions
- Data usage policies
- Enterprise options

## Output Format

Return JSON to parent agent:
```json
{
  "integrations": {
    "available": [
      {
        "name": "Stripe",
        "purpose": "Payment processing",
        "api_url": "https://stripe.com/docs/api",
        "api_type": "REST",
        "authentication": "API key",
        "documentation_quality": "excellent|good|adequate|poor",
        "documentation_url": "https://stripe.com/docs",
        "sdks": {
          "python": {
            "package": "stripe",
            "url": "https://pypi.org/project/stripe/",
            "quality": "official, well-maintained"
          },
          "typescript": {
            "package": "stripe",
            "url": "https://www.npmjs.com/package/stripe",
            "quality": "official, TypeScript native"
          }
        },
        "rate_limits": {
          "limit": "100 requests/second",
          "burst": "Higher bursts allowed",
          "sufficient": true
        },
        "sandbox": {
          "available": true,
          "url": "https://dashboard.stripe.com/test",
          "limitations": "Full functionality"
        },
        "pricing": {
          "model": "transaction_based",
          "cost": "2.9% + $0.30 per transaction",
          "free_tier": false,
          "enterprise_pricing": true
        },
        "reliability": {
          "uptime_sla": "99.99%",
          "status_page": "https://status.stripe.com",
          "recent_incidents": "Minor, well-communicated"
        },
        "feasibility": "high",
        "integration_effort": "low",
        "concerns": [],
        "recommendations": ["Use webhooks for async events"]
      }
    ],
    "problematic": [
      {
        "name": "Service Name",
        "purpose": "What we need it for",
        "issues": [
          {
            "issue": "Poor documentation",
            "severity": "medium",
            "workaround": "Use community guides"
          }
        ],
        "feasibility": "medium",
        "alternative_suggested": "Alternative service",
        "risk_level": "medium"
      }
    ],
    "unavailable": [
      {
        "name": "Desired Integration",
        "purpose": "What we need",
        "reason": "No public API available",
        "alternatives": [
          {
            "name": "Alternative",
            "trade_offs": "Different capabilities"
          }
        ],
        "workaround": "Scraping (TOS risk) or manual process"
      }
    ]
  },
  "integration_summary": {
    "total_required": 8,
    "fully_available": 6,
    "available_with_concerns": 1,
    "unavailable": 1,
    "overall_feasibility": "high|medium|low"
  },
  "integration_risks": [
    {
      "risk": "Dependency on single provider",
      "affected_integrations": ["Integration1"],
      "impact": "High - core functionality",
      "mitigation": "Abstract integration layer for switching"
    }
  ],
  "integration_costs": {
    "monthly_estimate": {
      "mvp": 50,
      "growth": 500,
      "scale": 5000
    },
    "breakdown": [
      {
        "integration": "Stripe",
        "cost_type": "transaction",
        "estimate": "Depends on volume"
      }
    ]
  },
  "implementation_order": [
    {
      "priority": 1,
      "integration": "Authentication",
      "rationale": "Foundational, blocks other work"
    },
    {
      "priority": 2,
      "integration": "Database",
      "rationale": "Core data storage"
    }
  ]
}
```

## Constraints

- Use haiku model for cost efficiency
- Verify API docs exist (don't assume)
- Check for recent API changes
- Note TOS restrictions
- Flag deprecated APIs
