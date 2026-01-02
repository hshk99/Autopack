# Protection and Retention Policy

## Overview

This document defines the **unified protection and retention policy** shared by both the Tidy System and Storage Optimizer. It establishes clear rules for what can and cannot be automated, age-based cleanup eligibility, and system-specific behaviors.

**Policy File**: [config/protection_and_retention_policy.yaml](../config/protection_and_retention_policy.yaml)

## Core Principles

1. **Absolute Protections**: Certain paths are NEVER deleted, moved, or modified by any automation
2. **Age-Based Retention**: Non-protected files have retention windows (30/90/180 days or permanent)
3. **Category-Based Limits**: Storage Optimizer enforces per-category execution caps (GB, file count, retries)
4. **System-Specific Overrides**: Tidy and Storage Optimizer respect the same protections but with different behaviors

## Protected Paths (Absolute)

### What is Protected?

Protected paths are **NEVER** deleted, moved, or modified by Tidy or Storage Optimizer automation:

**Source Code & Tests**:
- `src/**` - All source code
- `tests/**` - All test files
- `**/*.py`, `**/*.js`, `**/*.ts` - Source files anywhere

**Version Control & CI/CD**:
- `.git/**` - Git repository
- `.github/**` - GitHub Actions workflows
- `.gitignore`, `.gitattributes` - Git configuration

**SOT (Source of Truth) Core Documents**:
- `docs/PROJECT_INDEX.json` - Project metadata
- `docs/BUILD_HISTORY.md` - Build ledger
- `docs/DEBUG_LOG.md` - Debug trail
- `docs/ARCHITECTURE_DECISIONS.md` - Design decisions
- `docs/FUTURE_PLAN.md` - Future work
- `docs/LEARNED_RULES.json` - Learned patterns
- `docs/CHANGELOG.md` - Version history

**Configuration Files**:
- `config/**` - All configuration
- `*.yaml`, `*.yml`, `*.json`, `*.toml` - Config formats
- `package.json`, `requirements.txt` - Dependency manifests

**Databases**:
- `*.db`, `*.sqlite`, `*.sqlite3` - All database files
- `autopack.db`, `fileorganizer.db`, `telemetry_*.db` - Specific DBs

**Audit Trails**:
- `archive/superseded/**` - Tidy consolidation history
- `.autonomous_runs/*/checkpoints/**` - Phase checkpoints
- `.autonomous_runs/*/execution.log` - Execution logs

**Active State**:
- `.autonomous_runs/active/**` - Currently running
- `.autonomous_runs/current_run.json` - Run metadata
- `venv/**` - Python virtual environment
- `node_modules/**` - Excluded from Tidy scanning/routing by convention; **not** an absolute protection (Storage Optimizer may recommend cleanup with approval)

### Why These Protections?

- **Source code**: Core project value, irreplaceable
- **SOT docs**: Single source of truth, historical record
- **Databases**: Operational data, cannot be regenerated
- **Audit trails**: Compliance, debugging, accountability
- **Config**: System behavior definition
- **VCS**: Repository integrity

## Retention Policies (Age-Based)

Retention policies apply to **non-protected paths only**. Protected paths are retained indefinitely regardless of age.

### Short-Term (30 days)

**Temporary files and caches**:
- `C:/Users/*/AppData/Local/Temp/**`
- `C:/Windows/Temp/**`
- `/tmp/**`
- `*.tmp`, `*.temp`

**Use Case**: System temp files, build intermediates

### Medium-Term (90 days)

**Development caches and diagnostics**:
- `.autonomous_runs/*/errors/**` - Error diagnostics
- `archive/diagnostics/**` - Diagnostic snapshots
- `**/node_modules/**` - Node.js dependencies
- `**/__pycache__/**` - Python bytecode
- `**/dist/**`, `**/build/**` - Build outputs
- `**/.pytest_cache/**` - Test caches

**Use Case**: Development artifacts that can be regenerated

### Long-Term (180 days)

**Archived runs and user downloads**:
- `archive/runs/**` - Archived run data
- `C:/Users/*/Downloads/**` - User downloads
- `C:/Users/*/AppData/Local/Microsoft/Windows/INetCache/**` - Browser cache

**Use Case**: Historical data, user files (suggest cleanup)

### Permanent Retention

**Never age out** (but can be manually cleaned):
- `archive/superseded/**` - SOT consolidation history
- `docs/**` - All documentation
- `.autonomous_runs/*/checkpoints/**` - Execution checkpoints
- `*.db` - Databases (also protected)

**Use Case**: Historical record, compliance, audit trail

## Category-Specific Policies (Storage Optimizer)

Storage Optimizer uses category-based policies for execution limits.

### dev_caches

**Description**: Development tool caches and dependencies

**Patterns**:
- `**/node_modules/**`, `**/__pycache__/**`
- `**/dist/**`, `**/build/**`
- `**/.pytest_cache/**`, `**/target/**` (Rust), `**/.gradle/**`

**Retention**: 90 days
**Execution Limits**:
- Max GB per run: 50 GB
- Max files per run: 1000
- Max retries: 3 (for locked files)
- Retry backoff: [2s, 5s, 10s]

### diagnostics_logs

**Description**: Diagnostic logs and error snapshots

**Patterns**:
- `archive/diagnostics/**`
- `.autonomous_runs/*/errors/**`
- `*.log`

**Retention**: 90 days
**Execution Limits**:
- Max GB per run: 10 GB
- Max files per run: 500
- Max retries: 2
- Retry backoff: [2s, 5s]

### runs

**Description**: Archived autonomous run data

**Patterns**:
- `archive/runs/**`
- `.autonomous_runs/*/output/**`

**Retention**: 180 days
**Execution Limits**:
- Max GB per run: 20 GB
- Max files per run: 1000
- Max retries: 3
- Retry backoff: [2s, 5s, 10s]

### archive_buckets

**Description**: Superseded/archived documents

**Patterns**:
- `archive/superseded/**`

**Retention**: Permanent (never auto-delete)
**Execution Limits**:
- Max GB per run: 0 (disabled - protected)
- Max files per run: 0

## System-Specific Behaviors

### Tidy System

**Respects SOT Markers**:
- Content within `<!-- SOT_SUMMARY_START -->` ... `<!-- SOT_SUMMARY_END -->` is never consolidated
- `README.md` has SOT markers, so it's skipped

**Skip Patterns**:
- README.md (has SOT summary)
- Protected paths (listed above)

**Consolidation Target**:
- Scattered markdown files → SOT ledgers (BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS)

### Storage Optimizer

**Can Analyze Protected Paths**:
- Protected paths are scanned for size reporting
- Shown in disk usage statistics
- NEVER suggested for deletion

**Cannot Delete Protected Paths**:
- Protected paths filtered out before approval workflow
- Approval requests for protected paths rejected with error

**Respects Retention**:
- Age-based filtering before suggesting cleanup
- Only suggests files older than category retention window

## Usage Examples

### Storage Optimizer: Check Policy Compliance

```python
from autopack.storage_optimizer.policy import load_policy

policy = load_policy("config/protection_and_retention_policy.yaml")

# Check if path is protected
is_protected = policy.is_protected("docs/BUILD_HISTORY.md")
# Returns: True

# Check if path matches category
category = policy.match_category("C:/dev/project/node_modules/pkg/index.js")
# Returns: "dev_caches"

# Get retention window
retention = policy.get_retention_days("dev_caches")
# Returns: 90
```

### Tidy: Skip Protected Paths

```python
# Tidy consolidate_docs_v2.py already implements this
if any(Path(doc).match(glob) for glob in PROTECTED_GLOBS):
    print(f"[SKIP] Protected: {doc}")
    continue
```

### Manual Cleanup Validation

Before manually deleting files, check the policy:

```bash
# Check if path is protected
grep -E "docs/BUILD_HISTORY.md" config/protection_and_retention_policy.yaml

# Check retention window
grep -A 5 "dev_caches:" config/protection_and_retention_policy.yaml
```

## Policy Maintenance

### When to Update the Policy

1. **New protected path identified**: Add to `protected_paths` section
2. **New category added**: Add to `categories` section with retention + limits
3. **Retention window change**: Update `retention_days` for category
4. **Execution limit change**: Update `execution_limits` for category

### Update Process

1. Edit [config/protection_and_retention_policy.yaml](../config/protection_and_retention_policy.yaml)
2. Increment `version` field (e.g., "1.0" → "1.1")
3. Update `date` field
4. Test with `load_policy()` to ensure YAML is valid
5. Commit with message: `config: Update protection policy (v1.1) - <reason>`

### Validation

```bash
# Test policy loads correctly
python -c "from autopack.storage_optimizer.policy import load_policy; p = load_policy('config/protection_and_retention_policy.yaml'); print(f'Policy v{p.version} loaded successfully')"
```

## Future Enhancements (BUILD-154+)

### Database Retention (Not Yet Implemented)

**Planned**: Automatic cleanup of old database records

**Tables**:
- `execution_checkpoints` - 90 days
- `llm_usage_events` - 180 days
- `storage_scans` - 365 days

**Implementation**:
```sql
-- Example cleanup query (future)
DELETE FROM execution_checkpoints
WHERE timestamp < NOW() - INTERVAL '90 days';
```

**Status**: Disabled (enabled: false in policy)

### Cross-System Routing

**Planned**: Storage Optimizer suggests files → Tidy consolidates them

**Example**:
- Storage Optimizer finds scattered markdown in `archive/reports/`
- Suggests: "These files match Tidy consolidation patterns"
- User runs: `python scripts/tidy/consolidate_docs_v2.py`

**Status**: Manual workflow (future automation)

## Troubleshooting

### Protected Path Incorrectly Flagged for Deletion

**Symptom**: Storage Optimizer suggests deleting a protected path

**Diagnosis**:
```bash
# Check if path is in protected_globs
grep -E "your/path/here" config/protection_and_retention_policy.yaml
```

**Fix**:
1. Add missing glob to `protected_paths` section
2. Re-run scan: `python scripts/storage/scan_and_report.py --root C:/dev`
3. Verify path is now protected

### Category Retention Window Too Short

**Symptom**: Recent files suggested for cleanup

**Diagnosis**:
```bash
# Check category retention
grep -A 10 "dev_caches:" config/protection_and_retention_policy.yaml
```

**Fix**:
1. Update `retention_days` in policy YAML
2. Re-load policy: `load_policy("config/protection_and_retention_policy.yaml")`

### Tidy Consolidating Protected Docs

**Symptom**: SOT documents being moved to archive/superseded/

**Diagnosis**:
```bash
# Check if doc has SOT markers
grep -C 5 "SOT_SUMMARY_START" docs/BUILD_HISTORY.md
```

**Fix**:
1. Add `<!-- SOT_SUMMARY_START -->` ... `<!-- SOT_SUMMARY_END -->` markers
2. Or add to `protected_paths` in policy YAML

## See Also

- [Storage Optimizer MVP Completion](STORAGE_OPTIMIZER_MVP_COMPLETION.md) - Core features
- [Storage Optimizer Automation](STORAGE_OPTIMIZER_AUTOMATION.md) - Scheduled scans + delta reporting
- [Tidy System Usage](TIDY_SYSTEM_USAGE.md) - Tidy consolidation workflow
- [BUILD-153 Canary Test Report](BUILD-153_CANARY_TEST_REPORT.md) - Execution validation
