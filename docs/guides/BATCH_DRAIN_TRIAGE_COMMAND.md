# Batch Drain Triage Command - Token-Safe Backlog Processing

**Date**: 2025-12-28
**Backlog**: 274 FAILED phases across 56 runs
**Context**: Post telemetry-fix diagnostic sweep

---

## Recommended Triage Command

Based on diagnostic batch results showing **systematic CI import errors** in research-system runs, use this token-safe triage sweep:

```bash
# High-throughput triage: skip research-system cluster, detect telemetry issues early
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" TELEMETRY_DB_ENABLED=1 \
python scripts/batch_drain_controller.py \
  --batch-size 50 \
  --phase-timeout-seconds 600 \
  --max-total-minutes 60 \
  --max-fingerprint-repeats 2 \
  --max-timeouts-per-run 1 \
  --max-attempts-per-phase 1 \
  --skip-run-prefix research-system \
  --max-consecutive-zero-yield 10
```

---

## Parameter Justification

### Core Settings

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `--batch-size` | 50 | Large enough to discover full fingerprint distribution |
| `--phase-timeout-seconds` | 600 (10m) | Diagnostic batch showed 0% timeout rate; failures happen fast |
| `--max-total-minutes` | 60 | Time cap prevents runaway sessions during triage |

### Stop Conditions (Strict for Triage)

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `--max-fingerprint-repeats` | 2 | Quick brake on dominant "CI collection/import error" fingerprint |
| `--max-attempts-per-phase` | 1 | Retries won't fix deterministic collection errors |
| `--max-timeouts-per-run` | 1 | Timeouts are expensive; one is enough during triage |

### New Features (Token-Safe)

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `--skip-run-prefix research-system` | - | Diagnostic batch: 2/2 phases = same CI import error. Skip cluster during triage. |
| `--max-consecutive-zero-yield` | 10 | Stop if 10 consecutive phases show +0 telemetry (flags DB/flag mismatch early) |

---

## What This Command Does

### ✅ Includes (Triage Targets)
- **fileorg-p2-\*** runs (18-17 phases each, ~100 total phases)
- **build129/build127/build132** runs (telemetry-focused, different error patterns)
- Other non-research-system runs

### ❌ Excludes (Systematic Blockers)
- **research-system-\*** runs (v4-v9: known CI import errors, ~40-50 phases)
- Avoids burning tokens on deterministic failures during initial triage

### 🛑 Early Stop Triggers
1. **60 minutes elapsed** → Prevents runaway sessions
2. **Same fingerprint 2x** → Deprioritizes run, moves to next
3. **10 consecutive +0 telemetry** → Flags collection issues (DB mismatch, flag disabled, etc.)

---

## Expected Outcomes

### Success Metrics (from Triage)
- **Fingerprint distribution**: Top 3-5 error types across non-research-system runs
- **Telemetry yield baseline**: Median/P90 events/min for phases that reach Builder
- **Quick wins**: Identify runs with transient failures vs. deterministic blocks

### Decision Points After Triage

**If median yield < 0.5 events/min AND most phases show +0:**
→ Stop, investigate telemetry flag/DB issues

**If same 1-2 fingerprints dominate (like research-system):**
→ Fix systemic issue OR continue skipping those run prefixes

**If yield is good (>1.0 events/min) AND diverse fingerprints:**
→ Continue with larger batches, tuned stop conditions

---

## Follow-Up Commands

### 1. After Triage: Analyze Session

```bash
# Auto-analyze triage results
python scripts/analyze_batch_session.py --latest
```

Look for:
- % phases with events
- Median/P90 telemetry yield
- Top 3 fingerprints + counts

### 2. Query Telemetry Quality (Success-Only)

```bash
# Check telemetry event quality for successful phases
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

session = SessionLocal()
events = session.query(TokenEstimationV2Event).all()
success_events = [e for e in events if e.final_token_count > 0]

print(f'Total events: {len(events)}')
print(f'Success events: {len(success_events)}')
if success_events:
    median_waste = sorted([e.waste_ratio for e in success_events if e.waste_ratio])[len(success_events)//2]
    print(f'Median waste_ratio: {median_waste:.2f}')
session.close()
"
```

### 3. Continue with Adjusted Settings

Based on triage results, either:

**A. High-yield scenario (good telemetry):**
```bash
# Process full backlog with looser stop conditions
python scripts/batch_drain_controller.py \
  --batch-size 100 \
  --phase-timeout-seconds 900 \
  --max-total-minutes 120 \
  --max-fingerprint-repeats 3 \
  --skip-run-prefix research-system
```

**B. Low-yield scenario (systematic issues):**
```bash
# Focus on specific high-value runs
python scripts/batch_drain_controller.py \
  --batch-size 20 \
  --run-id fileorg-p2-20251208q \
  --phase-timeout-seconds 1200
```

**C. Fix Research-System CI Errors, Then Drain:**
1. Fix `tests/autopack/workflow/test_research_review.py` import errors
2. Rerun diagnostic batch WITHOUT `--skip-run-prefix`
3. Measure yield improvement

---

## Monitoring During Execution

### Real-Time Progress

Watch for these patterns:

```
[3/50] Selecting next phase...
  Draining: fileorg-p2-20251208q / fileorg-phase-1
  [FAIL] Failed: FAILED
    Error: Deliverable missing: scope.json
    [TELEMETRY] +0 events (0.00/min)           ← LOW YIELD

[4/50] Selecting next phase...
  Draining: build129-token-budget / build129-phase-2
  [OK] Success: COMPLETE
    [TELEMETRY] +12 events (4.20/min)          ← GOOD YIELD

[10/50] Selecting next phase...
  [STOP] 10 consecutive phases with 0 telemetry (limit: 10)  ← TELEMETRY FLAG ISSUE
```

### Session Persistence

All progress saved to:
```
.autonomous_runs/batch_drain_sessions/batch-drain-YYYYMMDD-HHMMSS.json
```

Resume if interrupted:
```bash
python scripts/batch_drain_controller.py --resume
```

---

## Troubleshooting

### Q: All phases being skipped?
**A**: Too many runs match `--skip-run-prefix`. Remove prefix or adjust:
```bash
# Check what's being skipped
python scripts/batch_drain_controller.py --batch-size 10 --dry-run --skip-run-prefix research-system
```

### Q: Hit 10 consecutive zero-yield immediately?
**A**: Telemetry collection is broken. Check:
1. `TELEMETRY_DB_ENABLED=1` is set (should be automatic now)
2. `DATABASE_URL` matches between controller and subprocess
3. Phases aren't all timing out before Builder execution

### Q: Same fingerprint repeating but not from research-system?
**A**: Discovered a new systematic blocker. Add another `--skip-run-prefix`:
```bash
--skip-run-prefix research-system --skip-run-prefix fileorg-p2
```

Or fix the root cause and rerun.

---

## Performance Expectations

### With Recommended Settings (10m timeout, strict stops, 60m cap)

- **Throughput**: ~15-20 phases/hour (mix of quick failures + some successes)
- **Token waste reduction**: ~50% vs. default settings (skips research-system cluster)
- **Telemetry yield**: Depends on phase types, expect 0.5-2.0 events/min baseline
- **Session duration**: Will hit 60m cap or exhaust non-research-system phases (~180-220 phases available)

### Time to Complete Full Non-Research-System Backlog

- **Conservative estimate**: 3-4 sessions @ 60m each = 3-4 hours
- **Aggressive estimate**: 2 sessions @ 60m + 1 session @ 30m = 2.5 hours

---

## References

- [Batch Drain Adaptive Controls](BATCH_DRAIN_ADAPTIVE_CONTROLS.md) - Full feature documentation
- [scripts/batch_drain_controller.py](../../scripts/batch_drain_controller.py) - Implementation
- [scripts/analyze_batch_session.py](../../scripts/analyze_batch_session.py) - Analysis tool
- [Telemetry Fix Commit](https://github.com/yourrepo/commit/4b951c49) - TELEMETRY_DB_ENABLED=1 fix

---

## Next Steps

1. **Run the triage command above**
2. **Analyze results** with `python scripts/analyze_batch_session.py --latest`
3. **Make decision** based on fingerprint distribution and telemetry yield:
   - Good yield? → Continue with larger batches
   - Zero yield? → Investigate telemetry flags/DB
   - Same errors? → Fix root cause OR skip more prefixes
4. **Iterate** with adjusted settings based on empirical data
