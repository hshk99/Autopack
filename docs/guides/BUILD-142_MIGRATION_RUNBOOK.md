# BUILD-142 Migration Runbook

**Purpose**: Upgrade existing telemetry databases to support BUILD-142 category-aware token budgeting

**Target Users**: Operators with pre-BUILD-142 telemetry data who need to add `actual_max_tokens` column

---

## What Changed in BUILD-142

BUILD-142 introduced **semantic separation** of token budget telemetry:

| Field | Meaning | When Recorded |
|-------|---------|---------------|
| `selected_budget` | Estimator **intent** (what the estimator recommended) | BEFORE P4 enforcement |
| `actual_max_tokens` | Final provider **ceiling** (what was sent to the API) | AFTER P4 enforcement |

**Why This Matters**:
- **Accurate waste calculation**: Use `actual_max_tokens / actual_output_tokens` instead of `selected_budget / actual_output_tokens`
- **Calibration correctness**: Waste measurements now reflect true API costs, not estimator intent
- **Provider parity**: OpenAI and Gemini clients now support category-aware budgets (docs/low = 4096 vs 8192)

---

## Prerequisites

Before running the migration:

1. **Backup your database** (highly recommended):
   ```bash
   # PowerShell
   Copy-Item "C:\dev\Autopack\telemetry_seed_v5.db" "C:\dev\Autopack\telemetry_seed_v5.db.backup"

   # Unix
   cp autopack.db autopack.db.backup
   ```

2. **Verify Python environment**:
   ```bash
   python --version  # Should be 3.8+
   ```

3. **Confirm database path** - You should know the exact path to your telemetry database.

---

## Migration Steps

### Step 1: Set Environment Variables

**PowerShell (Windows)**:
```powershell
$env:DATABASE_URL="sqlite:///C:/dev/Autopack/telemetry_seed_v5.db"
$env:PYTHONUTF8="1"
$env:PYTHONPATH="src"
```

**Bash (Unix/Linux)**:
```bash
export DATABASE_URL="sqlite:///autopack.db"
export PYTHONUTF8="1"
export PYTHONPATH="src"
```

**Important**: Replace the database path with your actual telemetry database location.

### Step 2: Run Migration Script

```bash
python scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py
```

**Expected Output**:
```
Initializing database...
Adding actual_max_tokens column to token_estimation_v2_events...
✅ Added actual_max_tokens column (nullable)
✅ Backfilled 1247 rows (copied selected_budget → actual_max_tokens)

✅ Migration complete!
   - actual_max_tokens column added
   - Existing rows backfilled from selected_budget
   - New telemetry will store both selected_budget (intent) and actual_max_tokens (ceiling)
```

**Notes**:
- Migration is **idempotent** - safe to run multiple times (will skip if column already exists)
- Backfill logic copies `selected_budget → actual_max_tokens` for historical data
- Historical data semantics preserved (pre-BUILD-142, `selected_budget` was the final value)

### Step 3: Verify Migration Success

**Option A: Quick Check (Python)**

```python
from autopack.database import SessionLocal, engine
from sqlalchemy import inspect

# Check column exists
inspector = inspect(engine)
columns = [col['name'] for col in inspector.get_columns('token_estimation_v2_events')]
print(f"Column exists: {'actual_max_tokens' in columns}")

# Check population rate
session = SessionLocal()
from sqlalchemy import text, func
from autopack.models import TokenEstimationV2Event

total_count = session.query(func.count(TokenEstimationV2Event.id)).scalar()
populated_count = session.query(func.count(TokenEstimationV2Event.id)).filter(
    TokenEstimationV2Event.actual_max_tokens.isnot(None)
).scalar()

population_rate = (populated_count / total_count * 100) if total_count > 0 else 0
print(f"Total events: {total_count}")
print(f"Populated: {populated_count} ({population_rate:.1f}%)")
session.close()
```

**Expected Output**:
```
Column exists: True
Total events: 1247
Populated: 1247 (100.0%)
```

**Option B: SQL Query (Direct)**

```bash
# PowerShell
sqlite3 "C:\dev\Autopack\telemetry_seed_v5.db" "SELECT COUNT(*) as total, COUNT(actual_max_tokens) as populated FROM token_estimation_v2_events;"

# Unix
sqlite3 autopack.db "SELECT COUNT(*) as total, COUNT(actual_max_tokens) as populated FROM token_estimation_v2_events;"
```

**Expected Output**:
```
total|populated
1247|1247
```

**Validation Criteria**:
- ✅ Column `actual_max_tokens` exists in schema
- ✅ Population rate = 100% (all rows have non-null `actual_max_tokens`)
- ✅ For pre-BUILD-142 data: `selected_budget == actual_max_tokens` (backfill correctness)

---

## Post-Migration Verification

### Check Sample Values

Verify that historical data was backfilled correctly:

```python
from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

session = SessionLocal()
samples = session.query(TokenEstimationV2Event).limit(5).all()

for event in samples:
    print(f"Phase: {event.phase_id}")
    print(f"  selected_budget: {event.selected_budget}")
    print(f"  actual_max_tokens: {event.actual_max_tokens}")
    print(f"  Match: {event.selected_budget == event.actual_max_tokens}")
    print()

session.close()
```

**Expected Output (Pre-BUILD-142 Data)**:
```
Phase: telemetry-p1-string-util
  selected_budget: 8192
  actual_max_tokens: 8192
  Match: True

Phase: telemetry-p2-test-generator
  selected_budget: 16384
  actual_max_tokens: 16384
  Match: True
```

**Note**: For **new telemetry** collected after BUILD-142, `selected_budget` and `actual_max_tokens` may differ due to:
- Category-aware budget floors (docs/low = 4096)
- P4 enforcement adjustments
- Provider-specific floor overrides

---

## Calibration Script Update

After migration, ensure you're using the **updated calibration script** that leverages `actual_max_tokens`:

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///C:/dev/Autopack/telemetry_seed_v5.db" \
    python scripts/calibrate_token_estimator.py \
    --min-samples 5 \
    --confidence-threshold 0.7
```

**Key Changes** (Automatic in updated script):
- Waste calculation now uses `actual_max_tokens / actual_output_tokens`
- Fallback to `selected_budget` for backward compatibility
- Coverage warning if <80% of samples have `actual_max_tokens` populated

**Example Output**:
```
Note: Waste = actual_max_tokens / actual_tokens (BUILD-142+)
      Fallback to selected_budget for pre-BUILD-142 telemetry
      Median waste >2x suggests over-budgeting

Telemetry coverage: actual_max_tokens populated in 1247/1247 samples (100.0%)
```

---

## Troubleshooting

### Issue: "Column already exists"

**Symptom**:
```
✅ actual_max_tokens column already exists, skipping migration
```

**Resolution**: Migration was already run. No action needed.

### Issue: "DATABASE_URL must be set explicitly"

**Symptom**:
```
ERROR: DATABASE_URL must be set explicitly.
```

**Resolution**: Set `DATABASE_URL` environment variable before running migration (see Step 1).

### Issue: Population rate <100%

**Symptom**:
```
Populated: 850/1247 (68.1%)
```

**Resolution**: Re-run migration script with backfill fix:
```bash
# Manual backfill (emergency)
sqlite3 "C:\dev\Autopack\telemetry_seed_v5.db" \
    "UPDATE token_estimation_v2_events SET actual_max_tokens = selected_budget WHERE actual_max_tokens IS NULL;"
```

### Issue: Migration fails with "table locked"

**Symptom**:
```
sqlite3.OperationalError: database is locked
```

**Resolution**:
1. Stop any running API servers or batch drain controllers
2. Close any database viewers (DB Browser, sqlite3 CLI)
3. Re-run migration script

---

## Rollback (If Needed)

SQLite **does not support `DROP COLUMN`**, so rollback requires recreating the table. Only use if migration caused data corruption:

```bash
# Restore from backup
Copy-Item "C:\dev\Autopack\telemetry_seed_v5.db.backup" "C:\dev\Autopack\telemetry_seed_v5.db" -Force
```

**Prevention**: Always back up before migration (see Prerequisites).

---

## Next Steps

After successful migration:

1. **Update telemetry workflow guide**: See [TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md](TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md) for BUILD-142 semantics

2. **Collect new telemetry**: Future telemetry runs will automatically populate both `selected_budget` and `actual_max_tokens` with correct semantics

3. **Run calibration**: Use updated calibration script to leverage accurate waste measurements

4. **Monitor coverage**: Check `actual_max_tokens` coverage in calibration output (should be >80% for reliable waste metrics)

---

## Summary

**What This Migration Does**:
- ✅ Adds `actual_max_tokens` column to `token_estimation_v2_events` table
- ✅ Backfills existing rows with `selected_budget` value (preserves historical semantics)
- ✅ Enables accurate waste calculation for future telemetry
- ✅ Supports BUILD-142 provider parity (Anthropic, OpenAI, Gemini)

**Migration Time**: <30 seconds for databases with <10K events

**Risk Level**: Low (idempotent, backfill preserves historical data, rollback via backup)

**Production Ready**: Yes (tested on telemetry_seed_v5.db with 1247 events)

---

For questions or issues, see [BUILD-142-PROVIDER-PARITY-REPORT.md](../BUILD-142-PROVIDER-PARITY-REPORT.md) for full implementation details.
