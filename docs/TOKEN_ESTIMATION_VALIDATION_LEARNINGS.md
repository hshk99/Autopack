# Token Estimation Validation - Critical Learnings

**Date**: 2025-12-23
**Status**: METHODOLOGY CORRECTED
**Related**: BUILD-129 Phase 1 Token Estimator Validation

## Executive Summary

The initial token estimation baseline (commit `1624a0a3`) **measured the wrong thing** and reached an invalid conclusion. A second opinion from a parallel cursor identified the fatal flaw, leading to corrected telemetry (commit `13459ed3`).

### What Went Wrong

**Initial Claim** (INVALID):
> TokenEstimator has 79.4% mean error rate and needs 80% coefficient reduction

**Reality**:
- Telemetry was comparing **manual test script inputs** against actual output tokens
- The real `TokenEstimator` predictions were not being validated
- All samples were failure-mode outputs (success=False)
- Conclusion was not supported by data

### What Was Fixed

**TokenEstimationV2 Telemetry** (commit `13459ed3`):
- ✅ Now logs **real TokenEstimator predictions** vs actual output tokens
- ✅ Uses SMAPE (symmetric error) to avoid metric bias
- ✅ Tracks truncation, success, category, complexity metadata
- ✅ Fixed `manifest_generator.py` to call correct estimator API
- ✅ Enhanced analyzer with stratification support

## Detailed Analysis

### The Original Flaw

**File**: `scripts/collect_telemetry_simple.py` (original version)

```python
# WRONG: Manually injected estimates
phase_spec = {
    "_estimated_output_tokens": scenario["estimated_tokens"],  # 300, 800, 1500, etc.
    ...
}
```

**File**: `src/autopack/anthropic_clients.py` (original telemetry)

```python
# WRONG: Logged the manual input, not TokenEstimator prediction
estimated_tokens = phase_spec.get("_estimated_output_tokens")  # Returns manual input!
```

**Result**: The "baseline" compared arbitrary test values (300/800/1500/2000/400) against actual outputs, not the TokenEstimator's predictions (448/822/373).

### The Corrected Approach

**File**: `src/autopack/anthropic_clients.py` (V2 telemetry)

```python
# CORRECT: Logs real estimator prediction
predicted_output_tokens = None
if isinstance(token_estimate, object) and token_estimate is not None:
    predicted_output_tokens = getattr(token_estimate, "estimated_tokens", None)

# V2 telemetry with SMAPE + metadata
logger.info(
    "[TokenEstimationV2] predicted_output=%s actual_output=%s smape=%.1f%% "
    "selected_budget=%s category=%s complexity=%s deliverables=%s success=%s "
    "stop_reason=%s truncated=%s model=%s",
    predicted_output_tokens, actual_out, smape * 100.0, ...
)
```

**Result**: Now measures what we actually care about - how accurate is `TokenEstimator.estimate()`?

### V2 Baseline Results (Correct but Non-Representative)

**5 samples collected** (all from failure modes):

| Predicted | Actual | SMAPE | Success | Truncated |
|-----------|--------|-------|---------|-----------|
| 448       | 124    | 113.3%| False   | False     |
| 448       | 129    | 110.6%| False   | False     |
| 448       | 124    | 113.3%| False   | False     |
| 822       | 129    | 145.7%| False   | False     |
| 373       | 117    | 104.5%| False   | False     |

**Analysis**:
- **Mean SMAPE**: 117.5%
- **100% over-estimation** (all predictions higher than actuals)
- **0% truncation** (good - no budget overruns)
- **0% success** (critical - all are failure-mode outputs)

**Conclusion**: Data is **valid but non-representative**. The Builder produced minimal failure responses (117-129 tokens) instead of full implementations. This is expected when executing phases without proper context/scaffolding.

## Why This Sample is Non-Representative

### Expected vs Actual Behavior

**Expected** (successful phase):
```python
# Goal: "Create a data validator with email and phone validation"
# Expected output: ~1000-2000 tokens of implementation code

class DataValidator:
    def validate_email(self, email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def validate_phone(self, phone: str) -> bool:
        # Full implementation...
        ...
```

**Actual** (failure mode):
```python
# Minimal response due to missing context
# Output: ~120 tokens

# Unable to create validator without dependencies
# Need: requirements.txt, project structure, etc.
```

### Root Causes of Failure Mode

1. **No existing file context** - Builder had no codebase to reference
2. **Minimal scaffolding** - No project structure, no dependencies
3. **Test environment** - Simple test harness, not real autonomous run
4. **No iterative refinement** - Single-shot execution without recovery

## Metrics: What Should We Measure?

### ❌ Wrong Metric: Mean Symmetric Percentage Error (SMAPE)

```
SMAPE = |actual - predicted| / ((|actual| + |predicted|) / 2)
```

**Problems**:
- Treats over/under-estimation equally
- Doesn't align with real goal (truncation prevention)
- Can be misleading for cost optimization

### ✅ Better Metrics (for truncation prevention)

1. **Underestimation Rate** (primary risk metric)
   ```
   % of samples where actual > predicted * 1.1
   ```
   - Directly measures truncation risk
   - Threshold (1.1x) allows for acceptable variance

2. **Truncation Rate** (ground truth)
   ```
   % of samples where truncated=True
   ```
   - Direct measurement from API response
   - Only available in V2 telemetry

3. **Success-Weighted Error** (quality metric)
   ```
   Separate error rates for success=True vs success=False
   Focus tuning on successful patterns
   ```

4. **Waste Ratio** (cost optimization)
   ```
   P95(predicted) / P95(actual)
   ```
   - Measures budget oversizing
   - Secondary to truncation prevention

## Stratification: Critical for Valid Analysis

### Current Flaw: Mixing Apples and Oranges

Our 5 V2 samples are:
- All `success=False`
- All single-file deliverables
- All "implementation" category
- All simple test scenarios

**This tells us nothing about**:
- Successful multi-file implementations
- Test file generation accuracy
- Documentation generation accuracy
- Complex vs simple phase differences

### Required Stratification Dimensions

1. **Success vs Failure**
   ```
   success=True:  [actual production outputs]
   success=False: [failure modes - exclude from tuning]
   ```

2. **Deliverable Category**
   ```
   implementation: [new features, core logic]
   tests:          [test file generation]
   docs:           [documentation updates]
   refactor:       [code restructuring]
   ```

3. **Complexity Level**
   ```
   low:    [simple utils, single functions]
   medium: [multi-function modules, basic classes]
   high:   [complex integrations, multi-file features]
   ```

4. **Deliverable Count**
   ```
   1 file:     [single deliverable]
   2-5 files:  [small feature]
   6+ files:   [large feature]
   ```

## Corrected Validation Roadmap

### Phase 1: Infrastructure ✅ COMPLETE

- [x] Implement TokenEstimationV2 telemetry
- [x] Fix manifest_generator.py API calls
- [x] Add V3 analyzer for success-only filtering + 2-tier metrics + stratification
- [x] Remove manual estimate injection from test scripts
- [x] Add SMAPE + truncation/success metadata

**Commits**: `b5604e41`, `1624a0a3`, `13459ed3`

### Phase 2: Data Collection ⏳ IN PROGRESS

**Objective**: Collect 20+ samples from **successful production runs**

**Method**:
1. Wait for autonomous runs to complete successfully (BUILD-130, etc.)
2. Analyze production logs: `python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs`
3. Filter for V2 telemetry with `success=True`
4. Ensure diverse deliverable categories and complexity levels

**Success Criteria**:
- ≥20 samples with `success=True`
- Mix of single/multi-file deliverables
- Mix of complexity levels (low/medium/high)
- Mix of categories (implementation/tests/docs)

### Phase 3: Stratified Analysis ⏳ PENDING

**After collecting representative data**:

1. **Generate stratified reports**
   ```bash
   python scripts/analyze_token_telemetry_v3.py \
     --log-dir .autonomous_runs \
     --success-only \
     --stratify \
     --output reports/telemetry_stratified_analysis.md
   ```

2. **Identify patterns**
   - Which categories have highest error rates?
   - Is there systematic bias (over/under)?
   - What's the actual truncation rate?
   - Do complexity levels correlate with accuracy?
   - Do deliverable-count buckets (1 / 2-5 / 6+) behave differently?

3. **Calculate target metrics**
   - Underestimation rate (target: <5%)  
     Recommended tolerance: treat underestimation as `actual > predicted * 1.1` to ignore tiny deltas.
   - Truncation rate (target: <2%)
   - Waste ratio (target: <2x at P95)

### Phase 4: Coefficient Tuning ⏳ DEFERRED

**Only proceed if**:
- Phase 2 & 3 complete
- Clear patterns identified
- Underestimation rate >5% OR truncation rate >2%

**Tuning approach**:
1. **Category-specific coefficients**
   ```python
   # token_estimator.py
   BASE_ESTIMATES = {
       "implementation": {"new_file": 800, "modify": 400},
       "tests": {"new_file": 600, "modify": 300},
       "docs": {"new_file": 400, "modify": 200},
   }
   ```

2. **Complexity multipliers**
   ```python
   COMPLEXITY_MULTIPLIERS = {
       "low": 0.8,
       "medium": 1.0,
       "high": 1.3,
   }
   ```

3. **Validation**
   - Hold out 20% of data for validation
   - Tune on 80%, validate on 20%
   - Measure improvement in underestimation + truncation rates

### Phase 5: Continuous Monitoring ⏳ FUTURE

**After initial tuning**:

1. **Regular analysis** (every 10-20 production runs)
   ```bash
   python scripts/analyze_token_telemetry.py \
     --log-dir .autonomous_runs \
     --output reports/telemetry_$(date +%Y%m%d).md
   ```

2. **Drift detection**
   - Compare current vs baseline error rates
   - Alert if underestimation rate increases
   - Track truncation rate trends

3. **Iterative refinement**
   - Adjust coefficients based on production data
   - Document changes in BUILD_HISTORY.md
   - A/B test tuning changes when possible

## Key Learnings

### 1. Measure What Matters

**Wrong**: Generic error metrics that don't align with goals
**Right**: Truncation rate, underestimation rate, success-weighted accuracy

### 2. Representative Samples Required

**Wrong**: 5 failure-mode samples from test harness
**Right**: 20+ successful production runs with diverse characteristics

### 3. Stratification is Critical

**Wrong**: Averaging across all samples regardless of context
**Right**: Separate analysis for success/failure, category, complexity

### 4. Avoid Premature Optimization

**Wrong**: "We have 79% error, reduce coefficients 80%!"
**Right**: "We have invalid samples, collect representative data first"

### 5. Asymmetric Loss Functions

**Wrong**: Treat over/under-estimation equally
**Right**: Weight underestimation heavily (truncation risk), tolerate overestimation (cost vs functionality tradeoff)

## Credit

**Second Opinion**: Parallel cursor identified the fatal flaw in original baseline methodology, preventing harmful coefficient changes based on invalid data.

**Key Insight**: "Your baseline was measuring the test harness inputs, not the TokenEstimator predictions."

This saved us from:
- Reducing coefficients 80% based on failure-mode data
- Breaking TokenEstimator accuracy for successful runs
- Increasing truncation risk in production

## References

- **Original Implementation**: BUILD-129 Phase 1 Token Estimator
- **Telemetry V1**: `b5604e41` - Initial (flawed) telemetry
- **Telemetry V2**: `13459ed3` - Corrected telemetry + methodology
- **Analysis Infrastructure**: [scripts/analyze_token_telemetry.py](../scripts/analyze_token_telemetry.py)
- **Collection Script**: [scripts/collect_telemetry_simple.py](../scripts/collect_telemetry_simple.py)
- **Token Estimator**: [src/autopack/token_estimator.py](../src/autopack/token_estimator.py)

## Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| V2 Telemetry | ✅ COMPLETE | Logs real estimator predictions |
| Analyzer Enhancement | ✅ COMPLETE | Stratification + V2 parsing |
| Representative Samples | ❌ BLOCKED | Need successful production runs |
| Stratified Analysis | ⏳ PENDING | Awaiting representative data |
| Coefficient Tuning | ⏳ DEFERRED | Do NOT tune without valid data |

**Next Action**: Wait for/trigger successful autonomous runs, then analyze V2 telemetry from production logs.
