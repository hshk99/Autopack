# Tidy Database Logging Implementation

**Date**: 2025-12-13
**Status**: 🚧 IN PROGRESS

---

## Requirements (From User)

1. ✅ **Database logging for manual tidy** - TidyLogger integrated into consolidate_docs_v2.py
2. 🚧 **Replace audit reports with database entries** - Modifying autonomous_tidy.py
3. ⏳ **Clean up obsolete archive/ files** - After consolidation (NEXT)
4. ⏳ **Prevent random file creation in archive/** - Configuration needed

---

## Changes Made

### 1. consolidate_docs_v2.py ✅

**Location**: Lines 17-30, 523-557, 1036-1044, 1067-1074, 1097-1104

**Changes**:
- Added `uuid` import
- Added sys.path for tidy_logger import
- Modified `__init__` to accept `run_id` and `project_id`
- Initialized `TidyLogger` in __init__
- Added database logging after each entry creation (BUILD, DEBUG, DECISION)

**Logging Format**:
```python
self.logger.log(
    run_id=self.run_id,
    action="consolidate",
    src=str(file_path.relative_to(self.project_dir)),
    dest="docs/BUILD_HISTORY.md",  # or DEBUG_LOG.md or ARCHITECTURE_DECISIONS.md
    reason=f"BUILD entry: {entry_id} - {status}"
)
```

### 2. autonomous_tidy.py 🚧

**Location**: Lines 21-33, 39-52

**Changes**:
- Added `uuid` import
- Added `TidyLogger` import
- Modified `PreTidyAuditor.__init__` to accept `run_id` and `project_id`
- Initialized `TidyLogger` in PreTidyAuditor

**TODO**:
- Modify `PostTidyAuditor.__init__` similarly
- Replace `_generate_report()` with database logging in both Auditors
- Modify `AutonomousTidy.run()` to pass run_id to all components

---

## Database Schema (Existing)

### Table: tidy_activity
```sql
create table tidy_activity (
    id serial primary key,
    run_id text,
    project_id text,
    action text,
    src text,
    dest text,
    reason text,
    src_sha text,
    dest_sha text,
    ts timestamptz not null default now()
);
```

**Usage**:
- `run_id`: UUID for each tidy execution (tracks all actions in one run)
- `project_id`: "autopack" or specific project name
- `action`: "consolidate", "audit_pre", "audit_post", etc.
- `src`: Source file path (e.g., "archive/reports/API_KEY_FIX.md")
- `dest`: Destination SOT file (e.g., "docs/DEBUG_LOG.md")
- `reason`: Human-readable reason (e.g., "DEBUG entry: DBG-001 - IMPLEMENTED")
- `ts`: Timestamp (automatically set)

---

## Audit Report Replacement Strategy

### Current (Markdown Reports)
```
PRE_TIDY_AUDIT_REPORT.md:
- File type distribution
- Routing recommendations
- Special handling cases

POST_TIDY_VERIFICATION_REPORT.md:
- SOT file validation
- Git status
- Verification results
```

### New (Database Logging)
```python
# Pre-Tidy Auditor logs:
logger.log(run_id, "audit_pre", src="archive", dest=None,
           reason=f"Scanned {total_files} files")

logger.log(run_id, "audit_pre_routing", src=file_path, dest=category,
           reason=f"Recommended: {category}")

logger.log(run_id, "audit_pre_special", src=file_path, dest=None,
           reason=f"Special handling: {reason}")

# Post-Tidy Auditor logs:
logger.log(run_id, "audit_post", src=None, dest="docs/BUILD_HISTORY.md",
           reason=f"Verified: {entry_count} entries")

logger.log(run_id, "audit_post_commit", src=None, dest=None,
           reason=f"Auto-committed: {commit_sha}")
```

### Query Examples
```sql
-- Get all actions for a specific tidy run
SELECT * FROM tidy_activity WHERE run_id = 'abc-123' ORDER BY ts;

-- Get tidy history for last 7 days
SELECT run_id, COUNT(*) as files_processed, MIN(ts) as started_at
FROM tidy_activity
WHERE ts > NOW() - INTERVAL '7 days'
GROUP BY run_id
ORDER BY started_at DESC;

-- Get all files consolidated to BUILD_HISTORY
SELECT src, reason, ts
FROM tidy_activity
WHERE dest = 'docs/BUILD_HISTORY.md'
ORDER BY ts DESC;
```

---

## Next Steps

### 2. Complete autonomous_tidy.py modifications
- [ ] Modify PostTidyAuditor.__init__ to add TidyLogger
- [ ] Replace _generate_report() in PreTidyAuditor with database logging
- [ ] Replace _generate_report() in PostTidyAuditor with database logging
- [ ] Modify AutonomousTidy.run() to generate and pass run_id

### 3. Clean up obsolete archive/ files (USER REQUEST #3)
- [ ] Inspect BUILD_HISTORY.md, DEBUG_LOG.md, ARCHITECTURE_DECISIONS.md
- [ ] Identify source files that were successfully consolidated
- [ ] Delete/archive obsolete files in archive/ directory
- [ ] Keep only: archive/prompts/, archive/tidy_v7/, archive/research/active/

### 4. Configure archive/ output restrictions (USER REQUEST #4)
- [ ] Create archive/.gitignore or validation rules
- [ ] Prevent Autopack from creating files in archive/ (except specific subdirs)
- [ ] Document allowed output locations

---

## Testing

### Test Database Logging
```bash
# Run manual tidy with database logging
DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
python scripts/tidy/consolidate_docs_v2.py --execute

# Check database
psycopg2-shell "postgresql://autopack:autopack@localhost:5432/autopack"
> SELECT * FROM tidy_activity ORDER BY ts DESC LIMIT 10;
```

### Test Autonomous Tidy
```bash
# Run autonomous tidy with database logging
DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
python scripts/tidy/autonomous_tidy.py archive --execute

# Verify no markdown reports generated
ls -la PRE_TIDY_AUDIT_REPORT.md POST_TIDY_VERIFICATION_REPORT.md
```

---

## Benefits

✅ **Queryable History** - SQL queries instead of grepping markdown files
✅ **Structured Data** - Timestamps, run tracking, source→dest mapping
✅ **No Clutter** - No markdown report files in repo root
✅ **Integration Ready** - Can be queried by dashboard/API
✅ **Audit Trail** - Complete traceable history of all tidy operations

---

**END OF IMPLEMENTATION GUIDE**
