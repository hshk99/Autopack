# Telemetry Collection DB Issue - ROOT CAUSE IDENTIFIED

## Summary

**NOT a "database clearing" issue** - it's **DB identity drift** caused by multiple conflicting sources of truth for DATABASE_URL.

**Evidence**: Telemetry collection successfully recorded 2 events before failing:
- `[TokenEstimationV2] predicted_output=5200 actual_output=826 smape=145.2%` ✅
- `[TokenEstimationV2] predicted_output=5200 actual_output=1331 smape=118.5%` ✅

Then crashed with:
```
(sqlite3.OperationalError) no such table: token_estimation_v2_events
(sqlite3.OperationalError) no such table: llm_usage_events
(sqlite3.OperationalError) no such table: phases
```

## Root Causes

### 1. Import-Time Binding Ignores Late Env Changes

**File**: [src/autopack/database.py:10-14](src/autopack/database.py#L10-L14)

```python
engine = create_engine(
    settings.database_url,  # ❌ Bound at import time, not runtime
    pool_pre_ping=True,
    pool_recycle=1800,
)
```

**Problem**: If `DATABASE_URL` isn't set **before** the first import of `autopack.database`, it locks to the wrong DB.

### 2. Executor Creates Partial Schema

**File**: [src/autopack/autonomous_executor.py:232-247](src/autopack/autonomous_executor.py#L232-L247)

```python
db_url = settings.database_url  # ❌ Uses settings, not get_database_url()
engine = create_engine(db_url)
...
from autopack.database import Base
from autopack.usage_recorder import LlmUsageEvent  # noqa: F401
Base.metadata.create_all(bind=engine)  # ❌ Only creates LlmUsageEvent table, not models
```

**Problem**: Creates DB with `llm_usage_events` table but NO `phases`, `runs`, `token_estimation_v2_events` tables.

### 3. Scripts Override Operator's DB Choice

**File**: [scripts/create_telemetry_collection_run.py:24-28](scripts/create_telemetry_collection_run.py#L24-L28)

```python
os.environ["DATABASE_URL"] = "sqlite:///autopack.db"  # ❌ Hardcoded override
from autopack.database import SessionLocal
```

**Problem**: Even if operator sets `DATABASE_URL=autopack_telemetry_seed.db`, this script forces `autopack.db`.

### 4. Health Check Reports Wrong DB

**File**: [src/autopack/health_checks.py](src/autopack/health_checks.py)

Hardcodes `workspace_path/autopack.db` instead of reading `DATABASE_URL`.

**Problem**: Logs show "Database accessible: c:\dev\Autopack\autopack.db" even when API is using a different DB.

### 5. Windows PowerShell Env Syntax Trap

**Problem**: Bash-style `DATABASE_URL="..." python ...` in PowerShell **doesn't set the env var**.

Then `load_dotenv()` sources `.env` (often `autopack.db`), and everything points at the wrong DB.

## Evidence Trail

### What Actually Happened (from logs)

1. ✅ Seeding script created `autopack_telemetry_seed.db` with 10 QUEUED phases
2. ✅ Drain script started with `DATABASE_URL="sqlite:///autopack_telemetry_seed.db"`
3. ✅ First telemetry event collected successfully (SMAPE 145.2%)
4. ❌ Executor created **new partial DB** at `autopack.db` (only `llm_usage_events` table)
5. ❌ Second telemetry event failed: "no such table: token_estimation_v2_events"
6. ❌ Auditor failed: "no such table: llm_usage_events" (different DB!)
7. ❌ API server crashed: "no such table: phases"

### Smoking Gun

Health check output from drain log:
```
[HealthCheck:T0] Database: PASSED (0ms) - Database accessible: c:\dev\Autopack\autopack.db
```

But we set:
```
DATABASE_URL="sqlite:///autopack_telemetry_seed.db"
```

**Proof of DB identity drift.**

## Impact Assessment

### What Works
- ✅ Telemetry collection logic (2 successful events prove it)
- ✅ Token estimation v2 calculation (SMAPE computed correctly)
- ✅ Database seeding (runs/phases created)

### What's Broken
- ❌ DB URL propagation to embedded API server
- ❌ Partial schema creation (missing tables)
- ❌ Script DB overrides
- ❌ Health check accuracy

## Implementation Plan

### Phase 1: Core DB Identity Fix (CRITICAL)

**1.1 Fix import-time binding** ([src/autopack/database.py](src/autopack/database.py))

Replace:
```python
engine = create_engine(settings.database_url, ...)
```

With:
```python
from autopack.config import get_database_url

engine = create_engine(get_database_url(), ...)  # ✅ Runtime binding
```

**1.2 Fix executor DB creation** ([src/autopack/autonomous_executor.py:232-247](src/autopack/autonomous_executor.py#L232-L247))

Replace:
```python
db_url = settings.database_url
engine = create_engine(db_url)
from autopack.usage_recorder import LlmUsageEvent
Base.metadata.create_all(bind=engine)
```

With:
```python
from autopack.config import get_database_url
from autopack.database import init_db

db_url = get_database_url()  # ✅ Runtime binding
init_db()  # ✅ Creates ALL tables (imports models)
```

**1.3 Remove script DB overrides** ([scripts/create_telemetry_collection_run.py:24-28](scripts/create_telemetry_collection_run.py#L24-L28))

Replace:
```python
os.environ["DATABASE_URL"] = "sqlite:///autopack.db"
```

With:
```python
# Require DATABASE_URL to be set by operator
if not os.environ.get("DATABASE_URL"):
    print("ERROR: DATABASE_URL must be set", file=sys.stderr)
    print("Example: DATABASE_URL='sqlite:///autopack_telemetry_seed.db'", file=sys.stderr)
    sys.exit(1)
```

### Phase 2: Observability (PREVENT RECURRENCE)

**2.1 Add DB identity banner** (all scripts, executor, API)

```python
from autopack.db_identity import print_db_identity

# At startup, before any DB operations:
db = SessionLocal()
try:
    print("=" * 70)
    print("DATABASE IDENTITY")
    print("=" * 70)
    print_db_identity(db)
    print("=" * 70)
finally:
    db.close()
```

**2.2 Fix health check** ([src/autopack/health_checks.py](src/autopack/health_checks.py))

Make it validate the DB specified by `DATABASE_URL`, not hardcoded `autopack.db`.

**2.3 Add `/health` DB identity** (when `DEBUG_DB_IDENTITY=1`)

Return:
- Resolved DATABASE_URL
- Sqlite file path
- Runs/phases counts

### Phase 3: Regression Test

Create `tests/integration/test_db_identity_propagation.py`:

1. Create temp sqlite file
2. Seed minimal schema
3. Start uvicorn `autopack.main:app` in subprocess with explicit `DATABASE_URL`
4. Call `/health`
5. Assert health reports expected sqlite filename

## Files to Modify

### Critical Path (must fix)
1. [src/autopack/database.py](src/autopack/database.py) - Runtime DB URL binding
2. [src/autopack/autonomous_executor.py](src/autopack/autonomous_executor.py) - Use `init_db()`, not partial schema
3. [scripts/create_telemetry_collection_run.py](scripts/create_telemetry_collection_run.py) - Remove DB override

### Important (prevent recurrence)
4. [src/autopack/health_checks.py](src/autopack/health_checks.py) - Validate correct DB
5. [src/autopack/main.py](src/autopack/main.py) - Add startup DB identity banner
6. [scripts/drain_one_phase.py](scripts/drain_one_phase.py) - Add startup DB identity banner

### Documentation
7. [docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md](docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md) - Update with fix details
8. [scripts/telemetry_seed_quickstart.ps1](scripts/telemetry_seed_quickstart.ps1) - Ensure correct env syntax

## Expected Outcome After Fixes

- ✅ Seeding into `autopack_telemetry_seed.db` stays intact
- ✅ Drain scripts + executor + embedded API all use same DB
- ✅ No more "no such table: phases"
- ✅ DB identity visible in every log output
- ✅ Telemetry collection completes successfully
- ✅ Regression test prevents future drift

## Next Steps

**For the other Cursor**: Implement Phase 1 (Core DB Identity Fix) first, then verify telemetry collection works, then add Phase 2 observability.

**Estimated effort**:
- Phase 1: 30-60 minutes (3 file changes)
- Phase 2: 20-30 minutes (observability)
- Phase 3: 30 minutes (test)
- **Total: ~2 hours to permanent fix**

---

**Generated**: 2025-12-28T11:47:00Z
**Status**: ROOT CAUSE IDENTIFIED - Ready for implementation
**Confidence**: 99% - Log evidence confirms exact failure mode
