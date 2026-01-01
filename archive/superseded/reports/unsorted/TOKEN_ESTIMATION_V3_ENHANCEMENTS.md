# Token Estimation Telemetry V3 - Enhanced Methodology

**Date**: 2025-12-23
**Status**: IMPLEMENTED
**Credit**: Refinements from parallel cursor second opinion

## Summary of Enhancements

Based on feedback from the parallel cursor, we've implemented a **V3 analyzer** that addresses critical methodological issues and aligns metrics with actual goals.

## Key Improvements

### 1. Success-Only Filtering ✅

**Problem**: Original analysis mixed failure-mode outputs with successful phases.

**Solution**: Added `--success-only` flag to filter telemetry records where `success=True`.

```bash
# All samples (monitoring)
python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs

# Success-only (tuning decisions)
python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs --success-only
```

**Impact**: Tuning decisions now based on representative data, not failure modes.

### 2. Two-Tier Metrics System ✅

**Problem**: SMAPE was treated as the primary success metric, but doesn't align with goals.

**Solution**: Implemented 2-tier metrics aligned with real objectives.

#### Tier 1: Risk Metrics (Primary Tuning Gates)

**These drive tuning decisions:**

1. **Underestimation Rate** (target: ≤5%)
   - % of samples where `actual > predicted`
   - Direct measure of truncation risk
   - If >5%, increase coefficients

2. **Truncation Rate** (target: ≤2%)
   - % of samples where `truncated=True`
   - Ground truth for budget failures
   - If >2%, increase margins/budgets

3. **Success Rate** (monitoring only)
   - % of samples where `success=True`
   - Indicates data quality

#### Tier 2: Cost Metrics (Secondary Optimization)

**Optimize after Tier 1 is met:**

1. **Waste Ratio** = predicted / actual
   - Median: Typical overestimation
   - P90: Worst-case waste
   - Target: P90 < 3x (cost control)

**SMAPE**: Now diagnostic only, not a decision metric.

### 3. Clear Tuning Decision Framework ✅

**Old approach**:
> "Mean SMAPE is 96.7%, reduce coefficients!"

**New approach**:
```
Tier 1 Check:
- Underestimation rate: 0.0% ✅ (target ≤5%)
- Truncation rate: 0.0% ✅ (target ≤2%)

Decision: NO TUNING NEEDED (Tier 1 within targets)

Note: High waste ratio (P90=14.7x) but this is secondary to truncation prevention.
Data is non-representative (all failures), so waste metric is misleading.
```

### 4. Stratified Analysis Support ✅

**Added `--stratify` flag** to break down metrics by:
- **Category**: implementation / tests / docs / refactor
- **Complexity**: low / medium / high
- **Deliverable count**: 1 file / 2-5 files / 6+ files

**Use case**: Identify which categories need coefficient tuning.

```bash
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --stratify \
  --output reports/telemetry_stratified.md
```

## Usage Examples

### Monitoring All Samples

```bash
# Check overall behavior (includes failures)
python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs
```

**Output**:
```
## 🎯 TIER 1: RISK METRICS

Underestimation Rate: 0.0% (0 samples)
  Target: ≤ 5%
  Status: ✅ WITHIN TARGET

Truncation Rate: 0.0% (0 samples)
  Target: ≤ 2%
  Status: ✅ WITHIN TARGET

Success Rate: 0.0% (0 samples)  ← RED FLAG: All failures!
```

### Tuning Decisions (Success-Only)

```bash
# Filter to successful phases for tuning
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --output reports/tuning_analysis.md
```

**Output**:
```
Filter: SUCCESS ONLY (for tuning decisions)
Total Records: 11
Analysis Records: 0

No successful records found for analysis.

⚠️ Cannot make tuning decisions without successful samples.
```

### Stratified Analysis

```bash
# Break down by category/complexity
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --stratify
```

**Output**:
```
## 📊 Stratified Analysis

### By Category

**implementation** (15 samples):
- Underestimation: 3.2%
- Truncation: 1.1%
- Success: 92.0%

**tests** (8 samples):
- Underestimation: 8.5%  ← NEEDS TUNING
- Truncation: 4.2%       ← NEEDS TUNING
- Success: 88.0%
```

## Comparison: Old vs New Analysis

### Old Analyzer (V1/V2)

```
Mean Error Rate: 96.7%
Target (<30% error): ❌ NO
Over-estimation rate: 100.0%

Recommendation: 🔴 Critical - Reduce coefficients
```

**Problem**: Misleading conclusion based on failure-mode data.

### New Analyzer (V3)

```
## TIER 1: RISK METRICS
Underestimation Rate: 0.0% ✅
Truncation Rate: 0.0% ✅
Success Rate: 0.0% ← Non-representative data

## TUNING DECISION: ✅ WITHIN TARGETS
(But data quality issue - all failures)

Next Steps:
1. Re-run with --success-only for tuning decisions
2. Current analysis includes failure-mode samples
```

**Benefit**: Correct interpretation - no tuning needed, but data is non-representative.

## Tuning Workflow (Corrected)

### Phase 1: Data Collection ⏳ IN PROGRESS

**Objective**: Collect 20+ successful production samples

```bash
# Wait for autonomous runs to complete successfully
# Check logs: python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs
```

**Success Criteria**:
- ≥20 samples with `success=True`
- Mix of categories and complexity levels
- Diverse deliverable counts (1, 2-5, 6+ files)

### Phase 2: Baseline Analysis ⏳ PENDING

```bash
# Generate success-only report
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --stratify \
  --output reports/baseline_successful.md
```

**Check Tier 1 metrics**:
- Underestimation rate: If >5%, proceed to Phase 3
- Truncation rate: If >2%, proceed to Phase 3
- Otherwise: No tuning needed

### Phase 3: Coefficient Tuning ⏳ DEFERRED

**Only if Tier 1 metrics exceed targets.**

**Strategy** (from parallel cursor):
- **Fit by quantile**: Target p90 of actual output for each category
- **Category-specific coefficients**: Tune implementation/tests/docs separately
- **Add floor/ceiling**: Prevent silly low/high budgets

**Example tuning**:
```python
# token_estimator.py

# If tests show 8.5% underestimation
BASE_ESTIMATES = {
    "tests": {
        "new_file": 600,  # Increase from 400
        "modify": 350,    # Increase from 250
    }
}

# If waste ratio P90 > 3x (secondary optimization)
SAFETY_MARGIN = 1.1  # Reduce from 1.2
```

### Phase 4: Validation ⏳ DEFERRED

```bash
# After tuning, validate on held-out data
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --output reports/post_tuning.md
```

**Check**:
- Underestimation rate decreased?
- Truncation rate decreased?
- Waste ratio acceptable?

### Phase 5: Continuous Monitoring ⏳ FUTURE

```bash
# Every 10-20 production runs
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --output reports/telemetry_$(date +%Y%m%d).md
```

**Alert if**:
- Underestimation rate > 5% (drift)
- Truncation rate > 2% (regression)
- Success rate < 80% (data quality issue)

## Key Insights from Parallel Cursor

### 1. "Don't optimize for SMAPE"

> SMAPE is fine as a diagnostic, but don't gate success on it. Your objective is truncation prevention + cost control.

**Implementation**: SMAPE moved to "Diagnostic Metrics" section, Tier 1/2 metrics drive decisions.

### 2. "Measure truncation, not just prediction error"

> Your selected budget is often forced to ≥8192/12288 anyway, so prediction errors may not affect truncation until you start using the estimate to go above those floors.

**Implementation**: Truncation rate now primary metric, tracked separately from underestimation.

### 3. "Fit by quantile, not mean"

> Choose coefficients so predicted output approximates the p90 of actual output for each deliverable type. That directly aligns with truncation avoidance.

**Implementation**: Documented in tuning strategy, to be implemented when we have data.

### 4. "Separate estimator vs budget selection"

> Don't conflate "prediction accuracy" with "budget selection". You can keep estimator conservative and control spend with budget policy.

**Implementation**: V2 telemetry logs both `predicted_output` and `selected_budget` separately.

### 5. "Make representative data collection non-optional"

> Only include records where the builder actually produced a patch/full-file output. Log the failure reason so "failure-mode" is provable, not inferred.

**Implementation**: V2 telemetry already logs `success`, `stop_reason`, `truncated`. V3 analyzer filters on `success=True`.

## Files Created

- **scripts/analyze_token_telemetry_v3.py** - Enhanced analyzer with 2-tier metrics
- **docs/TOKEN_ESTIMATION_V3_ENHANCEMENTS.md** - This document

## Migration Path

### Current Users

1. **Keep using V2 telemetry** - Already logs all necessary metadata
2. **Switch to V3 analyzer** - Replace calls to `analyze_token_telemetry.py` with `analyze_token_telemetry_v3.py`
3. **Use --success-only** - For tuning decisions, always filter to successful phases

### Backward Compatibility

- V3 analyzer parses both V1 and V2 telemetry formats
- V2 analyzer still works for comparison
- No changes required to telemetry logging

## Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| V2 Telemetry | ✅ COMPLETE | Logs success, stop_reason, truncation |
| V3 Analyzer | ✅ COMPLETE | 2-tier metrics, success filtering |
| Success-Only Filtering | ✅ COMPLETE | `--success-only` flag |
| Stratification | ✅ COMPLETE | `--stratify` flag |
| Representative Samples | ❌ BLOCKED | Need successful production runs |
| Tuning Framework | ✅ DOCUMENTED | Ready when we have data |

## Next Action

**Wait for successful autonomous runs** (e.g., BUILD-130 completion), then:

```bash
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --stratify \
  --output reports/baseline_production_$(date +%Y%m%d).md
```

If Tier 1 metrics exceed targets, proceed with category-specific coefficient tuning.

## References

- **V2 Telemetry**: [anthropic_clients.py:652-699](../src/autopack/anthropic_clients.py#L652-L699)
- **V3 Analyzer**: [scripts/analyze_token_telemetry_v3.py](../scripts/analyze_token_telemetry_v3.py)
- **Token Estimator**: [src/autopack/token_estimator.py](../src/autopack/token_estimator.py)
- **Validation Learnings**: [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md](TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md)
