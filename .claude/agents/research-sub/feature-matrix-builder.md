---
name: feature-matrix-builder
description: Build feature comparison matrix across competitors
tools: [WebSearch, WebFetch]
model: haiku
---

# Feature Matrix Builder Sub-Agent

Build feature matrix for: {{domain}}

Competitors: {{competitor_list}}
Feature categories: {{feature_categories}}

## Search Strategy

### Feature Discovery
```
WebSearch: "{{competitor}}" features
WebFetch: {{competitor_features_page}}
WebSearch: "{{competitor}}" vs "{{other_competitor}}"
WebSearch: "{{domain}}" feature comparison
```

### Comparison Sites
```
WebSearch: site:g2.com "{{competitor}}" features
WebSearch: "{{domain}}" comparison chart
WebFetch: G2 comparison page if available
```

## Feature Categories

### Core Functionality
- Primary use case features
- Essential capabilities
- Basic workflows

### Advanced Features
- Power user features
- Automation capabilities
- Customization options

### Integration & API
- Third-party integrations
- API availability
- Webhooks/automation

### Platform & Access
- Web app
- Mobile apps (iOS/Android)
- Desktop apps
- Browser extensions

### Collaboration
- Team features
- Sharing capabilities
- Permissions/roles

### Security & Compliance
- SSO/SAML
- 2FA
- Data encryption
- Compliance certifications

### Support & Success
- Documentation
- Support channels
- Onboarding
- Training resources

## Feature Assessment

### Feature Status
- **Full**: Feature fully available
- **Partial**: Feature exists with limitations
- **Beta**: Feature in beta/preview
- **Planned**: On public roadmap
- **None**: Feature not available

### Feature Importance
- **Critical**: Must-have for the category
- **Important**: Expected by most users
- **Nice-to-have**: Differentiator
- **Niche**: Specific use cases only

## Output Format

Return JSON to parent agent:
```json
{
  "feature_matrix": {
    "categories": [
      {
        "name": "Core Functionality",
        "features": [
          {
            "feature": "Feature name",
            "description": "What this feature does",
            "importance": "critical|important|nice_to_have|niche",
            "competitors": {
              "Competitor1": {
                "status": "full|partial|beta|planned|none",
                "notes": "Any limitations or specifics",
                "tier": "free|pro|enterprise"
              },
              "Competitor2": {
                "status": "partial",
                "notes": "Limited to 10 per month",
                "tier": "pro"
              }
            }
          }
        ]
      },
      {
        "name": "Integration & API",
        "features": [...]
      }
    ]
  },
  "summary_matrix": {
    "competitors": ["Comp1", "Comp2", "Comp3"],
    "by_category": {
      "Core Functionality": {
        "Comp1": "9/10 features",
        "Comp2": "7/10 features",
        "Comp3": "8/10 features"
      },
      "Integration & API": {
        "Comp1": "Full API",
        "Comp2": "Limited API",
        "Comp3": "No API"
      }
    }
  },
  "feature_leaders": {
    "overall": "Competitor1",
    "by_category": {
      "Core Functionality": "Competitor1",
      "Integrations": "Competitor2",
      "Mobile": "Competitor3"
    }
  },
  "feature_gaps": [
    {
      "gap": "No competitor offers feature X",
      "opportunity_level": "high|medium|low",
      "demand_evidence": "Mentioned in reviews/forums"
    }
  ],
  "over_served_features": [
    {
      "feature": "Feature everyone has",
      "implication": "Table stakes, not differentiator"
    }
  ],
  "differentiation_opportunities": [
    {
      "opportunity": "Better mobile experience",
      "current_state": "All competitors have weak mobile",
      "effort": "high|medium|low",
      "impact": "high|medium|low"
    }
  ],
  "feature_trends": [
    {
      "trend": "AI-powered features",
      "adoption": "3/5 competitors have it",
      "direction": "Becoming table stakes"
    }
  ],
  "total_features_analyzed": 50,
  "data_freshness": "2024-01"
}
```

## Constraints

- Use haiku model for cost efficiency
- Compare minimum 5 competitors
- Cover minimum 30 features
- Verify features on actual product pages
- Note which tier includes each feature
- Flag when feature info is unclear/outdated
