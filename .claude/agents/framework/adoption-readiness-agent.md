---
name: adoption-readiness-agent
description: Score market adoption readiness and go-to-market clarity
tools: [Task, WebSearch]
model: sonnet
---

# Adoption Readiness Agent

Score adoption readiness for: {{project_idea}}

Input data: {{social_sentiment_data}}, {{competitive_analysis_data}}

## Framework Overview

This agent assesses how ready the market is to adopt the proposed solution and how clear the path to market is.

## Scoring Dimensions

### 1. Problem Awareness (Weight: 20%)
- Do customers know they have the problem?
- How actively are they seeking solutions?
- Is market education needed?

### 2. Solution Acceptance (Weight: 20%)
- Are customers open to this type of solution?
- Past adoption of similar solutions?
- Trust in the category?

### 3. Buyer Accessibility (Weight: 20%)
- Can you reach decision makers?
- Clear buyer persona?
- Defined buying process?

### 4. Channel Clarity (Weight: 20%)
- Distribution channels available?
- Partnership opportunities?
- Marketing channel effectiveness?

### 5. Community Strength (Weight: 20%)
- Existing communities to leverage?
- Influencer landscape?
- Word-of-mouth potential?

## Scoring Rubric

Each dimension is scored 1-10 (higher = MORE ready):

### Problem Awareness Scoring
```
10: Urgent, top-of-mind problem, actively seeking solutions
 8: Well-known problem, moderate solution seeking
 6: Recognized problem, occasional searching
 4: Emerging awareness, education needed
 2: Unaware of problem, major education required
```

### Solution Acceptance Scoring
```
10: Category proven, high trust, eager adoption
 8: Category established, good trust
 6: Category known, some skepticism
 4: New category, significant skepticism
 2: Category unknown, high resistance
```

### Buyer Accessibility Scoring
```
10: Clear buyer, easy to reach, short sales cycle
 8: Defined buyer, reachable, moderate cycle
 6: Multiple stakeholders, accessible
 4: Complex buying center, hard to reach
 2: Unclear buyer, very hard to reach
```

### Channel Clarity Scoring
```
10: Proven channels, low CAC, high scalability
 8: Good channels, reasonable CAC
 6: Channels available but competitive
 4: Limited channels, high CAC
 2: No clear channels
```

### Community Strength Scoring
```
10: Strong communities, influential advocates, high WOM
 8: Active communities, good influencers
 6: Moderate community presence
 4: Limited communities, few influencers
 2: No relevant communities
```

## Output Format

Return comprehensive adoption readiness assessment:
```json
{
  "adoption_readiness_score": {
    "overall": 7.0,
    "max": 10,
    "interpretation": "Market ready with good adoption potential",
    "confidence": "high"
  },
  "dimension_scores": {
    "problem_awareness": {
      "score": 8,
      "weight": 0.20,
      "weighted_score": 1.6,
      "assessment": "High problem awareness, active solution seeking",
      "evidence": [
        {
          "indicator": "Search volume",
          "finding": "50K+ monthly searches for solutions",
          "source": "Keyword research"
        },
        {
          "indicator": "Forum discussions",
          "finding": "Active discussions in 5+ communities",
          "source": "Social sentiment analysis"
        },
        {
          "indicator": "Pain point articulation",
          "finding": "Clear, consistent pain points mentioned",
          "source": "Community analyzer"
        }
      ],
      "awareness_gaps": [
        "Some segments unaware of automation potential"
      ],
      "education_needs": "Minimal for core audience"
    },
    "solution_acceptance": {
      "score": 7,
      "weight": 0.20,
      "weighted_score": 1.4,
      "assessment": "Good category acceptance, some skepticism remains",
      "evidence": [
        {
          "indicator": "Competitor adoption",
          "finding": "Multiple competitors with significant user bases",
          "implication": "Category validated"
        },
        {
          "indicator": "AI acceptance",
          "finding": "Growing acceptance of AI tools",
          "implication": "Tailwind for adoption"
        },
        {
          "indicator": "Trust signals",
          "finding": "Some concerns about AI reliability",
          "implication": "Trust-building important"
        }
      ],
      "acceptance_barriers": [
        {
          "barrier": "AI skepticism",
          "severity": "medium",
          "mitigation": "Transparency, human oversight options"
        }
      ]
    },
    "buyer_accessibility": {
      "score": 7,
      "weight": 0.20,
      "weighted_score": 1.4,
      "assessment": "Clear buyer persona, accessible through digital channels",
      "buyer_profile": {
        "primary_buyer": "Operations Manager / Business Owner",
        "company_size": "10-200 employees",
        "industry": "E-commerce, SaaS, Professional Services",
        "buying_authority": "Direct or 1 approval level"
      },
      "accessibility_factors": [
        {
          "factor": "Digital presence",
          "assessment": "High - active on LinkedIn, Twitter",
          "reachability": "high"
        },
        {
          "factor": "Content consumption",
          "assessment": "Reads industry blogs, newsletters",
          "reachability": "high"
        },
        {
          "factor": "Event attendance",
          "assessment": "Virtual events, some conferences",
          "reachability": "medium"
        }
      ],
      "sales_cycle": {
        "expected_length": "2-4 weeks for SMB",
        "decision_makers": "1-2",
        "complexity": "low-medium"
      }
    },
    "channel_clarity": {
      "score": 6,
      "weight": 0.20,
      "weighted_score": 1.2,
      "assessment": "Good channels available but competitive",
      "channel_assessment": [
        {
          "channel": "Content marketing / SEO",
          "viability": "high",
          "competition": "high",
          "cac_estimate": "$50-150",
          "recommendation": "Core channel, long-term investment"
        },
        {
          "channel": "Product-led growth",
          "viability": "high",
          "competition": "medium",
          "cac_estimate": "$20-50",
          "recommendation": "Primary growth engine"
        },
        {
          "channel": "Paid acquisition",
          "viability": "medium",
          "competition": "high",
          "cac_estimate": "$100-300",
          "recommendation": "Supplementary, careful targeting"
        },
        {
          "channel": "Partnerships",
          "viability": "high",
          "competition": "low",
          "cac_estimate": "Variable",
          "recommendation": "Underutilized opportunity"
        }
      ],
      "gtm_recommendation": {
        "primary_strategy": "PLG with content support",
        "secondary_strategy": "Strategic partnerships",
        "avoid": "Heavy paid acquisition early"
      }
    },
    "community_strength": {
      "score": 7,
      "weight": 0.20,
      "weighted_score": 1.4,
      "assessment": "Strong community presence to leverage",
      "community_landscape": {
        "total_communities": 15,
        "high_value_communities": 5,
        "total_potential_reach": "500K+",
        "engagement_level": "high"
      },
      "influencer_landscape": {
        "total_influencers": 30,
        "potential_advocates": 10,
        "partnership_opportunities": 5,
        "estimated_reach": "2M+"
      },
      "word_of_mouth_potential": {
        "assessment": "high",
        "factors": [
          "Shareable results",
          "Professional communities active",
          "Tool comparison culture"
        ]
      },
      "community_strategy": [
        "Engage authentically in top 5 communities",
        "Build relationships with micro-influencers",
        "Create shareable content/results"
      ]
    }
  },
  "score_calculation": {
    "weighted_sum": 7.0,
    "final_score": 7.0,
    "adjustments": "None"
  },
  "adoption_velocity_estimate": {
    "early_adopter_timeline": "1-3 months to first 100 users",
    "growth_timeline": "6-12 months to 1000 users",
    "factors": [
      "PLG reduces friction",
      "Strong communities accelerate WOM",
      "Some education needed slows initial adoption"
    ],
    "acceleration_opportunities": [
      "Influencer partnerships",
      "Product Hunt launch",
      "Community-first launch"
    ]
  },
  "go_to_market_readiness": {
    "readiness_level": "high",
    "key_gtm_elements": {
      "positioning": {
        "status": "needs_refinement",
        "recommendation": "Test positioning with early users"
      },
      "messaging": {
        "status": "draft",
        "recommendation": "A/B test key messages"
      },
      "channels": {
        "status": "identified",
        "recommendation": "Start content creation now"
      },
      "pricing": {
        "status": "benchmarked",
        "recommendation": "Test willingness to pay"
      }
    },
    "launch_readiness_checklist": [
      {
        "item": "Landing page",
        "status": "needed",
        "priority": "critical"
      },
      {
        "item": "Community presence",
        "status": "needed",
        "priority": "high"
      },
      {
        "item": "Content foundation",
        "status": "needed",
        "priority": "high"
      },
      {
        "item": "Early access list",
        "status": "needed",
        "priority": "high"
      }
    ]
  },
  "adoption_risks": [
    {
      "risk": "Competitive marketing drowns out launch",
      "probability": "medium",
      "impact": "medium",
      "mitigation": "Niche positioning, community-first"
    },
    {
      "risk": "Slower SMB sales cycles than expected",
      "probability": "low",
      "impact": "medium",
      "mitigation": "PLG reduces dependency on sales"
    }
  ],
  "recommendations": {
    "pre_launch": [
      "Build community presence in top 3 communities",
      "Create foundational content pieces",
      "Identify and engage 5 potential advocates",
      "Set up early access waitlist"
    ],
    "launch_phase": [
      "Community-first soft launch",
      "Product Hunt timing optimization",
      "Influencer seeding",
      "PR outreach to relevant publications"
    ],
    "growth_phase": [
      "Scale content production",
      "Activate partnership channels",
      "Optimize PLG funnel",
      "Build customer advocacy program"
    ]
  },
  "framework_metadata": {
    "framework_version": "1.0",
    "evaluation_date": "2024-01-15",
    "communities_analyzed": 15,
    "influencers_evaluated": 30,
    "confidence_level": "high"
  }
}
```

## Quality Checks

Before returning results:
- [ ] All 5 dimensions scored with evidence
- [ ] Buyer persona clearly defined
- [ ] Channel recommendations specific
- [ ] Community/influencer opportunities identified
- [ ] GTM timeline realistic

## Constraints

- Use sonnet model for market analysis
- Base scores on actual research data
- Provide actionable GTM recommendations
- Consider both launch and growth phases
