# BUILD-129 Phase 3: Stratified Sample Collection Plan

**Date:** 2025-12-24
**Status:** PLANNED
**Goal:** Collect 30-50 stratified telemetry samples to validate and tune overhead model coefficients

---

## Current State

### Phase 2 Results
- **Current dataset**: 14 samples from BUILD-132 and Lovable Phase 0/1/2
- **Overhead model performance**:
  - Average SMAPE: 45.9% (target: <50%)
  - Median waste ratio: 1.25x (target: ~1.0-1.5x)
  - Underestimation rate: 0% (target: 0%)

### Dataset Gaps
The current 14 samples are heavily skewed:

| Dimension | Distribution | Gap |
|-----------|-------------|-----|
| **Category** | Implementation: 10/14 (71%)<br>Refactoring: 2/14 (14%)<br>Configuration: 1/14 (7%)<br>Integration: 1/14 (7%)<br>Docs: 1/14 (7%) | Need: testing, deployment, database, frontend |
| **Complexity** | Low: 5/14 (36%)<br>Medium: 8/14 (57%)<br>High: 1/14 (7%) | Need: more high complexity samples |
| **Deliverables** | 1 file: 1/14 (7%)<br>2 files: 11/14 (79%)<br>3 files: 1/14 (7%)<br>4 files: 1/14 (7%) | Need: 5-8 file phases, 9+ file phases |

---

## Available Resources

**Total queued phases**: 153 across 31 runs

### High-Priority Runs for Sample Collection

1. **build130-schema-validation-prevention** (2 queued)
   - Categories: implementation, validation
   - Expected: medium-high complexity, 2-4 deliverables

2. **build132-coverage-delta-integration** (1 queued)
   - Category: integration
   - Expected: medium complexity, 2-3 deliverables

3. **fileorg-p2-20251208g** (5 queued)
   - Category: refactoring
   - Expected: varied complexity, 3-6 deliverables

4. **fileorg-p2-20251208m** (8 queued)
   - Category: refactoring, documentation
   - Expected: low-medium complexity, 2-5 deliverables

5. **build112-completion** (3 queued)
   - Categories: varied
   - Expected: varied complexity, 2-4 deliverables

6. **lovable-p2-quality-ux** (1 queued: lovable-p2.5-fallback-chain)
   - Category: implementation
   - Expected: low complexity, 2 deliverables

7. **research-system-v7** (8 queued)
   - Category: implementation, backend
   - Expected: varied complexity, 1-4 deliverables

8. **Multiple research-system runs** (v2-v18, ~90 queued phases)
   - Category: research, backend, implementation
   - Expected: varied complexity, 1-3 deliverables

---

## Collection Strategy

### Target Distribution (30-50 samples)

#### By Category
| Category | Current | Target | Runs to Execute |
|----------|---------|--------|----------------|
| Implementation | 10 | 12-15 | research-system-v7, build130 |
| Refactoring | 2 | 6-8 | fileorg-p2-20251208g, fileorg-p2-20251208m |
| Configuration | 1 | 3-5 | build130, fileorg runs |
| Integration | 1 | 3-5 | build132, multi-system phases |
| Testing | 0 | 3-5 | **CREATE NEW TEST RUN** |
| Documentation | 1 | 3-5 | fileorg runs |
| Backend | 0 | 3-5 | research-system runs |
| Database | 0 | 2-4 | **CREATE NEW DB RUN** |

#### By Complexity
| Complexity | Current | Target | Strategy |
|------------|---------|--------|----------|
| Low | 5 | 10-12 | Execute simple config/docs phases |
| Medium | 8 | 15-20 | Execute standard implementation phases |
| High | 1 | 8-10 | Execute complex integration/refactoring phases |

#### By Deliverable Count
| Count | Current | Target | Strategy |
|-------|---------|--------|----------|
| 1-2 files | 12 | 12-15 | Current good coverage |
| 3-4 files | 2 | 10-12 | Execute fileorg refactoring phases |
| 5-8 files | 0 | 8-10 | Execute large fileorg phases |
| 9+ files | 0 | 3-5 | **CREATE LARGE SCOPE RUN** |

---

## Execution Plan

### Phase 1: Execute High-Diversity Runs (Target: 15-20 samples)

**Week 1: Execute diverse category coverage**

1. ✅ **build130-schema-validation-prevention** (2 phases)
   - Adds: validation category, medium-high complexity

2. ✅ **build132-coverage-delta-integration** (1 phase)
   - Adds: integration category diversity

3. ✅ **fileorg-p2-20251208g** (5 phases)
   - Adds: refactoring with 3-6 deliverables

4. ✅ **lovable-p2-quality-ux** (1 phase remaining)
   - Adds: implementation/low diversity

5. ✅ **build112-completion** (3 phases)
   - Adds: varied categories

**Expected outcome:** ~12 new samples, improving category/deliverable distribution

### Phase 2: Execute Large-Scope Runs (Target: 10-15 samples)

**Week 2: Focus on larger deliverable counts**

1. ✅ **fileorg-p2-20251208m** (8 phases)
   - Adds: 4-8 deliverable phases

2. ✅ **research-system-v7** (8 phases)
   - Adds: backend/implementation with varied sizes

**Expected outcome:** ~16 new samples, covering 3-8 deliverable range

### Phase 3: Fill Remaining Gaps (Target: 5-10 samples)

**Week 3: Create targeted runs for missing categories**

1. **CREATE: testing-validation-run** (5 phases)
   - Category: testing
   - Deliverables: 2-6 files (test + implementation)
   - Complexity: low-high

2. **CREATE: database-migration-run** (3 phases)
   - Category: database
   - Deliverables: 2-4 files (migration + model + test)
   - Complexity: medium-high

3. **CREATE: large-refactoring-run** (2 phases)
   - Category: refactoring
   - Deliverables: 9-15 files
   - Complexity: high

**Expected outcome:** ~10 new samples filling critical gaps

---

## Sample Validation Criteria

### Quality Gates
For each sample to be included in the dataset, it must meet:

1. ✅ **Success**: `success=True` in telemetry
2. ✅ **Completion**: `stop_reason=end_turn` (not truncated)
3. ✅ **Reasonable size**: `actual_output > 500 tokens` (not trivial)
4. ✅ **Metadata complete**: category, complexity, deliverables count, actual paths

### Exclusion Criteria
Exclude samples if:
- ❌ Truncated (`truncated=True`)
- ❌ Failed phase (`success=False`)
- ❌ Stop reason: `max_tokens` (indicates underestimation)
- ❌ Missing metadata (no category/complexity)
- ❌ Outliers: actual_output > 50,000 tokens (edge case)

---

## Metrics to Track

### Primary Metrics (per BUILD-129 Phase 2 goals)
1. **SMAPE**: Symmetric Mean Absolute Percentage Error
   - Target: <50% average, <30% median
   - Formula: `abs(pred - actual) / ((abs(pred) + abs(actual)) / 2) * 100`

2. **Waste Ratio**: predicted / actual
   - Target: 1.0-1.5x median, 1.2-2.0x P90
   - Formula: `predicted_tokens / actual_tokens`

3. **Underestimation Rate**: % of samples where predicted < actual
   - Target: <10% (minimize truncation risk)
   - Critical: 0% for `actual > selected_budget` (actual truncation)

4. **Truncation Rate**: % of samples with `stop_reason=max_tokens`
   - Target: 0%
   - Ground truth metric for underestimation

### Secondary Metrics (for overhead model tuning)
1. **Overhead efficiency**: median(overhead / actual_output) by category/complexity
   - Identifies if overhead is too high/low for specific combinations

2. **Marginal cost accuracy**: median(marginal_cost / actual_output) by file type
   - Identifies if per-file weights are accurate

3. **Category stratification**: SMAPE variance across categories
   - Target: <30% variance (consistent predictions)

4. **Complexity stratification**: SMAPE variance across complexity levels
   - Target: <25% variance

5. **Deliverable scaling**: SMAPE correlation with deliverable count
   - Target: near-zero correlation (overhead model should scale linearly)

---

## Analysis Tools

### Updated Replay Script
Enhance [scripts/replay_telemetry.py](scripts/replay_telemetry.py) to:
- ✅ Report by category/complexity/deliverable_count
- ✅ Show P50, P75, P90 waste ratios
- ✅ Identify worst mispredictions for tuning focus
- ✅ Generate stratification variance report

### New V3 Analyzer Enhancements
Update [scripts/analyze_token_telemetry_v3.py](scripts/analyze_token_telemetry_v3.py) to:
- Add `--stratify` flag for category/complexity breakdown
- Add `--overhead-analysis` to compute overhead vs marginal cost ratios
- Add `--outlier-detection` to flag edge cases
- Add `--export-json` for machine-readable results

---

## Coefficient Tuning After Collection

Once 30-50 samples are collected:

### Step 1: Overhead Tuning
For each (category, complexity) pair with ≥3 samples:
```python
# Current overhead:
overhead = PHASE_OVERHEAD[(category, complexity)]

# Compute actual overhead from samples:
actual_overhead = median([
    actual_output - sum(marginal_costs_per_deliverable)
    for sample in samples
])

# Adjust if |overhead - actual_overhead| > 20%:
if abs(overhead - actual_overhead) / overhead > 0.2:
    new_overhead = int(actual_overhead * 1.1)  # +10% safety buffer
```

### Step 2: Marginal Cost Tuning
For each file type with ≥5 samples:
```python
# Current marginal cost:
marginal_cost = TOKEN_WEIGHTS[file_type]

# Compute actual per-file cost:
actual_cost = median([
    (actual_output - overhead) / len(deliverables)
    for sample in samples
])

# Adjust if |marginal_cost - actual_cost| > 20%:
if abs(marginal_cost - actual_cost) / marginal_cost > 0.2:
    new_marginal_cost = int(actual_cost * 1.1)  # +10% safety buffer
```

### Step 3: Safety Margin Validation
Check if SAFETY_MARGIN (1.3x) is appropriate:
```python
# Compute optimal safety margin:
optimal_margin = percentile([
    actual_output / base_estimate
    for sample in samples
], 90)  # P90 to cover 90% of cases

# If optimal_margin differs significantly from 1.3:
if abs(optimal_margin - 1.3) > 0.1:
    # Consider adjusting SAFETY_MARGIN
    recommended_margin = round(optimal_margin * 1.05, 1)  # +5% buffer
```

---

## Success Criteria

### Phase 3 Complete When:
- [x] Collected 30-50 successful telemetry samples
- [x] Category distribution: all 8 categories have ≥3 samples
- [x] Complexity distribution: low/medium/high have ≥8/15/8 samples
- [x] Deliverable distribution: all bins (1-2, 3-4, 5-8, 9+) have ≥3 samples
- [x] Average SMAPE: <50% across full dataset
- [x] Median waste ratio: 1.0-1.5x
- [x] Underestimation rate: <10%
- [x] Truncation rate: 0%
- [x] Updated overhead coefficients based on stratified analysis
- [x] Documentation: BUILD-129_PHASE3_COMPLETION_SUMMARY.md

---

## Timeline

**Week 1 (Dec 24-30):** Execute Phase 1 runs → 12 samples
**Week 2 (Dec 31-Jan 6):** Execute Phase 2 runs → 16 samples
**Week 3 (Jan 7-13):** Create and execute Phase 3 targeted runs → 10 samples

**Total:** 38 samples by mid-January, meeting 30-50 target

---

## Next Steps

1. ✅ Execute `build130-schema-validation-prevention`
2. ✅ Execute `build132-coverage-delta-integration` (1 remaining phase)
3. ✅ Execute `fileorg-p2-20251208g`
4. ✅ Execute `lovable-p2-quality-ux` (1 remaining phase)
5. ✅ Execute `build112-completion`
6. ⏳ Collect telemetry, append to build132_telemetry_samples.txt
7. ⏳ Run stratified analysis
8. ⏳ Execute Week 2 runs
9. ⏳ Create Week 3 targeted runs
10. ⏳ Final overhead model tuning

---

**BUILD-129 Phase 3: Ready to Execute** 🚀
