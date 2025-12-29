# Database Hygiene and Telemetry Seeding Guide

## Overview

This guide establishes **strict DB hygiene** to prevent silent DB confusion and enable **safe telemetry calibration**.

We maintain **two separate databases**:
1. **Legacy Backlog DB** (`autopack_legacy.db`) - for draining existing failed phases
2. **Telemetry Seed DB** (`autopack_telemetry_seed.db`) - for collecting known-success calibration samples

## Non-Negotiable Rules

1. **NEVER rely on implicit `DATABASE_URL` defaults** - always set it explicitly
2. **DO NOT re-add any DB files to git** - all `*.db` files are `.gitignore`d
3. **DO NOT tune token estimator coefficients** without `success=True`, non-truncated, representative samples
4. **Treat legacy backlog draining as optional and token-safe** (sample-first + stop conditions)

---

## Part 1: Database Identity Guardrails

### Check DB Identity

Always verify which database you're operating on:

```bash
# Check legacy backlog DB
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
    python scripts/db_identity_check.py

# Check telemetry seed DB
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/db_identity_check.py
```

This prints:
- DATABASE_URL
- SQLite file path, size, mtime
- Row counts: runs, phases, telemetry events
- Phase state breakdown (COMPLETE/FAILED/QUEUED/EXECUTING)
- Telemetry statistics (success rate, truncation rate, category/complexity breakdown)

### Safety: Empty DB Warning

The `db_identity` module prevents accidental operations on empty DBs:

```python
from autopack.db_identity import print_db_identity, check_empty_db_warning

session = SessionLocal()
print_db_identity(session)

# Fail if DB is empty (unless --allow-empty-db flag passed)
check_empty_db_warning(
    session,
    script_name="batch_drain_controller",
    allow_empty=args.allow_empty_db
)
```

Scripts that implement this guardrail:
- `scripts/batch_drain_controller.py`
- `scripts/detect_stale_queued.py`

### Current DB State (as of 2025-12-28)

**Legacy DB** (`autopack_legacy.db`):
- 70 runs, 456 phases
- 207 FAILED, 107 QUEUED, 141 COMPLETE
- Contains real production failures from autonomous builds

**Telemetry Seed DB** (`autopack_telemetry_seed.db`):
- To be created fresh
- Purpose: collect ≥20 `success=True` telemetry samples for calibration

---

## Part 2: Telemetry Seeding (Primary Objective)

### Goal

Collect **≥20 successful telemetry events** (`success=True`, non-truncated) with representative:
- Categories: implementation, tests, docs
- Complexity: low, medium, high
- Deliverable counts: 1 file, 2-5 files

### Strategy

Use **simple, achievable phases** in a safe sandbox directory (`examples/telemetry_utils/`).

### Step-by-Step Runbook

#### 1. Create Telemetry Seed DB

```bash
# Verify DB doesn't exist yet (or delete old one)
rm -f autopack_telemetry_seed.db

# Run migrations to create fresh schema
# IMPORTANT: DATABASE_URL must be set BEFORE importing autopack modules
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python -c "from autopack.database import init_db; init_db(); print('[OK] Schema initialized')"
```

#### 2. Seed Known-Success Run

```bash
# Create run with 10 simple, achievable phases
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/create_telemetry_collection_run.py
```

This creates run `telemetry-collection-v4` with:
- 6 implementation phases (3 low, 3 medium complexity)
- 3 test phases (1 low, 2 medium complexity)
- 1 docs phase (low complexity)
- All in `examples/telemetry_utils/` directory

#### 3. Verify Run Created

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/db_identity_check.py
```

Expected output:
- 1 run, 10 phases (all QUEUED)
- 0 telemetry events (not drained yet)

#### 4. Drain Phases to Collect Telemetry

```bash
# Drain all 10 phases in batch (with telemetry enabled)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    TELEMETRY_DB_ENABLED=1 \
    python scripts/drain_queued_phases.py --run-id telemetry-collection-v4 --batch-size 10
```

**CRITICAL:** `TELEMETRY_DB_ENABLED=1` must be set, or no telemetry will be collected.

#### 5. Validate Success Telemetry

```bash
# Check telemetry collection results
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/db_identity_check.py
```

Expected output:
- 10 phases (most COMPLETE, some may be FAILED)
- ≥20 telemetry events (at least 20 with success=True)
- Breakdown by category/complexity shows representation

#### 6. Export and Analyze Telemetry

```bash
# Export telemetry to CSV
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/export_token_estimation_telemetry.py

# Analyze with V3 analyzer (success-only mode)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/analyze_token_telemetry_v3.py --success-only
```

### Troubleshooting

**Q: No telemetry events collected?**

Check:
1. Was `TELEMETRY_DB_ENABLED=1` set when draining?
2. Did phases reach the "LLM boundary" (i.e., Builder was invoked)?
3. Check logs in `.autonomous_runs/batch_drain_sessions/*/logs/` for errors

**Q: All telemetry events have `success=False`?**

This means phases failed during execution. Check:
1. Are phases too complex or vague?
2. Are deliverables missing dependencies?
3. Re-seed with simpler phases

**Q: High truncation rate?**

This is OK for initial seeding - we filter out truncated samples during calibration.

---

## Part 3: Legacy Backlog Draining (Secondary, Optional)

### Pre-Drain Safety Checklist

1. **Verify operating on legacy DB:**
   ```bash
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
       python scripts/db_identity_check.py
   ```

2. **Check for stale QUEUED phases:**
   ```bash
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
       python scripts/detect_stale_queued.py --report-only
   ```

3. **Optional: Mark stale QUEUED as FAILED (if blocking):**
   ```bash
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
       python scripts/detect_stale_queued.py --mark-failed --stale-hours 48
   ```

### Drain with Sample-First Triage

```bash
# Drain 10 failed phases with sample-first triage and telemetry tracking
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
    TELEMETRY_DB_ENABLED=1 \
    python scripts/batch_drain_controller.py \
        --batch-size 10 \
        --phase-timeout-seconds 900 \
        --max-total-minutes 60 \
        --max-timeouts-per-run 2 \
        --max-attempts-per-phase 2 \
        --max-fingerprint-repeats 3 \
        --max-consecutive-zero-yield 5
```

**Key features:**
- **Sample-first triage**: Drains 1 phase per run, evaluates yield/fingerprint, then decides whether to continue
- **Strict stop conditions**: Prevents token waste on repeating failures
- **Telemetry tracking**: Reports events collected and yield-per-minute

### Drain Behavior

The batch drain controller implements **T3: Sample-first per-run triage**:

1. **Unsampled runs** (never drained before): drain 1 phase (sample)
2. **Evaluate sample**:
   - **Promising** (success, OR telemetry >0, OR timeout): continue draining
   - **Deprioritize** (repeating fingerprint + 0 telemetry): skip run
3. **Promising runs**: drain more phases with stop conditions

### Telemetry Explainability

For each drained phase, the controller logs:
- **Telemetry events collected** (delta before/after drain)
- **Yield per minute** (events/min)
- **If 0 telemetry**: reason classification needed (see Part 4)

---

## Part 4: Telemetry Explainability (TODO)

### Why 0 Telemetry Events?

When a phase produces 0 telemetry events, we need to classify the reason:

1. **Never reached LLM boundary** (failed preflight checks)
2. **Failed before executor invoked model** (e.g., import errors, scope validation)
3. **Telemetry disabled** (`TELEMETRY_DB_ENABLED` not set)
4. **Telemetry tables missing** (schema issue)
5. **Reached LLM boundary but failed** (error during execution)
6. **Success but telemetry not flushed** (DB commit issue)

**TODO:** Enhance `drain_one_phase.py` and `autonomous_executor.py` to log these classifications.

---

## Part 5: Calibration Automation (Safe Proposal Only)

### Goal

Once we have ≥20 `success=True` samples, compute recommended coefficient tweaks.

### Strategy

Create `scripts/propose_estimator_calibration.py`:
- Load telemetry from DB
- Filter: `success=True`, `truncated=False`, representative categories/complexity
- Compute metrics: SMAPE, waste ratio, underestimation rate
- Output **proposal** (report + JSON of recommended tweaks)
- **DO NOT auto-modify `token_estimator.py`** without explicit approval

### Usage (after telemetry seeding)

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/propose_estimator_calibration.py --min-samples 20
```

Output:
- Report: `estimator_calibration_proposal_YYYYMMDD_HHMMSS.md`
- JSON: `estimator_calibration_proposal_YYYYMMDD_HHMMSS.json`

**TODO:** Implement this script (not yet created).

---

## Quick Reference

### Check DB Identity
```bash
# Legacy backlog DB
DATABASE_URL="sqlite:///autopack_legacy.db" python scripts/db_identity_check.py

# Telemetry seed DB
DATABASE_URL="sqlite:///autopack_telemetry_seed.db" python scripts/db_identity_check.py
```

### Seed Telemetry Run
```bash
DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/create_telemetry_collection_run.py

DATABASE_URL="sqlite:///autopack_telemetry_seed.db" TELEMETRY_DB_ENABLED=1 \
    python scripts/drain_queued_phases.py --run-id telemetry-collection-v4 --batch-size 10
```

### Drain Legacy Backlog (Sample-First)
```bash
DATABASE_URL="sqlite:///autopack_legacy.db" TELEMETRY_DB_ENABLED=1 \
    python scripts/batch_drain_controller.py --batch-size 10 --max-consecutive-zero-yield 5
```

### Analyze Telemetry
```bash
DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    python scripts/analyze_token_telemetry_v3.py --success-only
```

---

## Definition of Done

✅ **DB identity guardrails in place** (script + docs)
✅ **Telemetry seeding runbook** (seed + drain + analyze)
⏳ **Sample-first triage in batch drain** (already implemented, needs telemetry explainability)
⏳ **Telemetry explainability logging** (TODO: classify 0-yield reasons)
⏳ **Calibration proposal script** (TODO: safe coefficient recommendations)
