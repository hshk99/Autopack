# Self-Improvement Loop Architecture

> **IMP-DOC-001**: Comprehensive documentation of the telemetry → memory → task generation feedback loop

## Overview

Autopack implements a **closed-loop self-improvement system** that continuously learns from execution outcomes to improve future performance. This architecture enables the system to:

- Detect issues from telemetry data
- Store learnings in persistent memory
- Generate improvement tasks automatically
- Track task effectiveness and adjust confidence
- Prevent goal drift during autonomous execution

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SELF-IMPROVEMENT FEEDBACK LOOP                      │
└─────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
    │   EXECUTE    │────────▶│   ANALYZE    │────────▶│    STORE     │
    │    PHASE     │         │  TELEMETRY   │         │   MEMORY     │
    └──────────────┘         └──────────────┘         └──────────────┘
           ▲                                                  │
           │                                                  │
           │                                                  ▼
    ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
    │   INJECT     │◀────────│   GENERATE   │◀────────│   RETRIEVE   │
    │   CONTEXT    │         │    TASKS     │         │   INSIGHTS   │
    └──────────────┘         └──────────────┘         └──────────────┘
           │                                                  ▲
           │                                                  │
           ▼                                                  │
    ┌──────────────────────────────────────────────────────────────────┐
    │                    EFFECTIVENESS TRACKING                         │
    │   (Confidence Updates, Rule Generation, Goal Drift Detection)    │
    └──────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Complete Pipeline

```
Phase Execution Completes
        │
        ▼
┌─────────────────────────────────────────┐
│      TelemetryAnalyzer                  │
│  aggregate_telemetry(window_days)       │
│  - find_cost_sinks()                    │
│  - find_failure_modes()                 │
│  - find_retry_causes()                  │
└─────────────────────────────────────────┘
        │
        ▼ RankedIssues
┌─────────────────────────────────────────┐
│      TelemetryToMemoryBridge            │
│  (Circuit breaker + fallback queue)     │
│  - 3 retry attempts                     │
│  - File-based fallback on failure       │
│  - Automatic queue draining             │
└─────────────────────────────────────────┘
        │
        ▼ Persisted Insights
┌─────────────────────────────────────────┐
│      MemoryService                      │
│  - Vector embeddings (FAISS/Qdrant)     │
│  - Content compression (>5000 chars)    │
│  - Freshness filtering (30 days)        │
│  - Project namespace isolation          │
└─────────────────────────────────────────┘
        │
        ▼ Retrieved Insights
┌─────────────────────────────────────────┐
│      AutonomousTaskGenerator (ROAD-C)   │
│  - Multi-source insight collection      │
│  - Confidence-based filtering           │
│  - Task deduplication                   │
└─────────────────────────────────────────┘
        │
        ▼ UnifiedInsights
┌─────────────────────────────────────────┐
│      PriorityEngine                     │
│  - Success rate ranking                 │
│  - Blocking pattern detection           │
│  - Freshness-based boosting             │
└─────────────────────────────────────────┘
        │
        ▼ Prioritized Tasks
┌─────────────────────────────────────────┐
│      ROIAnalyzer                        │
│  - Payback period calculation           │
│  - Risk-adjusted ROI                    │
│  - Profitability assessment             │
└─────────────────────────────────────────┘
        │
        ▼ GeneratedTasks (ordered)
┌─────────────────────────────────────────┐
│      TaskEffectivenessTracker           │
│  - Register for verification            │
│  - Track before/after metrics           │
│  - Pattern detection                    │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│      AutonomousExecutor                 │
│  - ContextInjector retrieves memory     │
│  - Builder receives enriched prompt     │
│  - Phase execution with learnings       │
└─────────────────────────────────────────┘
        │
        ▼ Phase Outcome
┌─────────────────────────────────────────┐
│      FeedbackPipeline                   │
│  process_phase_outcome()                │
│  - Update MemoryService                 │
│  - Extract learning rules               │
│  - Validate task effectiveness          │
└─────────────────────────────────────────┘
        │
        ▼
   Next Iteration...
```

## Component Responsibilities

### 1. Telemetry Collection & Analysis

| Component | File | Purpose |
|-----------|------|---------|
| **TelemetryAnalyzer** | `src/autopack/telemetry/analyzer.py` | Aggregates phase outcomes, identifies cost sinks, failure modes, and retry causes |
| **AnomalyDetector** | `src/autopack/telemetry/anomaly_detector.py` | Real-time anomaly detection for token spikes, failure rates, duration anomalies |
| **CausalAnalyzer** | `src/autopack/telemetry/causal_analysis.py` | Analyzes causal relationships between changes and outcomes |
| **MetaMetricsTracker** | `src/autopack/telemetry/meta_metrics.py` | Measures feedback loop quality itself (ROAD-K) |
| **CostTracker** | `src/autopack/telemetry/cost_tracker.py` | Tracks token costs and budget management |

#### Key Data Structures

```python
@dataclass
class RankedIssue:
    """Issue detected from telemetry analysis."""
    rank: int
    issue_type: str  # cost_sink, failure_mode, retry_cause
    phase_id: str
    metric_value: float
    details: dict

@dataclass
class AnomalyAlert:
    """Real-time anomaly detection alert."""
    severity: str  # warning, critical
    metric: str
    phase_id: str
    current_value: float
    threshold: float
    baseline: float
```

### 2. Memory Service & Storage

| Component | File | Purpose |
|-----------|------|---------|
| **MemoryService** | `src/autopack/memory/memory_service.py` | Central vector memory store with semantic search |
| **ContextInjector** | `src/autopack/memory/context_injector.py` | Retrieves and formats historical context for injection |
| **GoalDrift** | `src/autopack/memory/goal_drift.py` | Prevents goal drift using embedding similarity |
| **InsightProvenance** | `src/autopack/memory/insight_provenance.py` | Audit trail from telemetry → insights → tasks |
| **Maintenance** | `src/autopack/memory/maintenance.py` | Lifecycle management (pruning, compression) |

#### Memory Collections

| Collection | Contents |
|------------|----------|
| `code_docs` | Workspace files and embeddings |
| `run_summaries` | Phase summaries with changes and outcomes |
| `errors_ci` | Failing test/error snippets |
| `doctor_hints` | Doctor hints and actions |
| `insights` | Telemetry insights from analysis |
| `discoveries` | External research insights (GitHub, Reddit, Web) |

#### Key Data Structures

```python
@dataclass
class ContextInjection:
    """Context retrieved for injection into prompts."""
    past_errors: List[str]
    strategies: List[str]
    hints: List[str]
    insights: List[str]

@dataclass
class EnrichedContextInjection:
    """Context with quality metadata."""
    context: ContextInjection
    freshness_hours: float
    confidence: float
    relevance_score: float
```

### 3. Task Generation

| Component | File | Purpose |
|-----------|------|---------|
| **AutonomousTaskGenerator** | `src/autopack/roadc/task_generator.py` | Converts unified insights into actionable tasks (ROAD-C) |
| **PriorityEngine** | `src/autopack/task_generation/priority_engine.py` | Data-driven task prioritization |
| **ROIAnalyzer** | `src/autopack/task_generation/roi_analyzer.py` | Calculate ROI including payback period |
| **TaskEffectivenessTracker** | `src/autopack/task_generation/task_effectiveness_tracker.py` | Closed-loop task validation |
| **DiscoveryContextMerger** | `src/autopack/roadc/discovery_context_merger.py` | Merges external research insights |

#### Insight Sources (Pluggable Architecture)

```python
class InsightConsumer(Protocol):
    """Protocol for pluggable insight sources."""
    def get_insights(self) -> List[UnifiedInsight]: ...

# Available consumers:
# - DirectInsightConsumer: Direct telemetry data
# - AnalyzerInsightConsumer: TelemetryAnalyzer output
# - MemoryInsightConsumer: Historical insights from MemoryService
```

#### Key Data Structures

```python
@dataclass
class UnifiedInsight:
    """Consistent insight format from any source."""
    id: str
    source: InsightSource  # DIRECT, ANALYZER, MEMORY
    category: str
    description: str
    confidence: float
    evidence: List[str]

@dataclass
class GeneratedTask:
    """Output task with execution metadata."""
    id: str
    title: str
    description: str
    priority: str  # critical, high, medium, low
    complexity: str
    estimated_cost: float
    source_insights: List[str]
```

### 4. Feedback Pipeline

| Component | File | Purpose |
|-----------|------|---------|
| **FeedbackPipeline** | `src/autopack/feedback_pipeline.py` | Unified orchestration of the complete loop |
| **TelemetryToMemoryBridge** | `src/autopack/telemetry/telemetry_to_memory_bridge.py` | Resilient bridge with circuit breaker |
| **LearningPipeline** | `src/autopack/executor/learning_pipeline.py` | Records lessons learned during execution |

#### FeedbackPipeline Methods

```python
class FeedbackPipeline:
    def process_phase_outcome(self, outcome: PhaseOutcome) -> None:
        """Capture telemetry and persist to memory."""
        pass

    def get_context_for_phase(self, phase_id: str) -> PhaseContext:
        """Retrieve context for next phase planning."""
        pass
```

### 5. Autonomous Execution

| Component | File | Purpose |
|-----------|------|---------|
| **AutonomousExecutor** | `src/autopack/autonomous_executor.py` | Main orchestration for phase execution |
| **AutonomousLoop** | `src/autopack/executor/autonomous_loop.py` | Main execution loop with circuit breaker |
| **ExecutorStateCheckpoint** | `src/autopack/executor/run_checkpoint.py` | Crash recovery with state restoration |

#### Circuit Breaker Configuration

```python
class CircuitBreaker:
    """Prevents runaway execution on repeated failures."""
    failure_threshold: int = 5      # Consecutive failures to trip
    reset_timeout: int = 300        # Seconds before testing recovery
    half_open_max_calls: int = 1    # Test calls in HALF_OPEN state

    # States: CLOSED (normal) → OPEN (tripped) → HALF_OPEN (testing)
```

## Pipeline Latency SLAs

The MetaMetricsTracker monitors latency through each stage:

| Stage | SLA |
|-------|-----|
| PHASE_COMPLETE → TELEMETRY_COLLECTED | 60 seconds |
| TELEMETRY_COLLECTED → MEMORY_PERSISTED | 60 seconds |
| MEMORY_PERSISTED → TASK_GENERATED | 60 seconds |
| TASK_GENERATED → TASK_EXECUTED | 120 seconds |
| **Total End-to-End** | **300 seconds (5 minutes)** |

## Resilience Features

### TelemetryToMemoryBridge

```
┌─────────────────────────────────────────────────────────────────┐
│                    Circuit Breaker Pattern                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Normal Operation                   Failure Recovery            │
│  ┌───────────┐                     ┌───────────────────┐       │
│  │  CLOSED   │──3 failures──▶      │  Fallback Queue   │       │
│  └───────────┘                     │  (file-based)     │       │
│       ▲                            └───────────────────┘       │
│       │                                     │                   │
│       │ success                             │                   │
│       │                                     ▼                   │
│  ┌───────────┐                     ┌───────────────────┐       │
│  │ HALF_OPEN │◀───────────────────│      OPEN         │       │
│  └───────────┘     reset timeout   │  (circuit tripped)│       │
│       │                            └───────────────────┘       │
│       │ test call                          │                   │
│       ▼                                    │                   │
│  If success: CLOSED                        │                   │
│  If failure: OPEN                 Auto queue drain on recovery │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Executor Crash Recovery

```python
@dataclass
class ExecutorState:
    """Persisted executor state for crash recovery."""
    current_phase_id: Optional[str]
    completed_phases: List[str]
    pending_phases: List[str]
    retry_counts: Dict[str, int]
    last_checkpoint: datetime
```

### Autonomous Loop Circuit Breaker

- **Failure Threshold**: 5 consecutive failures
- **Reset Timeout**: 300 seconds
- **Half-Open Max Calls**: 1 test call
- **States**: CLOSED → OPEN → HALF_OPEN → CLOSED

## Quality Assurance

### Context Injection Effectiveness (IMP-LOOP-021, IMP-LOOP-029)

```python
@dataclass
class ContextInjectionMetadata:
    """Tracks what context was injected for effectiveness measurement."""
    injection_id: str
    phase_id: str
    items_injected: int
    confidence_scores: List[float]
    freshness_hours: float

# Effectiveness is measured by comparing:
# - Success rate WITH context injection
# - Success rate WITHOUT context injection
# A delta >5% with n>=10 samples is considered significant
```

### Task Effectiveness Tracking (IMP-LOOP-017, IMP-LOOP-022)

```python
@dataclass
class EffectivenessLearningRule:
    """Auto-generated rule from effectiveness patterns."""
    pattern: str
    success_rate: float
    sample_size: int
    generated_at: datetime

@dataclass
class CorrectiveTask:
    """Generated after repeated task failures."""
    original_task_id: str
    failure_count: int
    corrective_action: str
    generated_at: datetime
```

### Goal Drift Detection (IMP-LOOP-028)

```python
def check_goal_drift(
    original_goal: str,
    current_intent: str,
    threshold: float = 0.7
) -> GoalDriftResult:
    """
    Detect goal drift using embedding similarity.

    Args:
        original_goal: The original task/run description
        current_intent: The current change intent
        threshold: Cosine similarity threshold (default 0.7)

    Returns:
        GoalDriftResult with drift_detected flag and similarity score
    """
    pass

# Modes:
# - Advisory: Log drift but don't block
# - Blocking: Block changes that drift too far (BLOCKED prefix)
```

## Configuration Options

### Memory Service

| Option | Default | Description |
|--------|---------|-------------|
| `freshness_hours` | 720 (30 days) | Maximum age for cross-cycle learning |
| `compression_threshold` | 5000 chars | Compress entries larger than this |
| `vector_backend` | `faiss` | Vector store backend (faiss, qdrant) |
| `namespace_isolation` | `true` | Isolate collections by project |

### Task Generator

| Option | Default | Description |
|--------|---------|-------------|
| `confidence_threshold` | 0.5 | Minimum confidence for task generation |
| `deduplication_window` | 24 hours | Time window for task deduplication |
| `max_tasks_per_cycle` | 10 | Maximum tasks generated per cycle |

### Circuit Breaker

| Option | Default | Description |
|--------|---------|-------------|
| `failure_threshold` | 5 | Consecutive failures to trip |
| `reset_timeout` | 300 seconds | Time before testing recovery |
| `half_open_max_calls` | 1 | Test calls in HALF_OPEN state |

### Goal Drift

| Option | Default | Description |
|--------|---------|-------------|
| `similarity_threshold` | 0.7 | Cosine similarity threshold |
| `mode` | `advisory` | advisory or blocking |

## Implemented IMP Specifications

| IMP-ID | Feature | Component |
|--------|---------|-----------|
| IMP-LOOP-001 | Unified feedback pipeline | feedback_pipeline.py |
| IMP-LOOP-003 | Memory freshness checking | memory_service.py |
| IMP-LOOP-006 | Circuit breaker for execution | autonomous_loop.py |
| IMP-LOOP-012 | Task effectiveness stats | analyzer.py |
| IMP-LOOP-013 | Unified insight interface | task_generator.py |
| IMP-LOOP-015 | Insight provenance tracking | insight_provenance.py |
| IMP-LOOP-016 | Confidence filtering | task_generator.py |
| IMP-LOOP-017 | Auto rule generation | task_effectiveness_tracker.py |
| IMP-LOOP-019 | Context quality metadata | context_injector.py |
| IMP-LOOP-020 | Telemetry persistence | telemetry_to_memory_bridge.py |
| IMP-LOOP-021 | Context injection effectiveness | meta_metrics.py |
| IMP-LOOP-022 | Corrective task generation | task_effectiveness_tracker.py |
| IMP-LOOP-023 | Cross-cycle learning | memory_service.py |
| IMP-LOOP-028 | Goal drift correction | goal_drift.py |
| IMP-LOOP-029 | Context injection tracking | context_injector.py |
| IMP-DISC-001 | Discovery context merger | discovery_context_merger.py |
| IMP-MEM-001 | Freshness-based priority | priority_engine.py |
| IMP-MEM-002 | Hint conflict detection | context_injector.py |
| IMP-MEM-012 | Content compression | memory_service.py |
| IMP-MEM-015 | Project namespace isolation | memory_service.py |
| IMP-REL-011 | Telemetry resilience | telemetry_to_memory_bridge.py |
| IMP-REL-015 | Executor crash recovery | run_checkpoint.py |
| IMP-AUTO-002 | Parallel phase execution | autonomous_loop.py |
| IMP-TASK-002 | Impact validation/calibration | insight_to_task.py |
| IMP-TASK-003 | ROI prediction learning | roi_analyzer.py |

## Use Cases

### Use Case 1: Automatic Task Generation from Failure Patterns

```
1. Phase "build_feature_x" fails repeatedly (3 times)
2. TelemetryAnalyzer detects failure pattern
3. RankedIssue created with issue_type="failure_mode"
4. TelemetryToMemoryBridge persists to insights collection
5. AutonomousTaskGenerator consumes insight
6. GeneratedTask: "Investigate and fix build_feature_x failures"
7. PriorityEngine ranks as high priority (frequent failure)
8. Task executes, fix applied
9. TaskEffectivenessTracker validates improvement
10. EffectivenessLearningRule: "failure_mode tasks have 80% success rate"
```

### Use Case 2: Cross-Cycle Learning

```
1. Run A: Error "ModuleNotFoundError: xyz" encountered
2. LearningPipeline records hint: "pip install xyz"
3. MemoryService stores with confidence=0.8, freshness=now
4. Run B (next day): Same error pattern detected
5. ContextInjector retrieves hint with relevance_score=0.95
6. Hint injected into builder prompt
7. Builder applies fix without manual intervention
8. IntentionEffectivenessTracker records success with context
9. Confidence boosted to 0.9 for future use
```

### Use Case 3: Goal Drift Prevention

```
1. Original task: "Add user authentication"
2. During execution, builder starts "refactoring database schema"
3. check_goal_drift() calculates similarity = 0.45 (below 0.7 threshold)
4. GoalDriftResult: drift_detected=True
5. In blocking mode: Change blocked with "BLOCKED: Goal drift detected"
6. In advisory mode: Warning logged, execution continues
7. GoalDriftDetector records event for pattern analysis
```

### Use Case 4: ROI-Driven Task Prioritization

```
1. TelemetryAnalyzer identifies 3 cost sinks:
   - Phase A: 50,000 tokens/run
   - Phase B: 30,000 tokens/run
   - Phase C: 10,000 tokens/run
2. ROIAnalyzer calculates payback:
   - Task to optimize A: Cost 5,000 tokens, saves 40,000/run → 0.125 run payback
   - Task to optimize B: Cost 8,000 tokens, saves 20,000/run → 0.4 run payback
   - Task to optimize C: Cost 3,000 tokens, saves 5,000/run → 0.6 run payback
3. PriorityEngine orders: A → B → C
4. High-ROI task A executed first
5. TaskEffectivenessTracker validates actual savings
6. ROIHistory records predicted vs actual for calibration
```

## Monitoring and Observability

### Key Metrics

| Metric | Description | Source |
|--------|-------------|--------|
| `loop_completeness` | % insights converted to tasks | MetaMetricsTracker |
| `loop_latency` | End-to-end pipeline latency | PipelineLatencyTracker |
| `loop_fidelity` | How well insights match improvements | MetaMetricsTracker |
| `context_injection_rate` | % phases receiving context | ContextInjector |
| `task_success_rate` | % generated tasks that succeed | TaskEffectivenessTracker |
| `goal_drift_rate` | % executions with drift detected | GoalDriftDetector |

### Health Assessment

```python
@dataclass
class FeedbackLoopHealth:
    """Overall health status of the feedback loop."""
    status: str  # healthy, degraded, unhealthy
    components: Dict[str, str]  # component → status
    latency_violations: List[str]  # SLA breaches
    recommendations: List[str]  # improvement suggestions
```

## Troubleshooting

### Common Issues

| Symptom | Possible Cause | Resolution |
|---------|----------------|------------|
| Tasks not generated | Confidence below threshold | Lower `confidence_threshold` or improve insight quality |
| Memory retrieval empty | Freshness window too narrow | Increase `freshness_hours` |
| Circuit breaker tripped | Repeated failures | Check logs, fix root cause, wait for reset |
| Goal drift false positives | Threshold too high | Lower `similarity_threshold` |
| High pipeline latency | Memory service slow | Check vector store performance |

### Diagnostic Commands

```bash
# Check memory service health
autopack memory status

# View recent insights
autopack memory list --collection insights --limit 10

# Check circuit breaker state
autopack executor status

# View task effectiveness history
autopack tasks effectiveness --days 7

# Check goal drift events
autopack goals drift-history --run <run_id>
```

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
- [MEMORY_SERVICE_OPERATOR_GUIDE.md](../MEMORY_SERVICE_OPERATOR_GUIDE.md) - Memory service operations
- [OPERATOR_RUNBOOK.md](../OPERATOR_RUNBOOK.md) - Operational procedures
- [PHASE_LIFECYCLE.md](../PHASE_LIFECYCLE.md) - Phase execution lifecycle
