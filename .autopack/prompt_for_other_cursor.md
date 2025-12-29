# Batch Drain Telemetry Diagnostic Results & Recommendations Request

## Context

You're being consulted on optimal settings for draining **274 FAILED phases across 56 runs** in the Autopack project. A diagnostic batch has been run to measure telemetry collection effectiveness after fixing a critical bug where `TELEMETRY_DB_ENABLED=1` was missing from subprocess environment (causing 100% telemetry loss).

## Current Batch Drain Controller Capabilities

The controller has adaptive controls with these tunable parameters:

- `--phase-timeout-seconds`: Timeout per phase (default: 900s = 15 minutes)
- `--max-total-minutes`: Total session time limit (default: unlimited)
- `--max-timeouts-per-run`: Skip run after N timeouts (default: 2)
- `--max-attempts-per-phase`: Skip phase after N attempts (default: 2)
- `--max-fingerprint-repeats`: Deprioritize run after same error repeats N times (default: 3)
- `--batch-size`: Number of phases to process per session (default: 10)

## Diagnostic Batch Results

**Session**: `batch-drain-20251228-061426`
**Status**: In progress (1/10 phases complete, started 17:14 UTC)

### Key Metrics (from first phase)

- **Success Rate**: 0% (0/1 succeeded)
- **Timeout Rate**: 0% (0/1 timed out)
- **Failure Rate**: 100% (1/1 failed)
- **Telemetry Yield**: 0.14 events/min (1 event in 7.4 minutes)
- **Phase Duration**: 441 seconds (~7.4 minutes)
- **Error Type**: CI collection/import error (ImportError in test module)

### Failure Pattern

**Fingerprint**: `FAILED|rc1|ci collectionpath error: testspath (importerror while importing test module 'path'.')`

**Error Message**: `CI collection/import error: tests/autopack/workflow/test_research_review.py (ImportError while importing test module 'c:\\dev\\Autopack\\tests\\autopack\\workflow\\test_research_review.py'.)`

**Observation**: Phase failed early (before heavy Builder execution), explaining the very low telemetry yield (0.14 events/min). This is expected for CI import errors.

### Telemetry Collection Status

✅ **TELEMETRY IS WORKING** - Previously broken due to missing `TELEMETRY_DB_ENABLED=1` flag. Now fixed and confirmed collecting events.

⚠️ **LOW YIELD** - 0.14 events/min is very low, but this is expected for phases that fail during CI collection (they don't reach token-heavy Builder operations).

## Backlog Composition

**Total**: 274 FAILED phases across 56 runs

**Top 10 Runs by Phase Count**:
1. fileorg-p2-20251208q: 18 phases
2. fileorg-p2-20251208r: 18 phases
3. fileorg-p2-20251208s: 17 phases
4. fileorg-p2-20251208t: 17 phases
5. build129-p3-week1-telemetry: 10 phases
6. fileorg-p2-20251208p: 8 phases
7. research-system-v5: 8 phases
8. research-system-v9: 8 phases
9. fileorg-p2-20251208m: 7 phases
10. research-system-v4: 7 phases

**Note**: Many of these are likely research-system runs with similar CI import errors (systematic issue).

## Current Diagnostic Batch Settings

```bash
python scripts/batch_drain_controller.py \
  --batch-size 10 \
  --phase-timeout-seconds 900 \
  --max-timeouts-per-run 2 \
  --max-attempts-per-phase 2 \
  --max-fingerprint-repeats 3
```

## Questions for Recommendations

Based on the diagnostic results so far and the backlog composition, please recommend:

### 1. Optimal Timeout Settings

- **Phase timeout**: Should we keep 900s (15m), reduce to 600s (10m) for faster triage, or increase to 1200s (20m) for phases that might complete?
- **Total session time limit**: Should we use `--max-total-minutes` to cap each draining session? If so, what value (60m, 120m, 180m)?

### 2. Stop Condition Tuning

- **Max fingerprint repeats**: Keep at 3, or adjust based on backlog composition?
- **Max timeouts per run**: Keep at 2, or make more/less strict?
- **Max attempts per phase**: Keep at 2, or allow more retries for high-value phases?

### 3. Batch Size Strategy

- **Small batches** (10-20 phases): More frequent checkpoints, easier to stop/resume
- **Medium batches** (30-50 phases): Better throughput, still manageable
- **Large batches** (100+ phases): Maximum automation, but long runtime

Given the 274-phase backlog, what batch size would you recommend?

### 4. Prioritization Strategy

Given that many phases appear to have **systematic CI import errors** (like research-system runs), should we:

- **Option A**: Process the entire backlog with current settings and let fingerprinting deprioritize repeating failures
- **Option B**: Fix the CI import issue first (research-system test imports), then drain
- **Option C**: Filter out research-system runs entirely and focus on other runs (fileorg, build129, etc.)
- **Option D**: Process everything but with stricter stop conditions to avoid wasting tokens on unfixable errors

### 5. Telemetry Collection Goals

Current yield is **0.14 events/min** (very low, but expected for CI errors). For token estimation calibration goals:

- What minimum yield threshold should trigger investigation (0.5/min, 1.0/min, 2.0/min)?
- Should we prioritize phases likely to reach Builder execution (exclude CI error phases)?
- Or process everything to identify which phase types generate good samples?

### 6. Special Considerations

- **fileorg runs** (many phases): These might have different error patterns than research-system runs
- **build129 runs**: Telemetry-focused runs, might have higher yield potential
- **API server reuse**: Should we use `--api-url http://localhost:8000` to prevent spawning hundreds of uvicorn processes?

## Expected Output

Please provide concrete recommendations in this format:

```bash
# Recommended command for draining the 274-phase backlog:
python scripts/batch_drain_controller.py \
  --batch-size <RECOMMENDED> \
  --phase-timeout-seconds <RECOMMENDED> \
  --max-total-minutes <RECOMMENDED or omit> \
  --max-timeouts-per-run <RECOMMENDED> \
  --max-attempts-per-phase <RECOMMENDED> \
  --max-fingerprint-repeats <RECOMMENDED> \
  [--run-id <filter> if you recommend focusing on specific runs] \
  [--api-url http://localhost:8000 if recommended]
```

Plus brief justification for each parameter choice based on:
- Expected success rate
- Expected timeout rate
- Expected telemetry yield
- Token budget optimization
- Time to completion estimate

## Additional Context

**Recent Fixes Applied**:
- ✅ TELEMETRY_DB_ENABLED=1 now set (was missing, causing 100% loss)
- ✅ Research CI import error diagnosed (tests/autopack/workflow/test_research_review.py)
- ✅ Integration tests added and passing (10/10 tests)
- ✅ Failure fingerprinting working correctly

**Available Tools**:
- `scripts/analyze_batch_session.py --latest` - Auto-analyze session results
- `scripts/telemetry_row_counts.py` - Check telemetry table counts
- `scripts/batch_drain_controller.py --dry-run` - Preview what would be processed

**Documentation**:
- Full adaptive controls guide: [docs/guides/BATCH_DRAIN_ADAPTIVE_CONTROLS.md](docs/guides/BATCH_DRAIN_ADAPTIVE_CONTROLS.md)

---

**Your Task**: Provide concrete, actionable drain settings for processing the 274-phase backlog efficiently while maximizing telemetry collection and minimizing token waste on deterministic failures.
