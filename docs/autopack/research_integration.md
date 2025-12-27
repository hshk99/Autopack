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
