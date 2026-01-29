---
name: quality-validator
description: Validate overall research quality and completeness
tools: [Task]
model: sonnet
---

# Quality Validator Agent

Validate research quality for: {{research_outputs}}

## Purpose

This agent performs a comprehensive quality assessment of the entire research output, checking for completeness, consistency, and adherence to research standards.

## Quality Dimensions

### 1. Completeness (Weight: 25%)
- All required sections present
- Key questions answered
- No critical gaps
- Sufficient depth

### 2. Consistency (Weight: 25%)
- Internal consistency
- Cross-section alignment
- Terminology consistency
- Methodology consistency

### 3. Accuracy (Weight: 25%)
- Facts verifiable
- Calculations correct
- Sources properly cited
- No logical errors

### 4. Actionability (Weight: 25%)
- Recommendations clear
- Next steps defined
- Priorities established
- Trade-offs articulated

## Quality Checklist

### Research Coverage
```
[ ] Market Research
    [ ] TAM/SAM/SOM calculated
    [ ] Growth trends analyzed
    [ ] Demand validated
    [ ] Pricing researched

[ ] Competitive Analysis
    [ ] Direct competitors profiled
    [ ] Indirect competitors considered
    [ ] Feature matrix complete
    [ ] Positioning analyzed
    [ ] Moats evaluated

[ ] Technical Feasibility
    [ ] Stack evaluated
    [ ] Integrations checked
    [ ] Complexity estimated
    [ ] Dependencies analyzed

[ ] Legal/Policy
    [ ] Regulations identified
    [ ] TOS analyzed
    [ ] IP risks assessed

[ ] Social Sentiment
    [ ] Sentiment aggregated
    [ ] Influencers mapped
    [ ] Communities analyzed

[ ] Tool Availability
    [ ] APIs checked
    [ ] SDKs evaluated
    [ ] Costs calculated
    [ ] Rate limits analyzed
```

### Framework Scores
```
[ ] Market Attractiveness scored
[ ] Competitive Intensity scored
[ ] Product Feasibility scored
[ ] Adoption Readiness scored
```

### Analysis Quality
```
[ ] Sources evaluated
[ ] Cross-references completed
[ ] Compilation generated
```

### Validation Status
```
[ ] Citations validated
[ ] Evidence validated
[ ] Recency validated
```

## Output Format

Return quality validation:
```json
{
  "quality_summary": {
    "overall_quality_score": 8.2,
    "max": 10,
    "quality_level": "high",
    "pass_threshold": 7.0,
    "status": "pass",
    "confidence": "high"
  },
  "dimension_scores": {
    "completeness": {
      "score": 9,
      "weight": 0.25,
      "weighted_score": 2.25,
      "assessment": "Comprehensive coverage of all required areas",
      "checklist_status": {
        "market_research": {
          "complete": true,
          "items_complete": 4,
          "items_total": 4
        },
        "competitive_analysis": {
          "complete": true,
          "items_complete": 5,
          "items_total": 5
        },
        "technical_feasibility": {
          "complete": true,
          "items_complete": 4,
          "items_total": 4
        },
        "legal_policy": {
          "complete": true,
          "items_complete": 3,
          "items_total": 3
        },
        "social_sentiment": {
          "complete": true,
          "items_complete": 3,
          "items_total": 3
        },
        "tool_availability": {
          "complete": true,
          "items_complete": 4,
          "items_total": 4
        }
      },
      "gaps": [],
      "strengths": ["All major areas covered", "Good depth in each section"]
    },
    "consistency": {
      "score": 8,
      "weight": 0.25,
      "weighted_score": 2.0,
      "assessment": "Generally consistent with minor discrepancies",
      "consistency_checks": [
        {
          "check": "Market size consistency",
          "status": "pass",
          "details": "TAM figures consistent across sections"
        },
        {
          "check": "Competitor data consistency",
          "status": "pass",
          "details": "Same competitors referenced consistently"
        },
        {
          "check": "Technical stack consistency",
          "status": "pass",
          "details": "Recommended stack consistent throughout"
        },
        {
          "check": "Terminology consistency",
          "status": "minor_issue",
          "details": "SMB vs small business used interchangeably",
          "recommendation": "Standardize terminology"
        }
      ],
      "inconsistencies_found": [
        {
          "type": "terminology",
          "description": "Mixed use of SMB and small business",
          "severity": "low",
          "recommendation": "Standardize to SMB"
        }
      ]
    },
    "accuracy": {
      "score": 8,
      "weight": 0.25,
      "weighted_score": 2.0,
      "assessment": "High accuracy with minor corrections needed",
      "accuracy_checks": [
        {
          "check": "Calculation verification",
          "status": "pass",
          "details": "Market calculations verified correct"
        },
        {
          "check": "Source accuracy",
          "status": "minor_issue",
          "details": "One data point needed correction (per citation validator)",
          "corrected": true
        },
        {
          "check": "Logical consistency",
          "status": "pass",
          "details": "Conclusions follow from evidence"
        }
      ],
      "errors_found": [
        {
          "type": "data_correction",
          "description": "Competitor funding corrected from $50M to $45M",
          "severity": "medium",
          "status": "corrected"
        }
      ]
    },
    "actionability": {
      "score": 8,
      "weight": 0.25,
      "weighted_score": 2.0,
      "assessment": "Clear recommendations with defined next steps",
      "actionability_checks": [
        {
          "check": "Clear recommendations",
          "status": "pass",
          "details": "Each section includes specific recommendations"
        },
        {
          "check": "Prioritization",
          "status": "pass",
          "details": "Recommendations prioritized by importance"
        },
        {
          "check": "Trade-offs articulated",
          "status": "pass",
          "details": "Key trade-offs clearly explained"
        },
        {
          "check": "Next steps defined",
          "status": "pass",
          "details": "Clear action items for implementation"
        }
      ]
    }
  },
  "research_coverage_matrix": {
    "by_section": {
      "market_research": {
        "coverage": "complete",
        "depth": "high",
        "quality": "excellent"
      },
      "competitive_analysis": {
        "coverage": "complete",
        "depth": "high",
        "quality": "excellent"
      },
      "technical_feasibility": {
        "coverage": "complete",
        "depth": "high",
        "quality": "good"
      },
      "legal_policy": {
        "coverage": "complete",
        "depth": "medium",
        "quality": "good"
      },
      "social_sentiment": {
        "coverage": "complete",
        "depth": "medium",
        "quality": "good"
      },
      "tool_availability": {
        "coverage": "complete",
        "depth": "high",
        "quality": "excellent"
      }
    },
    "overall_coverage": "94%"
  },
  "quality_issues": [
    {
      "issue": "Terminology inconsistency",
      "severity": "low",
      "impact": "Readability",
      "recommendation": "Standardize SMB terminology",
      "effort": "low"
    }
  ],
  "quality_strengths": [
    {
      "strength": "Comprehensive market research",
      "impact": "High confidence in market opportunity"
    },
    {
      "strength": "Well-documented competitive analysis",
      "impact": "Clear positioning strategy"
    },
    {
      "strength": "Detailed technical feasibility",
      "impact": "Reliable implementation planning"
    }
  ],
  "improvement_recommendations": [
    {
      "recommendation": "Add more primary research for user preferences",
      "priority": "medium",
      "rationale": "Would strengthen demand validation"
    },
    {
      "recommendation": "Deepen legal analysis for specific jurisdictions",
      "priority": "low",
      "rationale": "Current coverage sufficient for MVP"
    }
  ],
  "readiness_assessment": {
    "ready_for_autopack": true,
    "blocking_issues": [],
    "warnings": [
      "Note assumption about user price sensitivity"
    ],
    "data_quality_confidence": "high"
  },
  "validation_metadata": {
    "validator": "quality-validator",
    "validation_date": "2024-01-15",
    "sections_evaluated": 6,
    "checks_performed": 25,
    "methodology": "Comprehensive checklist + consistency analysis"
  }
}
```

## Quality Gates

### Pass (Score ≥ 7.0)
- Ready for Autopack handoff
- Minor improvements can be noted

### Conditional Pass (Score 5.0-6.9)
- Requires specific improvements
- Must address blocking issues

### Fail (Score < 5.0)
- Significant gaps or errors
- Must return to research phase

## Quality Checks

Before returning results:
- [ ] All dimensions scored
- [ ] Checklist complete
- [ ] Issues documented
- [ ] Recommendations prioritized
- [ ] Readiness clearly stated

## Constraints

- Use sonnet model for comprehensive assessment
- Apply consistent scoring criteria
- Provide specific improvement recommendations
- Clear pass/fail determination
