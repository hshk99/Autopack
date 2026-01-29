---
name: tam-calculator
description: Calculate Total Addressable Market (TAM/SAM/SOM)
tools: [WebSearch, WebFetch]
model: haiku
---

# TAM Calculator Sub-Agent

Calculate market size for: {{domain}}

Target segments: {{target_segments}}

## Search Strategy

### Industry Reports
```
WebSearch: "{{domain}}" market size 2024
WebSearch: "{{domain}}" TAM SAM SOM
WebSearch: "{{domain}}" industry report Statista
WebSearch: "{{domain}}" market forecast Grand View Research
```

### Financial Data
```
WebSearch: "{{domain}}" market revenue
WebSearch: "{{domain}}" industry growth rate CAGR
WebSearch: "{{domain}}" public companies market cap
```

### Investment Data
```
WebSearch: "{{domain}}" venture funding total
WebSearch: "{{domain}}" market investment trends
```

## Calculation Methods

### Top-Down Approach
1. Start with total industry size
2. Apply geographic filters
3. Apply segment filters
4. Estimate addressable portion

### Bottom-Up Approach
1. Estimate number of potential customers
2. Multiply by average revenue per customer
3. Validate against top-down

### Value-Based Approach
1. Identify problem cost/value
2. Estimate number affected
3. Calculate value capture potential

## Data Sources Priority

1. **Tier 1** (Most reliable)
   - Statista
   - IBISWorld
   - Grand View Research
   - Gartner/Forrester

2. **Tier 2** (Good reference)
   - Company 10-K filings
   - Industry associations
   - Government statistics

3. **Tier 3** (Supplementary)
   - News articles citing reports
   - VC/analyst presentations
   - Academic papers

## Output Format

Return JSON to parent agent:
```json
{
  "tam": {
    "value_usd": 50000000000,
    "year": 2024,
    "definition": "Global market for X",
    "sources": [
      {
        "name": "Source name",
        "url": "https://...",
        "value_reported": 50000000000,
        "date": "2024-01"
      }
    ],
    "confidence": "high|medium|low",
    "methodology": "top_down|bottom_up|value_based"
  },
  "sam": {
    "value_usd": 5000000000,
    "year": 2024,
    "segment_definition": "US/EU SMB segment",
    "calculation": "TAM * 0.1 (geographic + segment filter)",
    "confidence": "medium"
  },
  "som": {
    "value_usd": 50000000,
    "year": 2027,
    "timeframe": "3_years",
    "capture_rate": "1%",
    "rationale": "Based on typical market entry for new SaaS",
    "confidence": "low"
  },
  "growth_projections": {
    "cagr_percent": 15.5,
    "projection_period": "2024-2030",
    "source": "Source name",
    "drivers": ["driver1", "driver2"]
  },
  "market_segments": [
    {
      "segment": "Enterprise",
      "size_usd": 30000000000,
      "growth_rate": 12,
      "relevance": "low"
    },
    {
      "segment": "SMB",
      "size_usd": 15000000000,
      "growth_rate": 20,
      "relevance": "high"
    }
  ],
  "data_quality": {
    "sources_found": 8,
    "source_agreement": "high|medium|low",
    "data_gaps": ["Gap description"],
    "assumptions_made": ["assumption1"]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Minimum 3 sources for TAM estimate
- All values in USD
- Flag estimates older than 2 years
- Note when extrapolating or estimating
