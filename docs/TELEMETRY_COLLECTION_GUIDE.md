# Token Estimation Telemetry Collection Guide

**Status**: BUILD-129 Phase 1 validation infrastructure is **production-ready**, waiting for representative data

**Last Updated**: 2025-12-23

---

## Current Situation

### What We Have ✅

1. **V2 Telemetry Logging**: [anthropic_clients.py:652-699](../src/autopack/anthropic_clients.py#L652-L699)
   - Logs real TokenEstimator predictions vs actual output tokens
   - Captures metadata: success, truncation, category, complexity, deliverable count

2. **V3 Analyzer**: [scripts/analyze_token_telemetry_v3.py](../scripts/analyze_token_telemetry_v3.py)
   - 2-tier metrics (Risk + Cost)
   - Success-only filtering
   - Stratification by category/complexity/deliverable-count
   - Underestimation tolerance (--under-multiplier)

3. **Comprehensive Documentation**:
   - [BUILD-129_PHASE1_VALIDATION_COMPLETE.md](archive/superseded/reports/BUILD-129_PHASE1_VALIDATION_COMPLETE.md) - Implementation summary
   - [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md) - Methodology and learnings
   - [TOKEN_ESTIMATION_V3_ENHANCEMENTS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_V3_ENHANCEMENTS.md) - V3 analyzer details

### What We Need ⏳

**20+ successful production samples** with:
- `success=True` (not failure-mode outputs)
- Mix of complexity levels (low/medium/high)
- Mix of categories (implementation/tests/docs)
- Mix of deliverable counts (1 file / 2-5 files / 6+ files)

### Current Blocker 🚫

All existing telemetry samples have `success=False` (failure-mode outputs producing 117-129 tokens). These are non-representative and cannot be used for coefficient tuning.

**Why existing samples failed**:
1. **Test harness** (`collect_telemetry_simple.py`): Provides empty context, Builder can't create files
2. **BUILD-130 runs**: Failed on deliverables validation **before Builder execution**, so no telemetry logged

---

## How to Collect Representative Telemetry

### Option 1: Wait for Real Production Runs ⏰

**Easiest approach** - Just wait for the next successful autonomous run:

1. Run any real autonomous execution (BUILD-132, future builds, etc.)
2. Ensure phases complete successfully (success=True)
3. Telemetry will be automatically logged to the run's log file

**Pros**:
- No extra work needed
- Real-world telemetry
- Most representative data

**Cons**:
- May take longer to collect 20+ samples
- Depends on run success rate

### Option 2: Create Simple Utility Phases 🛠️

**Fastest approach** - Create achievable phases that will definitely succeed:

#### Step 1: Create Simple Implementation Run

Create a run with simple, self-contained utility functions:

```python
# Example phases:
# 1. String utilities (capitalize_words, reverse_string)
# 2. Number utilities (is_even, is_prime, factorial)
# 3. List utilities (chunk, flatten, unique, group_by)
# 4. Date utilities (format_date, parse_date, add_days)
# 5. Dict utilities (deep_merge, get_nested, set_nested)
# 6. Tests for above utilities
# 7. Documentation (README)
```

**Note**: The challenge is that run/phase creation requires proper database schema knowledge (tier_id, phase_index, etc.). See `scripts/create_telemetry_collection_run.py` for an attempt.

#### Step 2: Execute and Monitor

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python -m autopack.autonomous_executor --run-id <run-id>
```

#### Step 3: Analyze Telemetry

```bash
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs/<run-dir> \
  --success-only
```

### Option 3: Manual Test Harness (Not Recommended) ❌

**Why not recommended**: Previous attempts (`collect_telemetry_simple.py`) produced only failure-mode outputs because Builder needs real context to succeed.

---

## How to Know When You Have Enough Data

### Minimum Requirements

Run this command to check current status:

```bash
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only
```

**You have enough data when**:
- ✅ **≥20 samples** with `success=True`
- ✅ **Mix of categories**: implementation, tests, docs
- ✅ **Mix of complexity**: low, medium, high
- ✅ **Mix of deliverable counts**: 1 file, 2-5 files, 6+ files

**Current status** (as of 2025-12-23):
```
Total V2 records: 10
Success rate: 0.0% (0/10 samples)
❌ INSUFFICIENT DATA - all samples are failure modes
```

---

## Analysis Workflow

### Step 1: Check Overall Status

```bash
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only
```

**Look for**:
- Success rate (should be >0%)
- Total successful samples (need ≥20)

### Step 2: Generate Stratified Report

**Once you have ≥20 successful samples**:

```bash
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --stratify \
  --under-multiplier 1.1 \
  --output reports/telemetry_baseline_$(date +%Y%m%d).md
```

This will generate a report with:
- **Tier 1 (Risk) Metrics**: Underestimation rate, truncation rate
- **Tier 2 (Cost) Metrics**: Waste ratio (P50, P90)
- **Stratification**: Breakdown by category/complexity/deliverable-count
- **Tuning Decision**: Clear yes/no on whether to adjust coefficients

### Step 3: Tuning Decision

**Tier 1 Targets** (PRIMARY - drive tuning decisions):
- Underestimation rate: ≤5%
- Truncation rate: ≤2%

**Tier 2 Targets** (SECONDARY - optimize after Tier 1 met):
- Waste ratio P90: <3x

**If Tier 1 targets are exceeded**:
- Proceed with category-specific coefficient tuning
- See [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md Phase 4](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md#phase-4-coefficient-tuning--deferred)

**If Tier 1 targets are met**:
- ✅ No tuning needed
- TokenEstimator is working well
- Continue monitoring for drift

---

## Recommended Next Steps

### Immediate (Today)

1. ✅ **V3 Infrastructure Complete** - No action needed
2. ✅ **Documentation Complete** - No action needed
3. ⏳ **Wait for successful production run** - Let BUILD-132 or next implementation succeed

### When You Have Successful Runs

1. **Check telemetry collection**:
   ```bash
   grep "\[TokenEstimationV2\]" .autonomous_runs/<run-dir>/*.log | wc -l
   ```

2. **Verify success rate**:
   ```bash
   grep "\[TokenEstimationV2\].*success=True" .autonomous_runs/<run-dir>/*.log | wc -l
   ```

3. **Analyze when you hit 20+ successful samples**:
   ```bash
   python scripts/analyze_token_telemetry_v3.py \
     --log-dir .autonomous_runs \
     --success-only \
     --stratify \
     --under-multiplier 1.1 \
     --output reports/baseline_$(date +%Y%m%d).md
   ```

### Long Term (Continuous Monitoring)

**After every 10-20 production runs**:

1. Run stratified analysis
2. Compare to baseline
3. Check for drift (underestimation/truncation rate increases)
4. Adjust coefficients if Tier 1 metrics degrade

---

## FAQ

### Q: Why can't we use the 10 existing telemetry samples?

**A**: All 10 existing samples have `success=False` - they are failure-mode outputs where Builder produced minimal 117-129 token responses instead of full implementations. Tuning on failure modes would break successful runs.

### Q: Can we just create a test run to collect telemetry?

**A**: Attempted in `scripts/create_telemetry_collection_run.py`, but hit complexity with database schema (tier_id requirements, phase relationships). Real production runs are simpler and more representative.

### Q: How long until we can tune coefficients?

**A**: Depends on when we get 20+ successful production samples. Could be:
- **Days**: If BUILD-132 or other real implementations succeed soon
- **Weeks**: If we wait for natural production runs to accumulate

### Q: What if Tier 1 metrics are already within targets?

**A**: Great! That means TokenEstimator coefficients are well-calibrated. No tuning needed, just continue monitoring for drift.

### Q: Can we lower the 20-sample requirement?

**A**: Not recommended. Statistical significance requires ≥20 samples, especially when stratifying by category/complexity/deliverable-count. With <20 samples, per-stratum sample sizes become too small for confident tuning decisions.

---

## Current Baseline (2025-12-23)

**V2 Telemetry Samples**: 10 (all from test harness)

| Sample | Predicted | Actual | SMAPE | Success | Category | Complexity |
|--------|-----------|--------|-------|---------|----------|------------|
| 1      | 448       | 124    | 113.3%| False   | impl     | low        |
| 2      | 448       | 129    | 110.6%| False   | impl     | medium     |
| 3      | 448       | 124    | 113.3%| False   | impl     | medium     |
| 4      | 822       | 129    | 145.7%| False   | impl     | high       |
| 5      | 373       | 117    | 104.5%| False   | impl     | low        |

**Analysis**:
- Mean SMAPE: 117.5% (high but irrelevant - not the right metric)
- Underestimation rate: 0.0% ✅ (target ≤5%)
- Truncation rate: 0.0% ✅ (target ≤2%)
- **Success rate: 0.0%** ❌ (target >0% - BLOCKER)

**Conclusion**: Data is valid but non-representative. DO NOT TUNE until we have successful samples.

---

## References

- **V2 Telemetry**: [anthropic_clients.py:652-699](../src/autopack/anthropic_clients.py#L652-L699)
- **V3 Analyzer**: [scripts/analyze_token_telemetry_v3.py](../scripts/analyze_token_telemetry_v3.py)
- **Implementation Summary**: [BUILD-129_PHASE1_VALIDATION_COMPLETE.md](archive/superseded/reports/BUILD-129_PHASE1_VALIDATION_COMPLETE.md)
- **Methodology Learnings**: [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md)
- **V3 Enhancements**: [TOKEN_ESTIMATION_V3_ENHANCEMENTS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_V3_ENHANCEMENTS.md)
- **Token Estimator**: [src/autopack/token_estimator.py](../src/autopack/token_estimator.py)

---

## Contact / Questions

If you have questions about telemetry collection, coefficient tuning, or analysis:
1. Review [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md) for methodology
2. Check [BUILD-129_PHASE1_VALIDATION_COMPLETE.md](archive/superseded/reports/BUILD-129_PHASE1_VALIDATION_COMPLETE.md) for implementation details
3. Run `python scripts/analyze_token_telemetry_v3.py --help` for usage

**The infrastructure is ready - we just need successful production runs!** 🚀
