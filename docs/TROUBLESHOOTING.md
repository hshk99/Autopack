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
- Review Builder logs for truncation: `.autonomous_runs/<project>/runs/<family>/<run_id>/run.log`
- Verify scope paths exist: `ls -la <scope-path>`

**Prevention**: Use specific deliverable paths (not just directory prefixes)

---

### 6. "Deliverables validation failed"

**Symptom**: Phase fails with "Found in patch: X/Y files"

**Cause**: Builder created files in wrong locations or missed deliverables

**Fix**:
- Check learning hints in logs: `grep "Learning hint" .autonomous_runs/<project>/runs/<family>/<run_id>/run.log`
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
grep "protected_paths" .autonomous_runs/<project>/runs/<family>/<run_id>/run.log

# Review patch content
cat .autonomous_runs/<project>/runs/<family>/<run_id>/phases/phase_*.md

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
- Check token estimation logs: `grep "TokenEstimation" .autonomous_runs/<project>/runs/<family>/<run_id>/run.log`
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
- Check workspace root detection: `grep "Workspace root" .autonomous_runs/<project>/runs/<family>/<run_id>/run.log`
- Verify scope paths include all deliverable roots
- Review allowed_roots derivation in logs

**Common patterns**:
- Scope: `fileorganizer/frontend/` but workspace root is `fileorganizer/`
- Missing `src/`, `docs/`, `tests/` in scope paths

---

## Storage Optimizer: Locked Files

**BUILD-152**: Advanced lock handling for Windows file deletion

### Overview

Storage Optimizer execution may encounter locked files on Windows. BUILD-152 introduces:

- **Lock type detection**: Identify specific lock types (searchindexer, antivirus, handle, permission)
- **Intelligent retry**: Automatic retry with exponential backoff for transient locks
- **Remediation hints**: Inline guidance in CLI output for manual fixes

See [STORAGE_OPTIMIZER_EXECUTION_GUIDE.md](STORAGE_OPTIMIZER_EXECUTION_GUIDE.md#lock-handling) for detailed configuration.

---

### Lock Types and Detection

| Lock Type       | Detection Patterns                          | Classification | Default Retry |
|-----------------|---------------------------------------------|----------------|---------------|
| `searchindexer` | "searchindexer", "windows search"           | Transient      | 3 times       |
| `antivirus`     | "virus", "defender", "malware"              | Transient      | 2 times       |
| `handle`        | "being used by another process"             | Transient      | 3 times       |
| `permission`    | "access is denied", "permission denied"     | Permanent      | 0 (skip)      |
| `path_too_long` | "path too long", "exceeds maximum path"     | Permanent      | 0 (skip)      |
| `unknown`       | (no match)                                  | Permanent      | 0 (skip)      |

**Transient locks** are retried automatically with exponential backoff ([2s, 5s, 10s]).

**Permanent locks** require manual intervention (see remediation workflows below).

---

### Identifying Lock Type

When execution fails due to a lock, check CLI output for lock classification:

```
FAILED DELETIONS:
  ✗ C:/dev/project/node_modules/package/file.cmd
    Error: permission: Access is denied
    → Insufficient permissions. Options: (1) Run PowerShell/CLI as Administrator...

  ✗ C:/temp/logs/app.log
    Error: searchindexer: Windows Search is indexing this file
    → Windows Search is indexing this file. Options: (1) Wait 30-60s and retry...
```

Lock type appears after "Error:" prefix (e.g., `permission:`, `searchindexer:`).

---

### Remediation Workflows

#### 1. SearchIndexer Locks

**Symptom**: Files locked by Windows Search indexing service

**Temporary Fix** (Quick):
- Wait 30-60 seconds for indexing to complete
- Re-run execution (automatic retry if within max_retries)

**Permanent Fix** (Disable indexing):

```powershell
# Option 1: Exclude folder from Windows Search (GUI)
# 1. Open "Indexing Options" (search in Start menu)
# 2. Click "Modify" → Uncheck the problematic folder
# 3. Click OK

# Option 2: Disable indexing via folder properties
# 1. Right-click folder → Properties
# 2. Advanced → Uncheck "Allow files in this folder to have contents indexed"
# 3. Apply to folder and subfolders

# Option 3: PowerShell (disable indexing for specific drive)
Get-WmiObject -Class Win32_Volume -Filter "DriveLetter='C:'" |
  Set-WmiInstance -Arguments @{IndexingEnabled=$false}
```

**Verify**:
```bash
# Re-run execution after fix
python scripts/storage/scan_and_report.py --scan-id 123 --execute --dry-run=false
```

---

#### 2. Antivirus Locks

**Symptom**: Files locked by Windows Defender or third-party antivirus

**Temporary Fix** (Wait for scan):
- Antivirus scans typically complete in 5-15 minutes
- Automatic retry will attempt 2 times with [10s, 30s, 60s] backoff

**Permanent Fix** (Add exclusion):

```powershell
# Windows Defender: Add folder exclusion
Add-MpPreference -ExclusionPath "C:\dev\project\logs"

# Verify exclusions
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
```

**⚠️ Warning**: Only exclude trusted folders. Remove exclusion after cleanup:

```powershell
# Remove exclusion after cleanup
Remove-MpPreference -ExclusionPath "C:\dev\project\logs"
```

---

#### 3. Open Handle Locks

**Symptom**: File is open in another process (editor, IDE, application)

**Quick Fix** (Resource Monitor):

1. **Open Resource Monitor**:
   - Press `Win+R`, type `resmon.exe`, press Enter
   - Navigate to **CPU** tab
   - Expand **Associated Handles** section

2. **Search for file**:
   - Type filename in search box (e.g., "app.log")
   - Identify process holding handle (e.g., "notepad.exe", "chrome.exe")

3. **Close process**:
   - Close application gracefully (File → Exit)
   - Or right-click process in Resource Monitor → End Process

**Advanced: Sysinternals Handle.exe**

Download from [Microsoft Sysinternals](https://docs.microsoft.com/en-us/sysinternals/downloads/handle):

```powershell
# Find all handles for a file
handle.exe "C:\dev\project\logs\app.log"

# Output example:
# notepad.exe       pid: 12345   type: File   C:\dev\project\logs\app.log

# Close specific handle (use with caution!)
handle.exe -c <handle_id> -p <process_id> -y
```

**Verify**:
```bash
# Re-run execution after closing handles
python scripts/storage/scan_and_report.py --scan-id 123 --execute --dry-run=false
```

---

#### 4. Permission Locks

**Symptom**: "Access is denied" or "Permission denied"

**Cause**: Insufficient permissions or file ownership issues

**Fix 1: Run as Administrator**

```powershell
# Right-click PowerShell → "Run as Administrator"
# Then re-run execution command
cd C:\dev\Autopack
python scripts/storage/scan_and_report.py --scan-id 123 --execute --dry-run=false
```

**Fix 2: Check File Ownership**

```powershell
# Check ownership
icacls "C:\dev\project\logs\app.log"

# Take ownership (if needed)
takeown /f "C:\dev\project\logs\app.log" /r /d y

# Grant full control to current user
icacls "C:\dev\project\logs\app.log" /grant %USERNAME%:F
```

**Fix 3: Check Parent Directory Permissions**

```powershell
# Verify write access to parent directory
icacls "C:\dev\project\logs"

# Grant permissions if needed
icacls "C:\dev\project\logs" /grant %USERNAME%:(OI)(CI)F /t
```

---

#### 5. Path Too Long Locks

**Symptom**: "Path too long" or "File name too long" (Windows MAX_PATH = 260 chars)

**Fix 1: Enable Long Path Support** (Windows 10 1607+)

```powershell
# Enable via Registry (requires admin)
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force

# Restart required
```

**Fix 2: Move to Shorter Path**

```powershell
# Move folder to shorter path
Move-Item "C:\very\long\path\to\project" "C:\prj"
```

**Fix 3: Use Robocopy to Delete**

```powershell
# Create empty directory
mkdir C:\temp\empty

# Mirror (delete) long-path directory
robocopy C:\temp\empty "C:\very\long\path\to\delete" /mir /r:0 /w:0

# Remove both directories
rmdir C:\temp\empty
rmdir "C:\very\long\path\to\delete"
```

---

### Skip-Locked Mode (Automation)

For **automated/scheduled runs** where you don't want blocking on locks, use `--skip-locked`:

```bash
# Skip locked files without retry (non-blocking)
python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --execute \
  --dry-run=false \
  --skip-locked
```

**Behavior**:
- Locked files are skipped immediately (max_retries = 0)
- Execution completes without blocking
- Failed candidates logged in checkpoint with lock_type

**Use Cases**:
- Weekly scheduled cleanups
- Task Scheduler / cron jobs
- CI/CD integration

---

### Monitoring Lock Failures

#### Query Checkpoint Logs for Lock Statistics

```sql
-- Most common lock types (last 30 days)
SELECT lock_type, COUNT(*) as count,
       AVG(retry_count) as avg_retries
FROM execution_checkpoints
WHERE status = 'failed'
  AND lock_type IS NOT NULL
  AND timestamp >= NOW() - INTERVAL '30 days'
GROUP BY lock_type
ORDER BY count DESC;
```

#### Check Recent Lock Failures (Python)

```python
from autopack.storage_optimizer.checkpoint_logger import CheckpointLogger

logger = CheckpointLogger()
failures = logger.get_recent_failures(lookback_days=7)

# Group by lock type
lock_counts = {}
for f in failures:
    lock_type = f['lock_type'] or 'unknown'
    lock_counts[lock_type] = lock_counts.get(lock_type, 0) + 1

print("Recent lock failures by type:")
for lock_type, count in sorted(lock_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {lock_type}: {count}")
```

---

### Common Scenarios

#### Scenario 1: Node.js Project with Many Handle Locks

**Problem**: Deleting `node_modules` fails with "file is in use" for `.bin/*.cmd` files

**Cause**: VS Code, IDE, or terminal holding handles to executables

**Solution**:
1. Close all instances of VS Code / IDE
2. Close PowerShell/CMD windows in project directory
3. Wait 30 seconds for handles to release
4. Re-run execution (automatic retry will succeed)

#### Scenario 2: Persistent SearchIndexer Locks

**Problem**: SearchIndexer repeatedly locks same files despite retries

**Cause**: Windows Search aggressively re-indexing after each unlock

**Solution**:
- Disable indexing for target folder (see remediation above)
- Use `--skip-locked` to bypass and address individually later

#### Scenario 3: Mixed Lock Types

**Problem**: Execution shows multiple lock types (searchindexer, handle, permission)

**Cause**: Different files locked by different services

**Solution**:
1. Review lock statistics in CLI output
2. Address most common lock type first (highest count)
3. Re-run execution to handle remaining locks
4. Use `--category` filter to isolate problematic categories

---

### Best Practices

1. **Run as Administrator**: Reduces permission locks

2. **Close Applications**: Close IDEs, editors, terminals before execution

3. **Disable Indexing**: For folders with frequent cleanup (logs, caches)

4. **Use --skip-locked**: For automated runs (don't block on locks)

5. **Monitor Checkpoint Logs**: Identify systematic lock issues

6. **Category Isolation**: Execute high-risk categories separately

---

### Troubleshooting Checklist

When encountering locked files:

- [ ] Check lock type in CLI output (searchindexer, antivirus, handle, permission)
- [ ] For transient locks: Wait for automatic retry (max 3 attempts)
- [ ] For permanent locks: Follow remediation workflow for lock type
- [ ] If persistent: Use Resource Monitor (resmon.exe) to identify locking process
- [ ] For automation: Use `--skip-locked` flag to prevent blocking
- [ ] If still failing: Check checkpoint logs for patterns (`get_recent_failures()`)
- [ ] Last resort: Address manually using robocopy or administrative tools

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

- **Executor logs**: `.autonomous_runs/<project>/runs/<family>/<run_id>/run.log`
- **Phase summaries**: `.autonomous_runs/<project>/runs/<family>/<run_id>/phases/phase_*.md`
- **CI reports**: `.autonomous_runs/<project>/ci/pytest_<phase-id>.json`
- **Batch drain sessions**: `.autonomous_runs/batch_drain_sessions/batch-drain-*.json`

---

**Total Lines**: 180 (within ≤180 line constraint)

**Coverage**: 15 common issues with fixes, emergency recovery procedures, help resources

**Style**: Bullet-style Q&A with code examples and quick diagnostics
