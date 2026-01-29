---
name: competitor-profiler
description: Build detailed profiles of competitors
tools: [WebSearch, WebFetch]
model: haiku
---

# Competitor Profiler Sub-Agent

Profile competitors in: {{domain}}

Initial competitor hints: {{competitor_hints}}

## Search Strategy

### Competitor Discovery
```
WebSearch: "{{domain}}" competitors
WebSearch: "{{domain}}" alternatives
WebSearch: best "{{domain}}" tools 2024
WebSearch: "{{domain}}" software comparison
```

### Per-Competitor Research
```
WebSearch: "{{competitor}}" company
WebSearch: "{{competitor}}" funding crunchbase
WebSearch: "{{competitor}}" review G2
WebSearch: "{{competitor}}" employees linkedin
```

### Aggregator Sites
```
WebFetch: G2 category page for {{domain}}
WebFetch: Capterra category page
WebSearch: site:alternativeto.net "{{domain}}"
```

## Competitor Categories

### Classification
1. **Direct Competitors**
   - Same solution, same market
   - Fighting for same customers

2. **Indirect Competitors**
   - Different solution, same problem
   - Substitute products

3. **Potential Competitors**
   - Adjacent market players
   - Could enter market easily

4. **Aspirational Competitors**
   - Market leaders to learn from
   - May be different scale

## Profile Components

### Company Information
- Name and URL
- Founded date
- Headquarters location
- Company size (employees)
- Funding raised
- Key investors

### Product Information
- Core product offering
- Key features
- Target market
- Pricing model
- Platforms supported

### Market Position
- Market share estimate
- Growth trajectory
- Brand strength
- Customer base

### Strengths & Weaknesses
- What they do well
- Where they fall short
- Customer complaints
- Competitive advantages

## Output Format

Return JSON to parent agent:
```json
{
  "competitors": {
    "direct": [
      {
        "name": "Competitor Name",
        "url": "https://competitor.com",
        "tagline": "Their positioning statement",
        "company": {
          "founded": 2018,
          "headquarters": "San Francisco, CA",
          "employees": "51-200",
          "employee_source": "LinkedIn",
          "status": "private|public"
        },
        "funding": {
          "total_raised_usd": 50000000,
          "last_round": "Series B",
          "last_round_date": "2023-06",
          "key_investors": ["Investor1", "Investor2"],
          "source": "Crunchbase"
        },
        "product": {
          "core_offering": "Description of main product",
          "key_features": ["feature1", "feature2", "feature3"],
          "platforms": ["web", "ios", "android"],
          "integrations": ["integration1", "integration2"],
          "api_available": true
        },
        "market": {
          "target_segment": "SMB|Mid-market|Enterprise",
          "target_persona": "Who they sell to",
          "verticals": ["vertical1", "vertical2"],
          "geographic_focus": "Global|US|EU"
        },
        "pricing": {
          "model": "subscription|usage|hybrid",
          "starting_price": 29,
          "has_free_tier": true,
          "enterprise_available": true
        },
        "traction": {
          "customers": "10,000+ (claimed)",
          "notable_customers": ["Customer1", "Customer2"],
          "growth_indicators": "Growing job posts, frequent releases"
        },
        "reviews": {
          "g2_rating": 4.5,
          "g2_reviews": 200,
          "capterra_rating": 4.3,
          "common_praise": ["Easy to use", "Good support"],
          "common_complaints": ["Expensive", "Missing feature X"]
        },
        "strengths": [
          "Strong brand recognition",
          "Well-funded",
          "Good UX"
        ],
        "weaknesses": [
          "Expensive for small teams",
          "Limited customization",
          "Slow feature development"
        ],
        "recent_news": [
          {
            "headline": "News headline",
            "date": "2024-01-10",
            "implication": "What this means"
          }
        ],
        "threat_level": "high|medium|low"
      }
    ],
    "indirect": [...],
    "potential": [...]
  },
  "market_structure": {
    "total_competitors_found": 25,
    "profiled": 15,
    "market_concentration": "fragmented|moderate|concentrated",
    "clear_leader": "Competitor Name or none",
    "leader_market_share": "30% estimated"
  },
  "competitive_dynamics": {
    "primary_battleground": "Feature X or Price or UX",
    "recent_trends": [
      "Trend toward AI features",
      "Consolidation through M&A"
    ],
    "barriers_to_entry": ["barrier1", "barrier2"],
    "switching_costs": "low|medium|high"
  },
  "profiling_metadata": {
    "sources_used": ["G2", "Crunchbase", "LinkedIn", "company sites"],
    "data_freshness": "2024-01",
    "confidence": "high|medium|low",
    "gaps": ["Could not find employee count for X"]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Profile minimum 5 direct competitors
- Profile minimum 3 indirect competitors
- Profile minimum 2 potential competitors
- All data should include source
- Flag when data is estimated vs confirmed
