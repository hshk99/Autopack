# Telemetry Probe Failure Analysis - BUILD-141 Part 7

## Executive Summary

**Status**: ❌ PROBE FAILED
**Root Cause**: Database Identity Drift (BUILD-141 resurfaces despite fixes)
**Failure Mode**: API server spawned by autonomous executor uses different database than intended
**Impact**: Cannot test telemetry collection fixes (T1-T6) until DB identity issue is fully resolved

---

## Probe Execution Timeline

### 1. Initial Probe Attempt (12:13 UTC)
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    TELEMETRY_DB_ENABLED=1 \
    python scripts/probe_telemetry_phase.py --run-id telemetry-collection-v4 --phase-id telemetry-p1-string-util
```

**Result**: 404 Not Found - `telemetry-collection-v4` run not found in API server database

**Evidence**:
- Probe script set `DATABASE_URL=sqlite:///autopack_telemetry_seed.db`
- API server spawned on port 52130
- Executor tried to fetch run: `GET /runs/telemetry-collection-v4` → 404
- API server was using `autopack.db` (0 runs) instead of `autopack_telemetry_seed.db` (1 run, 10 phases)

### 2. Manual API Server Restart (12:16-12:17 UTC)
Killed wrong API server (PID 732268) and started new one with explicit DATABASE_URL:

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    TELEMETRY_DB_ENABLED=1 \
    uvicorn autopack.main:app --host 0.0.0.0 --port 52130
```

**Problem Discovered**: `approval_requests` table missing from `autopack_telemetry_seed.db`
- Schema incomplete - needs full `init_db()` run
- API server started but cleanup task crashed

### 3. Seeding Database (12:45 UTC)
Database was empty! Run had to be created:

```bash
PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/create_telemetry_collection_run.py
```

**Result**: Created run with 1 run, 10 QUEUED phases, but still 0 LLM events

### 4. Second Probe Attempt (12:46 UTC)
**Result**: Still 404 Not Found, but with DIFFERENT random port (62652)

**Critical Discovery**:
- `drain_one_phase.py` → `AutonomousExecutor` → spawns NEW API server on random port
- That spawned server uses `autopack.db` (from default or healthcheck detection)
- Ignores parent process `DATABASE_URL` environment variable

**Evidence**:
```
INFO: API URL: http://localhost:62652  ← DIFFERENT PORT, NEW SERVER
ERROR: 404 Client Error: Not Found for url: http://localhost:62652/runs/telemetry-collection-v4
```

---

## Root Cause Analysis

### Problem: Multi-Layer Database Identity Drift

**Issue 1: API Server Spawning**
- `AutonomousExecutor.__init__()` spawns its own API server if not detected
- Uses `_pick_free_local_port()` to find random port
- Spawned server does NOT inherit parent's DATABASE_URL correctly (BUILD-141 supposedly fixed this)

**Issue 2: Missing `--api-url` Flag**
- `drain_one_phase.py` has no `--api-url` argument
- Cannot force executor to use manually-started API server
- Always spawns new server, always gets DB identity drift

**Issue 3: Incomplete Schema in Telemetry Seed DB**
- `autopack_telemetry_seed.db` missing `approval_requests` table
- Created by `create_telemetry_collection_run.py` with partial schema
- Needs full `init_db()` run to create ALL tables (not just runs/phases/llm_usage_events)

**Issue 4: BUILD-141 Fixes Not Applied to Spawned Servers?**
- BUILD-141 fixed:
  - `database.py`: runtime binding via `get_database_url()`
  - `main.py`: `load_dotenv(override=False)` to preserve parent env vars
  - `autonomous_executor.py`: `init_db()` instead of partial schema
- But spawned servers still using wrong DB?

---

## Evidence Trails

### DATABASE_URL Environment Variable
```
[drain_one_phase] DATABASE_URL: sqlite:///autopack_telemetry_seed.db  ← SET CORRECTLY
[PROBE] DATABASE_URL: sqlite:///autopack_telemetry_seed.db              ← CONFIRMED
```

### API Server Logs (Manual Start)
```
INFO: Uvicorn running on http://0.0.0.0:52130  ← Correct port
sqlalchemy.exc.OperationalError: no such table: approval_requests  ← Missing table
```

### Executor Behavior
```
INFO: API URL: http://localhost:62652  ← SPAWNED NEW SERVER (not 52130!)
ERROR: 404 Not Found for /runs/telemetry-collection-v4  ← WRONG DATABASE
```

### Database State Confirmation
```
# Telemetry seed DB (INTENDED):
Runs: 1
Phases: 10
LLM usage events: 0

# Autopack DB (WRONG, but used by spawned servers):
Runs: 0
Phases: 0
```

---

## Why BUILD-141 Fixes Didn't Work

### Hypothesis 1: Subprocess Environment Inheritance Failure
- `AutonomousExecutor` spawns API server as subprocess
- Subprocess may not inherit `DATABASE_URL` correctly (Windows?)
- Even though parent process logs show correct DATABASE_URL

### Hypothesis 2: API Server Detection Logic
- Executor checks if API server already running on expected port
- If not found, spawns new one
- New server uses default database discovery (finds `autopack.db` first)

### Hypothesis 3: load_dotenv() Override Still Happening
- `main.py` has `load_dotenv(override=False)` fix
- But spawned subprocess might be calling `load_dotenv()` from different code path?
- `.env` file may have `DATABASE_URL=sqlite:///autopack.db` (default)

---

## Verification Commands

### Check if .env overrides DATABASE_URL:
```bash
cat .env | grep DATABASE_URL
```

### Manually test API server with explicit DATABASE_URL:
```bash
# Kill any running servers
taskkill //F //PID <pid>

# Start with explicit DATABASE_URL
PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    TELEMETRY_DB_ENABLED=1 \
    uvicorn autopack.main:app --host 127.0.0.1 --port 52130

# In another terminal, test
curl http://localhost:52130/runs/telemetry-collection-v4
```

### Check AutonomousExecutor API spawn logic:
```bash
# Search for where API server is spawned
grep -r "spawn.*api\|uvicorn.*app" src/autopack/autonomous_executor.py
```

---

## Next Steps (Recommendations)

### Option A: Fix drain_one_phase.py to Use Manual API Server
1. Add `--api-url` argument to `drain_one_phase.py`
2. Pass to `AutonomousExecutor` constructor
3. Skip API server spawning if `--api-url` provided
4. Run probe with:
   ```bash
   # Terminal 1: Start API server manually
   PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       uvicorn autopack.main:app --host 127.0.0.1 --port 52130

   # Terminal 2: Run probe pointing to manual server
   PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       AUTOPACK_API_URL="http://localhost:52130" \
       python scripts/probe_telemetry_phase.py ...
   ```

### Option B: Fix Subprocess DATABASE_URL Inheritance
1. Investigate how `AutonomousExecutor` spawns API server subprocess
2. Ensure `DATABASE_URL` is explicitly passed to subprocess environment
3. Verify `load_dotenv(override=False)` is working in spawned process

### Option C: Use Existing API Server (Manual Workflow)
1. Start API server manually with correct DATABASE_URL
2. Modify `autonomous_executor.py` to detect running server more reliably
3. Skip spawning if server already detected

### Option D: Full Schema Initialization for Telemetry Seed DB
1. Run full `init_db()` on `autopack_telemetry_seed.db` to create ALL tables
2. Re-run `create_telemetry_collection_run.py`
3. Verify schema completeness with:
   ```bash
   sqlite3 autopack_telemetry_seed.db ".tables"
   ```

---

## Recommended Investigation for Other GPT

### Core Question
**How is `AutonomousExecutor` spawning the API server subprocess, and why is it not inheriting the parent's `DATABASE_URL` environment variable?**

### Files to Investigate
1. [src/autopack/autonomous_executor.py](../src/autopack/autonomous_executor.py) - Search for:
   - API server spawning logic
   - Subprocess creation
   - Environment variable passing
   - `_pick_free_local_port()` usage

2. [src/autopack/main.py](../src/autopack/main.py) - Verify:
   - `load_dotenv(override=False)` is present and correct
   - Database initialization at startup
   - `get_database_url()` usage

3. [.env](./.env) - Check:
   - Default `DATABASE_URL` setting
   - Whether it overrides environment variable

### Key Evidence to Collect
1. **Subprocess spawn code**: How does executor start API server?
2. **Environment variable inheritance**: Is `DATABASE_URL` explicitly passed?
3. **Database URL resolution**: What order does `get_database_url()` check sources?

---

## Impact Assessment

### Immediate Impact
- ❌ Cannot test T1 prompt fixes (directory prefix, deliverables contract)
- ❌ Cannot test T2 retry logic (empty files array)
- ❌ Cannot collect telemetry samples for calibration
- ❌ Probe script unusable (always gets DB identity drift)

### Systemic Impact
- ❌ BUILD-141 fixes may be incomplete or not working as intended
- ❌ Database identity drift still happens in subprocess scenarios
- ❌ Any autonomous execution that spawns API server will have this issue
- ❌ Batch drain controller likely affected (if it spawns executors)

---

## Success Criteria for Resolution

1. **Probe runs successfully**:
   - Phase found in API server database
   - Executor completes phase execution
   - Telemetry events collected (token_estimation_v2_events > 0)

2. **Database identity maintained**:
   - Parent process, spawned executor, and API server all use same database
   - No 404 errors from run/phase lookups

3. **Schema completeness**:
   - `autopack_telemetry_seed.db` has all tables (runs, phases, tiers, llm_usage_events, token_estimation_v2_events, approval_requests, etc.)

---

## Appendix: Full Probe Output

### First Attempt (12:13 UTC)
```
[PROBE] Phase: telemetry-p1-string-util
[PROBE] DATABASE_URL: sqlite:///autopack_telemetry_seed.db
[PROBE] TELEMETRY_DB_ENABLED: 1

INFO: API URL: http://localhost:52130
ERROR: Failed to fetch run status: 404 Client Error: Not Found for url: http://localhost:52130/runs/telemetry-collection-v4

[PROBE] Drain exit code: 1
[PROBE] DB telemetry rows (after):
[PROBE]   - token_estimation_v2_events: 0 (NO INCREASE ❌)
[PROBE]   - llm_usage_events: 0 (NO INCREASE ❌)
```

### Second Attempt (12:46 UTC)
```
[PROBE] Phase: telemetry-p1-string-util
[PROBE] DATABASE_URL: sqlite:///autopack_telemetry_seed.db
[PROBE] TELEMETRY_DB_ENABLED: 1

INFO: API URL: http://localhost:62652  ← DIFFERENT PORT!
ERROR: Failed to fetch run status: 404 Client Error: Not Found for url: http://localhost:62652/runs/telemetry-collection-v4

[PROBE] Drain exit code: 1
[PROBE] DB telemetry rows (after):
[PROBE]   - token_estimation_v2_events: 0 (NO INCREASE ❌)
[PROBE]   - llm_usage_events: 0 (NO INCREASE ❌)
```

---

**Generated**: 2025-12-29T12:50:00Z
**Session**: BUILD-141 Part 7 Telemetry Unblock
**Status**: PROBE FAILED - Requires deeper DB identity investigation
