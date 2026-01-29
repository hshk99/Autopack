---
name: api-availability-checker
description: Check availability of required APIs
tools: [WebSearch, WebFetch]
model: haiku
---

# API Availability Checker Sub-Agent

Check APIs for: {{required_apis}}

Required capabilities: {{capabilities}}

## Search Strategy

### API Discovery
```
WebSearch: "{{capability}}" API
WebSearch: "{{service}}" API documentation
WebSearch: "{{service}}" developer API
WebFetch: {{service}}/developers
```

### API Comparison
```
WebSearch: "{{capability}}" API comparison
WebSearch: best "{{capability}}" API 2024
WebSearch: "{{api1}}" vs "{{api2}}"
```

### API Status
```
WebSearch: "{{api}}" status reliability
WebSearch: "{{api}}" API changes deprecation
WebFetch: {{api_status_page}}
```

## API Categories

### AI/ML APIs
- Language Models (Anthropic, OpenAI, Cohere, Google)
- Image Generation (DALL-E, Midjourney, Stability)
- Speech (Whisper, ElevenLabs, AssemblyAI)
- Embeddings (OpenAI, Cohere, Voyage)

### Data APIs
- Market Data (Yahoo Finance, Alpha Vantage, Polygon)
- Social Media (Twitter, Reddit, LinkedIn)
- E-commerce (Amazon, Etsy, Shopify)
- Weather (OpenWeatherMap, Tomorrow.io)

### Infrastructure APIs
- Auth (Auth0, Clerk, Firebase)
- Email (SendGrid, Mailgun, Postmark)
- SMS (Twilio, MessageBird, Vonage)
- Storage (AWS S3, Cloudflare R2)

### Business APIs
- Payments (Stripe, Square, PayPal)
- Invoicing (QuickBooks, FreshBooks)
- CRM (Salesforce, HubSpot)
- Analytics (Segment, Mixpanel)

## Evaluation Criteria

### Availability
- Public API exists
- Documentation quality
- Access requirements
- Geographic restrictions

### Capability Match
- Features match requirements
- Coverage completeness
- Data freshness
- Response formats

### Reliability
- Uptime SLA
- Rate limits
- Status page
- Incident history

### Business Terms
- Pricing clarity
- TOS compatibility
- Data rights
- Support options

## Output Format

Return JSON to parent agent:
```json
{
  "api_summary": {
    "capabilities_required": 8,
    "capabilities_met": 7,
    "capabilities_partial": 1,
    "capabilities_missing": 0,
    "overall_status": "good"
  },
  "apis": {
    "available": [
      {
        "capability": "Language Model AI",
        "recommended_api": {
          "name": "Anthropic Claude API",
          "provider": "Anthropic",
          "documentation_url": "https://docs.anthropic.com",
          "api_type": "REST",
          "availability": {
            "public": true,
            "signup_required": true,
            "approval_required": false,
            "waitlist": false,
            "geographic_restrictions": ["Some countries blocked"]
          },
          "capabilities": {
            "text_generation": true,
            "function_calling": true,
            "streaming": true,
            "vision": true,
            "embeddings": false
          },
          "documentation_quality": "excellent",
          "api_stability": "stable",
          "versioning": "Versioned endpoints",
          "authentication": {
            "method": "API key",
            "complexity": "simple"
          },
          "data_formats": {
            "request": "JSON",
            "response": "JSON/SSE for streaming"
          }
        },
        "alternatives": [
          {
            "name": "OpenAI GPT-4",
            "url": "https://platform.openai.com",
            "comparison": {
              "pros": ["Larger ecosystem", "More models"],
              "cons": ["Higher cost for same quality"],
              "when_to_use": "Need specific model capabilities"
            }
          },
          {
            "name": "Google Gemini",
            "url": "https://ai.google.dev",
            "comparison": {
              "pros": ["Google integration", "Generous free tier"],
              "cons": ["Newer, less battle-tested"],
              "when_to_use": "Google ecosystem integration"
            }
          }
        ],
        "status": "fully_available"
      },
      {
        "capability": "Payment Processing",
        "recommended_api": {
          "name": "Stripe API",
          "provider": "Stripe",
          "documentation_url": "https://stripe.com/docs/api",
          "api_type": "REST",
          "availability": {
            "public": true,
            "signup_required": true,
            "approval_required": "For some features (Connect)",
            "geographic_restrictions": ["Available in 46+ countries"]
          },
          "capabilities": {
            "card_payments": true,
            "subscriptions": true,
            "invoicing": true,
            "payouts": true,
            "fraud_detection": true
          },
          "documentation_quality": "excellent",
          "api_stability": "very_stable",
          "authentication": {
            "method": "API key (secret/publishable)",
            "complexity": "simple"
          }
        },
        "alternatives": [...],
        "status": "fully_available"
      }
    ],
    "partial": [
      {
        "capability": "Social Media Data",
        "status": "partially_available",
        "details": {
          "twitter": {
            "availability": "limited",
            "issues": ["Expensive API tiers", "Rate limits"],
            "workaround": "Use Basic tier for limited functionality"
          },
          "instagram": {
            "availability": "limited",
            "issues": ["Business accounts only", "Approval required"],
            "workaround": "Basic Display API for limited data"
          }
        },
        "recommendation": "Scope features based on available APIs"
      }
    ],
    "unavailable": []
  },
  "api_matrix": {
    "by_capability": [
      {
        "capability": "Language Model",
        "options": [
          {
            "api": "Anthropic",
            "availability": "full",
            "quality": "excellent",
            "cost": "$$"
          },
          {
            "api": "OpenAI",
            "availability": "full",
            "quality": "excellent",
            "cost": "$$$"
          },
          {
            "api": "Google",
            "availability": "full",
            "quality": "very_good",
            "cost": "$$"
          }
        ],
        "recommendation": "Anthropic for quality/cost balance"
      }
    ]
  },
  "access_requirements": [
    {
      "api": "Stripe",
      "requirements": [
        "Business registration",
        "Bank account for payouts"
      ],
      "timeline": "Instant approval",
      "blocking": false
    },
    {
      "api": "Twitter API v2",
      "requirements": [
        "Developer account application",
        "Project description"
      ],
      "timeline": "1-7 days approval",
      "blocking": false
    }
  ],
  "api_risks": [
    {
      "api": "Twitter API",
      "risk": "Frequent pricing/policy changes",
      "mitigation": "Abstract API layer, have fallback"
    }
  ],
  "recommendations": {
    "primary_apis": {
      "ai": "Anthropic Claude",
      "payments": "Stripe",
      "email": "SendGrid",
      "auth": "Clerk"
    },
    "next_steps": [
      "Create Anthropic account",
      "Create Stripe account",
      "Apply for any approval-required APIs"
    ]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Verify API docs are accessible
- Check for recent changes/deprecations
- Note any approval requirements
- Provide at least 2 alternatives per capability
