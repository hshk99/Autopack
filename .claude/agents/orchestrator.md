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
               3 Agents              4 Agents

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
# Sequential - each builds on previous
source_evaluation = await task("source-evaluator", research_results)
cross_reference = await task("cross-reference-agent", research_results, framework_scores)
compilation = await task("compilation-agent", all_results)
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
    anchors = await task("anchor-generator", all_results, audit)
    return Success(anchors)
else:
    return NoGo(audit.findings)
```

## State Management

### Checkpoint Files
After each phase, save state to the PROJECT directory (not Autopack):
```
{AUTOPACK_PROJECTS_ROOT}/{project-name}/.autopack/checkpoints/
├── phase1_discovery.json
├── phase2_research.json
├── phase3_framework.json
├── phase4_analysis.json
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
    "agents_executed": 52,
    "final_recommendation": "GO",
    "confidence": "high",
    "outputs": {
      "discovery": {...},
      "research": {...},
      "framework_scores": {...},
      "analysis": {...},
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
Phase 4: Analysis      ████████████ Complete (3/3 agents)
Phase 5: Validation    ████████████ Complete (4/4 agents)
Phase 6: Synthesis     ████████████ Complete (2/2 agents)

Total: 52 agents executed
Time: 24 minutes
Status: GO (Confidence: High)
```

## Constraints

- Use sonnet for orchestration decisions
- Respect API rate limits across all agents
- Save checkpoints after each phase
- Maximum total execution: 45 minutes
- Require human approval for NO-GO outcomes
