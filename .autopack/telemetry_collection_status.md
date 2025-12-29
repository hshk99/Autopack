# Telemetry Collection Status - 2025-12-28

## Current Situation

**Problem Encountered**: Database auto-reset during initial drain attempt
- First drain attempt using `drain_one_phase.py` failed with API 404 error
- Database was reset to empty state (likely due to schema migration or fresh DB creation)
- This confirms the user's concern about accidental empty DB creation

**Recovery Actions Taken**:
1. ✅ Verified `autopack_legacy.db` is intact (70 runs, 456 phases)
2. ✅ Recreated telemetry run using `scripts/create_telemetry_collection_run.py`
3. ✅ Started batch drain using `scripts/drain_queued_phases.py` with `TELEMETRY_DB_ENABLED=1`

## Current Database State

**autopack.db**:
- Runs: 1 (`telemetry-collection-v4`)
- Phases: 10 (all QUEUED, 1 currently draining)
- LLM usage events: 1 ✅ (telemetry collection WORKING!)

**autopack_legacy.db** (preserved):
- Runs: 70
- Phases: 456
- Intact for future analysis

## Active Background Tasks

**Task bde2b15**: Draining first telemetry phase (test run)
- Command: `drain_one_phase.py --run-id telemetry-collection-v4 --phase-id telemetry-p1-string-util --force`
- Environment: `TELEMETRY_DB_ENABLED=1` ✅ (WORKING - 1 event collected)
- Status: Running (currently in baseline capture phase)
- Timeout: 600 seconds

**Previous failed approaches**:
- `drain_queued_phases.py`: Database cleared due to API server conflicts
- `batch_drain_controller.py`: Only processes FAILED phases, not QUEUED
- Pre-started API server: Conflicted with drain script's embedded API server

## Expected Timeline

### Phase 1: Baseline Capture (0-3 min)
- Capturing T0 baseline at commit 3e2605a1
- This is a one-time startup cost for the run

### Phase 2: Phase Draining (3-120 min)
- 10 phases to drain, estimated 5-10 min per phase
- Each phase should produce LLM usage events if telemetry is enabled
- Success criteria: `LLM usage events > 0` after first phase completes

### Phase 3: Verification (immediately after)
- Check `db_identity_check.py` for telemetry event count
- Verify phase states (COMPLETE or FAILED)
- Look for T4 zero-yield diagnostics if events = 0

## Next Steps

### If Telemetry Collection Succeeds (≥5 events)
1. Run calibration job:
   ```bash
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
       python scripts/calibrate_token_estimator.py \
       --min-samples 5 \
       --confidence-threshold 0.7
   ```

2. Review outputs:
   - `token_estimator_calibration_YYYYMMDD_HHMMSS.md` - Human-readable report
   - `token_estimator_calibration_YYYYMMDD_HHMMSS.json` - Machine-readable patch

3. Apply coefficient updates manually if warranted

### If Telemetry Collection Fails (events = 0)
1. Check T4 zero-yield diagnostics in batch drain output
2. Verify `TELEMETRY_DB_ENABLED=1` was set correctly
3. Check for LLM boundary hits or early failures
4. Consider legacy DB analysis as fallback:
   ```bash
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
       python scripts/calibrate_token_estimator.py
   ```

## Lessons Learned

### Database Safety (T2 Importance)
- **Problem**: Scripts defaulting to `sqlite:///autopack.db` without explicit DATABASE_URL
- **Impact**: Auto-creation of empty databases, data loss (happened 3 times!)
- **Root Cause**: Each drain script starts its own embedded API server, causing database resets
- **Solution**: Always set `DATABASE_URL` explicitly + use simple `drain_one_phase.py` without external API
- **Guardrails**: T2 `check_empty_db_warning()` now prevents drain on empty DB

### Workflow Choice - REVISED
Following **Direct Drain Workflow** (simplified from unified guide):
1. ✅ Test single phase using `drain_one_phase.py --force` (WORKING - 1 event collected)
2. ⏳ Complete first phase drain (in progress)
3. Drain remaining 9 phases individually with same approach
4. Verify ≥5 telemetry events collected
5. Run calibration job

**Why this workflow**:
- No external API server conflicts (each drain manages its own)
- Simple, reliable, tested approach
- Explicit `TELEMETRY_DB_ENABLED=1` control
- No batch complexity until we have proven success

## References

- Unified Workflow Guide: `docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md`
- T1-T5 Handoff: `docs/guides/BUILD-139_T1-T5_HANDOFF.md`
- DB Identity Script: `scripts/db_identity_check.py`
- Calibration Job: `scripts/calibrate_token_estimator.py`

---

**Last Updated**: 2025-12-28T11:13:00Z
**Status**: Waiting for batch drain to complete (ETA: 30-120 min)
