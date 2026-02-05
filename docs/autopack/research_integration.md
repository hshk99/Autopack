# Research System Integration

This document describes how the research system integrates with Autopack's core infrastructure.

## Overview

The research system is integrated into Autopack through several key integration points:

1. **BUILD_HISTORY Integration** - Learns from past build decisions
2. **Phase System** - Implements RESEARCH as a first-class phase type
3. **Autonomous Mode** - Triggers research automatically when beneficial
4. **Review Workflow** - Validates research results before proceeding

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Autonomous Executor                       │
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │   Planning   │─────▶│  Execution   │                    │
│  └──────┬───────┘      └──────────────┘                    │
│         │                                                    │
│         │ pre_planning_hook()                               │
│         ▼                                                    │
│  ┌──────────────────────────────────────────────┐          │
│  │         Research Hooks                        │          │
│  │  • should_research()                          │          │
│  │  • execute_research()                         │          │
│  │  • post_planning_hook()                       │          │
│  └──────┬───────────────────────────────────────┘          │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────────────────┐          │
│  │      BUILD_HISTORY Integrator                 │          │
│  │  • Analyze patterns                           │          │
│  │  • Recommend research                         │          │
│  └──────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Research Phase                            │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │   Research   │─────▶│   Storage    │                    │
│  │   Session    │      │              │                    │
│  └──────────────┘      └──────────────┘                    │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Review Workflow                             │
│  • Auto-approval for high confidence                         │
│  • Human review for critical decisions                       │
│  • Integration with BUILD_HISTORY                            │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. BUILD_HISTORY Integrator

**Location**: `src/autopack/integrations/build_history_integrator.py`

**Purpose**: Analyzes past build decisions to inform research triggers.

**Key Features**:
- Parses BUILD_HISTORY.md to extract phase outcomes
- Identifies patterns in success/failure rates
- Recommends research based on historical data
- Provides context-aware suggestions

**Usage**:
```python
from autopack.integrations.build_history_integrator import BuildHistoryIntegrator

integrator = BuildHistoryIntegrator(
    build_history_path=Path("BUILD_HISTORY.md")
)

# Analyze patterns
patterns = integrator.analyze_patterns()

# Check if research should be triggered
should_research = integrator.should_trigger_research(
    task_description="Implement new feature",
    phase_type="IMPLEMENT_FEATURE"
)
```

### 2. Research Phase

**Location**: `src/autopack/phases/research_phase.py`

**Purpose**: Implements RESEARCH as a phase type in the build system.

**Key Features**:
- Executes research sessions with configurable parameters
- Extracts findings and recommendations
- Calculates confidence scores
- Stores results for later reference

**Usage**:
```python
from autopack.phases.research_phase import ResearchPhase, ResearchPhaseConfig

config = ResearchPhaseConfig(
    query="What are best practices for API design?",
    max_iterations=5,
    time_limit_seconds=300,
    required_confidence=0.7
)

phase = ResearchPhase(config=config)
result = phase.execute()

if result.success:
    print(f"Findings: {result.findings}")
    print(f"Recommendations: {result.recommendations}")
```

### 3. Research Hooks

**Location**: `src/autopack/autonomous/research_hooks.py`

**Purpose**: Provides integration hooks for autonomous mode.

**Key Features**:
- Non-invasive integration with existing executor
- Configurable research triggers
- Pre/post-planning hooks
- Graceful degradation if research unavailable

**Usage**:
```python
from autopack.autonomous.research_hooks import ResearchHooks, ResearchTriggerConfig

config = ResearchTriggerConfig(
    enabled=True,
    auto_trigger=True,
    build_history_path=Path("BUILD_HISTORY.md")
)

hooks = ResearchHooks(config=config)

# Pre-planning hook
context = hooks.pre_planning_hook(
    task_description="Implement authentication",
    phase_type="IMPLEMENT_FEATURE",
    context={}
)

# Check if research was triggered
if 'research_result' in context:
    print(f"Research findings: {context['research_findings']}")
```

### 4. Review Workflow

**Location**: `src/autopack/workflow/research_review.py`

**Purpose**: Manages review and approval of research results.

**Key Features**:
- Auto-approval for high-confidence research
- Human review workflow for critical decisions
- Review storage and retrieval
- Integration with BUILD_HISTORY

**Usage**:
```python
from autopack.workflow.research_review import ResearchReviewWorkflow, ReviewConfig

config = ReviewConfig(
    auto_approve_threshold=0.9,
    require_human_review=False
)

workflow = ResearchReviewWorkflow(config=config)
review = workflow.review_research(research_result, context={})

if review.decision == ReviewDecision.APPROVED:
    print("Research approved, proceeding with implementation")
```

## Integration Points

### Autonomous Mode Integration

The research system integrates with autonomous mode through hooks:

1. **Pre-Planning Hook**: Called before planning phase
   - Checks if research should be triggered
   - Executes research if needed
   - Injects findings into planning context

2. **Post-Planning Hook**: Called after planning phase
   - Augments plan with research metadata
   - Adds recommendations as plan notes
   - Links to research session for audit trail

### BUILD_HISTORY Integration

Research decisions are recorded in BUILD_HISTORY:

```markdown
## Phase: RESEARCH - API Design Best Practices (SUCCESS) [2024-01-15T10:30:00]

**Research Session**: abc123
**Confidence**: 0.85
**Findings**: 3 key findings
**Recommendations**: 2 recommendations

Research completed successfully. Findings will inform implementation phase.
```

### CLI Integration

Research commands are available through the CLI:

```bash
# Start research session
autopack research start "What are best practices for API design?"

# List past sessions
autopack research list

# Show session details
autopack research show abc123

# Export results
autopack research export abc123 --format markdown

# Analyze BUILD_HISTORY
autopack research analyze-history
```

## Configuration

### Research Trigger Configuration

```python
ResearchTriggerConfig(
    enabled=True,                    # Enable research system
    auto_trigger=True,               # Auto-trigger based on heuristics
    min_confidence_threshold=0.7,    # Minimum confidence for success
    max_research_time_seconds=300,   # Time limit per session
    build_history_path=Path("BUILD_HISTORY.md"),
    research_output_dir=Path(".autopack/research")
)
```

### Review Configuration

```python
ReviewConfig(
    auto_approve_threshold=0.9,      # Auto-approve above this confidence
    require_human_review=True,       # Require human review
    review_timeout_seconds=3600,     # Review timeout
    store_reviews=True,              # Store review decisions
    review_storage_dir=Path(".autopack/reviews")
)
```

## Best Practices

1. **Research Triggers**:
   - Use BUILD_HISTORY patterns to inform triggers
   - Consider task complexity and novelty
   - Balance research time vs. implementation time

2. **Confidence Thresholds**:
   - Set appropriate thresholds for auto-approval
   - Require human review for critical decisions
   - Adjust based on domain and risk tolerance

3. **Storage and Retrieval**:
   - Store research results for future reference
   - Link research sessions to implementation phases
   - Maintain audit trail in BUILD_HISTORY

4. **Error Handling**:
   - Gracefully degrade if research system unavailable
   - Continue with implementation if research fails
   - Log research failures for investigation

## Testing

Comprehensive tests are provided:

- **Unit Tests**: Test individual components
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete workflows

Run tests:
```bash
pytest tests/autopack/integrations/
pytest tests/autopack/phases/
pytest tests/autopack/autonomous/
pytest tests/autopack/workflow/
pytest tests/autopack/integration/
```

## Research Complete Callback (IMP-TRIGGER-001)

The research complete callback system enables mid-execution research triggering through a flexible callback mechanism. When research gaps are detected, the system can automatically trigger follow-up research without pausing execution.

### Overview

**Location**: `src/autopack/research/analysis/followup_trigger.py`

**Purpose**: Detect research gaps and automatically invoke registered callbacks for mid-execution research closure.

### Trigger Types

The system detects five types of research triggers:

| Type | Detection | Priority |
|------|-----------|----------|
| **UNCERTAINTY** | Low confidence findings (< 70%) | Dynamic based on confidence |
| **GAP** | Identified missing information | High |
| **DEPTH** | Critical topics with shallow coverage | High |
| **VALIDATION** | Failed validation claims | Medium |
| **EMERGING** | New unresearched entities mentioned | Medium |

### Callback Registration

Register callbacks with the autopilot controller to handle research triggers:

```python
from autopack.autonomy.autopilot import AutopilotController
from autopack.research.analysis.followup_trigger import FollowupTrigger

async def handle_research_trigger(trigger: FollowupTrigger):
    """Handle a research trigger by executing the planned research."""
    # Access trigger information
    print(f"Trigger: {trigger.trigger_type.value}")
    print(f"Reason: {trigger.reason}")
    print(f"Research Plan: {trigger.research_plan.queries}")

    # Execute research based on the plan
    findings = await execute_research(trigger.research_plan)

    # Return research results
    return {"findings": findings, "confidence": 0.85}

# Register the callback
controller = AutopilotController()
controller.register_followup_callback(handle_research_trigger)
```

### Async Callback Registration

For concurrent callback execution, use async callbacks:

```python
async def handle_research_async(trigger: FollowupTrigger):
    """Handle research trigger asynchronously."""
    research_result = await research_orchestrator.execute(
        trigger.research_plan
    )
    return {"findings": research_result.findings}

# Register async callback
controller.register_followup_async_callback(handle_research_async)
```

### Execution Flow

When triggers are detected, callbacks are executed in order:

1. **Analysis Phase**: Detect research gaps
   - Low confidence findings
   - Missing information
   - Shallow coverage on critical topics
   - Failed validations
   - New entities

2. **Selection Phase**: Prioritize triggers
   - Select up to 5 high-priority triggers
   - Skip already-addressed triggers
   - Consider budget constraints

3. **Callback Execution**: Invoke registered callbacks
   - Synchronous callbacks invoked sequentially
   - Async callbacks invoked concurrently (up to 3 at a time)
   - Results aggregated and stored

4. **Decision Phase**: Determine next action
   - PROCEED: Continue execution
   - PAUSE_FOR_RESEARCH: Pause for additional research
   - ADJUST_PLAN: Modify execution plan based on findings
   - BLOCK: Block execution due to critical gaps

### Telemetry and Observability

The system tracks comprehensive callback execution metrics:

```python
# Access metrics from research cycle integration
metrics = autopilot.research_cycle_integration.get_metrics()

print(f"Total callbacks invoked: {metrics.total_callbacks_invoked}")
print(f"Callbacks succeeded: {metrics.total_callbacks_succeeded}")
print(f"Callbacks failed: {metrics.total_callbacks_failed}")
print(f"Total callback time: {metrics.total_callback_time_ms}ms")
print(f"Total triggers detected: {metrics.total_triggers_detected}")
print(f"Total triggers executed: {metrics.total_triggers_executed}")
```

### Loop Prevention

The system prevents infinite research loops with:

- **Max Iterations**: Limited to 3 followup research iterations
- **Minimum New Information**: Requires 20% new information to continue
- **Addressed Tracking**: Prevents re-researching same gaps
- **Previous Triggers**: Deduplication across iterations

### Example: Complete Flow

```python
# 1. Register callback
async def my_research_handler(trigger):
    # Perform research based on trigger.research_plan
    return {"insights": [...]}

controller.register_followup_async_callback(my_research_handler)

# 2. Execute research cycle (happens automatically in autopilot)
# Research analysis detects triggers
# Callbacks are invoked
# Results are integrated

# 3. Access results
outcome = autopilot._last_research_outcome
if outcome and outcome.trigger_result:
    print(f"Detected: {outcome.trigger_result.triggers_detected} triggers")
    print(f"Selected: {outcome.trigger_result.triggers_selected} for research")
    if outcome.trigger_result.execution_result:
        result = outcome.trigger_result.execution_result
        print(f"Executed: {result.triggers_executed} callbacks")
        print(f"Success rate: {result.successful_executions}/{result.callbacks_invoked}")
```

## Future Enhancements

1. **Machine Learning Integration**:
   - Learn optimal research triggers from outcomes
   - Predict research value before execution
   - Adaptive confidence thresholds

2. **Distributed Research**:
   - Parallel research sessions
   - Distributed knowledge base
   - Collaborative research across builds

3. **Advanced Analytics**:
   - Research ROI metrics
   - Pattern mining from research history
   - Recommendation quality scoring
