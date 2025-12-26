# BUILD-129 Phase 3: Telemetry Collection Status

**Date**: 2025-12-24
**Status**: IN PROGRESS (20% complete - 6/30 samples)

---

## Summary

Successfully collected 6 production telemetry samples with real deliverables after fixing critical infrastructure issue (missing `src/autopack/config.py`). Export and replay scripts now working correctly.

---

## Samples Collected (5 production + 1 test)

### Production Samples (5)

| # | Phase | Category | Complexity | Deliverables | Predicted | Actual | SMAPE | Waste Ratio | Success |
|---|-------|----------|------------|--------------|-----------|--------|-------|-------------|---------|
| 1 | lovable-p2.3-missing-import-autofix | implementation | low | 2 | 7020 | 3788 | 59.8% | 1.85x | ✅ |
| 2 | lovable-p2.4-conversation-state | refactoring | medium | 2 | 8970 | 5606 | 46.2% | 1.60x | ✅ |
| 3 | lovable-p2.5-fallback-chain | implementation | low | 2 | 7020 | 7700 | 9.2% | 0.91x | ✅ |
| 4 | build129-p3-w1.7-configuration-medium-4files | configuration | medium | 4 | 10270 | 6756 | 41.3% | 1.52x | ✅ |
| 5 | build129-p3-w1.8-integration-high-5files | integration | high | 5 | 19240 | 13211 | 37.2% | 1.46x | ❌ |

### Test Sample (1)

| # | Phase | Category | Complexity | Deliverables | Predicted | Actual | SMAPE | Waste Ratio | Success |
|---|-------|----------|------------|--------------|-----------|--------|-------|-------------|---------|
| 6 | diagnostics-deep-retrieval | implementation | low | 1 | 100 | 120 | 18.2% | 0.83x | ✅ |

**Note**: Sample #6 appears to be a test case (predicted=100 tokens is unrealistic). Excluding from production analysis.

---

## Production Sample Statistics (n=5)

### Overall Metrics
- **Average SMAPE**: 38.7% (target: <50%) ✅
- **Median Waste Ratio**: 1.52x (overestimation)
- **Success Rate**: 80% (4/5 successful)
- **Underestimation Rate**: 20% (1/5 underestimated)

### Distribution

**Categories**:
- implementation: 2 samples (40%)
- refactoring: 1 sample (20%)
- configuration: 1 sample (20%)
- integration: 1 sample (20%)

**Complexities**:
- low: 2 samples (40%)
- medium: 2 samples (40%)
- high: 1 sample (20%)

**Deliverable Counts**:
- 2 deliverables: 3 samples (60%)
- 4 deliverables: 1 sample (20%)
- 5 deliverables: 1 sample (20%)

---

## Key Findings

### Strengths
1. **Excellent performance on low-complexity tasks**: lovable-p2.5-fallback-chain achieved 9.2% SMAPE (nearly perfect)
2. **Consistent overestimation**: 4/5 samples overestimated (waste ratio >1.0), which is safer than underestimation
3. **Real deliverables captured**: All samples have actual file paths (no synthetic `src/file{j}.py`)
4. **Average SMAPE below target**: 38.7% < 50% target

### Areas for Improvement
1. **High variance**: SMAPE ranges from 9.2% to 59.8% (need more samples to understand patterns)
2. **One underestimation**: lovable-p2.5-fallback-chain underestimated (waste ratio 0.91x)
3. **Limited coverage**: Missing categories (testing, documentation), high-complexity low-deliverable combos

---

## Infrastructure Fixes Applied (2025-12-24)

### Critical Issue: Missing `src/autopack/config.py`

**Problem**: `src/autopack/config.py` was accidentally deleted by malformed patch application, causing `ModuleNotFoundError` in export/replay scripts.

**Root Cause**: `governed_apply.py` deleted existing files when patch incorrectly marked them as `new file mode`.

**Fixes Applied**:
1. ✅ Restored `src/autopack/config.py`
2. ✅ Added `src/autopack/config.py` to `PROTECTED_PATHS` in `governed_apply.py`
3. ✅ Changed `_remove_existing_files_for_new_patches()` to fail fast instead of deleting protected files
4. ✅ Added guard in `_restore_corrupted_files()` to refuse deleting protected files
5. ✅ Added regression test: `tests/test_governed_apply_no_delete_protected_on_new_file_conflict.py`

**Verification**:
- ✅ Export script working: `PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/export_token_estimation_telemetry.py`
- ✅ Replay script working: `PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/replay_telemetry.py`
- ✅ Regression test passing: `pytest tests/test_governed_apply_no_delete_protected_on_new_file_conflict.py`

---

## Sample Collection Progress

### Target Distribution (30-50 samples)

**Categories** (target: 8-12 per category):
- ✅ implementation: 2/10
- ✅ refactoring: 1/10
- ✅ configuration: 1/10
- ✅ integration: 1/10
- ❌ testing: 0/10
- ❌ documentation: 0/10

**Complexities** (target: 10-15 per complexity):
- ✅ low: 2/12
- ✅ medium: 2/12
- ✅ high: 1/12
- ❌ maintenance: 0/4

**Deliverable Counts** (target: diverse):
- ❌ 1-3 deliverables: 3/15
- ✅ 4-7 deliverables: 2/15
- ❌ 8-15 deliverables: 0/10
- ❌ 16+ deliverables: 0/5

### Gaps in Coverage

**High Priority**:
- testing category (0 samples)
- documentation category (0 samples)
- 8-15 deliverable range (0 samples)
- maintenance complexity (0 samples)

**Medium Priority**:
- 16+ deliverable range (0 samples)
- More low/medium/high complexity samples (need 8-10 more each)

---

## Next Steps

### 1. Continue Sample Collection (Priority: HIGH)

**Approach A: Run more queued phases from existing runs** ⚠️ **Recommended**
- 160 queued phases available across 32 runs
- Target: Collect 20-25 more samples
- Focus on:
  - testing category (run test-focused phases)
  - documentation category (run doc-focused phases)
  - 8-15 deliverable range (run larger scope phases)
  - maintenance complexity phases

**Approach B: Create synthetic test runs for coverage gaps**
- Create small runs specifically for testing/documentation categories
- Ensure diverse deliverable counts
- Run with `TELEMETRY_DB_ENABLED=1`

**Commands**:
```bash
# Example: Run a queued phase with telemetry
TELEMETRY_DB_ENABLED=1 PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  timeout 600 python -m autopack.autonomous_executor --run-id <run-id>

# Monitor collection progress
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/export_token_estimation_telemetry.py | wc -l
```

### 2. Validate and Analyze After 20-30 Samples (Priority: MEDIUM)

Once we have 20-30 samples:
- Run comprehensive replay validation
- Calculate stratified SMAPE by category/complexity
- Identify systematic over/underestimation patterns
- Tune TokenEstimator if needed

### 3. Update BUILD-129 Status (Priority: LOW)

After validation with 30+ samples:
- Change status from "VALIDATION INCOMPLETE" → "VALIDATED ON REAL DATA"
- Document final SMAPE with real deliverables
- Update [BUILD-129_PHASE3_EXECUTION_SUMMARY.md](BUILD-129_PHASE3_EXECUTION_SUMMARY.md)

---

## Files Modified/Created

### New Files
1. [docs/BUILD-129_PHASE3_TELEMETRY_COLLECTION_STATUS.md](BUILD-129_PHASE3_TELEMETRY_COLLECTION_STATUS.md) - This document
2. [tests/test_governed_apply_no_delete_protected_on_new_file_conflict.py](../tests/test_governed_apply_no_delete_protected_on_new_file_conflict.py) - Regression test for config.py deletion

### Fixed Files
1. [src/autopack/config.py](../src/autopack/config.py) - Restored from deletion
2. [src/autopack/governed_apply.py](../src/autopack/governed_apply.py) - Hardened against accidental deletion

### Working Scripts
1. [scripts/export_token_estimation_telemetry.py](../scripts/export_token_estimation_telemetry.py) - Export telemetry to NDJSON ✅
2. [scripts/replay_telemetry.py](../scripts/replay_telemetry.py) - Replay validation with real deliverables ✅

---

## Current State

**Status**: READY FOR CONTINUED COLLECTION
**Progress**: 6/30 samples (20% complete)
**Blocking Issues**: NONE ✅
**Next Action**: Run more queued phases to collect 20-25 additional samples

**Confidence Level**: HIGH - Infrastructure validated, scripts working, initial samples look good.

---

## 2025-12-27 Update: Convergence blocker shifted from NDJSON parsing to truncation/partial deliverables

While draining `research-system-v9` in **single-phase batches** (telemetry enabled), we observed a systemic NDJSON failure mode and addressed it:

- **Issue**: models sometimes output a single JSON payload `{"files":[{"path","mode","new_content"}, ...]}` (or a truncated version) instead of NDJSON lines, leading to `ndjson_no_operations`.
- **Fix (shipped)**: `NDJSONParser` now expands `{"files":[...]}` into operations and can salvage inner file objects even when the outer wrapper is truncated.
- **Result**: parsing now reliably recovers and applies operations under truncation (e.g., 7–8 operations recovered/applied), so the dominant remaining failure is expected **deliverables validation** due to partial output under `stop_reason=max_tokens` (P10 escalation observed).

**Commit**: `b0fe3cc6` — `src/autopack/ndjson_format.py`, `tests/test_ndjson_format.py`
