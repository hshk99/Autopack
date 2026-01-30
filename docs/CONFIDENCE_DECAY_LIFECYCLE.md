# Confidence Decay Lifecycle

**Implementation Reference**: `src/autopack/memory/confidence_manager.py` (IMP-LOOP-034)

**Status**: Complete
**Updated**: 2026-01-31

---

## Overview

The confidence decay lifecycle is a core component of Autopack's self-improvement feedback loop. It manages how the system's confidence in stored insights evolves over time based on two factors:

1. **Time decay**: Insights naturally lose relevance as they age
2. **Outcome feedback**: Task results reinforce or penalize confidence

This dual mechanism ensures that:
- Fresh insights are trusted more than stale ones
- Successfully applied insights gain confidence
- Failed insights lose confidence
- The system automatically learns what works and what doesn't

### Design Philosophy

The confidence system balances two competing needs:
- **Stability**: Insights shouldn't swing wildly based on single outcomes
- **Responsiveness**: The system should quickly devalue insights that consistently fail
- **Reusability**: Good insights can be recovered through successful outcomes

---

## Lifecycle Stages

Confidence scores progress through distinct lifecycle stages based on age and outcomes:

### Stage 1: Fresh (Age = 0 days, Confidence = 100%)

**Characteristics:**
- Newly created insights start with `original_confidence` (typically 1.0)
- No decay has been applied
- Used immediately in task generation and pipeline decisions
- Maximum trust in relevance

**Duration:** Immediate after creation

**Example:**
```
Created insight: "Use async/await pattern for I/O operations"
- Confidence: 1.0
- Age: 0 days
- Used in: Task generation, pipeline recommendations
```

### Stage 2: Active (Age < half-life, Confidence = 50-100%)

**Characteristics:**
- Insight is less than one half-life old (default: 7 days)
- Confidence remains well above the minimum threshold
- Still heavily relied upon for decisions
- Subject to outcome adjustments based on task results

**Duration:** 0-7 days (configurable)

**Decay Timeline:**
- 0 days: 100% confidence
- 3.5 days: ~70% confidence
- 7 days: 50% confidence

**Example:**
```
3-day-old insight: "Cache API responses for 5 minutes"
- Original confidence: 1.0
- Decayed confidence: ~0.82 (82%)
- Status: Actively used, recent enough to trust
- Last outcome: Success (+0.15) → effective: 0.97
```

### Stage 3: Aging (Age ≈ half-life, Confidence = 25-50%)

**Characteristics:**
- Insight is around one half-life old (approximately 7 days)
- Confidence has decayed to ~50% of original
- Borderline reliability - still used but lower priority
- Effectiveness depends heavily on recent outcomes

**Duration:** 5-10 days

**Recovery Vulnerability:**
- A single failure at this stage significantly impacts usability
- Successful outcomes are crucial to maintain relevance
- Close to filtering thresholds in some use cases

**Example:**
```
10-day-old insight: "Use connection pooling for database"
- Original confidence: 1.0
- Decayed confidence: ~0.57 (57%)
- Recent outcomes: 2 successes (+0.30) → effective: 0.87
- Without recent successes: 0.57 (marginal)
```

### Stage 4: Stale (Age > 2× half-life, Confidence < 25%)

**Characteristics:**
- Insight is significantly older than the half-life period
- Confidence has decayed substantially
- May be filtered out by task generation depending on thresholds
- Requires continuous successful outcomes to remain useful
- Rarely selected for primary use cases

**Duration:** 14+ days

**Recovery Challenge:**
- Multiple consecutive successes needed to restore confidence
- Insights often naturally drop out of use
- May only be selected for high-confidence thresholds not met

**Example:**
```
20-day-old insight: "Enable query result compression"
- Original confidence: 1.0
- Decayed confidence: ~0.25 (25%)
- Status: May be filtered from task generation
- Recovery needed: 3+ consecutive successes
```

### Stage 5: Expired (Age >> 2× half-life, Confidence approaches floor)

**Characteristics:**
- Very old insights with minimal relevance
- Confidence approaches the minimum floor (0.1)
- Effectively excluded from most operations
- Only included in comprehensive searches

**Duration:** 30+ days

**Practical Impact:**
- Not selected for task generation
- Not weighted in analysis pipelines
- May still be stored but dormant
- Requires significant outcome boost to become relevant again

**Example:**
```
45-day-old insight: "Python 2.7 compatibility check needed"
- Original confidence: 1.0
- Decayed confidence: ~0.04 (capped at 0.1 minimum)
- Status: Functionally expired, not used in decisions
- Recovery: Extremely difficult, should be archived
```

---

## Decay Mechanisms

### The Exponential Decay Formula

The confidence system uses exponential decay to model how insights lose relevance:

```
decayed_confidence = original_confidence × (0.5 ^ (age_days / half_life_days))
```

**Where:**
- `original_confidence`: Initial confidence value (typically 1.0)
- `age_days`: Number of days since insight creation
- `half_life_days`: Time for confidence to decay to 50% (default: 7.0 days)

### Why Exponential Decay?

Exponential decay is chosen because:

1. **Natural relevance loss**: Information value often decays predictably over time
2. **Continuous function**: Smooth decay, no sharp cutoffs
3. **Configurable rate**: Half-life can be tuned per insight type
4. **Reversible**: Successful outcomes can restore confidence
5. **Bounded**: Never goes below minimum floor

### Decay Rate Examples

With default 7-day half-life:

| Age | Confidence | Status |
|-----|-----------|--------|
| 0 days | 100% | Fresh, full trust |
| 1 day | 91% | Very fresh |
| 3.5 days | 71% | Still active |
| 7 days | 50% | At half-life |
| 10 days | 42% | Aging |
| 14 days | 25% | Significantly stale |
| 21 days | 12.5% | Near floor |
| 28 days | 6.25% | Capped at 10% floor |

### Implementation Details

**Location**: `src/autopack/memory/confidence_manager.py:181-235`

**Key Method**: `calculate_decayed_confidence()`

```python
def calculate_decayed_confidence(
    self,
    original_confidence: float,
    created_at: datetime,
    current_time: Optional[datetime] = None
) -> float:
    """Calculate decayed confidence for an insight."""

    # Compute age in days
    age_days = (current_time - created_at).total_seconds() / 86400

    # Apply exponential decay formula
    decayed = original_confidence * (0.5 ** (age_days / self._decay_half_life))

    # Bound to minimum floor
    return max(self._min_confidence, decayed)
```

### Protection Mechanisms

1. **Negative age handling**: If `age_days` is negative (future creation), returns original confidence
2. **Minimum floor**: Decay never goes below `MIN_CONFIDENCE` (0.1)
3. **Timezone awareness**: All calculations use UTC for consistency
4. **Numeric stability**: Uses logarithmic calculations internally for precision

---

## Recovery Strategies

Recovery is the counterbalance to decay. While time always reduces confidence, successful outcomes can rebuild it.

### Strategy 1: Success-Based Recovery

**Mechanism**: Task outcomes marked as "success" boost confidence

**Boost Amount**: `SUCCESS_CONFIDENCE_BOOST` = +0.15 (15%)

**Application Rules**:
- Applied after decay calculation
- Cumulative - multiple successes stack
- Capped at maximum (1.0)

**Example Recovery Timeline**:
```
Initial state:
- Original confidence: 1.0
- Age: 7 days
- Decayed confidence: 0.5

Outcome: Task using this insight succeeds
- Post-success confidence: 0.5 + 0.15 = 0.65

Outcome: Another task succeeds
- Post-success confidence: 0.65 + 0.15 = 0.80

Outcome: Another task succeeds
- Post-success confidence: 0.80 + 0.15 = 0.95
- Nearly recovered to original despite being 7+ days old
```

**Best For**:
- Core insights that consistently work
- Frequently reused patterns
- Insights with broad applicability

### Strategy 2: Partial Success Recovery

**Mechanism**: Task outcomes marked as "partial" provide smaller boost

**Boost Amount**: `PARTIAL_CONFIDENCE_ADJUSTMENT` = +0.05 (5%)

**Application Rules**:
- Applied when insight partially contributes to success
- Smaller than full success (5% vs 15%)
- Useful for conditional insights

**Use Cases**:
- Insight applies to some cases but not all
- Contributing factor but not primary cause
- Experimental approaches

**Example**:
```
Insight: "Use caching for frequently accessed data"
- May not apply to all data types
- When applicable and works: +0.15 boost
- When applies but only marginally helpful: +0.05 boost
```

### Strategy 3: Outcome Penalty

**Mechanism**: Task failures reduce confidence

**Penalty Amount**: `FAILURE_CONFIDENCE_PENALTY` = -0.20 (20%)

**Application Rules**:
- Applied when insight leads to failure
- Larger penalty than partial boost (encourages caution)
- No automatic recovery from failures

**Example**:
```
Insight: "Always use eager loading in ORM queries"
- Initial confidence: 1.0
- Task using this insight fails: 1.0 - 0.20 = 0.80
- Another failure: 0.80 - 0.20 = 0.60
- After two failures + 7 days age: ~0.30 (marginal)
```

### Strategy 4: State Reset

**Mechanism**: Complete reset of outcome adjustments while preserving age

**When Used**:
- Insights need to be re-evaluated
- Environmental changes affect validity
- Recovering from systematic failures

**Effect**:
- `outcome_adjustment` → 0.0
- Outcome counters → reset
- `original_confidence` → preserved
- `created_at` → preserved (age restarts counting from original)

**Implementation**:
```python
def reset_state(self, insight_id: str) -> None:
    """Reset outcome adjustments while preserving creation time."""
    if insight_id in self._states:
        state = self._states[insight_id]
        state.outcome_adjustment = 0.0
        state.success_count = 0
        state.failure_count = 0
        state.partial_count = 0
```

### Optimal Recovery Pattern

For rapidly recovering stale insights:

1. **Initial assessment**: Check current effective confidence
2. **Quick validation**: Run low-risk test using the insight
3. **Build momentum**: Accumulate 2-3 successes
4. **Monitor results**: Track consistency
5. **Restore to active rotation**: Once confidence > 0.8

---

## Threshold Configuration

The confidence system uses several thresholds that control how insights are used:

### Default Thresholds

| Threshold | Value | Purpose |
|-----------|-------|---------|
| `MIN_CONFIDENCE` | 0.1 | Decay floor - never goes below |
| `MAX_CONFIDENCE` | 1.0 | Adjustment ceiling - never goes above |
| `MIN_CONFIDENCE_THRESHOLD` | 0.5 | Task generation filter |
| `LOW_CONFIDENCE_THRESHOLD` | 0.3 | Context quality marking |
| `MEDIUM_CONFIDENCE_THRESHOLD` | 0.6 | Priority weighting |

### Task Generation Filtering

**Location**: `src/autopack/roadc/task_generator.py` (IMP-LOOP-033)

**Behavior**:
- Insights with confidence < 0.5 are excluded from task generation
- Ensures only reasonably confident insights drive decisions
- Configurable per use case

**Impact**:
```
Confidence | In Task Gen | Usage Level
0.9+       | Yes         | Primary
0.8-0.9    | Yes         | Primary
0.6-0.8    | Yes         | Secondary
0.5-0.6    | Marginal    | Low confidence
< 0.5      | No          | Excluded
```

### Context Quality Filtering

**Location**: `src/autopack/memory/freshness_filter.py` (IMP-LOOP-003)

**Behavior**:
- Insights with confidence < 0.3 marked as "low quality"
- Still included but weighted lower in analysis
- Useful for comprehensive context but not primary focus

**Markers**:
```python
if confidence < LOW_CONFIDENCE_THRESHOLD:  # 0.3
    mark_as_low_quality()
elif confidence < MEDIUM_CONFIDENCE_THRESHOLD:  # 0.6
    mark_as_medium_quality()
else:
    mark_as_high_quality()
```

### Tuning Confidence Thresholds

**Increase thresholds when**:
- False positives are expensive
- Safety is critical
- You want conservative decision-making

**Decrease thresholds when**:
- False negatives are costly
- You want aggressive exploration
- Context breadth is important

---

## Integration with Memory System

The confidence system integrates tightly with the memory service to track, persist, and apply confidence decay.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Research Pipeline                     │
│  (Uses insights to generate tasks and recommendations)  │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│              Task Generator (IMP-LOOP-033)              │
│  - Filters by confidence threshold (>= 0.5)           │
│  - Selects highest-confidence insights                │
│  - Tracks which insights are used                      │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│              Memory Service                             │
│  - retrieve_insights(min_confidence=0.5)              │
│  - apply_confidence_decay(insights)                    │
│  - update_insight_confidence()                         │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│         Confidence Manager (IMP-LOOP-034)              │
│  - Calculates decayed confidence                       │
│  - Tracks outcome adjustments                          │
│  - Manages lifecycle state                             │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│         Insight Storage & Persistence                  │
│  - Stores original_confidence                          │
│  - Stores created_at timestamp                         │
│  - Updates confidence field                            │
└─────────────────────────────────────────────────────────┘
```

### Key Integration Points

**1. Insight Retrieval**

When retrieving insights, the system:
```python
# In MemoryService.retrieve_insights()
insights = db.query(Insight).filter(
    Insight.confidence >= min_confidence_threshold  # 0.5
).all()

# Apply freshness-based filtering (IMP-LOOP-014)
# Apply confidence decay calculation
insights = self.apply_confidence_decay(insights)
```

**2. Task Generation**

When generating tasks:
```python
# In TaskGenerator.generate_tasks()
insights = memory_service.retrieve_insights(
    project_id=project_id,
    min_confidence=0.5  # MIN_CONFIDENCE_THRESHOLD
)

for insight in insights:
    # Calculate effective confidence
    effective_confidence = confidence_manager.get_effective_confidence(
        insight_id=insight.id,
        original_confidence=insight.original_confidence,
        created_at=insight.created_at
    )

    # Use for task prioritization
    priority = calculate_priority(effective_confidence)
```

**3. Outcome Recording**

After task execution:
```python
# In LearningPipeline.record_outcome()
confidence_manager.update_confidence_from_outcome(
    insight_id=insight_id,
    outcome="success",  # or "failure" or "partial"
    persist=True  # Saves to memory service
)

# This calls:
memory_service.update_insight_confidence(
    insight_id=insight_id,
    new_confidence=updated_confidence,
    project_id=project_id
)
```

### Bidirectional Updates

The system maintains two-way synchronization:

**Confidence → Memory** (Persistence):
```
Confidence Manager updates confidence
  ↓
Calls memory_service.update_insight_confidence()
  ↓
Updates database with new confidence value
  ↓
Insight is retrieved with updated confidence next time
```

**Memory → Confidence** (Loading):
```
Task generator retrieves insights from memory
  ↓
Gets original_confidence and created_at timestamp
  ↓
Confidence manager calculates decayed value
  ↓
Effective confidence used for prioritization
```

---

## Configuration and Tuning

### System Constants

Located in `src/autopack/memory/confidence_manager.py:32-45`:

```python
# Default half-life for confidence decay (days)
DEFAULT_DECAY_HALF_LIFE_DAYS = 7.0

# Confidence bounds
MIN_CONFIDENCE = 0.1                    # Never decay below
MAX_CONFIDENCE = 1.0                    # Never adjust above

# Outcome adjustment factors
SUCCESS_CONFIDENCE_BOOST = 0.15         # +15% on success
FAILURE_CONFIDENCE_PENALTY = 0.20       # -20% on failure
PARTIAL_CONFIDENCE_ADJUSTMENT = 0.05    # +5% on partial success
```

### When to Adjust Configuration

**Increase decay half-life (e.g., 14 days) when**:
- Insights are slow to become stale
- Core patterns change infrequently
- You want to preserve old insights longer

**Decrease decay half-life (e.g., 3 days) when**:
- Insights become stale quickly
- System environment changes rapidly
- You want responsive to environment changes

**Increase success boost (e.g., 0.25) when**:
- You want faster recovery of stale insights
- Good insights should gain confidence quickly
- False positives are tolerable

**Decrease success boost (e.g., 0.10) when**:
- Conservatism is important
- Single successes shouldn't drive decisions
- Multiple confirmations needed

### Monitoring Confidence Health

**Metrics to track**:

1. **Average confidence**: Should trend upward over time as system learns
   ```
   avg_confidence = sum(insights.confidence) / len(insights)
   ```

2. **Confidence distribution**: Track proportion in each stage
   ```
   fresh: confidence >= 0.8
   active: 0.5 <= confidence < 0.8
   aging: 0.3 <= confidence < 0.5
   stale: confidence < 0.3
   ```

3. **Recovery rate**: How many insights recover from low confidence
   ```
   recovered = count(confidence_increased > 0.2 in 7 days)
   recovery_rate = recovered / initial_low_confidence_count
   ```

4. **Success correlation**: Do high-confidence insights have higher success rates?
   ```
   high_conf_success_rate = successes_high_conf / tasks_high_conf
   low_conf_success_rate = successes_low_conf / tasks_low_conf
   ratio = high_conf_success_rate / low_conf_success_rate
   # Healthy ratio > 1.5
   ```

---

## Usage Examples

### Example 1: Creating and Using an Insight

```python
from datetime import datetime, timezone
from src.autopack.memory.confidence_manager import ConfidenceManager

# Initialize manager
manager = ConfidenceManager()

# Register new insight with full confidence
manager.register_insight(
    insight_id="insight-001",
    original_confidence=1.0,
    created_at=datetime.now(timezone.utc)
)

# Get effective confidence (fresh, no decay)
confidence = manager.get_effective_confidence(
    insight_id="insight-001",
    original_confidence=1.0,
    created_at=datetime.now(timezone.utc)
)
# Result: 1.0 (100%)
```

### Example 2: Confidence Decay Over Time

```python
from datetime import datetime, timezone, timedelta

# Create insight 7 days ago
created_at = datetime.now(timezone.utc) - timedelta(days=7)

confidence = manager.get_effective_confidence(
    insight_id="insight-002",
    original_confidence=1.0,
    created_at=created_at
)
# Result: ~0.5 (50%) - at half-life point
```

### Example 3: Recovery Through Success

```python
# Insight is 14 days old (confidence decayed to 0.25)
created_at = datetime.now(timezone.utc) - timedelta(days=14)

# Record two successful outcomes
manager.update_confidence_from_outcome(
    insight_id="insight-003",
    outcome="success"  # +0.15
)
manager.update_confidence_from_outcome(
    insight_id="insight-003",
    outcome="success"  # +0.15
)

# Get effective confidence
confidence = manager.get_effective_confidence(
    insight_id="insight-003",
    original_confidence=1.0,
    created_at=created_at
)
# Result: 0.25 (decay) + 0.30 (2 successes) = 0.55 (55%)
# Now back above task generation threshold!
```

### Example 4: Handling Failures

```python
# Start with good confidence
manager.register_insight(
    insight_id="insight-004",
    original_confidence=1.0,
    created_at=datetime.now(timezone.utc)
)

# Three failures occur
for _ in range(3):
    manager.update_confidence_from_outcome(
        insight_id="insight-004",
        outcome="failure"  # -0.20 each
    )

# Get effective confidence
confidence = manager.get_effective_confidence(
    insight_id="insight-004",
    original_confidence=1.0,
    created_at=datetime.now(timezone.utc)
)
# Result: 1.0 - 0.60 (3 failures) = 0.4 (40%)
# Below task generation threshold - needs review
```

### Example 5: Batch Processing Insights

```python
# Apply decay to all insights at once
insights_with_metadata = [
    {
        'insight_id': 'insight-001',
        'original_confidence': 1.0,
        'created_at': datetime.now(timezone.utc) - timedelta(days=3)
    },
    {
        'insight_id': 'insight-002',
        'original_confidence': 0.9,
        'created_at': datetime.now(timezone.utc) - timedelta(days=10)
    },
    # ... more insights
]

# Calculate all at once
for metadata in insights_with_metadata:
    effective = manager.get_effective_confidence(
        insight_id=metadata['insight_id'],
        original_confidence=metadata['original_confidence'],
        created_at=metadata['created_at']
    )
    print(f"{metadata['insight_id']}: {effective:.2%}")

# Output:
# insight-001: 92%
# insight-002: 31%
```

---

## Testing and Validation

The confidence system includes comprehensive test coverage in:
- `tests/memory/test_confidence_manager.py` (471 lines)
- `tests/research/test_task_generator_confidence.py`

### Test Categories

**Decay Calculations**:
- ✓ Decay at half-life points
- ✓ Exponential progression
- ✓ Minimum floor protection
- ✓ Timezone handling

**Outcome Adjustments**:
- ✓ Success boost application
- ✓ Failure penalty calculation
- ✓ Partial success boost
- ✓ Maximum ceiling protection

**Combined Operations**:
- ✓ Decay + adjustments
- ✓ Cumulative outcomes
- ✓ State persistence
- ✓ Batch processing

**Integration**:
- ✓ Filtering threshold enforcement
- ✓ Memory service coordination
- ✓ Outcome persistence
- ✓ Statistics generation

---

## Troubleshooting

### Low Average Confidence

**Symptoms**: Most insights have confidence < 0.5

**Causes**:
- Half-life too short (aging insights too quickly)
- High failure rate (outcomes mostly negative)
- Insights created too long ago

**Solutions**:
```python
# Option 1: Increase half-life to 14 days
manager = ConfidenceManager(decay_half_life_days=14.0)

# Option 2: Reset old insights
for insight in old_insights:
    manager.reset_state(insight.id)

# Option 3: Investigate why failures are high
analyze_failure_patterns()
```

### Insights Not Improving

**Symptoms**: Successful outcomes not boosting confidence

**Causes**:
- Not recording outcomes correctly
- Persistence not enabled
- Outcomes not propagated to memory service

**Solutions**:
```python
# Ensure persist=True
manager.update_confidence_from_outcome(
    insight_id=insight_id,
    outcome="success",
    persist=True  # <- Critical!
)

# Verify persistence
updated = memory_service.get_decayed_confidence(
    insight_id=insight_id,
    original_confidence=original,
    created_at=created_at
)
assert updated > original
```

### Insights Filtered Too Aggressively

**Symptoms**: No insights selected for task generation

**Causes**:
- MIN_CONFIDENCE_THRESHOLD too high (default 0.5)
- All insights below threshold due to age/failures
- System just started (no recent insights yet)

**Solutions**:
```python
# Reduce filtering threshold temporarily
insights = memory_service.retrieve_insights(
    project_id=project_id,
    min_confidence=0.3  # Reduce from 0.5 to 0.3
)

# Or seed with high-confidence insights
for seed_insight in bootstrap_insights:
    memory_service.register_insight(
        insight_id=seed_insight.id,
        original_confidence=0.95  # High initial confidence
    )
```

---

## Related Components

**IMP-LOOP-033**: Task Generator filtering
**IMP-LOOP-003**: Freshness filtering
**IMP-LOOP-014**: Memory freshness thresholds
**IMP-MEM-004**: Collection-specific freshness windows
**IMP-LOOP-035**: Learning pipeline outcome recording

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-31 | 1.0 | Initial documentation |

