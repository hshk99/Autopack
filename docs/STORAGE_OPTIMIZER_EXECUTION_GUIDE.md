# Storage Optimizer Execution Guide (BUILD-152)

**Version:** 1.0
**Last Updated:** 2026-01-02
**Status:** Production-ready

## Overview

This guide covers **Storage Optimizer execution mode** with advanced safeguards introduced in BUILD-152:

- **Category execution caps**: GB/file limits to prevent runaway deletion
- **Checkpoint logging**: SHA256-based audit trail for idempotency and debugging
- **Lock-aware execution**: Intelligent retry logic for transient Windows file locks
- **Enhanced CLI**: Progress reporting with lock statistics and remediation hints

## Quick Start

### Basic Execution Workflow (Database-Based)

```bash
# Step 1: Scan for cleanup candidates
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-target C:/dev \
  --save-to-db

# Step 2: Review candidates (interactive approval)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --interactive \
  --approved-by "john.doe"

# Step 3: Execute deletion (DRY RUN first)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --execute \
  --dry-run

# Step 4: Execute deletion (ACTUAL)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --execute \
  --dry-run=false
```

### Approval Artifact Workflow (File-Based - BUILD-166)

**New in BUILD-166**: Generate approval artifacts from scan reports for safer execution.

```bash
# Step 1: Scan and generate report
python scripts/storage/scan_and_report.py \
  --dir C:/target \
  --report-out report.json

# Step 2: Review report.json manually (human approval step)
# Open report.json and verify cleanup candidates are safe to delete

# Step 3: Generate approval artifacts
python scripts/storage/generate_approval.py \
  --report report.json \
  --operator "Your Name" \
  --out approval.json

# Step 4: Execute cleanup with approval validation
python scripts/storage/scan_and_report.py \
  --dir C:/target \
  --execute \
  --approval-file approval.json
```

**Why use approval artifacts?**
- **Audit trail**: Operator name + timestamp in approval_audit.log
- **Safety**: Execution validates approval file exists before deletion
- **Expiry**: Approvals expire after 7 days (configurable with --expiry-days)
- **Binding**: Approval tied to specific scan report via content hash

### Automated Workflow (Skip Locked Files)

For automated/scheduled runs where you don't want blocking on locked files:

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --execute \
  --dry-run=false \
  --skip-locked
```

**Note**: `--skip-locked` disables retry logic, immediately skipping any locked files.

## Configuration

### Category Execution Caps

Category caps are defined in `config/protection_and_retention_policy.yaml` under each category's `execution_limits` section:

```yaml
categories:
  dev_caches:
    match_globs:
      - "**/node_modules/**"
      - "**/.next/**"
      - "**/__pycache__/**"
    allowed_actions:
      delete:
        enabled: true
        requires_approval: false
    execution_limits:
      max_gb_per_run: 50           # Stop after 50GB deleted
      max_files_per_run: 1000      # Stop after 1000 files deleted
      max_retries: 3               # Retry locked files 3 times
      retry_backoff_seconds: [2, 5, 10]  # Exponential backoff timing
```

### Cap Enforcement Behavior

When a cap is reached during execution:
1. **Execution stops immediately** for that category
2. **Remaining candidates stay in "approved" state** (can be executed later)
3. **Cap exceeded message** displayed in CLI output
4. **Partial completion counted** in execution results

Example output when cap is reached:

```
CATEGORY CAP REACHED:
  dev_caches: Stopped at 50.0 GB limit (45.2 GB deleted, 123 candidates remaining)
  Remaining candidates: 123
```

### Retry Configuration

Retry behavior is controlled per lock type:

| Lock Type       | Default Retries | Backoff (seconds) | Rationale                          |
|-----------------|-----------------|-------------------|------------------------------------|
| `searchindexer` | 3               | [2, 5, 10]        | Windows Search releases quickly    |
| `antivirus`     | 2               | [10, 30, 60]      | Scans take 5-15 minutes            |
| `handle`        | 3               | [2, 5, 10]        | User may close app soon            |
| `permission`    | 0               | N/A               | Permanent (needs admin/fix)        |
| `path_too_long` | 0               | N/A               | Permanent (needs path shortening)  |

**Override global retry count** in policy YAML:

```yaml
execution_limits:
  max_retries: 5  # Override default retry counts
```

## CLI Reference

### Execution Flags

| Flag              | Type    | Default | Description                                          |
|-------------------|---------|---------|------------------------------------------------------|
| `--execute`       | Boolean | False   | Execute approved deletions (DANGER: actual deletion) |
| `--dry-run`       | Boolean | True    | Preview actions without executing                    |
| `--scan-id`       | Integer | N/A     | Scan ID to operate on                                |
| `--category`      | String  | None    | Filter to specific category (e.g., `dev_caches`)     |
| `--skip-locked`   | Boolean | False   | Skip locked files without retry (for automation)     |
| `--compress`      | Boolean | False   | Compress files before deletion                       |

### Example Usage

#### Execute Single Category

```bash
# Only delete dev_caches category
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --execute \
  --dry-run=false \
  --category dev_caches
```

#### Skip Locked Files (Automation Mode)

```bash
# Don't wait for locked files - skip immediately
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --execute \
  --dry-run=false \
  --skip-locked
```

#### Compress Before Delete

```bash
# Archive files as .tar.gz before deleting
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/storage/scan_and_report.py \
  --scan-id 123 \
  --execute \
  --dry-run=false \
  --compress
```

Compressed archives stored in: `archive/superseded/storage_cleanup_{timestamp}/`

## Execution Output

### Standard Output (BUILD-152)

```
[EXECUTION] Starting cleanup (dry_run=False, compress=False)...
[EXECUTION] Category filter: dev_caches
[EXECUTION] Skip-locked mode: locked files will be skipped without retry

================================================================================
EXECUTION RESULTS (BUILD-152)
================================================================================
Total candidates: 250
✓ Successful:     200
✗ Failed:         30
⏸ Skipped:        20
Success rate:     80.0%
Freed space:      45.23 GB
Duration:         123s

LOCK STATISTICS:
  Locked files encountered: 30
  Files retried:            15

  Lock types:
    handle: 18 files
    permission: 7 files
    searchindexer: 5 files

CATEGORY CAP REACHED:
  dev_caches: Stopped at 50.0 GB limit (45.2 GB deleted, 50 candidates remaining)
  Remaining candidates: 50

FAILED DELETIONS:
  ✗ C:/dev/project/node_modules/package/.bin/file.cmd
    Error: permission: Access is denied
    → Insufficient permissions. Options: (1) Run PowerShell/CLI as Administrator...
```

### Lock Statistics Breakdown

- **Locked files encountered**: Total files that hit a lock during execution
- **Files retried**: Files that were retried (at least once) before success/failure
- **Lock types**: Grouping by detected lock type

## Checkpoint Logging

### Dual-Write Pattern

All executions are logged to:

1. **Primary**: PostgreSQL `execution_checkpoints` table
2. **Fallback**: JSONL at `.autonomous_runs/storage_execution.log`

### Schema

```sql
CREATE TABLE execution_checkpoints (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,                -- e.g., "scan-123-20260102-143052"
    candidate_id INTEGER,                -- FK to cleanup_candidates
    action TEXT NOT NULL,                -- 'delete' | 'compress'
    path TEXT NOT NULL,
    size_bytes BIGINT,
    sha256 TEXT,                         -- For idempotency
    status TEXT NOT NULL,                -- 'completed' | 'failed' | 'skipped'
    error TEXT,
    lock_type TEXT,                      -- 'searchindexer' | 'antivirus' | etc.
    retry_count INTEGER DEFAULT 0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Querying Checkpoints

**Recent executions:**

```sql
SELECT run_id, COUNT(*) as total,
       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
FROM execution_checkpoints
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY run_id
ORDER BY MAX(timestamp) DESC;
```

**Failed deletions with lock types:**

```sql
SELECT path, error, lock_type, retry_count, timestamp
FROM execution_checkpoints
WHERE status = 'failed'
  AND timestamp >= NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC
LIMIT 50;
```

**Deleted files by SHA256 (for idempotency):**

```sql
SELECT DISTINCT sha256, path, timestamp
FROM execution_checkpoints
WHERE action = 'delete'
  AND status = 'completed'
  AND sha256 IS NOT NULL
  AND timestamp >= NOW() - INTERVAL '90 days';
```

### Idempotency Checking

Storage Optimizer uses SHA256 checksums to prevent re-suggesting deleted files:

1. **Before deletion**: Compute SHA256 of file/directory
2. **Log to checkpoint**: Store SHA256 in `execution_checkpoints.sha256`
3. **Next scan**: Query deleted checksums from last 90 days
4. **Filter candidates**: Skip files matching deleted SHA256s

**Manual idempotency check:**

```python
from autopack.storage_optimizer.checkpoint_logger import CheckpointLogger

logger = CheckpointLogger()
deleted = logger.get_deleted_checksums(lookback_days=90)
print(f"Deleted files in last 90 days: {len(deleted)}")
```

## Lock Handling

### Lock Detection

Storage Optimizer detects lock types via exception message pattern matching:

| Lock Type       | Detection Patterns                                      | Classification |
|-----------------|---------------------------------------------------------|----------------|
| `searchindexer` | "searchindexer", "windows search", "indexing service"   | Transient      |
| `antivirus`     | "virus", "defender", "malware", "security"              | Transient      |
| `handle`        | "being used by another process", "file is in use"       | Transient      |
| `permission`    | "access is denied", "permission denied"                 | Permanent      |
| `path_too_long` | "path too long", "exceeds maximum path"                 | Permanent      |
| `unknown`       | (no match)                                              | Permanent      |

### Retry Logic

**Transient locks** (searchindexer, antivirus, handle):
- Automatically retried with exponential backoff
- Retry count controlled by `execution_limits.max_retries`
- Backoff timing: `[2, 5, 10]` seconds by default

**Permanent locks** (permission, path_too_long):
- Not retried (max_retries = 0)
- Logged with remediation hint
- User action required

### Remediation Hints

When a lock fails, remediation hints are displayed in CLI output:

**Example:**

```
✗ C:/dev/project/logs/app.log
  Error: searchindexer: Windows Search is indexing this file
  → Windows Search is indexing this file. Options: (1) Wait 30-60s and retry,
    (2) Disable indexing for this folder, (3) Run: resmon.exe → CPU →
    Associated Handles to verify
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#storage-optimizer-locked-files) for detailed remediation workflows.

## Safety Features

### Protected Paths

Storage Optimizer **never deletes** paths matching protection rules in `config/protection_and_retention_policy.yaml`:

```yaml
paths:
  protected_globs:
    - "**/src/**"              # Source code
    - "**/tests/**"            # Test suites
    - "**/.git/**"             # Git repositories
    - "**/config/**"           # Configuration
    - "**/docs/**"             # Documentation
    - "**/*.db"                # Databases
```

**Enforcement**: Pre-execution validation checks all candidates against protected globs. Any match is **automatically skipped**.

### Send2Trash (Recycle Bin)

All deletions go through `send2trash` library:
- Files sent to **Windows Recycle Bin** (not permanent deletion)
- Can be restored via Recycle Bin UI if needed
- Extra safety layer for accidental deletions

**Note**: Directories are deleted recursively (entire directory sent to Recycle Bin).

### Dry Run Default

The `--dry-run` flag defaults to `True` for safety:
- Must explicitly pass `--dry-run=false` to execute
- Dry run shows execution plan without modifying files
- Review dry run output before real execution

## Monitoring & Debugging

### Real-Time Progress

During execution, monitor progress via CLI output:

```
[INFO] [RETRY 1/3] C:/temp/file.log locked by searchindexer, retrying in 2s
[INFO] ✓ Deleted C:/temp/file.log after 1 retries
[WARNING] [LOCKED] C:/dev/protected.db - permission: Insufficient permissions...
```

### Execution Statistics

After execution, review summary statistics:

```
EXECUTION RESULTS (BUILD-152)
Total candidates: 250
✓ Successful:     200
✗ Failed:         30
⏸ Skipped:        20
Success rate:     80.0%
Freed space:      45.23 GB
Duration:         123s
```

### Checkpoint Log Analysis

Query PostgreSQL for execution history:

```sql
-- Executions in last 7 days
SELECT run_id, COUNT(*) as files,
       SUM(size_bytes) / (1024*1024*1024.0) as freed_gb
FROM execution_checkpoints
WHERE status = 'completed'
  AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY run_id
ORDER BY MAX(timestamp) DESC;
```

### Lock Failure Analysis

Identify problematic lock types:

```sql
-- Most common lock types
SELECT lock_type, COUNT(*) as count,
       AVG(retry_count) as avg_retries
FROM execution_checkpoints
WHERE status = 'failed'
  AND lock_type IS NOT NULL
  AND timestamp >= NOW() - INTERVAL '30 days'
GROUP BY lock_type
ORDER BY count DESC;
```

## Best Practices

### 1. Start with Dry Run

**Always run dry run first** to preview execution plan:

```bash
# Dry run (safe)
python scripts/storage/scan_and_report.py --scan-id 123 --execute --dry-run

# Review output, then execute for real
python scripts/storage/scan_and_report.py --scan-id 123 --execute --dry-run=false
```

### 2. Use Category Filters

**Execute high-risk categories separately** to minimize blast radius:

```bash
# Safe categories first (dev_caches, temp_files)
python scripts/storage/scan_and_report.py --scan-id 123 --execute --category dev_caches

# Review results, then proceed to next category
python scripts/storage/scan_and_report.py --scan-id 123 --execute --category diagnostics_logs
```

### 3. Set Conservative Caps

**Start with low caps** for initial runs, then increase:

```yaml
# Initial run: conservative caps
execution_limits:
  max_gb_per_run: 10
  max_files_per_run: 100

# After validation: increase caps
execution_limits:
  max_gb_per_run: 50
  max_files_per_run: 1000
```

### 4. Monitor Checkpoint Logs

**Check execution_checkpoints regularly** for failures:

```bash
# View recent failures
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.storage_optimizer.checkpoint_logger import CheckpointLogger
logger = CheckpointLogger()
failures = logger.get_recent_failures(lookback_days=7)
for f in failures[:10]:
    print(f\"{f['path']}: {f['lock_type']} - {f['error']}\")
"
```

### 5. Use --skip-locked for Automation

**For scheduled/automated runs**, use `--skip-locked` to prevent blocking:

```bash
# Task Scheduler / cron job
0 2 * * 0 cd /c/dev/Autopack && python scripts/storage/scan_and_report.py \
  --scan-id latest \
  --execute \
  --dry-run=false \
  --skip-locked
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#storage-optimizer-locked-files) for:

- Windows lock remediation runbook
- Lock type identification steps
- resmon.exe usage guide
- Sysinternals handle.exe workflows
- Common error scenarios and solutions

## Examples

### Example 1: Interactive Approval → Execution

```bash
# Step 1: Scan
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/storage/scan_and_report.py \
  --scan-target C:/dev \
  --save-to-db

# Output: Scan ID: 42

# Step 2: Interactive approval
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/storage/scan_and_report.py \
  --scan-id 42 \
  --interactive \
  --approved-by "john.doe"

# Approve categories: dev_caches, temp_files

# Step 3: Dry run
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/storage/scan_and_report.py \
  --scan-id 42 \
  --execute \
  --dry-run

# Review output

# Step 4: Execute
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/storage/scan_and_report.py \
  --scan-id 42 \
  --execute \
  --dry-run=false
```

### Example 2: Automated Weekly Cleanup

```bash
#!/bin/bash
# weekly_cleanup.sh

# Set environment
export PYTHONUTF8=1
export PYTHONPATH=src
export DATABASE_URL="sqlite:///autopack.db"

# Run scan
scan_output=$(python scripts/storage/scan_and_report.py \
  --scan-target C:/dev \
  --save-to-db)

# Extract scan ID (assumes output format: "Scan ID: 123")
scan_id=$(echo "$scan_output" | grep "Scan ID:" | awk '{print $3}')

# Auto-approve safe categories (dev_caches only)
# NOTE: This requires implementing auto-approval logic

# Execute with skip-locked (don't block on locks)
python scripts/storage/scan_and_report.py \
  --scan-id "$scan_id" \
  --execute \
  --dry-run=false \
  --category dev_caches \
  --skip-locked

# Send notification (optional)
echo "Weekly cleanup complete: Scan ID $scan_id"
```

### Example 3: Lock Remediation Workflow

```bash
# Step 1: Execute with retry enabled
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/storage/scan_and_report.py \
  --scan-id 42 \
  --execute \
  --dry-run=false

# Output shows locked files:
# ✗ C:/dev/project/logs/app.log - searchindexer

# Step 2: Identify locking process with resmon.exe
# (See TROUBLESHOOTING.md for detailed steps)

# Step 3: Retry after addressing lock
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/storage/scan_and_report.py \
  --scan-id 42 \
  --execute \
  --dry-run=false \
  --category diagnostics_logs  # Only retry this category
```

## Related Documentation

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md#storage-optimizer-locked-files) - Lock remediation runbook
- [config/protection_and_retention_policy.yaml](../config/protection_and_retention_policy.yaml) - Policy configuration (canonical)
- [BUILD-152 Plan](../docs/plans/BUILD-152.md) - Implementation details
- [Storage Optimizer API](.autonomous_runs/file-organizer-app-v1/src/frontend/node_modules/postcss-selector-parser/API.md#storage-optimizer) - API endpoints

## Changelog

### BUILD-152 (2026-01-02)
- ✅ Added category execution caps (GB/file limits)
- ✅ Implemented checkpoint logging (PostgreSQL + JSONL)
- ✅ Added lock-aware execution with retry logic
- ✅ Enhanced CLI with progress reporting and `--skip-locked` flag
- ✅ Created execution guide and troubleshooting runbook

### BUILD-151 (2025-12-XX)
- ✅ Policy-driven scanning and classification
- ✅ Protected path enforcement
- ✅ PostgreSQL schema and migrations
- ✅ Execution engine with send2trash
- ✅ Approval workflow state machine
- ✅ Intelligence features (pattern learning, recommendations)
