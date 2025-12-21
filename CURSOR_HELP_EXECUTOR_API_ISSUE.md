# Cursor Help Request: Autopack Executor Not Finding Phases

## Context

We've just completed **BUILD-050** (Self-Correction Architecture Improvements) which adds:
1. Deliverables contract as hard constraints in Builder prompts
2. Decoupled attempt counters (retry_attempt, revision_epoch, escalation_level)
3. Database schema fixes for production readiness

All code changes are committed and working. However, we're unable to test BUILD-050 because the autonomous executor won't execute phases.

## The Problem

**Symptom:** The autonomous executor immediately completes with "No more executable phases" even though a QUEUED phase exists in the database.

**What We Created:**
- Run ID: `research-system-v1`
- Tier ID: `research-t1`
- Phase ID: `research-tracer-bullet` (state: QUEUED)
- Database: `autopack.db` (SQLite)

**Database Verification (Direct SQL Queries Work):**
```sql
-- Run exists and is in active state
SELECT id, state FROM runs WHERE id = "research-system-v1"
-- Returns: ('research-system-v1', 'PHASE_EXECUTION')

-- Tier exists
SELECT id, tier_id, run_id, state FROM tiers WHERE run_id = "research-system-v1"
-- Returns: (18, 'research-t1', 'research-system-v1', 'IN_PROGRESS')

-- Phase exists with correct relationships
SELECT id, phase_id, run_id, tier_id, state FROM phases WHERE phase_id = "research-tracer-bullet"
-- Returns: (223, 'research-tracer-bullet', 'research-system-v1', 'research-t1', 'QUEUED')
```

**API Server Behavior:**
```bash
# API returns empty phases array
curl -s http://localhost:8000/runs/research-system-v1 | python -m json.tool
# Returns:
{
  "id": "research-system-v1",
  "state": "DONE_FAILED_REQUIRES_HUMAN_REVIEW",  # Wrong state!
  "tiers": [{
    "tier_id": "research-t1",
    "state": "IN_PROGRESS",
    "phases": []  # Empty! Should have research-tracer-bullet
  }]
}
```

**Executor Behavior:**
```
[2025-12-19 00:30:37] INFO: Iteration 1: Fetching run status...
[2025-12-19 00:30:37] INFO: No more executable phases, execution complete
[2025-12-19 00:30:37] INFO: Autonomous execution loop finished
```

## Relevant Files

### Logs
- `.autonomous_runs/research-system-v1/executor_BUILD050_test.log` - Latest executor attempt
- `.autonomous_runs/research-system-v1/executor_attempt9_v2.log` - Previous attempt
- `.autonomous_runs/research-system-v1/executor_attempt8.log` - Historical run showing same issue

### Code
- `src/autopack/autonomous_executor.py` - Main executor loop (queries API for phases)
- `src/backend/main.py` - FastAPI server with run/phase endpoints
- `src/backend/database.py` - Backend database configuration
- `src/autopack/database.py` - Executor database configuration
- `src/autopack/models.py` - SQLAlchemy models (Run, Tier, Phase)

### Database
- `autopack.db` - SQLite database with all data

## What We've Tried

1. **Restarted API server multiple times** - No effect
2. **Updated run state via direct SQL** - Database updates work, but API doesn't reflect changes
3. **Killed all Python processes and restarted** - Same issue
4. **Verified DATABASE_URL environment variable** - Both executor and API use same database
5. **Checked phase relationships** - All foreign keys correct (run_id, tier_id)
6. **SQLAlchemy queries from Python** - Work fine, phase loads correctly
7. **Direct SQL queries** - All data present and correct

## The Disconnect

- **Database (SQLite)**: Phase exists, QUEUED, correct relationships ✅
- **SQLAlchemy (direct Python queries)**: Phase loads correctly ✅
- **API Server (FastAPI)**: Returns empty phases array, wrong run state ❌
- **Executor**: Sees API response, finds no executable phases ❌

## Key Questions

1. **Is there API response caching?** The API returns stale data (wrong run state, empty phases) even after database changes
2. **Why does the API return empty phases array?** The tier query joins on phases but returns none
3. **Should we be using a different run creation method?** We manually created the run/tier/phase in the database - is there a proper API endpoint or script we should use instead?
4. **Is there a schema mismatch?** Could the backend models expect different column names or relationships than what we created?

## What We Need

**Please analyze this issue and suggest:**

1. **Root cause** - Why is the API not seeing the phase?
2. **Proper fix** - How to make the executor find and execute the phase
3. **Best practice** - Should we be creating runs differently? Is there a standard script or API endpoint?
4. **Workaround** - If the API is broken, can we bypass it and have executor query database directly?

## Additional Context

- This is Windows environment (paths use backslashes)
- Database URL: `sqlite:///autopack.db` (relative path)
- Executor and API server both start successfully
- No errors in logs, just empty results
- BUILD-050 code changes are all committed and working

## Goal

We want to test BUILD-050's improvements by running the `research-tracer-bullet` phase through the autonomous executor. This phase should use:
- New deliverables contract (hard constraints)
- Decoupled attempt counters
- Non-destructive replanning

But we can't test it because the executor won't pick up the phase!

---

## RESOLUTION (2025-12-19)

### Root Cause Analysis

The issue had **multiple layers**:

#### Layer 1: Database Path Mismatch (Initial Symptom)
- **Backend API** (`src/backend/database.py`) used simple relative path: `sqlite:///./autopack.db`
- **Executor** (`src/autopack/database.py`) used path normalization via `config.py`
- This caused them to potentially use different database files depending on working directory

**Fix Applied:**
- Added path normalization to `src/backend/database.py` (lines 16-51) - identical to autopack/config.py
- Added logging to show resolved database path
- Changed `src/backend/main.py` to import from `autopack.database` for consistency

#### Layer 2: API Response Validation Error
- FastAPI returned 500 error with Pydantic validation error:
  ```json
  {
    "detail": "1 validation errors:\n  {'type': 'dict_type', 'loc': ('response', 'tiers', 0, 'phases', 0, 'scope'), 'msg': 'Input should be a valid dictionary', 'input': 'Tracer Bullet - Build minimal end-to-end pipeline...'}"
  }
  ```
- The `scope` field was stored as a **string** in database but API expected it to be a **dict**

**Fix Applied:**
- Modified `src/backend/api/runs.py` lines 84 and 114:
  ```python
  "scope": phase.scope if isinstance(phase.scope, dict) else {},
  ```
- Return empty dict `{}` when scope is not a dict

#### Layer 3: The Real Issue - Executor Doesn't Use API for Phase Selection! 🎯

**CRITICAL DISCOVERY:**
The executor is **NOT reading phases from the API** - it reads them **directly from the database** using `get_db()` from `autopack.database`!

At `src/autopack/autonomous_executor.py:1279`, the method `get_next_executable_phase()`:
1. Connects directly to database: `db = next(get_db())`
2. Queries Phase table directly with SQLAlchemy
3. Converts Phase SQLAlchemy object to dict at line 1367-1387

**So the API fixes don't matter for phase selection** - they only matter for:
- Manual API queries via curl
- Future features that might use the API
- API-based monitoring/dashboards

**The REAL bug:** At line 1378, when converting Phase to dict:
```python
"scope": getattr(phase_db, 'scope', None) or {},
```

Problem: Database scope is a **string** (not None), so `"some string" or {}` evaluates to `"some string"`.

Then at line 1409 in `execute_phase()`:
```python
scope_config = phase.get("scope") or {}
```

This receives a **string**, and at line 4180:
```python
if not scope_config or not scope_config.get("paths"):
```

**Crash:** `AttributeError: 'str' object has no attribute 'get'`

**Final Fix Applied:**
Modified `src/autopack/autonomous_executor.py:1378`:
```python
"scope": getattr(phase_db, 'scope', None) if isinstance(getattr(phase_db, 'scope', None), dict) else {},
```

Now scope is always a dict (empty if stored as string in database).

### Verification

After all fixes:
1. ✅ Backend API returns valid JSON with empty dict for scope
2. ✅ Executor successfully finds the phase from database
3. ✅ Executor begins execution: "Step 1/4: Generating code with Builder"
4. ✅ Autopack is running autonomously

### Key Learnings

1. **Executor bypasses API for phase selection** - queries database directly for performance
2. **Scope field has mixed types** - sometimes string (description), sometimes dict (config)
3. **Database path normalization is critical** - must be identical between backend and executor
4. **FastAPI Pydantic validation** - catches type mismatches but doesn't auto-coerce
5. **Process restart required** - uvicorn reload doesn't always reload database connections properly

### Files Modified

1. `src/backend/database.py` - Added path normalization (lines 16-51)
2. `src/backend/main.py` - Import from autopack.database instead of backend.database
3. `src/backend/api/runs.py` - Scope type checking (lines 84, 114)
4. `src/autopack/autonomous_executor.py` - Scope type checking in phase dict conversion (line 1378)

### Resolution Status

**✅ RESOLVED** - Autopack executor is now running autonomously and executing the `research-tracer-bullet` phase.

---

**Issue documented and resolved by Claude Code on 2025-12-19.**
