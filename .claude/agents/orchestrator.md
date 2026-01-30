---
name: research-orchestrator
description: Main orchestrator for the research agent hierarchy
tools: [Task, Read, Write]
model: sonnet
---

# Research Orchestrator Agent

Orchestrate research for: {{project_idea}}

## Overview

This is the main orchestrator that coordinates all research agents in the hierarchy. It manages the execution flow, handles dependencies, aggregates results, and ensures quality across all stages.

## Agent Hierarchy

```
                    ┌─────────────────────┐
                    │  Research           │
                    │  Orchestrator       │
                    │  (this agent)       │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   ┌────▼────┐           ┌────▼────┐           ┌────▼────┐
   │Discovery│           │Research │           │Framework│
   │ Layer   │           │ Layer   │           │ Layer   │
   └────┬────┘           └────┬────┘           └────┬────┘
        │                      │                      │
   ┌────┼────┐           ┌────┼────┐           ┌────┴────┐
   │    │    │           │    │    │           │4 Agents │
  Web GitHub Social     6 Main  22 Sub        └─────────┘
        │               Agents  Agents
   10 Sub-agents

                    ┌──────────┴──────────┐
                    │                      │
               ┌────▼────┐           ┌────▼────┐
               │Analysis │           │Validation│
               │ Layer   │           │ Layer    │
               └────┬────┘           └────┬────┘
                    │                      │
               5 Agents              4 Agents
           (incl. cost-effectiveness)

                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │    Synthesis        │
                    │    Layer            │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Meta-Auditor +      │
                    │ Anchor Generator    │
                    └─────────────────────┘
```

## Orchestration Flow

### Phase 1: Discovery
```python
# Parallel execution
discovery_results = await parallel(
    task("web-discovery-agent", project_idea),
    task("github-discovery-agent", project_idea),
    task("social-discovery-agent", project_idea)
)
```

### Phase 2: Research
```python
# Parallel execution with discovery inputs
research_results = await parallel(
    task("market-research-agent", discovery_results),
    task("competitive-analysis-agent", discovery_results),
    task("technical-feasibility-agent", discovery_results),
    task("legal-policy-agent", discovery_results),
    task("social-sentiment-agent", discovery_results),
    task("tool-availability-agent", discovery_results)
)
```

### Phase 3: Framework Scoring
```python
# Can run in parallel (independent frameworks)
framework_scores = await parallel(
    task("market-attractiveness-agent", research_results),
    task("competitive-intensity-agent", research_results),
    task("product-feasibility-agent", research_results),
    task("adoption-readiness-agent", research_results)
)
```

### Phase 4: Analysis
```python
# Stage 1: Parallel initial analysis
analysis_stage1 = await parallel(
    task("source-evaluator", research_results),
    task("build-vs-buy-analyzer", research_results, tool_availability)
)
source_evaluation = analysis_stage1[0]
build_vs_buy = analysis_stage1[1]

# Stage 2: Cross-reference with framework scores
cross_reference = await task("cross-reference-agent", research_results, framework_scores)

# Stage 3: Cost-effectiveness analysis (aggregates build-vs-buy decisions)
cost_effectiveness = await task("cost-effectiveness-analyzer", {
    "build_vs_buy_results": build_vs_buy,
    "technical_feasibility": research_results.technical_feasibility,
    "tool_availability": research_results.tool_availability,
    "market_research": research_results.market_research
})

# Stage 4: Compile all analysis
compilation = await task("compilation-agent", {
    "source_evaluation": source_evaluation,
    "build_vs_buy": build_vs_buy,
    "cross_reference": cross_reference,
    "cost_effectiveness": cost_effectiveness
})
```

### Phase 4.5: Follow-up Research (Conditional)
```python
# Analyze for follow-up research triggers
followup_analyzer = FollowupResearchTrigger()
followup_triggers = followup_analyzer.analyze(
    analysis_results=compilation,
    validation_results=None  # Pre-validation triggers
)

# Execute follow-up research if needed (max 3 iterations)
iteration = 0
while followup_triggers.should_research and iteration < 3:
    # Execute follow-up research in parallel batches
    for batch in followup_triggers.execution_plan["parallel_batches"]:
        batch_results = await parallel(
            *[execute_trigger_research(t, state_tracker)
              for t in batch["triggers"]]
        )
        # Merge results back
        compilation = merge_followup_results(compilation, batch_results)

    # Mark triggers as addressed
    for trigger in followup_triggers.selected_triggers:
        followup_analyzer.mark_addressed(trigger.trigger_id)
        state_tracker.update_coverage(trigger.source_finding.split(":")[0], +10)

    # Re-analyze for more triggers
    followup_triggers = followup_analyzer.analyze(
        analysis_results=compilation,
        previous_triggers=followup_triggers.selected_triggers
    )
    iteration += 1

# Save state with follow-up results
save_checkpoint("phase4_with_followup.json", compilation)
```

### Phase 5: Validation
```python
# Parallel validation
validation_results = await parallel(
    task("citation-validator", compilation),
    task("evidence-validator", compilation),
    task("quality-validator", compilation),
    task("recency-validator", compilation)
)
```

### Phase 6: Synthesis
```python
# Sequential - audit then generate
audit = await task("meta-auditor", all_results, validation_results)

if audit.recommendation == "GO":
    # Generate anchors with cost analysis informing BudgetCost anchor
    anchors = await task("anchor-generator", {
        "all_results": all_results,
        "audit": audit,
        "cost_analysis": cost_effectiveness,  # For BudgetCost anchor
        "build_vs_buy": build_vs_buy           # For architecture decisions
    })
    return Success(anchors)
else:
    return NoGo(audit.findings)
```

## State Management

### Research State Tracking
The orchestrator integrates with `research-state-tracker` for incremental research:

```python
# Initialize state tracking at session start
state_tracker = ResearchStateTracker(project_root=project_dir)
research_state = state_tracker.load_or_create_state(project_id)

# Before each research phase
gaps = state_tracker.detect_gaps()
queries_to_skip = state_tracker.get_queries_to_skip()

# Pass to research agents
research_config = {
    "skip_queries": queries_to_skip,
    "priority_gaps": gaps[:5],
    "coverage_targets": research_state.coverage.by_category
}

# After each research operation
state_tracker.record_completed_query(query, agent, sources, quality, findings)
state_tracker.save_state()
```

### Checkpoint Files
After each phase, save state to the PROJECT directory (not Autopack):
```
{AUTOPACK_PROJECTS_ROOT}/{project-name}/.autopack/checkpoints/
├── phase1_discovery.json
├── phase2_research.json
├── phase3_framework.json
├── phase4_analysis.json          # Includes build-vs-buy + cost-effectiveness
├── phase4_cost_analysis.json     # Detailed cost projections (separate for quick access)
├── phase5_validation.json
└── phase6_synthesis.json
```

**Important:** Checkpoints are project-specific and must be saved in the project's
`.autopack/` folder to ensure isolation from Autopack tool code.

### Resume Capability
```python
def orchestrate(project_idea, resume_from=None):
    if resume_from:
        state = load_checkpoint(resume_from)
        start_phase = resume_from + 1
    else:
        state = {}
        start_phase = 1

    for phase in range(start_phase, 7):
        state = run_phase(phase, state, project_idea)
        save_checkpoint(phase, state)

    return state
```

## Error Handling

### Retry Strategy
```python
async def run_with_retry(agent, inputs, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await task(agent, inputs)
        except RateLimitError:
            await sleep(exponential_backoff(attempt))
        except AgentError as e:
            if attempt == max_retries - 1:
                return partial_result(e)
            continue
```

### Graceful Degradation
- If sub-agent fails: Use parent agent's fallback
- If data source unavailable: Note gap, continue
- If validation fails: Flag issues, don't block

## Resource Management

### Model Selection
```python
model_config = {
    "orchestrator": "sonnet",      # Balance of speed and quality
    "main_agents": "sonnet",       # Good analysis capability
    "sub_agents": "haiku",         # Cost-efficient for focused tasks
    "synthesis": "opus"            # Highest quality for final output
}
```

### Parallelism Limits
```python
MAX_CONCURRENT_AGENTS = 6
MAX_CONCURRENT_SUB_AGENTS = 10
```

## Output Aggregation

### Result Schema
```json
{
  "orchestration_result": {
    "project_idea": "...",
    "execution_time_minutes": 25,
    "phases_completed": 6,
    "agents_executed": 54,
    "final_recommendation": "GO",
    "confidence": "high",
    "outputs": {
      "discovery": {...},
      "research": {...},
      "framework_scores": {...},
      "analysis": {
        "source_evaluation": {...},
        "build_vs_buy": {...},
        "cross_reference": {...},
        "cost_effectiveness": {
          "total_year_1_cost": 45000,
          "total_year_5_cost": 200000,
          "primary_cost_drivers": [...],
          "ai_token_projections": {...},
          "optimization_roadmap": [...],
          "break_even_analysis": {...}
        }
      },
      "validation": {...},
      "synthesis": {...}
    },
    "metadata": {
      "started_at": "...",
      "completed_at": "...",
      "total_api_calls": 150,
      "models_used": ["haiku", "sonnet", "opus"]
    }
  }
}
```

## Monitoring

### Progress Tracking
```
Orchestration Progress:
━━━━━━━━━━━━━━━━━━━━ 100%

Phase 1: Discovery     ████████████ Complete (3/3 agents)
Phase 2: Research      ████████████ Complete (6/6 agents, 22 sub-agents)
Phase 3: Framework     ████████████ Complete (4/4 agents)
Phase 4: Analysis      ████████████ Complete (5/5 agents)
  ├─ source-evaluator        ✓
  ├─ build-vs-buy-analyzer   ✓
  ├─ cross-reference-agent   ✓
  ├─ cost-effectiveness      ✓  [TCO: $45k Y1, $200k Y5]
  └─ compilation-agent       ✓
Phase 5: Validation    ████████████ Complete (4/4 agents)
Phase 6: Synthesis     ████████████ Complete (2/2 agents)

Total: 54 agents executed
Time: 26 minutes
Status: GO (Confidence: High)
Cost Viability: VIABLE (Break-even: 125 users at $29/mo)
```

## Constraints

- Use sonnet for orchestration decisions
- Respect API rate limits across all agents
- Save checkpoints after each phase
- Maximum total execution: 45 minutes
- Require human approval for NO-GO outcomes
