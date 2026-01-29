---
name: positioning-analyzer
description: Analyze market positioning and messaging strategies
tools: [WebSearch, WebFetch]
model: haiku
---

# Positioning Analyzer Sub-Agent

Analyze positioning for: {{domain}}

Competitors: {{competitor_list}}

## Search Strategy

### Messaging Analysis
```
WebFetch: {{competitor_homepage}}
WebSearch: "{{competitor}}" tagline mission
WebSearch: "{{competitor}}" value proposition
```

### Positioning Research
```
WebSearch: "{{domain}}" market positioning
WebSearch: "{{competitor}}" target customer
WebSearch: "{{competitor}}" vs comparison
```

### Brand Perception
```
WebSearch: "{{competitor}}" brand perception
WebSearch: "{{competitor}}" reviews sentiment
```

## Positioning Dimensions

### Price-Value Positioning
- Premium (high price, high value)
- Mid-market (competitive price, good value)
- Budget (low price, basic value)
- Freemium (free + paid tiers)

### Complexity Positioning
- Enterprise (full-featured, complex)
- Professional (feature-rich, moderate)
- Simple (easy-to-use, focused)
- No-code (accessible to non-technical)

### Target Market Positioning
- Enterprise focus
- Mid-market focus
- SMB focus
- Consumer/Prosumer focus

### Use Case Positioning
- Horizontal (general purpose)
- Vertical (industry-specific)
- Point solution (single use case)
- Platform (multiple use cases)

## Messaging Analysis

### Key Elements
- Headline/tagline
- Value propositions
- Key benefits
- Feature highlights
- Social proof types
- Call-to-action style

### Persona Signals
- Language used
- Use cases highlighted
- Customer logos shown
- Pricing transparency

## Output Format

Return JSON to parent agent:
```json
{
  "competitor_positioning": [
    {
      "competitor": "Competitor Name",
      "homepage_url": "https://...",
      "messaging": {
        "tagline": "Their main tagline",
        "value_propositions": [
          "VP 1",
          "VP 2",
          "VP 3"
        ],
        "key_benefits": ["benefit1", "benefit2"],
        "tone": "professional|casual|technical|friendly",
        "key_words": ["word1", "word2", "word3"]
      },
      "positioning": {
        "price_position": "premium|mid-market|budget|freemium",
        "complexity_position": "enterprise|professional|simple|no-code",
        "market_focus": "enterprise|mid-market|smb|consumer",
        "use_case_breadth": "horizontal|vertical|point_solution|platform",
        "primary_differentiator": "What they claim makes them unique"
      },
      "target_persona": {
        "title": "Marketing Manager",
        "company_size": "50-500 employees",
        "industry": "All or specific",
        "pain_points_addressed": ["pain1", "pain2"],
        "evidence": "Customer logos, case studies, language"
      },
      "social_proof": {
        "types_used": ["logos", "testimonials", "stats", "awards"],
        "notable_customers": ["Customer1", "Customer2"],
        "claimed_metrics": ["10K+ customers", "4.8 rating"]
      }
    }
  ],
  "positioning_map": {
    "axes": {
      "x": {
        "label": "Price",
        "low": "Budget",
        "high": "Premium"
      },
      "y": {
        "label": "Complexity",
        "low": "Simple",
        "high": "Enterprise"
      }
    },
    "positions": [
      {
        "competitor": "Competitor1",
        "x": 0.8,
        "y": 0.9,
        "quadrant": "Premium Enterprise"
      },
      {
        "competitor": "Competitor2",
        "x": 0.3,
        "y": 0.4,
        "quadrant": "Budget Simple"
      }
    ]
  },
  "positioning_clusters": [
    {
      "cluster": "Premium Enterprise",
      "competitors": ["Comp1", "Comp2"],
      "characteristics": "High price, full features, enterprise focus",
      "saturation": "high|medium|low"
    }
  ],
  "white_space": [
    {
      "position": "Affordable professional tier",
      "description": "No competitor offers professional features at SMB prices",
      "x_range": "0.3-0.5",
      "y_range": "0.5-0.7",
      "opportunity_size": "medium",
      "entry_difficulty": "low"
    }
  ],
  "messaging_patterns": {
    "common_claims": ["Easy to use", "Save time", "All-in-one"],
    "overused_terms": ["AI-powered", "Revolutionary"],
    "messaging_gaps": ["No one emphasizes X"]
  },
  "positioning_recommendations": {
    "recommended_position": {
      "price": "mid-market",
      "complexity": "professional",
      "market": "smb",
      "differentiator": "Recommended unique angle"
    },
    "messaging_recommendations": [
      "Emphasize X which competitors ignore",
      "Avoid overused term Y"
    ],
    "positioning_risks": [
      "Risk of being perceived as 'another X'"
    ]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Analyze minimum 5 competitor homepages
- Map all competitors on positioning axes
- Identify at least one white space opportunity
- Include actual taglines and messaging
