---
name: dropship-platform-research
description: Research dropshipping platforms including Coupang, Naver, Amazon
tools: [WebSearch, WebFetch]
model: haiku
---

# Dropshipping Platform Research Sub-Agent

Research dropshipping on: {{platforms}}

## Platforms to Research

### Korean Platforms
1. Coupang (쿠팡)
2. Naver Shopping (네이버 쇼핑)
3. Gmarket
4. 11st (11번가)

### Global Platforms
1. Amazon (US, UK, JP, etc.)
2. eBay
3. Walmart Marketplace
4. AliExpress

### Fulfillment Services
1. Coupang Fulfillment Services
2. Amazon FBA
3. Naver Fulfillment
4. Third-party 3PLs

## Research Areas

### Platform Requirements
- Seller registration process
- Business license requirements
- Fee structures
- Payment terms

### Dropshipping Policies
- Permitted vs prohibited
- Shipping time requirements
- Return handling
- Quality standards

### Automation Capabilities
- API availability
- Bulk listing tools
- Order management
- Inventory sync

### Market Characteristics
- Customer demographics
- Popular categories
- Competition level
- Seasonal patterns

## Output Format

```json
{
  "platforms_analyzed": [
    {
      "name": "Coupang",
      "country": "Korea",
      "url": "https://www.coupang.com",
      "seller_requirements": {
        "business_registration": "Required (Korean)",
        "foreign_seller": "Possible through partner",
        "initial_fees": "None",
        "commission": "5-15% by category",
        "source": "URL"
      },
      "dropshipping_policy": {
        "allowed": true|false,
        "restrictions": [
          {
            "restriction": "Shipping within 2-3 days required",
            "implication": "Need local inventory or fast supplier",
            "source": "URL"
          }
        ],
        "rocket_delivery_requirement": "2-day shipping for featured placement"
      },
      "automation": {
        "api_available": true,
        "api_documentation": "URL",
        "bulk_upload": true,
        "order_api": true,
        "rate_limits": "X requests/day"
      },
      "fulfillment_options": {
        "coupang_fulfillment": {
          "available": true,
          "fees": "storage + fulfillment",
          "benefits": "Rocket delivery badge"
        },
        "self_fulfillment": {
          "allowed": true,
          "shipping_requirements": "Within 2-3 days"
        }
      },
      "market_insights": {
        "monthly_visitors": "X million",
        "popular_categories": ["category1", "category2"],
        "average_order_value": "$X",
        "competition_level": "high|medium|low"
      },
      "pros": ["Large market", "Fast growth", "Good logistics"],
      "cons": ["Korean language required", "Fast shipping expected"],
      "best_for": "Sellers with Korean presence or partners"
    },
    {
      "name": "Amazon US",
      "country": "USA",
      "seller_requirements": {
        "business_registration": "Not required for individual",
        "foreign_seller": "Allowed",
        "monthly_fee": "$39.99 Professional",
        "commission": "8-15% by category"
      },
      "dropshipping_policy": {
        "allowed": true,
        "restrictions": [
          {
            "restriction": "Must be seller of record",
            "implication": "Cannot ship from Amazon/retail arbitrage",
            "source": "URL"
          },
          {
            "restriction": "No supplier branding",
            "implication": "Must be your brand on packing"
          }
        ]
      },
      "automation": {
        "api_available": true,
        "sp_api": "Selling Partner API",
        "mws_deprecated": true,
        "bulk_upload": true
      },
      "fulfillment_options": {
        "fba": {
          "available": true,
          "benefits": "Prime badge, better rankings",
          "fees": "storage + fulfillment per unit"
        },
        "fbm": {
          "allowed": true,
          "requirements": "Meet shipping promises"
        }
      }
    }
  ],
  "cross_platform_comparison": {
    "easiest_entry": "Amazon (Individual seller)",
    "best_margins": "Naver Shopping",
    "fastest_growth": "Coupang",
    "best_automation": "Amazon (SP-API)"
  },
  "automation_recommendation": {
    "tools": [
      {
        "name": "Tool name",
        "platforms_supported": ["Amazon", "eBay"],
        "features": ["listing", "repricing", "orders"],
        "pricing": "$X/month"
      }
    ],
    "custom_build_complexity": "medium",
    "api_integration_order": ["Amazon first", "Then Coupang", "Then others"]
  },
  "never_allow": [
    {
      "operation": "Dropship from competitor marketplace",
      "rationale": "Policy violation on most platforms",
      "platforms": ["Amazon", "eBay"]
    }
  ],
  "compliance_checklist": [
    "Verify dropshipping is allowed",
    "Meet shipping time requirements",
    "Handle returns properly",
    "Maintain inventory accuracy"
  ]
}
```

## Constraints

- Use haiku for cost efficiency
- Research both Korean and global platforms
- Note language/registration requirements
- Include API availability details
- Flag policy restrictions clearly
