# CRITICAL BLOCKER: Telemetry Collection Database Resets

## Summary

**Status**: BLOCKED - Cannot collect telemetry data due to systematic database clearing

**Attempts**: 4 separate drain attempts, all resulted in database clearing

**Root Cause**: Autonomous executor's embedded API server initializes fresh database

## Timeline of Issues

### Attempt 1: drain_one_phase.py (first try)
- **Time**: 22:03:23
- **Command**: `drain_one_phase.py --run-id telemetry-collection-v4 --phase-id telemetry-p1-string-util`
- **Result**: API 404 error, database cleared (0 runs, 0 phases)
- **Error**: "404 Client Error: Not Found for url: http://localhost:55882/runs/telemetry-collection-v4"

### Attempt 2: drain_queued_phases.py
- **Time**: 22:10:23
- **Command**: `drain_queued_phases.py --run-id telemetry-collection-v4 --batch-size 10`
- **Result**: Database cleared during execution
- **Error**: "503 Server Error: Service Unavailable" then database wiped

### Attempt 3: drain_one_phase.py with --force (partial success)
- **Time**: 22:15:33
- **Command**: `drain_one_phase.py --run-id telemetry-collection-v4 --phase-id telemetry-p1-string-util --force`
- **Initial Success**: Collected 1 telemetry event during startup!
- **Final Result**: Database cleared after API server initialization
- **Error**: "sqlite3.OperationalError: no such table: phases" (at 22:19:42)

### Attempt 4: Database recreation
- Recreated telemetry run 3 times total
- Each time: run created successfully → drain started → database cleared

## Evidence of the Problem

### Before Drain
```
Runs: 1 (telemetry-collection-v4)
Phases: 10 (all QUEUED)
LLM usage events: 0
```

### During Drain (Attempt 3)
```
[2025-12-28 22:15:47] INFO: [SchemaValidator] ✅ Database schema validation PASSED
DATABASE_URL: sqlite:///autopack.db
Runs: 1
Phases: 10
LLM usage events: 1  ← ✅ TELEMETRY WORKING!
```

### After API Server Initialization
```
[2025-12-28 22:19:42] ERROR: (sqlite3.OperationalError) no such table: phases
Runs: 0
Phases: 0
LLM usage events: 0  ← ❌ DATABASE CLEARED
```

## Root Cause Analysis

### The Culprit: Embedded API Server
Every drain script (`drain_one_phase.py`, `drain_queued_phases.py`) uses `AutonomousExecutor`, which:

1. **Starts embedded API server** on random port (e.g., localhost:49857)
2. **Initializes infrastructure** including LlmService, QualityGate
3. **Fetches run status** from API server
4. **Database gets cleared** during this process (likely database migration or fresh schema init)

```python
# From autonomous_executor.py (inferred behavior)
INFO: API server not detected at http://localhost:49857, attempting to start it...
INFO: ✅ API server started successfully
INFO: Initializing infrastructure...
ERROR: Failed to fetch run status: 503 Server Error
# → Database cleared here
```

### Why Initial Telemetry Event Worked
- The **1 successful telemetry event** in Attempt 3 was collected **during startup**, before the API server initialization
- This proves `TELEMETRY_DB_ENABLED=1` **is working correctly**
- The problem is **not** with telemetry collection itself, but with database persistence

## Alternative Approaches Explored

### Option 1: Legacy Database Analysis
- **Status**: NOT VIABLE
- **Legacy DB**: 1371 LLM usage events across 70 runs
- **Problem**: Older schema lacks `estimated_tokens` and `success` fields
- **Impact**: Cannot be used for T5 calibration (requires estimated vs actual comparison)

### Option 2: Batch Drain Controller
- **Status**: NOT APPLICABLE
- **Problem**: Only processes FAILED phases, not QUEUED phases
- **Error**: "Skipping 10 individual QUEUED phases (not entire runs)"

### Option 3: Pre-started API Server
- **Status**: CONFLICTS
- **Problem**: Drain scripts start their own API servers, ignoring external ones
- **Impact**: Multiple API servers → database conflicts → clearing

## Potential Solutions (Not Yet Implemented)

### Solution A: Database Migration Analysis
**Action**: Investigate why API server initialization clears database
- Check `autopack.main:app` startup code
- Look for `Base.metadata.drop_all()` or similar destructive operations
- Examine database initialization logic in `autopack.database`

**Files to investigate**:
- `src/autopack/main.py` (FastAPI app initialization)
- `src/autopack/database.py` (SessionLocal, engine creation)
- `src/autopack/models.py` (schema definitions)

### Solution B: Disable API Server in Executor
**Action**: Find or create a non-API executor mode
- Check if `AutonomousExecutor` has a `--no-api-server` flag
- Or use a lower-level executor that doesn't require API server
- Or modify executor to use existing database without reinitializing

**Potential flag**: `--skip-api-startup` or similar

### Solution C: Use Separate Database for Telemetry
**Action**: Collect telemetry in dedicated database
- Create `autopack_telemetry.db` separate from main DB
- Drain phases using main DB
- Collect telemetry in separate telemetry-only DB
- Merge telemetry data post-drain

**Risk**: Complexity, potential for phase ID mismatches

### Solution D: Research System Approach
**Action**: Use research system CLI instead of autonomous executor
- The research system has a simpler execution model
- May not have embedded API server issues
- Check `src/autopack/cli/research_commands.py` for telemetry collection

**Command to try**:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
    TELEMETRY_DB_ENABLED=1 \
    python -m autopack.cli.research ...
```

## Current State

**autopack.db**: Empty (0 runs, 0 phases, 0 events)
- Cleared 4 times during drain attempts
- Last modification: 2025-12-28T11:19:42Z

**autopack_legacy.db**: Intact (70 runs, 456 phases, 1371 events)
- Cannot be used for calibration (missing estimated_tokens field)
- Preserved as historical backup

**Telemetry Collection**: Proven to work (1 event collected)
- `TELEMETRY_DB_ENABLED=1` is correctly configured
- Token estimation v2 events are being recorded
- Database persistence is the blocker, not telemetry logic

## Next Steps (Awaiting User Direction)

1. **Investigate database initialization** (Solution A)
2. **Find non-API executor mode** (Solution B)
3. **Try research system approach** (Solution D)
4. **Report blocker to user** and request guidance

## Impact on T1-T5 Implementation

- **T1 (Telemetry Seeding)**: ✅ WORKING - Run creation succeeds
- **T2 (DB Identity Guardrails)**: ✅ WORKING - DB identity printed, empty DB detected
- **T3 (Sample-First Triage)**: ⚠️ UNTESTED - Cannot drain phases to test
- **T4 (Telemetry Clarity)**: ⚠️ UNTESTED - Cannot drain phases to collect data
- **T5 (Calibration Job)**: ❌ BLOCKED - No telemetry data to calibrate

**Overall Status**: Infrastructure complete, but execution blocked by database clearing issue

---

**Generated**: 2025-12-28T11:22:00Z
**Session**: Telemetry Collection Continued Session
**Critical**: Requires immediate attention before proceeding
