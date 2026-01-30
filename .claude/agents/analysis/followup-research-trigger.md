---
name: followup-research-trigger
description: Analyzes findings to trigger automated follow-up research
tools: [Read, Write, Task]
model: sonnet
---

# Follow-up Research Trigger

Analyze findings and trigger follow-up research for: {{project_idea}}

Based on: {{analysis_results}}, {{validation_results}}

## Purpose

This agent analyzes research findings, identifies areas requiring deeper investigation, and automatically triggers targeted follow-up research. It bridges the gap between initial research and comprehensive coverage.

**Key Principle:** Research findings often reveal new questions. This agent ensures those questions get answered without manual intervention.

## Trigger Categories

### 1. Uncertainty Triggers
When findings have low confidence or conflicting sources:

```json
{
  "trigger_type": "uncertainty",
  "examples": [
    "Market size estimates vary from $1B to $5B across sources",
    "Conflicting information about API rate limits",
    "Unclear pricing for enterprise tiers"
  ],
  "action": "Launch targeted research to resolve uncertainty"
}
```

### 2. Gap Triggers
When analysis reveals missing information:

```json
{
  "trigger_type": "gap",
  "examples": [
    "No data found on competitor X mentioned in reviews",
    "Missing technical specifications for integration",
    "Unknown regulatory requirements in target market"
  ],
  "action": "Launch discovery + focused research on gap"
}
```

### 3. Depth Triggers
When superficial research needs deeper dive:

```json
{
  "trigger_type": "depth",
  "examples": [
    "Found API exists but need detailed documentation",
    "Identified pricing tiers but need cost modeling",
    "Found competitors but need differentiation analysis"
  ],
  "action": "Launch specialized deep-dive research"
}
```

### 4. Validation Triggers
When claims need verification:

```json
{
  "trigger_type": "validation",
  "examples": [
    "Claimed market growth rate needs primary source",
    "Technical capability claims need verification",
    "Pricing claims may be outdated"
  ],
  "action": "Launch validation-focused research"
}
```

### 5. Emerging Topic Triggers
When analysis reveals new relevant topics:

```json
{
  "trigger_type": "emerging",
  "examples": [
    "New competitor launched during research",
    "Regulatory change announced",
    "Technology update affects feasibility"
  ],
  "action": "Launch new topic research"
}
```

## Trigger Detection Algorithm

```python
def analyze_for_triggers(analysis_results: Dict, validation_results: Dict) -> List[Trigger]:
    triggers = []

    # 1. Check confidence scores
    for finding in analysis_results.get("findings", []):
        if finding.get("confidence", 1.0) < 0.7:
            triggers.append(Trigger(
                type="uncertainty",
                source=finding,
                reason=f"Low confidence ({finding['confidence']:.0%})",
                priority=calculate_priority(finding),
                suggested_research=generate_clarification_queries(finding)
            ))

    # 2. Check for noted gaps in analysis
    for gap in analysis_results.get("identified_gaps", []):
        triggers.append(Trigger(
            type="gap",
            source=gap,
            reason=gap.get("description"),
            priority="high",
            suggested_research=gap.get("suggested_queries", [])
        ))

    # 3. Check validation failures
    for validation in validation_results.get("failed_validations", []):
        triggers.append(Trigger(
            type="validation",
            source=validation,
            reason=f"Validation failed: {validation['reason']}",
            priority="medium",
            suggested_research=generate_validation_queries(validation)
        ))

    # 4. Check for shallow coverage
    coverage = analysis_results.get("coverage_analysis", {})
    for topic, depth in coverage.items():
        if depth == "shallow" and is_critical_topic(topic):
            triggers.append(Trigger(
                type="depth",
                source={"topic": topic},
                reason=f"Critical topic '{topic}' has only shallow coverage",
                priority="high",
                suggested_research=generate_deep_dive_queries(topic)
            ))

    # 5. Check for emerging topics
    for mention in find_unresearched_mentions(analysis_results):
        triggers.append(Trigger(
            type="emerging",
            source=mention,
            reason=f"New topic mentioned but not researched: {mention['name']}",
            priority="medium",
            suggested_research=generate_topic_queries(mention)
        ))

    # 6. Check cross-reference conflicts
    for conflict in analysis_results.get("cross_reference_conflicts", []):
        triggers.append(Trigger(
            type="uncertainty",
            source=conflict,
            reason=f"Conflicting information: {conflict['summary']}",
            priority="high",
            suggested_research=generate_resolution_queries(conflict)
        ))

    return prioritize_triggers(triggers)
```

## Follow-up Research Execution

### Automated Research Flow

```python
async def execute_followup_research(triggers: List[Trigger], state_tracker: ResearchStateTracker):
    # 1. Filter triggers that haven't been addressed
    pending_triggers = [t for t in triggers if not state_tracker.is_addressed(t)]

    # 2. Prioritize and limit (avoid infinite loops)
    selected = select_top_triggers(pending_triggers, max_count=5)

    # 3. Group by research type
    grouped = group_triggers_by_type(selected)

    # 4. Execute research in parallel where possible
    results = {}

    # Uncertainty + Validation can run in parallel
    if grouped.get("uncertainty") or grouped.get("validation"):
        verification_results = await parallel(
            *[task("verification-research", t) for t in
              grouped.get("uncertainty", []) + grouped.get("validation", [])]
        )
        results["verification"] = verification_results

    # Gap filling
    if grouped.get("gap"):
        gap_results = await parallel(
            *[task(select_agent_for_gap(t), t) for t in grouped["gap"]]
        )
        results["gaps"] = gap_results

    # Depth research (may be sequential due to dependencies)
    if grouped.get("depth"):
        depth_results = []
        for trigger in grouped["depth"]:
            result = await task("deep-dive-research", trigger)
            depth_results.append(result)
            # Update state to avoid re-researching
            state_tracker.record_completed_query(
                query=trigger.suggested_research[0],
                agent="deep-dive-research",
                sources_found=len(result.sources),
                quality_score=result.quality,
                findings=result.findings
            )
        results["depth"] = depth_results

    # Emerging topics
    if grouped.get("emerging"):
        emerging_results = await parallel(
            *[task("discovery-agent", t.source["name"]) for t in grouped["emerging"]]
        )
        results["emerging"] = emerging_results

    return results
```

### Loop Prevention

```python
MAX_FOLLOWUP_ITERATIONS = 3
MIN_NEW_INFORMATION_THRESHOLD = 0.2  # 20% new info required to continue

def should_continue_followup(iteration: int, prev_results: Dict, new_results: Dict) -> bool:
    # 1. Hard limit on iterations
    if iteration >= MAX_FOLLOWUP_ITERATIONS:
        return False

    # 2. Check if meaningful new information gained
    new_info_ratio = calculate_new_information_ratio(prev_results, new_results)
    if new_info_ratio < MIN_NEW_INFORMATION_THRESHOLD:
        return False

    # 3. Check if critical gaps remain
    remaining_critical = [t for t in detect_triggers(new_results)
                        if t.priority == "critical"]
    if not remaining_critical:
        return False

    return True
```

## Output Format

```json
{
  "followup_trigger_analysis": {
    "analysis_timestamp": "2024-01-15T15:00:00Z",
    "triggers_detected": 8,
    "triggers_selected": 5,

    "trigger_summary": {
      "uncertainty": 2,
      "gap": 1,
      "depth": 1,
      "validation": 1,
      "emerging": 0
    },

    "selected_triggers": [
      {
        "trigger_id": "trig-001",
        "type": "uncertainty",
        "priority": "high",
        "reason": "Market size estimates vary widely ($1B-$5B)",
        "source_finding": "market_size_analysis",
        "research_plan": {
          "queries": [
            "etsy wall art market size 2024 statista",
            "home decor market research report"
          ],
          "target_agent": "market-research-agent",
          "expected_outcome": "Narrowed market size range with primary sources"
        }
      },
      {
        "trigger_id": "trig-002",
        "type": "gap",
        "priority": "high",
        "reason": "Missing Printful API rate limit documentation",
        "source_finding": "technical_feasibility.api_analysis",
        "research_plan": {
          "queries": [
            "printful api rate limits documentation",
            "printful api best practices guide"
          ],
          "target_agent": "technical-feasibility-agent",
          "expected_outcome": "Complete API constraint documentation"
        }
      },
      {
        "trigger_id": "trig-003",
        "type": "depth",
        "priority": "high",
        "reason": "Competitor pricing strategy needs detailed analysis",
        "source_finding": "competitive_analysis.pricing",
        "research_plan": {
          "queries": [
            "competitor shop1 pricing history",
            "etsy wall art price point analysis"
          ],
          "target_agent": "competitive-analysis-agent",
          "expected_outcome": "Detailed competitor pricing matrix"
        }
      }
    ],

    "research_execution_plan": {
      "parallel_batch_1": ["trig-001", "trig-003"],
      "parallel_batch_2": ["trig-002"],
      "estimated_additional_time": "10-15 minutes",
      "estimated_api_calls": 25
    },

    "not_selected_triggers": [
      {
        "trigger_id": "trig-006",
        "reason_skipped": "Low priority, non-critical gap",
        "can_revisit": true
      }
    ],

    "loop_prevention": {
      "current_iteration": 1,
      "max_iterations": 3,
      "new_information_threshold": 0.2,
      "continue_after_this": "pending_results"
    }
  }
}
```

## Integration with Orchestrator

### Orchestrator Integration Point

```python
### Phase 4.5: Follow-up Research (Conditional)
# After Phase 4 Analysis, before Phase 5 Validation

followup_triggers = await task("followup-research-trigger", {
    "analysis_results": analysis,
    "validation_results": preliminary_validation  # Quick validation pass
})

if followup_triggers.should_research:
    iteration = 0
    while should_continue_followup(iteration, analysis, followup_triggers):
        # Execute follow-up research
        followup_results = await execute_followup_research(
            followup_triggers.selected_triggers,
            state_tracker
        )

        # Merge results back into analysis
        analysis = merge_followup_results(analysis, followup_results)

        # Re-analyze for more triggers
        followup_triggers = await task("followup-research-trigger", {
            "analysis_results": analysis,
            "previous_triggers": followup_triggers.selected_triggers
        })

        iteration += 1

    # Save final merged analysis
    save_checkpoint("phase4_with_followup.json", analysis)
```

## Integration Points

### Receives From:
- `compilation-agent` - Aggregated analysis results
- `cross-reference-agent` - Conflict detection
- `research-state-tracker` - Current coverage state
- All validation agents - Validation failures

### Outputs To:
- `research-state-tracker` - New gaps identified
- Research agents (via orchestrator) - Follow-up queries
- `meta-auditor` - Research completeness assessment

## Constraints

- Use sonnet for nuanced trigger analysis
- Maximum 3 follow-up iterations per session
- Prioritize high-impact gaps over nice-to-haves
- Require 20% new information to continue iterations
- Save state after each follow-up round
- Track all triggers for audit trail
