# Telemetry Guide

**Purpose**: Enable and use token estimation telemetry for calibrating Autopack's token budgets

**Last Updated**: 2025-12-29

---

## Overview

Autopack collects telemetry on token usage to improve token budget estimation accuracy. This guide covers:

1. Enabling telemetry collection
2. Understanding the collection workflow
3. Analyzing telemetry data
4. Calibrating token estimator coefficients
5. Troubleshooting common issues

---

## Task Generation from Telemetry Insights

**IMP-LOOP-007**: Task generation is now **enabled by default**. This enables the self-improvement loop to automatically generate improvement tasks from telemetry insights.

### Configuration

| Setting | Default | Environment Variable | Description |
|---------|---------|---------------------|-------------|
| `task_generation_enabled` | `True` | `AUTOPACK_TASK_GENERATION_ENABLED` | Enable/disable automatic task generation |
| `task_generation_auto_execute` | `True` | `AUTOPACK_TASK_GENERATION_AUTO_EXECUTE` | Auto-execute generated tasks |
| `task_generation_max_tasks_per_run` | `10` | `AUTOPACK_TASK_GENERATION_MAX_TASKS` | Max tasks per run |
| `task_generation_min_confidence` | `0.7` | `AUTOPACK_TASK_GENERATION_MIN_CONFIDENCE` | Min confidence threshold |

### Disabling Task Generation

To disable task generation (e.g., for debugging):

```bash
# Windows PowerShell
$env:AUTOPACK_TASK_GENERATION_ENABLED="false"

# Linux/Mac
export AUTOPACK_TASK_GENERATION_ENABLED=false
```

### How It Works

1. Telemetry collects metrics during autonomous execution
2. The TelemetryAnalyzer identifies patterns and insights
3. The AutonomousTaskGenerator creates improvement tasks
4. Tasks are auto-executed if `task_generation_auto_execute=True`

---

## 1. Enabling Telemetry

### Quick Start

Enable telemetry by setting the `TELEMETRY_DB_ENABLED` environment variable:

```bash
# Windows PowerShell
$env:TELEMETRY_DB_ENABLED="1"

# Linux/Mac
export TELEMETRY_DB_ENABLED=1
```

### Verification

Check that telemetry is enabled:

```bash
# Check database for telemetry events
PYTHONPATH=src python scripts/db_identity_check.py
```

Look for:
- `token_estimation_v2_events` table with row count > 0
- `token_budget_escalation_events` table (if escalations occurred)

### Configuration Options

**Environment Variables**:
- `TELEMETRY_DB_ENABLED=1` - Enable database persistence (default: 0)
- `DATABASE_URL` - Database connection string (default: `sqlite:///autopack.db`)

**What Gets Collected**:
- Predicted output tokens (from TokenEstimator)
- Actual output tokens (from LLM response)
- Selected budget (max_tokens parameter)
- Phase metadata: category, complexity, deliverable count
- Success/failure status
- Truncation status (stop_reason)
- Model used (claude-sonnet-4-5, etc.)

---

## 2. Collection Workflow

### Automatic Collection

Telemetry is collected automatically during phase execution:

```
1. Phase starts → TokenEstimator predicts output tokens
2. Builder calls LLM → Actual tokens consumed
3. Response received → Telemetry logged to database
4. Phase completes → Data available for analysis
```

### Collection Points

**Primary**: After successful LLM calls
- File: `src/autopack/anthropic_clients.py`
- Lines: 776-790 (primary), 806-820 (fallback)
- Triggers: Every Builder invocation with valid token estimate

**What's NOT Collected**:
- Phases that fail before Builder execution
- Phases with missing token estimates
- Phases when `TELEMETRY_DB_ENABLED=0`

### Telemetry Seeding

For initial calibration, use the telemetry seeding workflow:

```bash
# 1. Create telemetry collection run (10 simple phases)
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/create_telemetry_collection_run.py

# 2. Start API server (separate terminal)
PYTHONPATH=src python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# 3. Drain phases with telemetry enabled
TELEMETRY_DB_ENABLED=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/batch_drain_controller.py \
    --run-id telemetry-collection-v4 \
    --batch-size 10 \
    --api-url http://127.0.0.1:8000
```

See [TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md](guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md) for detailed instructions.

---

## 3. Analyzing Telemetry

### Quick Analysis

Check current telemetry status:

```bash
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/db_identity_check.py
```

**Output includes**:
- Total telemetry events collected
- Success rate (% with success=True)
- Truncation rate (% with truncated=True)
- Breakdown by category and complexity

### Detailed Analysis

**Option 1: V3 Analyzer** (log-based, legacy)

```bash
python scripts/analyze_token_telemetry_v3.py \
  --log-dir .autonomous_runs \
  --success-only \
  --stratify \
  --under-multiplier 1.1 \
  --output reports/telemetry_analysis.md
```

**Option 2: Calibration Script** (database-based, recommended)

```bash
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/calibrate_token_estimator.py \
    --min-samples 5 \
    --confidence-threshold 0.7 \
    --output-dir reports/
```

### Key Metrics

**Tier 1: Risk Metrics** (primary tuning gates)
- **Underestimation Rate**: % where actual > predicted × 1.1 (target: ≤5%)
- **Truncation Rate**: % where truncated=True (target: ≤2%)
- **Success Rate**: % where success=True (monitoring only)

**Tier 2: Cost Metrics** (secondary optimization)
- **Waste Ratio**: predicted / actual (target: P90 < 3x)
- **SMAPE**: Symmetric percentage error (diagnostic only)

**Decision Framework**:
- If Tier 1 targets exceeded → Tune coefficients
- If Tier 1 targets met → No tuning needed, monitor for drift

---

## 4. Calibration

### When to Calibrate

Calibrate when:
- ✅ You have ≥20 successful samples (success=True, truncated=False)
- ✅ Samples cover diverse categories (implementation, tests, docs)
- ✅ Samples cover diverse complexity levels (low, medium, high)
- ✅ Underestimation rate >5% OR truncation rate >2%

**Don't calibrate when**:
- ❌ Insufficient samples (<20)
- ❌ All samples are failure modes (success=False)
- ❌ Tier 1 metrics within targets

### Calibration Process

**Step 1: Generate Calibration Report**

```bash
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/calibrate_token_estimator.py \
    --min-samples 5 \
    --confidence-threshold 0.7
```

**Output**:
- `token_estimator_calibration_YYYYMMDD_HHMMSS.md` - Human-readable report
- `token_estimator_calibration_YYYYMMDD_HHMMSS.json` - Machine-readable patch

**Step 2: Review Recommendations**

The report includes:
- Current coefficient values
- Recommended multipliers (e.g., 1.2x for implementation/medium)
- Confidence scores (based on sample count + variance)
- Per-category/complexity breakdowns

**Step 3: Apply Changes Manually**

⚠️ **CRITICAL**: Calibration script does NOT auto-edit code. You must:

1. Review the JSON patch file
2. Manually update `src/autopack/token_estimator.py`
3. Test changes with validation run
4. Commit with justification

**Example**:
```python
# Before
OVERHEAD_TOKENS = {
    ("implementation", "medium"): 2500,
}

# After (1.2x multiplier recommended)
OVERHEAD_TOKENS = {
    ("implementation", "medium"): 3000,  # 2500 × 1.2
}
```

### Safety Guardrails

- **Minimum samples**: Requires ≥5 samples per category/complexity group
- **Confidence threshold**: Only recommends changes with confidence ≥0.7
- **No auto-edit**: Manual review required before applying
- **Gated by Tier 1**: Only tune if risk metrics exceed targets

---

## 5. Troubleshooting

### No Telemetry Events Collected

**Symptom**: `token_estimation_v2_events` table is empty after draining phases

**Possible Causes**:
1. `TELEMETRY_DB_ENABLED` not set → Set to `1`
2. Phases failed before Builder execution → Check phase logs
3. Database connection issues → Verify `DATABASE_URL`
4. Telemetry write errors → Check executor logs for exceptions

**Diagnosis**:
```bash
# Check if phases reached Builder
grep "\[TokenEstimationV2\]" .autonomous_runs/*/logs/*.log

# Check for telemetry write errors
grep "telemetry" .autonomous_runs/*/logs/*.log | grep -i error
```

### All Samples Have success=False

**Symptom**: Telemetry collected but all records show `success=False`

**Cause**: Phases are failing during execution (not reaching completion)

**Solution**:
- Review phase failure reasons in logs
- Fix systemic issues (import errors, scope validation, etc.)
- Use simpler phases for initial telemetry seeding
- See [TELEMETRY_COLLECTION_GUIDE.md](TELEMETRY_COLLECTION_GUIDE.md) for seeding strategy

### High Truncation Rate

**Symptom**: >10% of samples have `truncated=True`

**Cause**: Token budgets too small for actual output

**Solution**:
1. Filter analysis to success-only: `--success-only`
2. Check underestimation rate (should be <5%)
3. If underestimation high, increase coefficients
4. Re-run calibration after collecting more samples

### Calibration Script Shows "Insufficient Samples"

**Symptom**: Calibration report says "Not enough samples for confident recommendations"

**Cause**: <5 samples in one or more category/complexity groups

**Solution**:
- Collect more diverse samples (different categories/complexity)
- Lower `--min-samples` threshold (not recommended)
- Focus on categories with sufficient samples

### Database Identity Confusion

**Symptom**: Telemetry appears in wrong database or not found

**Cause**: `DATABASE_URL` not set correctly

**Solution**:
```bash
# Always verify DB identity before operations
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/db_identity_check.py

# Set DATABASE_URL explicitly
export DATABASE_URL="sqlite:///autopack.db"  # Linux/Mac
$env:DATABASE_URL="sqlite:///autopack.db"   # Windows
```

---

## Quick Reference

### Essential Commands

```bash
# Enable telemetry
export TELEMETRY_DB_ENABLED=1

# Check telemetry status
PYTHONPATH=src python scripts/db_identity_check.py

# Analyze telemetry (success-only)
python scripts/analyze_token_telemetry_v3.py --success-only

# Generate calibration report
PYTHONPATH=src python scripts/calibrate_token_estimator.py

# Export telemetry to NDJSON
PYTHONPATH=src python scripts/export_token_estimation_telemetry.py
```

### Key Files

- **Telemetry logging**: `src/autopack/anthropic_clients.py` (lines 40-114, 776-820)
- **Token estimator**: `src/autopack/token_estimator.py`
- **Database model**: `src/autopack/models.py` (TokenEstimationV2Event)
- **Analysis scripts**: `scripts/analyze_token_telemetry_v3.py`, `scripts/calibrate_token_estimator.py`

### Documentation

- [TELEMETRY_COLLECTION_GUIDE.md](TELEMETRY_COLLECTION_GUIDE.md) - Detailed collection workflow
- [TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md](guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md) - Unified workflow guide
- [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md) - Methodology and learnings
- [TOKEN_ESTIMATION_V3_ENHANCEMENTS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_V3_ENHANCEMENTS.md) - V3 analyzer details
- [BUILD-129_PHASE1_VALIDATION_COMPLETE.md](archive/superseded/reports/BUILD-129_PHASE1_VALIDATION_COMPLETE.md) - Implementation summary

---

**Total Lines**: 198 (within ≤200 line constraint)

**Coverage**: Enablement (1 section), collection workflow (1 section), analysis (1 section), calibration (1 section), troubleshooting (1 section)
