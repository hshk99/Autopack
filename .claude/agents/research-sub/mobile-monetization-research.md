---
name: mobile-monetization-research
description: Research mobile app monetization strategies and ad networks
tools: [WebSearch, WebFetch]
model: haiku
---

# Mobile Monetization Research Sub-Agent

Research monetization options for: {{app_type}}

## Monetization Models

### Ad-Based
1. AdMob (Google)
2. Facebook Audience Network
3. Unity Ads
4. AppLovin
5. ironSource

### Subscription
1. In-app subscriptions
2. Paywalls
3. Freemium models

### In-App Purchases
1. Consumables
2. Non-consumables
3. Premium features

### Hybrid Models
1. Ads + Premium
2. Subscription + IAP
3. Rewarded ads

## Research Areas

### Ad Networks Comparison
- eCPM rates by region
- Fill rates
- Integration complexity
- Payment terms
- Mediation support

### Revenue Optimization
- Ad placement strategies
- Frequency capping
- User segmentation
- A/B testing approaches

### Platform Fees
- Apple/Google commission rates
- Payment processing fees
- Tax considerations

### Industry Benchmarks
- ARPU by category
- Conversion rates
- Retention vs monetization

## Output Format

```json
{
  "app_type": "utility app",
  "ad_networks": [
    {
      "name": "AdMob",
      "provider": "Google",
      "ad_formats": ["banner", "interstitial", "rewarded", "native"],
      "average_ecpm": {
        "banner": "$0.10-0.50",
        "interstitial": "$1-5",
        "rewarded": "$5-15",
        "region_variance": "US 3-5x higher than developing markets",
        "source": "URL"
      },
      "fill_rate": "95%+",
      "payment": {
        "threshold": "$100",
        "net_terms": "Net 30",
        "methods": ["bank transfer", "check"]
      },
      "integration": {
        "complexity": "easy",
        "sdk_size": "~1MB",
        "documentation": "URL"
      },
      "pros": ["High fill rate", "Reliable payments", "Good documentation"],
      "cons": ["Lower eCPM than some alternatives"],
      "best_for": "Most apps, especially starting out"
    }
  ],
  "mediation_platforms": [
    {
      "name": "AdMob Mediation",
      "supported_networks": 20,
      "auto_optimization": true,
      "setup_complexity": "medium"
    }
  ],
  "subscription_strategies": {
    "pricing_benchmarks": {
      "utility_apps": "$2.99-9.99/month",
      "content_apps": "$4.99-14.99/month",
      "productivity": "$9.99-29.99/month"
    },
    "conversion_rates": {
      "free_to_trial": "2-5%",
      "trial_to_paid": "30-50%",
      "source": "URL"
    },
    "best_practices": [
      "Offer free trial",
      "Annual discount (20-40%)",
      "Feature gating not content gating"
    ]
  },
  "platform_fees": {
    "apple": {
      "standard": "30%",
      "small_business": "15% (under $1M)",
      "subscriptions_year2": "15%"
    },
    "google": {
      "standard": "30%",
      "small_business": "15% (under $1M)",
      "subscriptions": "15%"
    }
  },
  "revenue_estimates": {
    "1000_dau_ad_supported": {
      "banner_only": "$1-3/day",
      "with_interstitials": "$5-15/day",
      "with_rewarded": "$10-30/day"
    },
    "1000_dau_freemium": {
      "2_percent_conversion": "$60-200/day",
      "assumptions": "Average $3-10 purchase"
    }
  },
  "recommendation": {
    "for_new_apps": {
      "model": "Freemium with ads",
      "rationale": "Monetize free users while building premium",
      "ad_network": "Start with AdMob"
    },
    "for_established_apps": {
      "model": "Subscription + Rewarded ads",
      "rationale": "Maximize LTV with multiple streams"
    }
  },
  "implementation_priority": [
    "1. AdMob integration (immediate revenue)",
    "2. Subscription tier (higher LTV users)",
    "3. Mediation (optimize ad revenue)",
    "4. A/B test pricing"
  ]
}
```

## Constraints

- Use haiku for cost efficiency
- Include real eCPM benchmarks
- Compare multiple networks
- Note platform fee structures
- Consider user experience impact
