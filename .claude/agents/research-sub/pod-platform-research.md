---
name: pod-platform-research
description: Research Print-on-Demand platforms and fulfillment services
tools: [WebSearch, WebFetch]
model: haiku
---

# POD Platform Research Sub-Agent

Research POD platforms for: {{product_types}}

## Platforms to Research

### Major POD Platforms
1. Printful
2. Printify
3. Gooten
4. SPOD
5. Gelato
6. CustomCat

### Marketplace Integrations
1. Etsy + POD integrations
2. Shopify + POD apps
3. Amazon Merch
4. Redbubble
5. Temu seller programs

## Research Areas

### Platform Comparison
- Product catalog (t-shirts, mugs, etc.)
- Print quality reviews
- Pricing and margins
- Shipping costs and times
- International availability

### API/Integration Capabilities
- API availability
- Automation support
- Bulk order handling
- Inventory sync

### Seller Experience
- Setup complexity
- Support quality
- Payment terms
- Return handling

## Output Format

```json
{
  "platforms_analyzed": [
    {
      "name": "Printful",
      "url": "https://www.printful.com",
      "products_available": ["t-shirts", "hoodies", "mugs", "..."],
      "pricing": {
        "base_cost_range": "$X-Y",
        "typical_margin": "X%",
        "source": "URL"
      },
      "integrations": {
        "etsy": true,
        "shopify": true,
        "api_available": true,
        "automation_support": "full|partial|none"
      },
      "shipping": {
        "domestic_time": "X-Y days",
        "international": true,
        "average_cost": "$X"
      },
      "reviews": {
        "quality_rating": 4.5,
        "reliability_rating": 4.0,
        "source": "URL"
      },
      "pros": ["pro1", "pro2"],
      "cons": ["con1", "con2"],
      "best_for": "use case description"
    }
  ],
  "recommended_for_automation": {
    "platform": "Printful",
    "rationale": "Best API, reliable quality",
    "monthly_cost_estimate": "$X for Y orders"
  },
  "integration_requirements": {
    "etsy_integration": {
      "setup_steps": ["step1", "step2"],
      "api_keys_needed": ["key1"],
      "limitations": ["limit1"]
    }
  }
}
```

## Constraints

- Use haiku for cost efficiency
- Compare at least 3 platforms
- Include real pricing data
- Note automation capabilities specifically
