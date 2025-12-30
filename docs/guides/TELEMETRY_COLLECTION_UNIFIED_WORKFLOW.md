# Telemetry Collection - Unified Workflow Guide

**Purpose**: Collect token usage telemetry for calibrating token estimation coefficients

**Combines**: BUILD-139 T1-T5 framework + DB Hygiene quickstart workflow

---

## Quick Start (Recommended)

### Windows (Automated via PowerShell)

```powershell
# Option 1: Run full automated workflow
powershell -ExecutionPolicy Bypass -File scripts\telemetry_seed_quickstart.ps1

# Option 2: Manual steps (more control)
$env:DATABASE_URL="sqlite:///autopack.db"
$env:PYTHONUTF8="1"
$env:PYTHONPATH="src"
$env:TELEMETRY_DB_ENABLED="1"

# Verify DB state
python scripts\db_identity_check.py

# Start API server (separate terminal)
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Drain phases (main terminal)
python scripts\batch_drain_controller.py `
    --run-id telemetry-collection-v4 `
    --batch-size 10 `
    --api-url http://127.0.0.1:8000
```

### Unix/Linux (Automated via Bash)

```bash
# Option 1: Run full automated workflow
bash scripts/telemetry_seed_quickstart.sh

# Option 2: Manual steps (more control)
export DATABASE_URL="sqlite:///autopack.db"
export PYTHONUTF8="1"
export PYTHONPATH="src"
export TELEMETRY_DB_ENABLED="1"

# Verify DB state
python scripts/db_identity_check.py

# Start API server (separate terminal)
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Drain phases (main terminal)
python scripts/batch_drain_controller.py \
    --run-id telemetry-collection-v4 \
    --batch-size 10 \
    --api-url http://127.0.0.1:8000
```

---

## Workflow Comparison

### BUILD-139 Approach (Direct Drain)
**Best for**: Quick single-phase testing, debugging
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
    TELEMETRY_DB_ENABLED=1 timeout 600 \
    python scripts/drain_one_phase.py \
    --run-id telemetry-collection-v4 \
    --phase-id telemetry-p1-string-util \
    --force
```

**Pros**:
- ✅ No API server needed
- ✅ Direct subprocess execution
- ✅ Simpler for debugging single phases

**Cons**:
- ⚠️ Must specify `--force` flag (run has multiple QUEUED phases)
- ⚠️ Manual per-phase execution for full run

### DB Hygiene Approach (API-Based Batch Drain)
**Best for**: Full run processing, production workflows
```bash
# Terminal 1: API server
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Batch drain
python scripts/batch_drain_controller.py \
    --run-id telemetry-collection-v4 \
    --batch-size 10 \
    --api-url http://127.0.0.1:8000
```

**Pros**:
- ✅ Processes all phases automatically
- ✅ Sample-first triage active (T3)
- ✅ LLM boundary detection (T4)
- ✅ Zero-yield diagnostics (T4)
- ✅ Batch session tracking

**Cons**:
- ⚠️ Requires API server running
- ⚠️ DATABASE_URL must be set before importing autopack (import-time binding issue)

---

## Recommended Workflow (Hybrid)

### Phase 1: Test Single Phase (Validate Setup)

```bash
# Windows
$env:DATABASE_URL="sqlite:///autopack.db"
$env:PYTHONUTF8="1"
$env:PYTHONPATH="src"
$env:TELEMETRY_DB_ENABLED="1"

python scripts\drain_one_phase.py `
    --run-id telemetry-collection-v4 `
    --phase-id telemetry-p1-string-util `
    --force

# Unix/Linux
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
    TELEMETRY_DB_ENABLED=1 timeout 600 \
    python scripts/drain_one_phase.py \
    --run-id telemetry-collection-v4 \
    --phase-id telemetry-p1-string-util \
    --force
```

**Verify**:
```bash
python scripts/db_identity_check.py
```
- Check "LLM usage events" > 0
- Verify phase state changed from QUEUED → COMPLETE or FAILED

### Phase 2: Batch Drain Remaining Phases

```bash
# Terminal 1: Start API server
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Batch drain
python scripts/batch_drain_controller.py \
    --run-id telemetry-collection-v4 \
    --batch-size 9 \
    --api-url http://127.0.0.1:8000 \
    --max-consecutive-zero-yield 10
```

**Benefits**:
- ✅ Single phase validates TELEMETRY_DB_ENABLED works
- ✅ Batch drain processes remaining efficiently
- ✅ Sample-first triage prevents token waste
- ✅ Clear diagnostics on zero-yield phases

### Phase 3: Analyze Telemetry

**Option A: BUILD-139 Calibration (Recommended)**
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
    python scripts/calibrate_token_estimator.py \
    --min-samples 5 \
    --confidence-threshold 0.7
```

**Output**:
- `token_estimator_calibration_YYYYMMDD_HHMMSS.md` - Human-readable report
- `token_estimator_calibration_YYYYMMDD_HHMMSS.json` - Machine-readable patch

**Option B: V3 Analyzer (Legacy)**
```bash
python scripts/analyze_token_telemetry_v3.py \
    --log-dir .autonomous_runs \
    --success-only \
    --stratify \
    --under-multiplier 1.1 \
    --output reports/telemetry_success_stratified.md
```

**Comparison**:
| Feature | calibrate_token_estimator.py (T5) | analyze_token_telemetry_v3.py |
|---------|-----------------------------------|-------------------------------|
| Data Source | Database (llm_usage_events) | Log files (.autonomous_runs) |
| Filtering | success=True AND truncated=False | --success-only flag |
| Grouping | category + complexity | category + complexity + deliverable-count |
| Confidence | Sample count + variance | N/A |
| Output | Markdown + JSON patch | Markdown only |
| Safety | Gated, no auto-edit | Manual coefficient tuning |

**Recommendation**: Use `calibrate_token_estimator.py` (T5) for database-driven calibration with confidence scoring.

---

## Environment Variables Reference

### Required
- `DATABASE_URL` - Database connection string (e.g., `sqlite:///autopack.db`)
- `PYTHONUTF8=1` - Enable UTF-8 encoding (Windows)
- `PYTHONPATH=src` - Python module path
- `TELEMETRY_DB_ENABLED=1` - **CRITICAL** for telemetry collection

### Optional
- `AUTOPACK_API_URL` - API server URL (for batch drain with API)

---

## Token Budget Semantics (BUILD-142)

### Budget Terminology

Post-BUILD-142, the system maintains **two separate values** to distinguish estimator intent from final API ceiling:

| Field | Meaning | When Recorded | Usage |
|-------|---------|---------------|-------|
| **selected_budget** | Estimator **intent** | BEFORE P4 enforcement | Understanding estimator behavior |
| **actual_max_tokens** | Final provider **ceiling** | AFTER P4 enforcement | Waste calculation, API cost analysis |

**Waste Calculation**: Always use `actual_max_tokens / actual_output_tokens` (not `selected_budget / actual_output_tokens`) for accurate API cost measurement.

### Category-Aware Base Budgets

BUILD-142 introduced category-aware base budget floors to reduce token waste for documentation and testing phases:

| Category | Complexity | Base Budget | Rationale |
|----------|-----------|-------------|-----------|
| **docs** (all variants) | low | 4096 | Concise documentation rarely needs >4K output |
| **tests** | low | 6144 | Test generation typically moderate complexity |
| **implementation** | low | 8192 | Code changes require more context |
| All other categories | any | 8192 | Default floor maintained |

**Provider Coverage**: These floors apply across **Anthropic**, **OpenAI**, and **Gemini** clients (BUILD-142 provider parity).

**Docs Variants**: The category-aware logic recognizes `docs`, `documentation`, `doc_synthesis`, `doc_sot_update` as docs-like categories.

### Verification Snippet

After running telemetry collection with BUILD-142, verify that docs/low budgets are hitting the expected 4096 floor:

```python
# Python verification
from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

session = SessionLocal()
docs_low_events = session.query(TokenEstimationV2Event).filter(
    TokenEstimationV2Event.category.in_(["docs", "documentation", "doc_synthesis", "doc_sot_update"]),
    TokenEstimationV2Event.complexity == "low"
).all()

for event in docs_low_events[:5]:  # Show first 5 samples
    print(f"{event.phase_id}: selected_budget={event.selected_budget}, actual_max_tokens={event.actual_max_tokens}")

session.close()
```

**Expected Output**: `selected_budget` values around 4096-5000 for docs/low phases (vs. 8192+ pre-BUILD-142).

### Migration Notes

If you have existing telemetry data from **before BUILD-142**, run the migration to add the `actual_max_tokens` column:

```bash
# PowerShell
$env:DATABASE_URL="sqlite:///C:/dev/Autopack/telemetry_seed_v5.db"
python scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py

# Unix
DATABASE_URL="sqlite:///autopack.db" python scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py
```

See [BUILD-142 Migration Runbook](BUILD-142_MIGRATION_RUNBOOK.md) for detailed migration instructions and verification steps.

---

## Telemetry Collection Targets

### Minimum Viable
- **5 successful phases** - Minimum for calibration (min-samples=5)
- **1 category/complexity group** - At least one group with ≥5 samples

### Production Ready
- **20 successful phases** - Recommended for robust calibration
- **3+ category/complexity groups** - Diverse sample coverage

### Optimal
- **50+ successful phases** - High-confidence coefficient updates
- **5+ groups** - Comprehensive category/complexity coverage

---

## Troubleshooting

### Issue: "LLM usage events: 0" after draining phase
**Cause**: `TELEMETRY_DB_ENABLED=1` not set
**Fix**:
```bash
# Verify environment variable before draining
echo $TELEMETRY_DB_ENABLED  # Unix
echo %TELEMETRY_DB_ENABLED%  # Windows CMD
echo $env:TELEMETRY_DB_ENABLED  # PowerShell
```

### Issue: "Refusing to drain non-exclusively"
**Cause**: Run has multiple QUEUED phases, drain_one_phase.py requires exclusive execution
**Fix**: Add `--force` flag
```bash
python scripts/drain_one_phase.py ... --force
```

### Issue: API server not connecting (batch drain)
**Cause**: DATABASE_URL not set before importing autopack
**Fix**: Set DATABASE_URL in same terminal session BEFORE starting API server
```bash
# Windows
$env:DATABASE_URL="sqlite:///autopack.db"
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Unix
export DATABASE_URL="sqlite:///autopack.db"
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000
```

### Issue: Calibration says "No high-confidence groups"
**Cause**: Insufficient samples or high variance
**Fix**:
1. Collect more successful phases (target: ≥10 per group)
2. Lower `--confidence-threshold 0.5`
3. Check for systematic failures (use T4 zero-yield diagnostics)

---

## Success Metrics

### Collection Phase
- [x] ≥5 phases COMPLETE (minimum viable)
- [x] ≥20 phases COMPLETE (production ready)
- [x] LLM usage events > 0 (telemetry enabled)
- [x] success=True events ≥ 50% (phases completing successfully)

### Analysis Phase
- [x] Calibration finds ≥1 high-confidence group
- [x] Median ratios within 0.8-1.5x (reasonable estimation)
- [x] Confidence scores ≥ 0.7 (statistically significant)

### Coefficient Update Phase
- [x] Markdown report reviewed
- [x] JSON patch validated
- [x] Changes tested in isolated environment
- [x] Committed with clear justification

---

## Next Steps After Calibration

### 1. Review Calibration Output
```bash
# Read markdown report
cat token_estimator_calibration_YYYYMMDD_HHMMSS.md

# Check JSON patch
cat token_estimator_calibration_YYYYMMDD_HHMMSS.json
```

### 2. Validate Proposed Changes
- Check median ratios (1.2+ = underestimating, 0.8- = overestimating)
- Verify confidence scores ≥ 0.7
- Review sample counts per group

### 3. Apply Coefficient Updates (MANUAL)
```python
# Example: Update PHASE_OVERHEAD in src/autopack/token_estimator.py

# Before (from calibration report: implementation/low underestimating by 40%)
("implementation", "low"): 2000,

# After (multiply by proposed_multiplier = 1.4)
("implementation", "low"): 2800,
```

### 4. Test Changes
```bash
# Create test run with updated coefficients
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_test.db" \
    python scripts/create_telemetry_collection_run.py

# Drain and compare results
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_test.db" \
    TELEMETRY_DB_ENABLED=1 \
    python scripts/drain_one_phase.py ... --force
```

### 5. Commit Changes
```bash
git add src/autopack/token_estimator.py
git commit -m "feat: calibrate token estimator coefficients based on telemetry

Calibration results (YYYYMMDD):
- implementation/low: 2000 → 2800 (+40%, n=12, confidence=0.85)
- testing/medium: 2500 → 3000 (+20%, n=8, confidence=0.72)

Source: token_estimator_calibration_YYYYMMDD_HHMMSS.md
Validation: 15 successful phases with median error reduction 45% → 15%"
```

---

## Advanced Workflows

### Legacy Backlog Draining (Optional)
Use restored legacy database with sample-first triage:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_legacy.db" \
    python scripts/batch_drain_controller.py \
    --batch-size 30 \
    --max-fingerprint-repeats 2 \
    --max-attempts-per-phase 1 \
    --max-timeouts-per-run 1 \
    --max-consecutive-zero-yield 10 \
    --api-url http://127.0.0.1:8000
```

**Benefits**:
- Real-world failure patterns (207 FAILED phases)
- Historical telemetry data (1371 events)
- Sample-first triage prevents token waste on systematic failures

### Continuous Calibration
```bash
# After every 20-30 successful phases
python scripts/calibrate_token_estimator.py

# Track coefficient drift over time
git diff src/autopack/token_estimator.py
```

---

## Files Reference

### Scripts
- `scripts/create_telemetry_collection_run.py` - Create telemetry run (T1)
- `scripts/drain_one_phase.py` - Drain single phase
- `scripts/batch_drain_controller.py` - Batch drain with triage (T3+T4)
- `scripts/db_identity_check.py` - Check DB state
- `scripts/calibrate_token_estimator.py` - Calibration job (T5)
- `scripts/analyze_token_telemetry_v3.py` - Legacy analyzer
- `scripts/telemetry_seed_quickstart.ps1` - Windows automation
- `scripts/telemetry_seed_quickstart.sh` - Unix automation

### Modules
- `src/autopack/db_identity.py` - DB identity utilities (T2)
- `src/autopack/token_estimator.py` - Token estimation logic

### Documentation
- `docs/guides/BUILD-139_T1-T5_HANDOFF.md` - Complete T1-T5 implementation
- `docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md` - DB hygiene workflow
- `docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md` - This document

---

## Summary

**Recommended Path**:
1. ✅ **Test**: Single phase drain with `--force` flag
2. ✅ **Collect**: Batch drain remaining 9 phases via API
3. ✅ **Verify**: Check DB identity for LLM usage events
4. ✅ **Analyze**: Run calibration job (T5)
5. ✅ **Review**: Read markdown report + JSON patch
6. ✅ **Apply**: Manually update token_estimator.py
7. ✅ **Test**: Validate changes with test run
8. ✅ **Commit**: Push coefficient updates with justification

**Key Safety Features**:
- DB identity guardrails (T2) - prevents wrong-database operations
- Sample-first triage (T3) - reduces token waste
- Telemetry clarity (T4) - explains zero-yield phases
- Gated calibration (T5) - requires manual review before applying changes

---

## Best Practices for Future Telemetry Runs

### Preventing Doc-Phase Truncation

Documentation phases can generate unexpectedly large outputs, leading to truncation and wasted tokens. To prevent this:

**Phase Specification Guidelines**:
- Explicitly cap output size in phase goals:
  - README: "≤ 150 lines, bullet-style overview"
  - USAGE.md: "≤ 200 lines, 1-2 examples per function"
  - Design notes: "≤ 150 lines, high-level architecture only"
- Avoid "comprehensive" or "detailed" language that encourages lengthy outputs

**Context Loading**:
- For docs phases, limit context files to 5-10 most relevant files
- Don't load all implementation files into prompt for documentation tasks
- Use targeted context (e.g., just function signatures, not full implementations)

**Token Budget**:
- Use lower initial budgets for docs (4K-8K output tokens)
- Documentation should be concise by design
- If docs phase hits token limits, review scope rather than escalating budget

**Validation**:
- After telemetry collection, check for doc-phase truncation:
  ```sql
  SELECT phase_id, truncated, actual_output_tokens
  FROM token_estimation_v2_events
  WHERE phase_id LIKE '%doc%' OR phase_id LIKE '%readme%'
  ORDER BY actual_output_tokens DESC;
  ```

These practices ensure documentation phases contribute clean telemetry samples without token waste.

---

All workflows are production-ready and fully documented! 🚀
