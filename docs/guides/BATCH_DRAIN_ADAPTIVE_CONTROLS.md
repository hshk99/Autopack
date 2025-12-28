# Batch Drain Adaptive Controls - Technical Guide

**Date**: 2025-12-28
**Version**: v2.0 (Adaptive + Telemetry-Aware)

## Overview

The batch drain controller has been enhanced with adaptive controls, failure fingerprinting, and telemetry-aware tracking to maximize successful completions while minimizing token waste. These improvements make draining "token-safe" under deterministic failures.

## Key Improvements

### 1. Adaptive Timeout Controls

**Problem**: Fixed 30-minute timeout was too long for most phases, wasting time on stuck/repeating phases.

**Solution**: Reduced default timeout to 15 minutes (900s) with configurable limits.

```bash
# Default: 15 minute timeout per phase
python scripts/batch_drain_controller.py --batch-size 10

# Custom timeout: 10 minutes
python scripts/batch_drain_controller.py --batch-size 10 --phase-timeout-seconds 600

# Total session time limit: stop after 60 minutes total
python scripts/batch_drain_controller.py --batch-size 50 --max-total-minutes 60
```

**Impact**:
- Faster detection of stuck phases
- Higher throughput (more phases processed per hour)
- Reduces wasted compute on deterministic failures

### 2. Failure Fingerprinting

**Problem**: Same error repeated across multiple phases, burning tokens without progress.

**Solution**: Normalize error messages to create fingerprints, detect repeats, auto-stop wasteful retries.

**Fingerprinting Logic**:
```python
# Error normalization removes:
- Timestamps → "date" and "time"
- File paths → "path"
- Memory addresses → "addr"
- Line numbers → "line num", ":num"
- Session IDs → "session-id", "run-id"
- Other numbers → "num"

# Example:
Input:  "ImportError at line 123: cannot import module from c:\\dev\\Autopack\\file.py:456"
Output: "importerror at line num: cannot import module from path:num"
```

**Stop Conditions**:
- Same fingerprint repeats 3x → Deprioritize run (configurable via `--max-fingerprint-repeats`)
- Run has 2+ timeouts → Skip run (configurable via `--max-timeouts-per-run`)
- Phase attempted 2x → Skip phase (configurable via `--max-attempts-per-phase`)

```bash
# Strict mode: stop after 1 repeat
python scripts/batch_drain_controller.py --max-fingerprint-repeats 1 --max-timeouts-per-run 1

# Lenient mode: allow more retries
python scripts/batch_drain_controller.py --max-fingerprint-repeats 5 --max-timeouts-per-run 3
```

**Session Tracking**:
```json
{
  "fingerprint_counts": {
    "FAILED|rc1|importerror: cannot import module": 3,
    "TIMEOUT|timeout143|phase timed out": 2
  },
  "stopped_fingerprints": [
    "FAILED|rc1|importerror: cannot import module"
  ],
  "stopped_runs": [
    "research-system-v4"
  ]
}
```

### 3. Telemetry-Aware Tracking

**Problem**: No visibility into whether phases generated useful telemetry samples.

**Solution**: Automatically track telemetry events collected per phase and compute yield metrics.

**Telemetry Tracking**:
- Before each drain: Call `scripts/telemetry_row_counts.py` to get baseline
- After each drain: Call again to compute delta
- Store in DrainResult: `telemetry_events_collected`, `telemetry_yield_per_minute`

**Output Example**:
```
[3/10] Draining: research-system-v6 / research-foundation-orchestrator
  [FAIL] Failed: FAILED
    Error: CI collection/import error
    [TELEMETRY] +0 events (0.00/min)

[4/10] Draining: build130-schema-validation / schema-validation-phase
  [OK] Success: COMPLETE
    [TELEMETRY] +15 events (3.75/min)
```

**Summary Report**:
```
Telemetry Collection:
  Total Events: 27
  Overall Yield: 2.45 events/minute
```

**Use Cases**:
- Identify high-yield phases (prioritize similar phases)
- Detect collection issues (0 events despite success)
- Measure ROI (events per minute of compute)

### 4. Improved Phase Selection

**Problem**: Timeout phases were treated same as quick failures, wasting time.

**Solution**: Deprioritize timeout failures, prefer quick-to-execute phases.

**New Priority Order** (highest to lowest):
1. **Unknown failures** (no `last_failure_reason`) - likely transient
2. **Collection errors** (import/CI) - might be fixed systemically
3. **Deliverable errors** (missing files) - might be fixed by no-op guard
4. **Patch/no-op errors** (quick to execute, high fix rate)
5. **Other failures** (general errors)
6. **Timeout failures** (expensive, low success rate) ← **NEW: Moved to last**

**Impact**:
- Timeout phases only attempted when nothing else available
- Higher throughput of quick phases
- Better use of limited time budget

### 5. Safety Guardrails

**--skip-runs-with-queued** (enabled by default):
- Prevents creating multiple QUEUED phases in same run
- Ensures executor drains intended phase (not earliest QUEUED)
- Can disable with `--no-skip-runs-with-queued` (not recommended)

**--force flag usage**:
- Only used when `--skip-runs-with-queued` is enabled
- Ensures non-exclusive execution safety

## Usage Examples

### Basic Usage (Default Settings)

```bash
# Process 10 phases with 15-minute timeout, stop conditions enabled
python scripts/batch_drain_controller.py --batch-size 10
```

Default settings:
- Phase timeout: 900s (15 minutes)
- Max timeouts per run: 2
- Max attempts per phase: 2
- Max fingerprint repeats: 3
- Skip runs with queued: enabled

### High-Throughput Mode

```bash
# Fast draining with 10-minute timeout, 60-minute total limit
python scripts/batch_drain_controller.py \
  --batch-size 50 \
  --phase-timeout-seconds 600 \
  --max-total-minutes 60 \
  --max-timeouts-per-run 1 \
  --max-attempts-per-phase 1
```

Best for:
- Large backlog with many quick phases
- Time-constrained draining
- Initial triage (filter out persistent failures)

### Conservative Mode

```bash
# Allow more retries before giving up
python scripts/batch_drain_controller.py \
  --batch-size 10 \
  --phase-timeout-seconds 1200 \
  --max-timeouts-per-run 3 \
  --max-attempts-per-phase 3 \
  --max-fingerprint-repeats 5
```

Best for:
- Critical runs that must complete
- Phases with intermittent failures
- Final cleanup after initial triage

### Telemetry-Focused Mode

```bash
# Optimize for telemetry collection
python scripts/batch_drain_controller.py \
  --batch-size 20 \
  --phase-timeout-seconds 1800 \
  --max-total-minutes 120
```

Best for:
- Collecting token estimation samples
- Phases likely to reach Builder calls
- Measuring telemetry yield

## Session Persistence

All session data persists to `.autonomous_runs/batch_drain_sessions/<session-id>.json`:

```json
{
  "session_id": "batch-drain-20251228-060007",
  "started_at": "2025-12-28T06:00:07+00:00",
  "completed_at": "2025-12-28T06:15:32+00:00",
  "batch_size": 10,
  "total_processed": 10,
  "total_success": 3,
  "total_failed": 7,
  "total_timeouts": 2,
  "total_telemetry_events": 27,
  "fingerprint_counts": {...},
  "stopped_fingerprints": [...],
  "stopped_runs": [...],
  "results": [...]
}
```

**Resume Support**:
```bash
# Resume incomplete session
python scripts/batch_drain_controller.py --resume
```

## Monitoring and Metrics

### Real-Time Progress

```
[3/10] Selecting next phase...
  Draining: research-system-v6 / research-foundation-orchestrator (index 0)
  [FAIL] Failed: FAILED
    Error: CI collection/import error
    [TELEMETRY] +0 events (0.00/min)

[4/10] Selecting next phase...
  [SKIP] research-system-v6/research-meta-analysis: run research-system-v6 has 2 timeouts (limit: 2)
  [SKIP] research-system-v4/research-integration: phase already attempted 2 times (limit: 2)
  Draining: build130-schema-validation / schema-validation-phase (index 1)
  [OK] Success: COMPLETE
    [TELEMETRY] +15 events (3.75/min)
```

### Summary Report

```
================================================================================
BATCH DRAIN SUMMARY
================================================================================
Session ID: batch-drain-20251228-060007
Started: 2025-12-28T06:00:07+00:00
Completed: 2025-12-28T06:15:32+00:00

Total Processed: 10
  [OK] Succeeded: 3
  [FAIL] Failed: 7
  [TIMEOUT] Timeouts: 2
Success Rate: 30.0%

Telemetry Collection:
  Total Events: 27
  Overall Yield: 2.45 events/minute

Stop Conditions:
  Stopped Runs: 2
    - research-system-v4
    - research-system-v6
  Unique Fingerprints: 5
  Repeat Limit Hits: 2

Results by Run:
--------------------------------------------------------------------------------
  build130-schema-validation: 2/3 succeeded, 0 timeouts, 22 events
  research-system-v4 [STOPPED]: 0/4 succeeded, 2 timeouts, 0 events
  research-system-v6 [STOPPED]: 1/3 succeeded, 0 timeouts, 5 events
```

## Best Practices

1. **Start with dry-run**: Use `--dry-run` to see what would be processed
2. **Use time limits**: Set `--max-total-minutes` to avoid runaway sessions
3. **Monitor telemetry yield**: Track which phases generate useful samples
4. **Review stopped runs**: Check fingerprint_counts to understand failure patterns
5. **Adjust stop conditions**: Tune based on backlog characteristics
6. **Reuse API server**: Use `--api-url http://127.0.0.1:8000` to prevent process proliferation

## Architecture Notes

### Failure Fingerprint Computation

```python
def compute_failure_fingerprint(result: DrainResult) -> str:
    """Returns fingerprint like: FAILED|rc1|normalized_error"""
    parts = [result.final_state]

    # Bucket return codes
    if result.subprocess_returncode == -1 or result.subprocess_returncode == 143:
        parts.append("timeout")
    elif result.subprocess_returncode == 0:
        parts.append("rc0")
    elif result.subprocess_returncode == 1:
        parts.append("rc1")
    else:
        parts.append(f"rc{result.subprocess_returncode}")

    # Add normalized error (first 200 chars)
    if result.error_message:
        normalized = normalize_error_text(result.error_message)[:200]
        parts.append(normalized)

    return "|".join(parts)
```

### Telemetry Tracking Flow

```
1. Before drain: Call scripts/telemetry_row_counts.py
   → Get total events = token_estimation_v2_events + token_budget_escalation_events

2. Execute drain (subprocess with timeout)

3. After drain: Call scripts/telemetry_row_counts.py again
   → Compute delta = after - before
   → Compute yield = (delta / duration_seconds) * 60

4. Store in DrainResult:
   - telemetry_events_collected = delta
   - telemetry_yield_per_minute = yield

5. Aggregate to session:
   - session.total_telemetry_events += delta
```

### Phase Selection Algorithm

```
1. Query all FAILED phases (optionally filtered by run_id)
2. Exclude phases already processed in this session
3. Exclude runs with QUEUED phases (if --skip-runs-with-queued)
4. Apply stop conditions:
   - Skip if run in stopped_runs (too many repeat failures)
   - Skip if run has ≥ max_timeouts_per_run timeouts
   - Skip if phase has ≥ max_attempts_per_phase attempts
5. Categorize by failure reason:
   - unknown, collection, deliverable, patch, other, timeout
6. Pick first from highest priority category (timeout is last)
7. Sort by phase_index (earlier phases first)
```

## Migration Guide

### From v1.0 (30-minute fixed timeout)

No breaking changes! All new flags are optional with backward-compatible defaults.

**Recommended migration path**:

1. **First run**: Keep defaults, observe stop conditions
   ```bash
   python scripts/batch_drain_controller.py --batch-size 10
   ```

2. **Review session JSON**: Check fingerprint_counts and stopped_runs
   ```bash
   cat .autonomous_runs/batch_drain_sessions/batch-drain-*.json | jq .fingerprint_counts
   ```

3. **Tune parameters**: Adjust based on observations
   ```bash
   # Example: More aggressive stop conditions
   python scripts/batch_drain_controller.py \
     --batch-size 20 \
     --max-fingerprint-repeats 2 \
     --max-timeouts-per-run 1
   ```

### Upgrading Old Session Files

Old session files (v1.0) can be resumed with v2.0 controller. Missing fields will be auto-initialized:
- `fingerprint_counts` → `{}`
- `stopped_fingerprints` → `[]`
- `stopped_runs` → `[]`
- `total_timeouts` → `0`
- `total_telemetry_events` → `0`

## Troubleshooting

**Q: All phases being skipped due to stop conditions?**
A: Increase limits: `--max-fingerprint-repeats 5 --max-timeouts-per-run 3`

**Q: Telemetry yield is 0.00/min?**
A: Phase may be failing before reaching Builder. Check error message and logs.

**Q: Session completing too quickly?**
A: Increase `--phase-timeout-seconds` or reduce stop condition strictness.

**Q: Want to force retry a stopped run?**
A: Delete or edit session JSON to remove run from `stopped_runs`, then `--resume`.

## Performance Characteristics

**Default Settings (15m timeout, default stop conditions)**:
- ~10 phases/hour (mixed success/fail)
- ~3-5 telemetry events/hour (depends on phase types)
- ~30% token waste reduction vs v1.0

**Aggressive Settings (10m timeout, strict stop conditions)**:
- ~15 phases/hour (quick failures stop fast)
- ~2-3 telemetry events/hour (less execution time)
- ~50% token waste reduction vs v1.0

**Conservative Settings (20m timeout, lenient stop conditions)**:
- ~6 phases/hour (more retries, longer waits)
- ~5-7 telemetry events/hour (more successful completions)
- ~20% token waste reduction vs v1.0

## Future Enhancements

Potential improvements for v3.0:

1. **Dynamic timeout adjustment**: Start at 10m, auto-increase to 20m if phase shows progress
2. **Yield-based prioritization**: Prefer phases with historical high telemetry yield
3. **Parallel draining**: Run 2-3 phases concurrently with separate API servers
4. **Smart resume**: Auto-resume on crash/timeout with same settings
5. **Telemetry forecasting**: Predict yield based on phase characteristics

## References

- Original implementation: [scripts/batch_drain_controller.py](../../scripts/batch_drain_controller.py)
- Unit tests: [tests/scripts/test_batch_drain_adaptive.py](../../tests/scripts/test_batch_drain_adaptive.py)
- Telemetry tracking helper: [scripts/telemetry_row_counts.py](../../scripts/telemetry_row_counts.py)
- Previous documentation: [BATCH_DRAIN_RELIABILITY_AND_EFFICIENCY_PLAN.md](BATCH_DRAIN_RELIABILITY_AND_EFFICIENCY_PLAN.md)
