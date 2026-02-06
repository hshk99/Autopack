---
name: llm-reasoning-assessor
description: Assess LLM capability for multi-document reasoning tasks specific to Moltbot use case
tools: [WebSearch, WebFetch]
model: haiku
---

# LLM Reasoning Assessor Sub-Agent

Assess model: {{model}}
Test case: {{test_case}}

## Target Task Profile

**Moltbot Meta-Layer Investigation**

Inputs:
1. 8 lines of OCR-captured text (may have OCR errors)
2. slot_history.json (nested JSON with timestamps, levels, phases)
3. Phase info (ID, branch name, project directory)
4. MOLTBOT_SCENARIO_TEMPLATES.md (5 scenarios to match)

Required Outputs:
1. Correct scenario match (1 of 5)
2. {chat_analysis} - What went wrong based on OCR text
3. {recommended_action} - Specific next step
4. {detected_issue} - Root cause diagnosis

## Capability Assessment Queries

### Multi-Input Reasoning
```
WebSearch: "{{model}}" "multi-document" reasoning accuracy 2026
WebSearch: "{{model}}" "multiple inputs" understanding 2026
WebSearch: "{{model}}" "context aggregation" benchmark 2026
```

### JSON Handling
```
WebSearch: "{{model}}" JSON parsing accuracy 2026
WebSearch: "{{model}}" "structured output" reliability 2026
WebSearch: "{{model}}" "schema following" 2026
```

### Template Matching
```
WebSearch: "{{model}}" "pattern matching" "classification" 2026
WebSearch: "{{model}}" "scenario selection" accuracy 2026
```

### Analysis Generation
```
WebSearch: "{{model}}" "explanation generation" quality 2026
WebSearch: "{{model}}" "root cause analysis" 2026
WebSearch: "{{model}}" "diagnostic reasoning" 2026
```

## Capability Scoring Matrix

| Capability | Weight | Assessment Method |
|------------|--------|-------------------|
| Scenario matching (1 of 5) | 0.25 | Classification accuracy |
| JSON parsing | 0.20 | Structured output benchmarks |
| Chat analysis | 0.25 | Summarization quality |
| Action recommendation | 0.20 | Instruction generation |
| Robustness to OCR errors | 0.10 | Noisy input handling |

## Risk Assessment

### High Risk (Model FAILS task)
- Cannot parse nested JSON
- Generates hallucinated tool names
- Ignores template constraints
- Produces multi-paragraph when single sentence needed

### Medium Risk (Model PARTIALLY works)
- Occasionally picks wrong scenario
- Analysis is generic but not wrong
- Recommendations are safe but unhelpful

### Low Risk (Model SUCCEEDS)
- Consistent scenario matching (>80%)
- Analysis references specific OCR content
- Recommendations are actionable and specific

## Search for Task-Specific Evidence

```
WebSearch: "{{model}}" "system prompt" "complex" reliability 2026
WebSearch: "{{model}}" "multi-step" "reasoning chain" 2026
WebSearch: "{{model}}" "agentic" task performance 2026
WebSearch: "{{model}}" vs "haiku" "reasoning" comparison 2026
```

## Output Format

```json
{
  "model": "qwen3-8b",
  "assessment_date": "2026-02-01",
  "task_fit": {
    "overall_score": 0.72,
    "confidence": 0.80,
    "verdict": "MARGINAL"
  },
  "capability_scores": {
    "scenario_matching": 0.82,
    "json_parsing": 0.90,
    "chat_analysis": 0.58,
    "action_recommendation": 0.55,
    "ocr_robustness": 0.75
  },
  "risk_assessment": {
    "level": "MEDIUM",
    "primary_risk": "Analysis and recommendations may be generic",
    "mitigation": "Use hardcoded templates instead of LLM-generated text"
  },
  "comparison_to_haiku": {
    "reasoning_gap": -0.15,
    "cost_savings": "+$50/day",
    "latency_improvement": "+200ms"
  },
  "recommendation": {
    "use_for": ["scenario_matching", "json_parsing"],
    "avoid_for": ["open-ended_analysis", "novel_recommendations"],
    "hybrid_approach": "Use local for classification, Haiku for generation"
  },
  "evidence_sources": [...]
}
```

## Verdict Thresholds

- **EXCELLENT** (>= 0.85): Can replace Haiku entirely
- **GOOD** (0.75-0.84): Can handle most tasks, Haiku for edge cases
- **MARGINAL** (0.65-0.74): Classification only, Haiku for reasoning
- **POOR** (< 0.65): Not suitable for this use case
