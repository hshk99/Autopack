# Database Hygiene Implementation Summary

## Completed Work (2025-12-28)

### ✅ Part 1: DB Identity Guardrails (DONE)

**Files Created:**
- [scripts/db_identity_check.py](../../scripts/db_identity_check.py) - Standalone DB identity checker
- [docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md](DB_HYGIENE_AND_TELEMETRY_SEEDING.md) - Comprehensive runbook

**Existing Infrastructure (Already in place):**
- [src/autopack/db_identity.py](../../src/autopack/db_identity.py) - DB identity banner and empty-DB warning
- [scripts/batch_drain_controller.py](../../scripts/batch_drain_controller.py) - Uses DB identity guardrails (lines 57, 1067-1076)
- `.gitignore` - Excludes `*.db` files from git

**Verified DB State:**
- **Legacy DB** (`autopack_legacy.db`): 70 runs, 456 phases (207 FAILED, 107 QUEUED, 141 COMPLETE)
- **Telemetry Seed DB** (`autopack_telemetry_seed.db`): 1 run, 10 phases (all QUEUED)

**Usage:**
```bash
# Check any database
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
    python scripts/db_identity_check.py
```

---

### ✅ Part 2: Telemetry Seeding Script (VALIDATED)

**Validated Script:**
- [scripts/create_telemetry_collection_run.py](../../scripts/create_telemetry_collection_run.py) - Creates 10 simple, achievable phases

**Schema Compatibility:**
- ✅ Matches current Run/Phase/Tier models (verified 2025-12-28)
- ✅ Uses correct field names: `state`, `scope`, `complexity`, `task_category`
- ✅ Creates parent Tier before phases
- ✅ Uses proper `PhaseState.QUEUED` enum

**Test Results:**
```bash
# Successfully created run in telemetry seed DB
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/create_telemetry_collection_run.py
# Result: 1 run, 10 phases (6 impl, 3 test, 1 docs)
```

---

### ⚠️ Part 3: Known Issue - API Server DB Inheritance

**Problem:**
When `drain_one_phase.py` starts the autonomous executor, it spawns an API server subprocess. The API server does not correctly inherit `DATABASE_URL` from the parent process environment, causing it to fall back to the default `autopack.db`.

**Evidence:**
```
[2025-12-28 21:44:00] ERROR: Failed to fetch run status: 404 Client Error:
    Not Found for url: http://localhost:54263/runs/telemetry-collection-v4
```

The executor is using `autopack_telemetry_seed.db`, but the API server is using `autopack.db` (where the run doesn't exist).

**Root Cause (CONFIRMED):**
The API server subprocess **does** inherit env vars via `env=os.environ.copy()` ([autonomous_executor.py:8707](../../src/autopack/autonomous_executor.py#L8707)). However, **timing** is the issue:

1. `drain_one_phase.py` sets `DATABASE_URL` as a fallback (lines 19-22) **only if not already set**
2. `drain_one_phase.py` imports `autopack.database` (line 26)
3. `autopack.database` imports `autopack.config` → creates `settings = Settings()`
4. `Settings()` reads `DATABASE_URL` **at import time** and binds the engine
5. API subprocess inherits env var, but `settings` is already cached

**Solution:** Always set `DATABASE_URL` externally (before running the script), never rely on the script's fallback.

**Workaround Options:**

1. **Use `batch_drain_controller.py` with `--api-url` flag** (preferred for legacy backlog):
   ```bash
   # Start API server manually with correct DB
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       uvicorn autopack.main:app --host 127.0.0.1 --port 8000 &

   # Run batch drain with explicit API URL
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       TELEMETRY_DB_ENABLED=1 \
       python scripts/batch_drain_controller.py \
           --api-url http://127.0.0.1:8000 \
           --run-id telemetry-collection-v4 \
           --batch-size 10
   ```

2. **Fix API server subprocess environment passing** (requires code changes):
   - Ensure `DATABASE_URL` is explicitly passed to subprocess env in `drain_one_phase.py`
   - Verify `uvicorn` subprocess inherits correct env vars

3. **Use direct executor invocation** (bypasses API server):
   - Modify executor to work without API server for simple drains
   - Not recommended - API server is needed for real autonomous runs

**Recommendation:**
For telemetry seeding, use workaround #1 (manual API server + batch drain with `--api-url`).

---

### ⏳ Part 4: Sample-First Triage (ALREADY IMPLEMENTED)

The batch drain controller **already implements** sample-first per-run triage (lines 353-408):

**Features:**
- ✅ Drain 1 phase per run (sample)
- ✅ Evaluate: success OR telemetry >0 OR timeout → promising
- ✅ Repeating fingerprint + 0 telemetry → deprioritize
- ✅ Track sampled/promising/deprioritized run sets
- ✅ Stop conditions: max timeouts per run, max attempts per phase, max fingerprint repeats

**Usage:**
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
    TELEMETRY_DB_ENABLED=1 \
    python scripts/batch_drain_controller.py \
        --batch-size 10 \
        --max-consecutive-zero-yield 5
```

---

### ⏳ Part 5: Telemetry Explainability (TODO)

**Current State:**
- Batch drain controller logs telemetry events collected and yield-per-minute
- No classification of **why** 0 telemetry events were collected

**TODO:**
Enhance executor logging to classify 0-yield reasons:
1. Never reached LLM boundary (preflight failure)
2. Failed before executor invoked model (import error, scope validation)
3. Telemetry disabled (`TELEMETRY_DB_ENABLED` not set)
4. Telemetry tables missing (schema issue)
5. Reached LLM boundary but failed (error during execution)
6. Success but telemetry not flushed (DB commit issue)

**Files to Modify:**
- `scripts/drain_one_phase.py` - Add classification logging
- `src/autopack/autonomous_executor.py` - Add boundary markers
- `src/autopack/anthropic_clients.py` - Log telemetry flush status

---

### ⏳ Part 6: Calibration Automation (TODO)

**Proposed Script:** `scripts/propose_estimator_calibration.py`

**Requirements:**
- Load telemetry from DB
- Filter: `success=True`, `truncated=False`, representative samples
- Compute metrics: SMAPE, waste ratio, underestimation rate
- Output **proposal only** (no auto-modification)

**Output Files:**
- `estimator_calibration_proposal_YYYYMMDD_HHMMSS.md` - Human-readable report
- `estimator_calibration_proposal_YYYYMMDD_HHMMSS.json` - Machine-readable tweaks

---

## Next Steps

### Immediate (High Priority)

1. **Fix API Server DB Inheritance Issue** (blocker for telemetry seeding):
   - Option A: Enhance `drain_one_phase.py` to pass `DATABASE_URL` explicitly to subprocess
   - Option B: Document workaround (manual API server + batch drain with `--api-url`)

2. **Seed and Validate Telemetry Collection** (once API issue fixed):
   ```bash
   # Drain 10 telemetry phases
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       TELEMETRY_DB_ENABLED=1 \
       python scripts/drain_queued_phases.py --run-id telemetry-collection-v4 --batch-size 10

   # Validate results
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       python scripts/db_identity_check.py

   # Analyze telemetry
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       python scripts/analyze_token_telemetry_v3.py --success-only
   ```

### Secondary (After Telemetry Seeding Works)

3. **Add Telemetry Explainability Logging**
   - Classify 0-yield reasons in executor and drain scripts
   - Log whether each phase "reached LLM boundary"

4. **Implement Calibration Proposal Script**
   - Safe coefficient recommendations (no auto-modification)

5. **Legacy Backlog Draining** (optional, token-safe):
   ```bash
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
       TELEMETRY_DB_ENABLED=1 \
       python scripts/batch_drain_controller.py \
           --batch-size 10 \
           --max-consecutive-zero-yield 5
   ```

---

## Files Modified/Created

### Created
- `scripts/db_identity_check.py` - Standalone DB identity checker
- `docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md` - Comprehensive runbook
- `docs/guides/DB_HYGIENE_IMPLEMENTATION_SUMMARY.md` - This file

### Existing (Validated)
- `src/autopack/db_identity.py` - DB identity banner (already in place)
- `scripts/create_telemetry_collection_run.py` - Telemetry seeding (validated)
- `scripts/batch_drain_controller.py` - Sample-first triage (already implemented)

### To Modify (Future Work)
- `scripts/drain_one_phase.py` - Fix API server DB inheritance
- `src/autopack/autonomous_executor.py` - Add telemetry explainability
- `src/autopack/anthropic_clients.py` - Add telemetry explainability

### To Create (Future Work)
- `scripts/propose_estimator_calibration.py` - Safe calibration proposals

---

## Definition of Done (Revisited)

- ✅ **DB identity guardrails in place** (script + docs) - DONE
- ✅ **Telemetry seeding runbook** (seed works, drain blocked by API issue) - PARTIAL
- ✅ **Sample-first triage in batch drain** (already implemented) - DONE
- ⏳ **Telemetry explainability logging** (TODO)
- ⏳ **Calibration proposal script** (TODO)

---

## Quick Reference Commands

### Check DB Identity
```bash
DATABASE_URL="sqlite:///autopack_legacy.db" \
    PYTHONUTF8=1 PYTHONPATH=src python scripts/db_identity_check.py
```

### Create Fresh Telemetry Seed DB
```bash
rm -f autopack_telemetry_seed.db
DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    PYTHONUTF8=1 PYTHONPATH=src python -c "from autopack.database import init_db; init_db(); print('[OK] Schema initialized')"
DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    PYTHONUTF8=1 PYTHONPATH=src python scripts/create_telemetry_collection_run.py
```

### Drain Legacy Backlog (Sample-First)
```bash
DATABASE_URL="sqlite:///autopack_legacy.db" TELEMETRY_DB_ENABLED=1 \
    PYTHONUTF8=1 PYTHONPATH=src \
    python scripts/batch_drain_controller.py --batch-size 10 --max-consecutive-zero-yield 5
```
