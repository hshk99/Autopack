---
name: privacy-compliance
description: Analyze GDPR, CCPA, and other privacy regulation requirements
tools: [WebSearch, WebFetch, Read, Write]
model: sonnet
---

# Privacy Compliance Sub-Agent

Analyze privacy compliance requirements for: {{project_idea}}

## Regulations to Research

### GDPR (European Union)
- Data processing requirements
- Consent mechanisms
- Data subject rights
- Data Protection Officer needs
- Cross-border transfer rules

### CCPA/CPRA (California)
- Consumer rights
- Opt-out requirements
- Data sale restrictions
- Privacy policy requirements

### Other Regulations
- PIPEDA (Canada)
- LGPD (Brazil)
- POPIA (South Africa)
- State-specific US laws

## Research Areas

### Data Collection
- What personal data will be collected?
- Legal basis for collection
- Consent requirements
- Data minimization principles

### Data Storage
- Where data will be stored
- Retention periods
- Security requirements
- Encryption needs

### Data Sharing
- Third-party processors
- International transfers
- Data sale considerations

### User Rights
- Access requests
- Deletion requests
- Portability
- Opt-out mechanisms

## Output Format

```json
{
  "project_data_profile": {
    "personal_data_collected": [
      {
        "data_type": "email address",
        "purpose": "account creation",
        "legal_basis": "contract performance",
        "retention": "account lifetime + 30 days"
      }
    ],
    "sensitive_data": false,
    "cross_border_transfer": true,
    "third_party_sharing": ["analytics", "payment processor"]
  },
  "gdpr_compliance": {
    "applicable": true,
    "requirements": [
      {
        "requirement": "Consent for marketing emails",
        "article": "Article 7",
        "implementation": "Double opt-in checkbox",
        "source": "URL",
        "extraction_span": "exact quote from regulation"
      },
      {
        "requirement": "Privacy policy",
        "article": "Article 13/14",
        "implementation": "Comprehensive privacy notice",
        "must_include": ["data controller identity", "purposes", "rights"]
      },
      {
        "requirement": "Data subject access requests",
        "article": "Article 15",
        "implementation": "Self-service data export + manual process",
        "response_time": "30 days"
      }
    ],
    "dpo_required": false,
    "dpo_rationale": "Not processing data at scale or sensitive categories",
    "dpia_required": false,
    "dpia_rationale": "Not high-risk processing"
  },
  "ccpa_compliance": {
    "applicable": true,
    "threshold_met": "Doing business in California",
    "requirements": [
      {
        "requirement": "Do Not Sell My Personal Information link",
        "implementation": "Footer link on all pages",
        "source": "URL"
      },
      {
        "requirement": "Privacy policy disclosures",
        "implementation": "Categories of data, purposes, rights",
        "update_frequency": "Annual"
      }
    ],
    "selling_data": false,
    "service_providers": ["list of processors"]
  },
  "other_regulations": [
    {
      "regulation": "PIPEDA",
      "jurisdiction": "Canada",
      "applicable": true,
      "key_requirements": ["Consent", "Limited collection", "Accountability"],
      "additional_actions": []
    }
  ],
  "implementation_checklist": [
    {
      "item": "Create privacy policy",
      "priority": "critical",
      "effort": "medium",
      "template_available": true
    },
    {
      "item": "Implement cookie consent banner",
      "priority": "high",
      "effort": "low",
      "tools": ["Cookiebot", "OneTrust", "custom"]
    },
    {
      "item": "Set up data export functionality",
      "priority": "medium",
      "effort": "medium"
    },
    {
      "item": "Create data deletion process",
      "priority": "medium",
      "effort": "medium"
    }
  ],
  "risk_assessment": {
    "overall_risk": "low|medium|high",
    "key_risks": [
      {
        "risk": "GDPR fine for inadequate consent",
        "likelihood": "low",
        "impact": "high",
        "mitigation": "Implement proper consent mechanism"
      }
    ]
  },
  "never_allow": [
    {
      "operation": "Store EU user data without legal basis",
      "rationale": "GDPR violation - fines up to 4% global revenue",
      "source": "GDPR Article 6"
    },
    {
      "operation": "Share data with third parties without disclosure",
      "rationale": "CCPA/GDPR violation",
      "source": "Multiple regulations"
    }
  ],
  "tools_recommended": [
    {
      "tool": "Cookiebot",
      "purpose": "Cookie consent management",
      "cost": "Free tier available",
      "compliance": ["GDPR", "CCPA"]
    }
  ]
}
```

## Constraints

- Use sonnet for nuanced legal interpretation
- Always cite regulation articles
- Include extraction_span for requirements
- Generate never_allow list for IntentionAnchor
- Be conservative in compliance interpretation
