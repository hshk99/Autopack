# Research Workflow Guide

This guide describes the complete workflow for using the research system in Autopack.

## Workflow Overview

```
┌─────────────────┐
│  Task Received  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  Should Research?           │
│  • Check BUILD_HISTORY      │
│  • Analyze task complexity  │
│  • Check keywords           │
└────────┬────────────────────┘
         │
         ├─── No ──▶ Continue to Planning
         │
         ▼ Yes
┌─────────────────────────────┐
│  Execute Research Phase     │
│  • Formulate query          │
│  • Run research session     │
│  • Extract findings         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Review Research Results    │
│  • Check confidence         │
│  • Auto-approve or review   │
│  • Store decision           │
└────────┬────────────────────┘
         │
         ├─── Rejected ──▶ More Research or Abort
         │
         ▼ Approved
┌─────────────────────────────┐
│  Augment Planning Context   │
│  • Add findings             │
│  • Add recommendations      │
│  • Link research session    │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Proceed with Planning      │
│  • Use research insights    │
│  • Reference findings       │
│  • Follow recommendations   │
└─────────────────────────────┘
```

## Step-by-Step Workflow

### 1. Task Reception

When a new task is received, the system evaluates whether research would be beneficial.

**Triggers for Research**:
- Task contains research keywords ("research", "investigate", "explore")
- Task involves unfamiliar territory ("new", "unknown")
- Task is complex ("complex", "multiple approaches")
- BUILD_HISTORY shows low success rate for similar tasks
- Task explicitly requests research

### 2. Research Decision

The system uses multiple signals to decide if research should be triggered:

```python
# Automatic decision
if hooks.should_research(task_description, phase_type, context):
    # Trigger research
    pass

# Manual trigger via CLI
autopack research start "Your research query"
```

**Decision Factors**:
1. **BUILD_HISTORY Analysis**: Past success rates for similar tasks
2. **Task Characteristics**: Complexity, novelty, keywords
3. **Context Flags**: Explicit research requirements
4. **Configuration**: Auto-trigger settings

### 3. Research Execution

Once triggered, the research phase executes:

```python
# Configure research
config = ResearchPhaseConfig(
    query="What are best practices for X?",
    max_iterations=5,
    time_limit_seconds=300,
    required_confidence=0.7
)

# Execute
phase = ResearchPhase(config=config)
result = phase.execute()
```

**Research Process**:
1. Formulate research query from task description
2. Execute research session (up to max_iterations)
3. Extract findings from research results
4. Generate recommendations
5. Calculate confidence score
6. Store results and artifacts

### 4. Result Review

Research results are reviewed before proceeding:

```python
# Configure review
review_config = ReviewConfig(
    auto_approve_threshold=0.9,
    require_human_review=False
)

# Review results
workflow = ResearchReviewWorkflow(config=review_config)
review = workflow.review_research(research_result, context)
```

**Review Outcomes**:
- **APPROVED**: High confidence, proceed with findings
- **REJECTED**: Low quality, need more research
- **NEEDS_MORE_RESEARCH**: Insufficient findings
- **PENDING**: Awaiting human review

**Auto-Approval Criteria**:
- Confidence score ≥ auto_approve_threshold
- At least 2 findings extracted
- Research session completed successfully

### 5. Context Augmentation

Approved research results augment the planning context:

```python
# Pre-planning hook adds research to context
context = hooks.pre_planning_hook(
    task_description,
    phase_type,
    context
)

# Context now includes:
# - research_result: Full research result
# - research_findings: List of findings
# - research_recommendations: List of recommendations
# - research_confidence: Confidence score
```

### 6. Planning with Research

The planner uses research insights:

```python
# Plan is created with research context
plan = create_plan(task_description, context)

# Post-planning hook augments plan
final_plan = hooks.post_planning_hook(plan, context)

# Plan now includes:
# - metadata.research_session_id
# - metadata.research_confidence
# - notes with recommendations
```

## Usage Examples

### Example 1: Automatic Research Trigger

```python
# Task that triggers research automatically
task = "Research and implement OAuth2 authentication"

# System detects "research" keyword and triggers
context = {}
context = hooks.pre_planning_hook(task, "IMPLEMENT_FEATURE", context)

# Context now has research results
if 'research_result' in context:
    print(f"Research completed: {len(context['research_findings'])} findings")
    for finding in context['research_findings']:
        print(f"  - {finding}")
```

### Example 2: Manual Research Session

```bash
# Start research from CLI
autopack research start "What are best practices for API versioning?"

# View results
autopack research show <session_id>

# Export for reference
autopack research export <session_id> --format markdown --output api_versioning.md
```

### Example 3: BUILD_HISTORY-Driven Research

```python
# Analyze BUILD_HISTORY
integrator = BuildHistoryIntegrator(
    build_history_path=Path("BUILD_HISTORY.md")
)

# Get recommendations
recommendations = integrator.get_research_recommendations(
    "Implement new payment processing"
)

# Check if research should be triggered
if integrator.should_trigger_research("Implement payment", "IMPLEMENT_FEATURE"):
    print("BUILD_HISTORY suggests research for this task")
    for rec in recommendations:
        print(f"  - {rec}")
```

### Example 4: Human Review Workflow

```python
# Configure for human review
review_config = ReviewConfig(
    auto_approve_threshold=0.9,
    require_human_review=True  # Always require human review
)

workflow = ResearchReviewWorkflow(config=review_config)

# Research is executed
research_result = phase.execute()

# Review is pending
review = workflow.review_research(research_result, {})
assert review.decision == ReviewDecision.PENDING

# Human submits review
final_review = workflow.submit_review(
    session_id=research_result.session_id,
    decision=ReviewDecision.APPROVED,
    reviewer="john_doe",
    comments="Findings look good, proceed with implementation",
    approved_findings=research_result.findings
)
```

## Configuration Options

### Research Trigger Configuration

```python
ResearchTriggerConfig(
    # Enable/disable research system
    enabled=True,

    # Auto-trigger based on heuristics
    auto_trigger=True,

    # Minimum confidence for success
    min_confidence_threshold=0.7,

    # Time limit per research session
    max_research_time_seconds=300,

    # Path to BUILD_HISTORY for pattern analysis
    build_history_path=Path("BUILD_HISTORY.md"),

    # Output directory for research results
    research_output_dir=Path(".autopack/research")
)
```

### Research Phase Configuration

```python
ResearchPhaseConfig(
    # Research query
    query="What are best practices for X?",

    # Maximum research iterations
    max_iterations=5,

    # Time limit in seconds
    time_limit_seconds=300,

    # Required confidence for success
    required_confidence=0.7,

    # Output directory
    output_dir=Path(".autopack/research"),

    # Store results to disk
    store_results=True
)
```

### Review Configuration

```python
ReviewConfig(
    # Auto-approve above this confidence
    auto_approve_threshold=0.9,

    # Require human review
    require_human_review=False,

    # Review timeout
    review_timeout_seconds=3600,

    # Store review decisions
    store_reviews=True,

    # Review storage directory
    review_storage_dir=Path(".autopack/reviews")
)
```

## Best Practices

### 1. Research Query Formulation

**Good Queries**:
- "What are best practices for API versioning in REST APIs?"
- "How should I implement rate limiting in a web service?"
- "What are common security considerations for OAuth2?"

**Poor Queries**:
- "API" (too vague)
- "How do I code?" (too broad)
- "Fix bug" (not a research question)

### 2. Confidence Thresholds

- **High-risk tasks**: Set threshold to 0.9+ and require human review
- **Standard tasks**: Use 0.7-0.8 threshold with auto-approval
- **Exploratory tasks**: Accept 0.6+ threshold

### 3. Time Limits

- **Quick research**: 60-120 seconds, 2-3 iterations
- **Standard research**: 300 seconds, 5 iterations
- **Deep research**: 600+ seconds, 10+ iterations

### 4. Storage and Organization

```
.autopack/
├── research/
│   ├── session_abc123.json
│   ├── session_abc123_summary.md
│   └── ...
└── reviews/
    ├── session_abc123_review.json
    └── ...
```

### 5. Integration with BUILD_HISTORY

Always record research phases in BUILD_HISTORY:

```markdown
## Phase: RESEARCH - API Design Best Practices (SUCCESS) [2024-01-15T10:30:00]

**Session**: abc123
**Query**: What are best practices for RESTful API design?
**Confidence**: 0.85
**Findings**: 5 key findings extracted
**Recommendations**: 3 recommendations provided

Research completed successfully. Key findings:
1. Use proper HTTP methods (GET, POST, PUT, DELETE)
2. Implement versioning from the start
3. Provide comprehensive documentation

Proceeding with implementation phase using research insights.
```

## Troubleshooting

### Research Not Triggering

**Problem**: Research doesn't trigger when expected

**Solutions**:
1. Check `enabled=True` in config
2. Verify `auto_trigger=True`
3. Check BUILD_HISTORY exists and is readable
4. Add explicit research keywords to task description
5. Set `requires_research=True` in context

### Low Confidence Scores

**Problem**: Research consistently produces low confidence

**Solutions**:
1. Increase `max_iterations`
2. Extend `time_limit_seconds`
3. Refine research query to be more specific
4. Check research system connectivity
5. Review research session logs

### Review Workflow Issues

**Problem**: Reviews not being stored or retrieved

**Solutions**:
1. Check `store_reviews=True`
2. Verify `review_storage_dir` exists and is writable
3. Check file permissions
4. Review error logs

## Monitoring and Metrics

### Key Metrics to Track

1. **Research Trigger Rate**: How often research is triggered
2. **Research Success Rate**: Percentage of successful research sessions
3. **Average Confidence**: Mean confidence score across sessions
4. **Time per Session**: Average research duration
5. **Auto-Approval Rate**: Percentage of auto-approved results
6. **Research ROI**: Impact on implementation success rate

### Logging

Research system logs important events:

```python
import logging

logger = logging.getLogger('autopack.research')
logger.setLevel(logging.INFO)

# Logs include:
# - Research trigger decisions
# - Research execution progress
# - Confidence calculations
# - Review decisions
# - Integration events
```

## Advanced Usage

### Custom Research Triggers

```python
class CustomResearchHooks(ResearchHooks):
    def should_research(self, task_description, phase_type, context):
        # Custom logic
        if context.get('team_size', 0) > 5:
            return True  # Large teams benefit from research
        return super().should_research(task_description, phase_type, context)
```

### Research Result Post-Processing

```python
def post_process_research(result: ResearchPhaseResult) -> ResearchPhaseResult:
    # Filter findings
    result.findings = [
        f for f in result.findings
        if len(f) > 50  # Only substantial findings
    ]

    # Enhance recommendations
    result.recommendations = [
        f"[HIGH PRIORITY] {rec}" if "critical" in rec.lower() else rec
        for rec in result.recommendations
    ]

    return result
```

### Integration with External Systems

```python
class ExternalResearchIntegration:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def augment_research(self, result: ResearchPhaseResult):
        # Call external API for additional insights
        external_data = self.fetch_external_insights(result.query)
        result.findings.extend(external_data['insights'])
        return result
```
