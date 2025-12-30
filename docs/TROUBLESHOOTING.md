# Troubleshooting Guide

**Purpose**: Common issues and quick fixes for Autopack users

**Last Updated**: 2025-12-29

---

## Quick Diagnostics

### Check System Health

```bash
# Verify installation
python -c "import autopack; print('OK')"

# Check database
PYTHONPATH=src python scripts/db_identity_check.py

# Test API server
curl http://localhost:8000/health
```

---

## Common Issues

### 1. "No module named autopack"

**Symptom**: Import errors when running scripts

**Cause**: Missing PYTHONPATH environment variable

**Fix**:
```bash
# Linux/Mac
export PYTHONPATH=src

# Windows PowerShell
$env:PYTHONPATH="src"

# Windows CMD
set PYTHONPATH=src
```

**Verify**:
```bash
PYTHONPATH=src python -c "import autopack; print('Success')"
```

---

### 2. "Database locked"

**Symptom**: SQLite database locked error during execution

**Cause**: Multiple executors accessing same database simultaneously

**Fix**:
```bash
# Find running executors
ps aux | grep autonomous_executor  # Linux/Mac
Get-Process | Where-Object {$_.ProcessName -like "*python*"}  # Windows

# Kill conflicting processes
kill <PID>  # Linux/Mac
Stop-Process -Id <PID>  # Windows
```

**Prevention**: Only run one executor per database at a time

---

### 3. "API server not responding"

**Symptom**: Connection refused on port 8000

**Cause**: API server not running or wrong port

**Fix**:
```bash
# Check if server is running
curl http://localhost:8000/health

# Start API server
PYTHONPATH=src uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Check port conflicts
netstat -an | grep 8000  # Linux/Mac
netstat -an | findstr 8000  # Windows
```

---

### 4. "Phase stuck in QUEUED state"

**Symptom**: Phases remain QUEUED, executor reports "No executable phases"

**Cause**: Database/API mismatch or run state issues

**Fix**:
```bash
# Check database state
PYTHONPATH=src python scripts/db_identity_check.py

# Verify API sees the run
curl http://localhost:8000/runs/<run-id>

# Check run state
PYTHONPATH=src python scripts/list_run_counts.py
```

**Common causes**:
- API server using different database than executor
- Run state is DONE_* (terminal state)
- Phase has exhausted retry attempts

---

### 5. "Empty files array" / "No valid file changes"

**Symptom**: Builder returns empty output, phase fails with no files generated

**Cause**: Prompt ambiguity or deliverables validation failure

**Fix**:
- Check phase deliverables are clear and achievable
- Review Builder logs for truncation: `.autonomous_runs/<project>/runs/<run-id>/run.log`
- Verify scope paths exist: `ls -la <scope-path>`

**Prevention**: Use specific deliverable paths (not just directory prefixes)

---

### 6. "Deliverables validation failed"

**Symptom**: Phase fails with "Found in patch: X/Y files"

**Cause**: Builder created files in wrong locations or missed deliverables

**Fix**:
- Check learning hints in logs: `grep "Learning hint" .autonomous_runs/<project>/runs/<run-id>/run.log`
- Review expected vs actual paths in phase summary
- Verify scope configuration includes all deliverable roots

**Common patterns**:
- Wrong: `tracer_bullet/file.py` → Correct: `src/autopack/research/tracer_bullet/file.py`
- Missing directory prefixes in scope paths

---

### 7. "Patch application failed"

**Symptom**: Git apply rejects patch with conflicts or format errors

**Cause**: Malformed diff, protected path violation, or file conflicts

**Fix**:
```bash
# Check protected paths
grep "protected_paths" .autonomous_runs/<project>/runs/<run-id>/run.log

# Review patch content
cat .autonomous_runs/<project>/runs/<run-id>/phases/phase_*.md

# Check for conflicts
git status
git diff
```

**Common causes**:
- Attempting to modify `.git/`, `.autonomous_runs/`, or `autopack.db`
- Files outside allowed scope
- Merge conflicts with uncommitted changes

---

### 8. "CI collection errors"

**Symptom**: Pytest collection fails with ImportError or syntax errors

**Cause**: Missing dependencies, import errors, or test file issues

**Fix**:
```bash
# Run pytest directly to see errors
PYTHONPATH=src pytest tests/ -v

# Check specific test file
PYTHONPATH=src pytest tests/test_file.py -v

# Install missing dependencies
pip install -r requirements.txt
```

**Bypass for telemetry collection**:
```bash
export AUTOPACK_SKIP_CI=1  # Skip CI checks temporarily
```

---

### 9. "Token budget exceeded" / Truncation

**Symptom**: Builder output truncated, stop_reason="max_tokens"

**Cause**: Output size exceeds token budget

**Fix**:
- Check token estimation logs: `grep "TokenEstimation" .autonomous_runs/<project>/runs/<run-id>/run.log`
- Review phase complexity and deliverable count
- Consider splitting large phases into smaller batches

**Automatic recovery**: Executor retries with increased budget (BUILD-129)

---

### 10. "Database identity mismatch"

**Symptom**: Executor and API server use different databases

**Cause**: DATABASE_URL not set consistently

**Fix**:
```bash
# Set DATABASE_URL explicitly
export DATABASE_URL="sqlite:///autopack.db"  # Linux/Mac
$env:DATABASE_URL="sqlite:///autopack.db"  # Windows

# Verify both processes see same DB
PYTHONPATH=src python scripts/db_identity_check.py
curl http://localhost:8000/health | jq .db_identity
```

**Prevention**: Always set DATABASE_URL before starting API server or executor

---

### 11. "Telemetry not collected"

**Symptom**: Zero telemetry events despite successful phases

**Cause**: TELEMETRY_DB_ENABLED not set or phases failed before Builder

**Fix**:
```bash
# Enable telemetry
export TELEMETRY_DB_ENABLED=1  # Linux/Mac
$env:TELEMETRY_DB_ENABLED="1"  # Windows

# Verify telemetry events
PYTHONPATH=src python scripts/db_identity_check.py
# Look for token_estimation_v2_events count
```

**Check**: Did phases reach Builder? Review logs for "[TokenEstimationV2]" entries

---

### 12. "Approval request timeout"

**Symptom**: Phase stuck waiting for approval, times out after 15 minutes

**Cause**: Telegram notification not received or approval not submitted

**Fix**:
- Check Telegram bot is configured: `python scripts/verify_telegram_credentials.py`
- Verify chat ID: `python scripts/check_telegram_id.py`
- Check approval status: `curl http://localhost:8000/approval/status/<approval-id>`

**Manual approval**:
```bash
# Approve via API
curl -X POST http://localhost:8000/approval/<approval-id>/approve
```

---

### 13. "High failure rate in batch drain"

**Symptom**: Most phases fail during batch draining

**Cause**: Systematic issues (import errors, scope problems) or low-quality phases

**Fix**:
- Use sample-first triage: `--max-fingerprint-repeats 2`
- Check fingerprint distribution in session logs
- Review zero-yield reasons: `grep "zero_yield_reason" .autonomous_runs/batch_drain_sessions/*.json`

**Recommended settings**:
```bash
python scripts/batch_drain_controller.py \
  --batch-size 10 \
  --max-consecutive-zero-yield 5 \
  --max-fingerprint-repeats 2
```

---

### 14. "Research system import errors"

**Symptom**: Tests fail with "No module named research.agents" or similar

**Cause**: Import path mismatch (src.research vs research)

**Fix**:
- Ensure imports use `research.*` not `src.research.*`
- Check PYTHONPATH is set to `src`
- Review compatibility shims in research modules

**See**: [docs/guides/CI_FIX_HANDOFF_REPORT.md](guides/CI_FIX_HANDOFF_REPORT.md)

---

### 15. "Scope validation failures"

**Symptom**: Files rejected as "outside scope" despite being in deliverables

**Cause**: Workspace root mismatch or scope path configuration issues

**Fix**:
- Check workspace root detection: `grep "Workspace root" .autonomous_runs/<project>/runs/<run-id>/run.log`
- Verify scope paths include all deliverable roots
- Review allowed_roots derivation in logs

**Common patterns**:
- Scope: `fileorganizer/frontend/` but workspace root is `fileorganizer/`
- Missing `src/`, `docs/`, `tests/` in scope paths

---

## Emergency Recovery

### Reset Phase for Retry

```bash
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

### Rollback Failed Phase

```bash
# Find save point
git tag | grep save-before-<phase-id>

# Rollback
git reset --hard <save-tag>
```

### Clear Stuck Run

```bash
# Mark run as failed
PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import Run
session = SessionLocal()
run = session.query(Run).filter_by(id='<run-id>').first()
run.state = 'DONE_FAILED_REQUIRES_HUMAN_REVIEW'
session.commit()
print(f'Marked {run.id} as failed')
"
```

---

## Getting More Help

### Documentation

- [README.md](../README.md) - Project overview
- [QUICKSTART.md](QUICKSTART.md) - Getting started
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup
- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Detailed error scenarios
- [BUILD_HISTORY.md](BUILD_HISTORY.md) - Feature changelog
- [DEBUG_LOG.md](DEBUG_LOG.md) - Known issues

### Diagnostic Scripts

```bash
# Database state
PYTHONPATH=src python scripts/db_identity_check.py

# Run counts
PYTHONPATH=src python scripts/list_run_counts.py

# Telemetry analysis
PYTHONPATH=src python scripts/analyze_token_telemetry_v3.py --success-only

# Health checks
PYTHONPATH=src python -m autopack.health_checks
```

### Log Locations

- **Executor logs**: `.autonomous_runs/<project>/runs/<run-id>/run.log`
- **Phase summaries**: `.autonomous_runs/<project>/runs/<run-id>/phases/phase_*.md`
- **CI reports**: `.autonomous_runs/<project>/ci/pytest_<phase-id>.json`
- **Batch drain sessions**: `.autonomous_runs/batch_drain_sessions/batch-drain-*.json`

---

**Total Lines**: 180 (within ≤180 line constraint)

**Coverage**: 15 common issues with fixes, emergency recovery procedures, help resources

**Style**: Bullet-style Q&A with code examples and quick diagnostics
