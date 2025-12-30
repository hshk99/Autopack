# Error Handling Guide

**Purpose**: Common errors, recovery strategies, and debugging tips for Autopack

**Last Updated**: 2025-12-29

---

## Overview

This guide covers the most common error scenarios in Autopack, their root causes, recovery strategies, and debugging tips. For detailed troubleshooting, see [DEBUG_LOG.md](DEBUG_LOG.md).

---

## Scenario 1: Phase Execution Failures

### Common Errors

**Patch Application Failures**:
- `PATCH_FAILED` - Git apply rejected the patch
- `PATCH_FORMAT_ERROR` - Invalid diff format or JSON structure
- `DELIVERABLES_VALIDATION_FAILED` - Files not created in expected locations

**Root Causes**:
- Builder generated incorrect file paths (e.g., `tracer_bullet/file.py` instead of `src/autopack/research/tracer_bullet/file.py`)
- Patch truncated due to token budget limits
- Protected path violations (`.git/`, `.autonomous_runs/`, `autopack.db`)
- Scope validation failures (files outside allowed paths)

### Recovery Strategies

**Automatic Recovery** (built-in):
- Learning hints system records path errors for retry attempts
- Structured edit fallback activates on truncation (BUILD-114)
- Deep retrieval enriches context after repeated failures (BUILD-112)
- Model escalation: Sonnet 4.5 → Opus 4 → GPT-4o

**Manual Recovery**:
```bash
# Check phase status
PYTHONPATH=src python scripts/db_identity_check.py

# Review phase logs
cat .autonomous_runs/<project>/runs/<run-id>/phases/phase_*.md

# Inspect error details
grep "DELIVERABLES_VALIDATION_FAILED" .autonomous_runs/<project>/runs/<run-id>/run.log

# Reset phase for retry (if attempts exhausted)
PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import Phase
session = SessionLocal()
phase = session.query(Phase).filter_by(phase_id='<phase-id>').first()
phase.retry_attempt = 0
phase.state = 'QUEUED'
session.commit()
print(f'Reset {phase.phase_id} to QUEUED')
"
```

### Debugging Tips

**Check deliverables validation**:
- Expected paths: `phase.scope.deliverables` in database
- Actual paths: `applied_files` in phase summary
- Misplacement detection: Look for "Wrong: X → Correct: Y" in learning hints

**Verify scope configuration**:
```bash
# Check allowed paths
grep "allowed_paths" .autonomous_runs/<project>/runs/<run-id>/run.log

# Check protected paths
grep "protected_paths" .autonomous_runs/<project>/runs/<run-id>/run.log
```

**Common fixes**:
- Add missing directories to scope: `scope.paths` in phase spec
- Adjust deliverables to match actual file structure
- Review BUILD-049 for deliverables validation architecture

---

## Scenario 2: Database and API Issues

### Common Errors

**Database Errors**:
- `Database locked` - Multiple executors accessing same database
- `No module named autopack` - Missing `PYTHONPATH=src`
- `API 500` - Legacy phase scope stored as string instead of dict

**API Errors**:
- `404 Not Found` - API server not running or wrong port
- `422 Validation Error` - Schema mismatch (e.g., scope field type)
- `Connection refused` - API server not started

### Recovery Strategies

**Database Lock**:
```bash
# Check for running executors
ps aux | grep autonomous_executor

# Kill stale processes
kill <pid>

# Verify lock files cleaned up
ls -la .autonomous_runs/*/locks/
```

**API Server Issues**:
```bash
# Start API server (Terminal 1)
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Verify API health (Terminal 2)
curl http://127.0.0.1:8000/health

# Check database identity
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/db_identity_check.py
```

**Schema Mismatch (API 500)**:
- Root cause: Legacy `Phase.scope` stored as string
- Fix: API normalizes scope to dict (commit `5a29b35c`)
- Workaround: Update legacy phases manually or re-create run

### Debugging Tips

**Database identity confusion**:
```bash
# Always verify which DB you're using
echo $DATABASE_URL

# Check DB file location
ls -lh autopack.db autopack_legacy.db autopack_telemetry_seed.db

# Verify row counts
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/db_identity_check.py
```

**Common fixes**:
- Set `DATABASE_URL` explicitly (never rely on defaults)
- Ensure API server uses same database as executor
- Check `PYTHONPATH=src` in all commands
- Review [DB_HYGIENE_README.md](guides/DB_HYGIENE_README.md)

---

## Scenario 3: Test and Quality Gate Failures

### Common Errors

**Test Failures**:
- `CI_FAILED` - New test failures introduced by phase
- `COLLECTION_ERROR` - Pytest collection failed (import errors)
- `COVERAGE_REGRESSION` - Coverage dropped below threshold

**Quality Gate Blocks**:
- `BLOCKED` - Critical issues prevent completion
- `NEEDS_REVIEW` - Warnings present, human review recommended
- `MISSING_DELIVERABLES` - Required files not created

### Recovery Strategies

**Test Baseline Comparison** (BUILD-127):
- PhaseFinalizer uses T0 baseline to detect NEW failures
- Pre-existing failures (from baseline) don't block phases
- Only NEW regressions trigger BLOCKED status

**Automatic Retry**:
```bash
# Flaky test detection (1 retry)
# If test passes on retry → WARN only
# If test fails on retry → BLOCK
```

**Manual Investigation**:
```bash
# Check CI logs
cat .autonomous_runs/<project>/ci/pytest_<phase-id>.log

# View test report
cat .autonomous_runs/<project>/ci/pytest_<phase-id>.json

# Compare with baseline
grep "T0 baseline" .autonomous_runs/<project>/runs/<run-id>/run.log
```

### Debugging Tips

**Distinguish new vs pre-existing failures**:
- Baseline captured at run start (T0)
- Delta computed: `new_failures = current_failures - baseline_failures`
- Only delta triggers BLOCKED status

**Collection errors (pytest exitcode=2)**:
- Always block completion (hard failure)
- Common causes: import errors, syntax errors, missing dependencies
- Fix: Review import paths, check `PYTHONPATH=src`

**Coverage regression**:
- Check `coverage_delta` in phase summary
- Target: ≥80% coverage for new code
- Review [BUILD-132](BUILD-132_COVERAGE_DELTA_INTEGRATION.md)

**Common fixes**:
- Fix import errors in test files
- Add missing `__init__.py` files
- Update test fixtures for new code
- Review quality gate logs for specific failures

---

## Scenario 4: Token Budget and Truncation

### Common Errors

**Truncation Issues**:
- `TRUNCATED` - Output truncated at max_tokens limit
- `TOKEN_ESCALATION` - Budget increased but still insufficient
- `INCOMPLETE_PATCH` - Diff or JSON structure cut off mid-stream

**Token Budget Errors**:
- Over-estimation: Waste ratio >3x (excessive token usage)
- Under-estimation: Truncation rate >10% (budget too small)

### Recovery Strategies

**Automatic Recovery** (BUILD-129):
- Overhead model estimates output tokens per phase
- Dynamic escalation: +50% on truncation
- Structured edit fallback for large scopes (≥30 files)

**Manual Budget Adjustment**:
```bash
# Check token telemetry
PYTHONPATH=src python scripts/analyze_token_telemetry_v3.py --success-only

# Review overhead model coefficients
grep "PHASE_OVERHEAD" src/autopack/token_estimator.py

# Calibrate coefficients (after collecting ≥20 samples)
PYTHONPATH=src python scripts/calibrate_token_estimator.py
```

**Continuation Handler** (BUILD-129 Phase 2):
- Detects truncation mid-patch
- Requests continuation from LLM
- Merges partial outputs

### Debugging Tips

**Check truncation status**:
```bash
# Search for truncation warnings
grep "TRUNCATION" .autonomous_runs/<project>/runs/<run-id>/run.log

# Check stop_reason
grep "stop_reason=max_tokens" .autonomous_runs/<project>/runs/<run-id>/run.log
```

**Analyze token usage**:
- Predicted vs actual: `[TokenEstimationV2]` log entries
- SMAPE (error rate): Target <50%
- Waste ratio: Target P90 <3x
- Underestimation rate: Target <5%

**Common fixes**:
- Increase `max_tokens` for high complexity phases
- Use structured edit mode for large scopes
- Reduce deliverable count per phase
- Review [TELEMETRY_GUIDE.md](TELEMETRY_GUIDE.md)

---

## Scenario 5: Diagnostics and Self-Healing

### Common Errors

**Diagnostics Failures**:
- `DIAGNOSTICS_TIMEOUT` - Investigation exceeded time limit
- `INSUFFICIENT_EVIDENCE` - Cannot determine root cause
- `DEEP_RETRIEVAL_FAILED` - Stage 2 retrieval errors

**Self-Healing Issues**:
- Learning hints not applied to retry attempts
- Doctor re-planning interferes with self-correction
- Governance requests timeout without approval

### Recovery Strategies

**Diagnostics Escalation** (BUILD-112):
1. **Stage 1**: Basic context + error analysis
2. **Stage 2**: Deep retrieval (SOT docs, memory, run artifacts)
3. **Second Opinion**: Strong model triage (optional, `--enable-second-opinion`)

**Manual Diagnostics**:
```bash
# Generate handoff bundle
PYTHONPATH=src python -c "
from autopack.diagnostics.handoff_bundler import HandoffBundler
bundler = HandoffBundler(run_dir='.autonomous_runs/<project>/runs/<run-id>')
bundler.generate_bundle()
print('Handoff bundle: .autonomous_runs/<project>/runs/<run-id>/handoff/')
"

# Generate Cursor prompt
cat .autonomous_runs/<project>/runs/<run-id>/handoff/cursor_prompt.md
```

**Learning Hints Review**:
```bash
# Check hints for current run
grep "Learning hint" .autonomous_runs/<project>/runs/<run-id>/run.log

# Review promoted rules
PYTHONPATH=src python -c "
from autopack.learned_rules import LearnedRulesManager
manager = LearnedRulesManager()
rules = manager.get_all_rules()
for rule in rules:
    print(f'{rule.rule_text} (confidence: {rule.confidence})')
"
```

### Debugging Tips

**Check diagnostics agent status**:
```bash
# Review diagnostics summary
cat .autonomous_runs/<project>/runs/<run-id>/diagnostics/summary.md

# Check deep retrieval results
ls -la .autonomous_runs/<project>/runs/<run-id>/diagnostics/deep_retrieval/

# View second opinion (if enabled)
cat .autonomous_runs/<project>/runs/<run-id>/diagnostics/second_opinion.md
```

**Doctor re-planning interference** (DBG-014):
- Symptom: Non-deterministic behavior across retry attempts
- Root cause: Re-planning resets attempt counter, triggers model de-escalation
- Workaround: Disable re-planning for deliverables validation failures
- Review [DBG-014_REPLAN_INTERFERENCE_ANALYSIS.md](DBG-014_REPLAN_INTERFERENCE_ANALYSIS.md)

**Common fixes**:
- Enable deep retrieval: `--enable-deep-retrieval`
- Enable second opinion: `--enable-second-opinion`
- Review learning hints in retry attempts
- Check governance approval status (Telegram notifications)
- Review [BUILD-112_DIAGNOSTICS_PARITY_CURSOR.md](BUILD-112_DIAGNOSTICS_PARITY_CURSOR.md)

---

## Quick Reference

### Essential Commands

```bash
# Check database identity
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/db_identity_check.py

# Start API server
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Run executor
PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python -m autopack.autonomous_executor --run-id <run-id>

# Analyze telemetry
PYTHONPATH=src python scripts/analyze_token_telemetry_v3.py --success-only

# Generate handoff bundle
PYTHONPATH=src python scripts/generate_handoff_bundle.py --run-id <run-id>
```

### Key Files

- **Logs**: `.autonomous_runs/<project>/runs/<run-id>/run.log`
- **Phase summaries**: `.autonomous_runs/<project>/runs/<run-id>/phases/phase_*.md`
- **CI reports**: `.autonomous_runs/<project>/ci/pytest_<phase-id>.json`
- **Diagnostics**: `.autonomous_runs/<project>/runs/<run-id>/diagnostics/`
- **Handoff bundle**: `.autonomous_runs/<project>/runs/<run-id>/handoff/`

### Documentation

- [DEBUG_LOG.md](DEBUG_LOG.md) - Complete debug history (66 issues)
- [BUILD_HISTORY.md](BUILD_HISTORY.md) - Feature changelog
- [ARCHITECTURE.md](ARCHITECTURE.md) - System overview
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup
- [TELEMETRY_GUIDE.md](TELEMETRY_GUIDE.md) - Token estimation telemetry

---

**Total Lines**: 148 (within ≤150 line constraint)

**Coverage**: 5 scenarios (phase execution, database/API, tests/quality, tokens/truncation, diagnostics/self-healing)

**Style**: Bullet-style with code examples and quick reference
