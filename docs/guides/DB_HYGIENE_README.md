# Database Hygiene & Telemetry Seeding - Quick Start

## TL;DR

This guide establishes **strict DB hygiene** for safe backlog draining and telemetry calibration.

**Key Files:**
- 📘 [DB_HYGIENE_AND_TELEMETRY_SEEDING.md](DB_HYGIENE_AND_TELEMETRY_SEEDING.md) - Complete runbook
- 📊 [DB_HYGIENE_IMPLEMENTATION_SUMMARY.md](DB_HYGIENE_IMPLEMENTATION_SUMMARY.md) - Implementation status
- 🔧 [scripts/telemetry_seed_quickstart.ps1](../../scripts/telemetry_seed_quickstart.ps1) - Automated seeding (Windows)
- 🔧 [scripts/telemetry_seed_quickstart.sh](../../scripts/telemetry_seed_quickstart.sh) - Automated seeding (Unix)

---

## Quick Start (Windows)

```powershell
# Automated workflow (recommended)
powershell -ExecutionPolicy Bypass -File scripts\telemetry_seed_quickstart.ps1
```

**Manual steps:**

```powershell
# 1. Create fresh telemetry seed DB
$env:PYTHONUTF8="1"; $env:PYTHONPATH="src"; $env:DATABASE_URL="sqlite:///autopack_telemetry_seed.db"
python -c "from autopack.database import init_db; init_db(); print('[OK] Schema initialized')"

# 2. Seed known-success run
python scripts\create_telemetry_collection_run.py

# 3. Check DB state
python scripts\db_identity_check.py

# 4. Start API server (in separate terminal)
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# 5. Drain phases (in original terminal)
$env:TELEMETRY_DB_ENABLED="1"
python scripts\batch_drain_controller.py --run-id telemetry-collection-v4 --batch-size 10 --api-url http://127.0.0.1:8000

# 6. Analyze results
python scripts\analyze_token_telemetry_v3.py --success-only
```

---

## Quick Start (Linux/Mac)

```bash
# Automated workflow (recommended)
bash scripts/telemetry_seed_quickstart.sh
```

**Manual steps:**

```bash
# 1. Create fresh telemetry seed DB
export PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db"
python -c "from autopack.database import init_db; init_db(); print('[OK] Schema initialized')"

# 2. Seed known-success run
python scripts/create_telemetry_collection_run.py

# 3. Check DB state
python scripts/db_identity_check.py

# 4. Start API server (in separate terminal)
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# 5. Drain phases (in original terminal)
export TELEMETRY_DB_ENABLED=1
python scripts/batch_drain_controller.py \
    --run-id telemetry-collection-v4 \
    --batch-size 10 \
    --api-url http://127.0.0.1:8000

# 6. Analyze results
python scripts/analyze_token_telemetry_v3.py --success-only
```

---

## Two-Database Strategy

### Telemetry Seed DB (`autopack_telemetry_seed.db`)
**Purpose:** Collect ≥20 `success=True` telemetry samples for calibration

**Characteristics:**
- Fresh, clean database
- Simple, achievable phases in `examples/telemetry_utils/`
- High success rate expected
- Representative mix: categories (impl/test/docs), complexity (low/med), deliverable counts (1-5)

**When to use:**
```powershell
$env:DATABASE_URL="sqlite:///autopack_telemetry_seed.db"
```

### Legacy Backlog DB (`autopack_legacy.db`)
**Purpose:** Drain real production failures (optional, secondary)

**Characteristics:**
- 70 runs, 456 phases (207 FAILED, 107 QUEUED, 141 COMPLETE)
- Real failure patterns and fingerprints
- Lower success rate expected
- Sample-first triage to avoid token waste

**When to use:**
```powershell
$env:DATABASE_URL="sqlite:///autopack_legacy.db"
```

---

## Critical Rules

1. **ALWAYS set `DATABASE_URL` explicitly** - never rely on defaults
2. **DO NOT add `*.db` files to git** - already in `.gitignore`
3. **DO NOT tune coefficients** without `success=True`, non-truncated samples
4. **Legacy backlog is optional** - telemetry seeding is primary goal

---

## Common Tasks

### Check DB Identity
```powershell
$env:DATABASE_URL="sqlite:///autopack_telemetry_seed.db"
python scripts\db_identity_check.py
```

### Seed Fresh Telemetry Run
```powershell
# Create DB
$env:DATABASE_URL="sqlite:///autopack_telemetry_seed.db"
python -c "from autopack.database import init_db; init_db(); print('[OK]')"

# Seed run
python scripts\create_telemetry_collection_run.py
```

### Drain Legacy Backlog (Sample-First)
```powershell
$env:DATABASE_URL="sqlite:///autopack_legacy.db"
$env:TELEMETRY_DB_ENABLED="1"
python scripts\batch_drain_controller.py --batch-size 10 --max-consecutive-zero-yield 5
```

### Analyze Telemetry
```powershell
$env:DATABASE_URL="sqlite:///autopack_telemetry_seed.db"
python scripts\analyze_token_telemetry_v3.py --success-only
```

---

## Expected Outcomes

### After Telemetry Seeding
- ✅ 1 run, 10 phases (most COMPLETE)
- ✅ ≥20 telemetry events (success=True)
- ✅ Representative distribution across categories/complexity/deliverable counts
- ✅ Low truncation rate (<10%)

### After Legacy Backlog Draining (Sample-First)
- ✅ Fingerprint clusters identified (repeating errors)
- ✅ Telemetry collected from successful drains
- ✅ Deprioritized runs with repeating failures (no token waste)
- ✅ Clear 0-yield reason classifications (once explainability is added)

---

## Troubleshooting

### "No telemetry events collected"
1. Was `TELEMETRY_DB_ENABLED=1` set?
2. Did phases reach the LLM boundary (Builder invoked)?
3. Check logs: `.autonomous_runs/batch_drain_sessions/*/logs/`

### "API server 404 errors"
1. Ensure `DATABASE_URL` is set **before** running drain script
2. Use `--api-url` flag or start API server manually
3. See [DB_HYGIENE_IMPLEMENTATION_SUMMARY.md](DB_HYGIENE_IMPLEMENTATION_SUMMARY.md#part-3-known-issue---api-server-db-inheritance)

### "High truncation rate"
- Filter out truncated samples during analysis: `--success-only` + check `truncated=False`
- Consider increasing token budgets in future runs (not for initial seeding)

---

## Implementation Status

- ✅ **DB identity guardrails** (script + docs)
- ✅ **Telemetry seeding runbook** (validated)
- ✅ **Sample-first triage** (already in batch drain)
- ⏳ **Telemetry explainability** (TODO: classify 0-yield reasons)
- ⏳ **Calibration proposal script** (TODO: safe coefficient recommendations)

See [DB_HYGIENE_IMPLEMENTATION_SUMMARY.md](DB_HYGIENE_IMPLEMENTATION_SUMMARY.md) for details.

---

## Files Created/Modified

### Created
- `scripts/db_identity_check.py` - Standalone DB checker
- `scripts/telemetry_seed_quickstart.ps1` - Windows automation
- `scripts/telemetry_seed_quickstart.sh` - Unix automation
- `docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md` - Complete runbook
- `docs/guides/DB_HYGIENE_IMPLEMENTATION_SUMMARY.md` - Status report
- `docs/guides/DB_HYGIENE_README.md` - This file

### Existing (Validated)
- `src/autopack/db_identity.py` - Identity banner + empty-DB warning
- `scripts/create_telemetry_collection_run.py` - Telemetry seeding
- `scripts/batch_drain_controller.py` - Sample-first triage

---

## Next Steps

1. **Run telemetry seeding** (use quickstart script)
2. **Validate ≥20 success samples** (check with `db_identity_check.py`)
3. **Analyze telemetry** (use `analyze_token_telemetry_v3.py`)
4. **Optional: Drain legacy backlog** (sample-first, token-safe)
5. **Future: Add telemetry explainability** (classify 0-yield reasons)
6. **Future: Calibration proposal** (safe coefficient recommendations)

---

## Support

- See [DB_HYGIENE_AND_TELEMETRY_SEEDING.md](DB_HYGIENE_AND_TELEMETRY_SEEDING.md) for detailed runbook
- See [DB_HYGIENE_IMPLEMENTATION_SUMMARY.md](DB_HYGIENE_IMPLEMENTATION_SUMMARY.md) for status and next steps
- Check existing telemetry scripts: `scripts/*telemetry*.py`
