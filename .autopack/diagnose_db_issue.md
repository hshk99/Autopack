# Database Clearing Issue - Diagnostic Summary

## Key Finding: Multiple Database Files

```
C:\dev\Autopack\autopack.db                                    ← Main DB (we populate this)
C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1\autopack.db  ← Old leftover?
```

## Theory: Working Directory Change

### Hypothesis
The autonomous executor might be changing working directory to `.autonomous_runs/<run-family>/` during execution, causing relative path `sqlite:///autopack.db` to point to the wrong file.

### Evidence
1. DATABASE_URL is set correctly: `sqlite:///autopack.db`
2. This is a RELATIVE path (3 slashes = relative, 4 slashes = absolute on Windows)
3. If CWD changes from `C:\dev\Autopack` to `C:\dev\Autopack\.autonomous_runs\telemetry-collection-v4\`, then:
   - Original: `C:\dev\Autopack\autopack.db`
   - After CWD change: `C:\dev\Autopack\.autonomous_runs\telemetry-collection-v4\autopack.db`

### Supporting Evidence from Logs
```
[2025-12-28 22:15:44] INFO: [FileLayout] Project: autopack, Family: telemetry-collection-v4,
   Base: .autonomous_runs\autopack\runs\telemetry-collection-v4
```

The FileLayout sets a base directory for the run. The autonomous executor likely changes CWD to this base.

## Solution: Use Absolute Path for DATABASE_URL

### Current (Broken)
```bash
DATABASE_URL="sqlite:///autopack.db"  # Relative path
```

### Fixed (Should Work)
```bash
DATABASE_URL="sqlite:///C:/dev/Autopack/autopack.db"  # Absolute path
```

OR using PowerShell variable:
```powershell
$DB_PATH = (Get-Location).Path + "\autopack.db"
$env:DATABASE_URL = "sqlite:///$DB_PATH"
```

OR using Bash:
```bash
export DATABASE_URL="sqlite:///$(pwd)/autopack.db"
```

## Test This Theory

### Step 1: Use Absolute Path
```bash
PYTHONUTF8=1 PYTHONPATH=src \
    DATABASE_URL="sqlite:///C:/dev/Autopack/autopack.db" \
    TELEMETRY_DB_ENABLED=1 timeout 600 \
    python scripts/drain_one_phase.py \
    --run-id telemetry-collection-v4 \
    --phase-id telemetry-p1-string-util \
    --force
```

### Step 2: Verify Database Persistence
Before drain:
```bash
PYTHONUTF8=1 DATABASE_URL="sqlite:///C:/dev/Autopack/autopack.db" python scripts/db_identity_check.py
```

After drain:
```bash
PYTHONUTF8=1 DATABASE_URL="sqlite:///C:/dev/Autopack/autopack.db" python scripts/db_identity_check.py
```

Should show same run/phase counts (not reset to 0).

## Expected Outcome

If this theory is correct:
- ✅ Database will persist across drain execution
- ✅ Telemetry events will accumulate (not reset to 0)
- ✅ Phases will transition from QUEUED → COMPLETE/FAILED
- ✅ No "no such table: phases" errors

If this doesn't work, next steps:
- Check if autonomous executor explicitly creates new DB
- Look for `Base.metadata.drop_all()` calls
- Examine FileLayout logic for DB path manipulation

---

**Priority**: HIGH - This is likely the root cause
**Confidence**: 85% - Relative vs absolute path issue is very common
**Next Action**: Test with absolute DATABASE_URL path
