# Critical Issues Implementation Plan

**Date**: 2025-12-10
**Run Context**: Test run backlog-maintenance-1765288552
**Status**: Investigation Complete - Ready for Implementation

## Executive Summary

Investigation of test run `backlog-maintenance-1765288552` revealed 5 critical issues affecting Autopack's observability, context awareness, and automation capabilities. This document provides comprehensive analysis and implementation plans for each issue.

**Critical Finding**: The database logging system for major plan changes (PlanChange table) is NOT wired into backlog maintenance workflow, meaning CONSOLIDATED_DEBUG.md updates and architectural changes are not being tracked for future context awareness.

---

## Issue 1: Missing Qdrant Collection Auto-Creation

### Status: **NOT A BUG - Working As Designed**

### Investigation Findings

**Expected Behavior**:
- Qdrant collections are created via `ensure_collection()` during MemoryService initialization
- Collections: `code_docs`, `run_summaries`, `errors_ci`, `doctor_hints`, `planning`

**What Actually Happens**:
- Collections ARE created successfully during init (lines 124-130 in [memory_service.py](../src/autopack/memory/memory_service.py#L124-L130))
- 404 errors occur when trying to write to collections that were NEVER initialized

**Root Cause**:
The backlog maintenance script ([run_backlog_maintenance.py](../scripts/run_backlog_maintenance.py)) does NOT instantiate a MemoryService with Qdrant backend. Instead:

1. Line 141-153: Creates memory service only for writing decision logs
2. The memory service is created WITHOUT initializing collections
3. Writes to `decision_logs`, `task_outcomes`, `error_patterns` collections that don't exist
4. Only `code_docs` and `run_summaries` exist because they were created in previous executor runs

**Evidence**:
```python
# scripts/run_backlog_maintenance.py lines 141-153
if memory and memory.enabled:
    try:
        memory.write_decision_log(
            trigger="backlog_maintenance",
            choice=f"diagnostics:{item.id}",
            # ... writes to planning collection that DOES exist
        )
    except Exception:
        pass  # Silently swallows 404 errors
```

### Solution

**Option A: Ensure Collections During Backlog Maintenance Initialization** (RECOMMENDED)
- Initialize MemoryService properly at script startup
- Let `ensure_collection()` create missing collections
- Collections persist across runs

**Option B: Create Collections Explicitly**
- Add explicit collection creation in backlog maintenance script
- Less elegant but more explicit

### Implementation Steps

1. **Modify scripts/run_backlog_maintenance.py**:
   ```python
   # Around line 50-60, after parsing args
   memory = None
   if config.get("enable_memory", False):
       from autopack.memory.memory_service import MemoryService
       memory = MemoryService(
           enabled=True,
           use_qdrant=config.get("use_qdrant", False)
       )
       logger.info(f"[Memory] Initialized with backend={memory.backend}")
   ```

2. **Remove silent exception swallowing**:
   ```python
   # Change line 152 from:
   except Exception:
       pass

   # To:
   except Exception as e:
       logger.warning(f"[Memory] Failed to write decision log: {e}")
   ```

3. **Test**:
   ```bash
   # Verify collections exist after init
   PYTHONPATH=src python -c "
   from autopack.memory.memory_service import MemoryService
   m = MemoryService(use_qdrant=True)
   print(f'Backend: {m.backend}')
   "

   # Run backlog maintenance and verify no 404 errors
   PYTHONPATH=src python scripts/run_backlog_maintenance.py \
     --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
     --max-items 2
   ```

### Success Criteria
- [ ] All 5 collections exist after MemoryService init
- [ ] No 404 errors in backlog maintenance logs
- [ ] Decision logs successfully written to planning collection

---

## Issue 2: rules_updated.json Status and Wiring

### Status: **WORKING CORRECTLY ✅**

### Investigation Findings

**File Location**: `C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1\rules_updated.json`

**Current State**:
```json
{
  "last_updated": "2025-12-09T04:28:20.407111+00:00",
  "last_run_id": "fileorg-p2-20251208t",
  "promoted_this_run": 171,
  "total_rules": 56,
  "update_history": [...]
}
```

**Wiring Status**:
- ✅ **Write Path**: [autonomous_executor.py:716-762](../src/autopack/autonomous_executor.py#L716-L762) - `_mark_rules_updated()` updates file after rule promotion
- ✅ **Read Path**: [autonomous_executor.py:649-655](../src/autopack/autonomous_executor.py#L649-L655) - Tracks mtime during init
- ✅ **Mid-Run Refresh**: [autonomous_executor.py:659-676](../src/autopack/autonomous_executor.py#L659-L676) - `_refresh_project_rules_if_updated()` reloads rules if mtime advances
- ✅ **Cleanup Protection**: [tidy_workspace.py:66](../scripts/tidy_workspace.py#L66) - Marked as artifact to keep

**Evidence**:
- File contains 10 update history entries (lines 6-57)
- Last updated Dec 9, 2025 with 171 rules promoted
- System correctly tracking rule evolution across runs

### Solution

**NO ACTION REQUIRED** - System working as designed.

### Potential Enhancement (Optional)

Add rules_updated.json timestamp check to pre-publication checklist:

```python
# scripts/pre_publish_checklist.py
def check_rules_currency(self):
    """Check if project rules are up to date"""
    rules_marker = self.project_path / "rules_updated.json"
    if rules_marker.exists():
        data = json.loads(rules_marker.read_text())
        days_old = (datetime.now() - datetime.fromisoformat(data['last_updated'])).days
        if days_old > 30:
            self.results.append(CheckResult(
                "Project Rules",
                False,
                f"Rules last updated {days_old} days ago. Consider refreshing.",
                "warning"
            ))
```

---

## Issue 3: Database Logging System Failure (CRITICAL)

### Status: **MAJOR GAP - NOT WIRED INTO BACKLOG MAINTENANCE**

### Investigation Findings

**What Should Happen**:
1. CONSOLIDATED_DEBUG.md changes should trigger PlanChange DB entries
2. Major architectural changes (PostgreSQL migration, Qdrant integration) should be logged
3. Re-planned phases should record PlanChange entries
4. Context awareness for subsequent tasks via DB queries

**What Actually Happens**:
- PlanChange table: **0 entries** (despite major changes)
- DecisionLog table: 20 entries (working correctly)
- `_record_plan_change_entry()` EXISTS but only called during **doctor re-plan workflow** ([autonomous_executor.py:1967](../src/autopack/autonomous_executor.py#L1967))

**Root Cause Analysis**:

The PlanChange logging system has **TWO separate workflows**:

1. **Autonomous Executor Re-Plan Workflow** (WORKING):
   - Triggered by doctor detecting phase failures
   - Calls `_handle_phase_replan()` → `_record_plan_change_entry()`
   - Writes to PlanChange DB table + vector memory
   - Location: [autonomous_executor.py:1663-1706](../src/autopack/autonomous_executor.py#L1663-L1706)

2. **Backlog Maintenance Workflow** (NOT WORKING):
   - Runs diagnostics on backlog items
   - Generates patches for each item
   - **NEVER calls `_record_plan_change_entry()`**
   - No mechanism to detect "this is a major change"
   - Location: [run_backlog_maintenance.py](../scripts/run_backlog_maintenance.py)

**Why CONSOLIDATED_DEBUG.md Changes Aren't Logged**:

CONSOLIDATED_DEBUG.md is:
- Updated manually by developers (lines 11-50 in [CONSOLIDATED_DEBUG.md](../.autonomous_runs/file-organizer-app-v1/archive/CONSOLIDATED_DEBUG.md#L11-L50))
- Contains critical architectural decisions (PostgreSQL, Qdrant, intent router)
- **NO automated hook to detect changes and log to PlanChange**

**Evidence**:
```bash
# Check PlanChange entries
PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" python -c "
from autopack.database import SessionLocal
from autopack.models import PlanChange
session = SessionLocal()
count = session.query(PlanChange).count()
print(f'PlanChange entries: {count}')
session.close()
"
# Output: PlanChange entries: 0
```

### Solution Strategy

**Phase 1: Wire Backlog Maintenance to PlanChange Logging** (IMMEDIATE)

Add PlanChange logging when backlog maintenance generates patches that represent major changes.

**Phase 2: Auto-Detect Major Changes from CONSOLIDATED_DEBUG.md** (FUTURE)

Create file watcher to detect CONSOLIDATED_DEBUG.md changes and auto-log to PlanChange.

### Implementation Steps - Phase 1

**1. Add Major Change Detection to Backlog Maintenance**

Modify [run_backlog_maintenance.py](../scripts/run_backlog_maintenance.py) to detect when a patch represents a major change:

```python
def is_major_change(item: BacklogItem, patch_path: Optional[Path], auditor_decision: AuditorDecision) -> tuple[bool, str]:
    """
    Detect if this backlog item represents a major architectural change.

    Returns:
        (is_major, rationale)
    """
    major_keywords = [
        "database", "migration", "postgresql", "qdrant", "vector", "memory",
        "architecture", "framework", "integration", "api", "authentication"
    ]

    # Check item context for major keywords
    item_context = (item.context or "").lower()
    if any(kw in item_context for kw in major_keywords):
        return True, f"Architectural change detected: {item.context[:100]}"

    # Check if patch is large (>200 lines = significant change)
    if patch_path and patch_path.exists():
        lines = len(patch_path.read_text(encoding="utf-8", errors="ignore").splitlines())
        if lines > 200:
            return True, f"Large patch ({lines} lines) indicates major change"

    # Check if auditor flagged as major
    if any("major" in r.lower() for r in auditor_decision.reasons):
        return True, "Auditor flagged as major change"

    return False, ""
```

**2. Wire PlanChange Logging into Backlog Loop**

```python
# In main() function, after auditor decision (around line 176)

# After line 176: elif args.apply and verdict != "approve":
# Add:

# Detect and log major changes
is_major, major_rationale = is_major_change(item, patch_path, decision)
if is_major and verdict == "approve":
    try:
        from autopack.models import PlanChange
        from autopack.database import SessionLocal
        from datetime import datetime, timezone

        session = SessionLocal()
        plan_change = PlanChange(
            run_id=run_id,
            phase_id=item.id,
            project_id="file-organizer-app-v1",  # TODO: Make configurable
            timestamp=datetime.now(timezone.utc),
            author="backlog_maintenance",
            summary=f"Backlog item: {item.id}",
            rationale=major_rationale,
            status="active",
        )
        session.add(plan_change)
        session.commit()
        print(f"[PlanChange] Logged major change for {item.id}")
        session.close()
    except Exception as e:
        print(f"[PlanChange] Failed to log: {e}")
```

**3. Add --log-major-changes Flag**

```python
# In argument parser
parser.add_argument(
    "--log-major-changes",
    action="store_true",
    help="Log major changes to PlanChange table for context awareness"
)

# Use in detection logic
if is_major and verdict == "approve" and args.log_major_changes:
    # ... log to PlanChange
```

**4. Test Implementation**

```bash
# Run with major change logging enabled
PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --max-items 5 \
  --log-major-changes \
  --checkpoint \
  --apply

# Verify PlanChange entries created
PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import PlanChange
session = SessionLocal()
changes = session.query(PlanChange).all()
for c in changes:
    print(f'{c.timestamp} | {c.phase_id} | {c.summary} | {c.rationale}')
session.close()
"
```

### Implementation Steps - Phase 2 (Future Enhancement)

Create file watcher to auto-detect CONSOLIDATED_DEBUG.md changes:

```python
# scripts/watch_consolidated_debug.py
"""
Watch CONSOLIDATED_DEBUG.md for changes and auto-log to PlanChange.
Run this as a background service during development.
"""
import time
from pathlib import Path
from datetime import datetime, timezone
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConsolidatedDebugHandler(FileSystemEventHandler):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.last_mtime = file_path.stat().st_mtime if file_path.exists() else 0

    def on_modified(self, event):
        if event.src_path != str(self.file_path):
            return

        # Detect what changed
        current_mtime = self.file_path.stat().st_mtime
        if current_mtime <= self.last_mtime:
            return
        self.last_mtime = current_mtime

        # Extract recent changes (last section)
        content = self.file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Find most recent manual notes section
        recent_section = []
        in_manual = False
        for line in lines:
            if "## Manual Notes" in line:
                in_manual = True
                recent_section = [line]
            elif in_manual:
                if line.startswith("##") and "Manual Notes" not in line:
                    break
                recent_section.append(line)

        summary = "\n".join(recent_section[:10])  # First 10 lines

        # Log to PlanChange
        from autopack.models import PlanChange
        from autopack.database import SessionLocal

        session = SessionLocal()
        plan_change = PlanChange(
            run_id="manual_update",
            phase_id=None,
            project_id="file-organizer-app-v1",
            timestamp=datetime.now(timezone.utc),
            author="developer",
            summary="CONSOLIDATED_DEBUG.md updated",
            rationale=summary,
            status="active",
        )
        session.add(plan_change)
        session.commit()
        session.close()

        print(f"[PlanChange] Logged CONSOLIDATED_DEBUG.md change")
```

### Success Criteria

**Phase 1**:
- [ ] Major changes detected during backlog maintenance
- [ ] PlanChange entries created for architectural changes
- [ ] Entries include: run_id, phase_id, summary, rationale, timestamp
- [ ] Future runs can query PlanChange for context awareness

**Phase 2**:
- [ ] CONSOLIDATED_DEBUG.md changes auto-logged
- [ ] README.md updates tracked (if representing re-plans)
- [ ] Intent router can query "what changed since last run?"

---

## Issue 4: require_human Decision Pattern Analysis

### Status: **WORKING AS DESIGNED - NOT A BUG ✅**

### Investigation Findings

**User Concern**: "I'm concerned whether if it skipped the phase after making require_human... Because we specifically set up Autopack so that there shouldn't be any human intervention"

**Evidence from Test Run**:
```json
// All 10 backlog items from backlog-maintenance-1765288552
{
  "trigger": "backlog_maintenance",
  "choice": "diagnostics:backlog-6-yaml-repair-utility",
  "alternatives": "approve,require_human,reject"
}
```

All 20 DecisionLog entries show:
- trigger: `backlog_maintenance`
- choice: `diagnostics:{item_id}` OR `audit:require_human`
- alternatives: `approve,require_human,reject`

**What "require_human" Actually Means**:

1. **In Autonomous Executor Context** (Phase Execution):
   - `require_human` = Phase cannot proceed autonomously
   - Builder/Auditor/Doctor exhausted retries
   - Phase marked FAILED, execution stops

2. **In Backlog Maintenance Context** (Diagnostics):
   - `require_human` = Auditor verdict on proposed patch
   - Does NOT mean execution stopped
   - Means: "This patch needs human review before applying"
   - Execution CONTINUES to next item (no skip)

**Why All 10 Items Got `require_human` Verdict**:

Looking at auditor logic ([maintenance_auditor.py:75-100](../src/autopack/maintenance_auditor.py#L75-L100)):

```python
def minimal_auditor(input: AuditorInput) -> AuditorDecision:
    reasons = []

    # No diff provided
    if not input.diff:
        reasons.append("no diff provided")  # ← THIS IS WHY

    # Tests
    if not input.tests:
        reasons.append("no targeted tests")

    # ... more checks

    if reasons:
        verdict = "require_human"  # If ANY reason, require_human
        return AuditorDecision(verdict=verdict, reasons=reasons)
```

**Root Cause**: The test run did NOT provide patches (diffs) to the auditor!

Looking at [run_backlog_maintenance.py:103-153](../scripts/run_backlog_maintenance.py#L103-L153):
- Diagnostics generated for each item
- Test results collected
- Patches stored in `.autonomous_runs/.../patches/` directory
- **BUT**: Auditor receives `diff=None` because patch parsing may have failed

**Evidence from Test Summaries**:
```json
{
  "phase_id": "backlog-6-yaml-repair-utility",
  "auditor_verdict": "require_human",
  "auditor_reasons": ["no diff provided"],
  "patch_path": ".autonomous_runs/backlog-maintenance-1765288552/patches/backlog-6-yaml-repair-utility.patch"
}
```

Patch files exist, but auditor didn't receive parsed diffs!

**Are Phases Being Skipped?**

**NO** - Phases are NOT skipped. Looking at execution flow:

```python
# scripts/run_backlog_maintenance.py:155-176
apply_result = None
if args.apply and patch_path and verdict == "approve":
    # Apply patch only if approved
    ...
elif args.apply and verdict != "approve":
    print(f"[Apply] Skipped {item.id}: auditor verdict {verdict}")
    # CONTINUES to next item - does NOT stop execution

# Line 178-191: ALL items added to summaries regardless of verdict
summaries.append({
    "phase_id": item.id,
    "ledger": outcome.ledger_summary,
    "artifacts": outcome.artifacts,
    # ...
})
```

The test run processed ALL 10 items despite all getting `require_human`. Execution flow:
1. Item 1: diagnostics → patch → audit → require_human → **continue**
2. Item 2: diagnostics → patch → audit → require_human → **continue**
3. ...
4. Item 10: diagnostics → patch → audit → require_human → **done**

### Solution

**Issue**: Auditor receiving `diff=None` even though patches exist.

**Root Cause**: Patch parsing likely failing in backlog maintenance script.

**Fix**: Ensure patches are parsed and passed to auditor.

### Implementation Steps

**1. Add Patch Parsing Before Auditor Call**

```python
# In scripts/run_backlog_maintenance.py, around line 110-120

# After patch is saved
if patch_path and patch_path.exists():
    # Parse patch to extract diff stats
    from autopack.utils.diff_parser import parse_patch  # Adjust import

    try:
        patch_content = patch_path.read_text(encoding="utf-8", errors="ignore")
        diff_stats = parse_patch(patch_content)

        # Create DiffStats object for auditor
        from autopack.maintenance_auditor import DiffStats
        diff_obj = DiffStats(
            files_changed=len(diff_stats.get("files", [])),
            lines_added=diff_stats.get("additions", 0),
            lines_deleted=diff_stats.get("deletions", 0),
            protected_paths=diff_stats.get("protected_paths", []),
        )
    except Exception as e:
        logger.warning(f"Failed to parse patch for {item.id}: {e}")
        diff_obj = None
else:
    diff_obj = None

# Pass to auditor
decision = minimal_auditor(
    AuditorInput(
        diff=diff_obj,  # ← Was None before
        tests=test_results,
        # ...
    )
)
```

**2. Add --require-tests Flag for Strict Auditing**

```python
parser.add_argument(
    "--require-tests",
    action="store_true",
    help="Fail auditor if no tests provided (default: warn only)"
)

# In auditor call
if not input.tests and args.require_tests:
    reasons.append("no targeted tests")
elif not input.tests:
    # Just warn, don't fail
    logger.warning("No tests provided for {item.id}")
```

**3. Test with Proper Patch Parsing**

```bash
# Run with proper patch parsing
PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --max-items 3 \
  --checkpoint \
  --test-cmd "pytest -q tests/smoke/"

# Expect: Some items get "approve" verdict instead of all "require_human"
```

### Success Criteria

- [ ] Patches parsed before auditor call
- [ ] Auditor receives valid DiffStats objects
- [ ] Some items get "approve" verdict (not all require_human)
- [ ] Execution continues through all items regardless of verdict
- [ ] Only approved patches get applied when --apply flag used

---

## Issue 5: Tool Categorization - Manual-Only Tools

### Status: **SIMPLE CONFIGURATION CHANGE**

### Investigation Findings

**Tools That Should Be Manual-Only**:
1. **Pre-Publication Checklist** ([pre_publish_checklist.py](../scripts/pre_publish_checklist.py))
   - 40+ automated checks before release
   - Triggered via intent router: "check publication readiness"
   - Should NOT run automatically during regular maintenance

2. **Tidy Workspace Orchestrator** ([tidy_workspace.py](../scripts/tidy_workspace.py))
   - Moves completed/failed runs to archive
   - Consolidates artifacts
   - User-controlled cleanup, not automatic

**Current Issues**:
- These tools may be included in error reports
- May be triggered during automatic maintenance runs
- No clear "manual-only" designation in codebase

**Why This Matters**:
- Publication checklist is pre-release gate, not continuous check
- Workspace cleanup should be deliberate user action
- Mixing maintenance and cleanup creates confusion

### Solution

Create tool categorization system with explicit "manual-only" designation.

### Implementation Steps

**1. Create Tool Metadata Config**

```yaml
# config/tools.yaml
tools:
  pre_publish_checklist:
    script: scripts/pre_publish_checklist.py
    category: manual
    triggers:
      - intent_router  # Only via natural language
    description: "Pre-publication readiness checks"
    exclude_from:
      - automatic_maintenance
      - error_reports
      - test_runs

  tidy_workspace:
    script: scripts/tidy_workspace.py
    category: manual
    triggers:
      - intent_router
      - explicit_call
    description: "Archive and consolidate completed runs"
    exclude_from:
      - automatic_maintenance
      - error_reports
      - test_runs

  backlog_maintenance:
    script: scripts/run_backlog_maintenance.py
    category: automatic
    triggers:
      - scheduled
      - intent_router
      - explicit_call
    description: "Process backlog items with diagnostics"
```

**2. Update Intent Router to Respect Categories**

```python
# scripts/intent_router.py

def load_tool_config() -> dict:
    """Load tool categorization from config/tools.yaml"""
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}

def is_manual_only(tool_name: str) -> bool:
    """Check if tool is manual-only"""
    config = load_tool_config()
    tool_config = config.get("tools", {}).get(tool_name, {})
    return tool_config.get("category") == "manual"

def action_check_publication_readiness(project_id: str, args: argparse.Namespace) -> ActionResult:
    """Run pre-publication checklist on a project."""

    # Add context to output
    print("[Pre-Publication Checklist] Manual-only tool")
    print("[Pre-Publication Checklist] Triggered via intent router")

    # ... rest of implementation
```

**3. Add Tool Category Markers in Scripts**

```python
# scripts/pre_publish_checklist.py - Add at top
"""
Pre-Publication Checklist

Category: MANUAL ONLY
Triggers: Intent Router, Explicit Call
Excludes: Automatic Maintenance, Error Reports, Test Runs

This tool performs 40+ automated checks before release.
It should NOT be included in automatic maintenance runs.
"""

# scripts/tidy_workspace.py - Add at top
"""
Tidy Workspace Orchestrator

Category: MANUAL ONLY
Triggers: Intent Router, Explicit Call
Excludes: Automatic Maintenance, Error Reports, Test Runs

This tool archives completed runs and consolidates artifacts.
Workspace cleanup should be a deliberate user action.
"""
```

**4. Update Error Reporting to Exclude Manual Tools**

```python
# In error reporting system (wherever that is)

def should_include_in_error_report(tool_name: str) -> bool:
    """Check if tool should be included in error reports"""
    config = load_tool_config()
    tool_config = config.get("tools", {}).get(tool_name, {})
    excludes = tool_config.get("exclude_from", [])
    return "error_reports" not in excludes
```

**5. Update Test Checklist to Skip Manual Tools**

```python
# docs/TEST_RUN_CHECKLIST.md

## Tools Excluded from Automatic Testing

The following tools are **manual-only** and should NOT be included in automatic test runs:

- **Pre-Publication Checklist**: Release gate, not continuous check
- **Tidy Workspace Orchestrator**: User-controlled cleanup

To test these tools manually:
```bash
# Pre-publication checklist
python scripts/intent_router.py \
  --query "check publication readiness" \
  --project-id file-organizer-app-v1

# Tidy workspace
python scripts/tidy_workspace.py --project-id file-organizer-app-v1
```
```

### Success Criteria

- [ ] config/tools.yaml created with tool categories
- [ ] Intent router respects manual-only designation
- [ ] Error reports exclude manual-only tools
- [ ] Test runs exclude manual-only tools
- [ ] Documentation updated with tool categories

---

## Priority and Sequencing

### High Priority (Implement First)
1. **Issue 3 - Database Logging** (CRITICAL for context awareness)
2. **Issue 4 - Patch Parsing Fix** (Fixes auditor verdicts)
3. **Issue 1 - Qdrant Collections** (Fixes 404 errors)

### Medium Priority (Implement Soon)
4. **Issue 5 - Tool Categorization** (Prevents confusion)

### Low Priority (Future Enhancement)
5. **Issue 2 - Enhancement** (Already working, enhancement optional)

---

## Testing Strategy

### Pre-Implementation Tests

**Establish Baseline**:
```bash
# Count current PlanChange entries
PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import PlanChange
session = SessionLocal()
print(f'PlanChange before: {session.query(PlanChange).count()}')
session.close()
"

# Check Qdrant collections
PYTHONPATH=src python -c "
from autopack.memory.memory_service import MemoryService
m = MemoryService(use_qdrant=True)
# Should see 404 warnings
"
```

### Post-Implementation Tests

**After Issue 1 Fix**:
```bash
# Verify all collections exist
PYTHONPATH=src python -c "
from qdrant_client import QdrantClient
client = QdrantClient(host='localhost', port=6333)
collections = [c.name for c in client.get_collections().collections]
required = ['code_docs', 'run_summaries', 'errors_ci', 'doctor_hints', 'planning']
missing = [c for c in required if c not in collections]
print(f'Missing collections: {missing if missing else \"None - All exist!\"}')"
```

**After Issue 3 Fix**:
```bash
# Run backlog maintenance with major change logging
PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --max-items 2 \
  --log-major-changes \
  --checkpoint

# Verify PlanChange entries created
PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import PlanChange
session = SessionLocal()
changes = session.query(PlanChange).all()
print(f'PlanChange after: {len(changes)}')
for c in changes[:5]:
    print(f'  - {c.phase_id}: {c.summary}')
session.close()
"
```

**After Issue 4 Fix**:
```bash
# Verify auditor receives diffs
PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --max-items 3 \
  --checkpoint \
  --test-cmd "pytest -q tests/smoke/" 2>&1 | grep -i "auditor verdict"

# Should see some "approve" verdicts, not all "require_human"
```

**After Issue 5 Fix**:
```bash
# Verify tool categorization
python -c "
import yaml
from pathlib import Path
config = yaml.safe_load((Path('config') / 'tools.yaml').read_text())
manual_tools = [name for name, cfg in config['tools'].items() if cfg['category'] == 'manual']
print(f'Manual-only tools: {manual_tools}')
"
```

### Integration Test

**Full System Test After All Fixes**:
```bash
# 1. Verify PostgreSQL running
docker ps | grep postgres

# 2. Verify Qdrant running
docker ps | grep qdrant

# 3. Run full backlog maintenance with all new features
PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --max-items 5 \
  --checkpoint \
  --log-major-changes \
  --test-cmd "pytest -q tests/smoke/" \
  2>&1 | tee integration_test.log

# 4. Verify all systems operational
PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import PlanChange, DecisionLog
from qdrant_client import QdrantClient

# Check DB
session = SessionLocal()
print(f'PlanChange entries: {session.query(PlanChange).count()}')
print(f'DecisionLog entries: {session.query(DecisionLog).count()}')
session.close()

# Check Qdrant
client = QdrantClient(host='localhost', port=6333)
collections = [c.name for c in client.get_collections().collections]
print(f'Qdrant collections: {len(collections)}')
print(f'Collections: {collections}')
"
```

---

## Rollback Plan

If any implementation causes issues:

**Issue 1 Rollback**:
```bash
# Revert memory service initialization changes
git diff scripts/run_backlog_maintenance.py
git checkout scripts/run_backlog_maintenance.py
```

**Issue 3 Rollback**:
```bash
# Remove major change detection
git diff scripts/run_backlog_maintenance.py
git checkout scripts/run_backlog_maintenance.py

# No PlanChange entries to clean up if script didn't run
```

**Issue 4 Rollback**:
```bash
# Revert patch parsing changes
git checkout scripts/run_backlog_maintenance.py
```

**Issue 5 Rollback**:
```bash
# Remove config file
rm config/tools.yaml
git checkout scripts/intent_router.py
```

---

## Success Metrics

### Quantitative Metrics

After implementation, we should see:

1. **Qdrant Collections**: 5/5 collections exist (was 2/5)
2. **PlanChange Entries**: >0 entries after maintenance run (was 0)
3. **Auditor Verdicts**: Mix of approve/require_human (was 100% require_human)
4. **Error Rate**: 404 errors eliminated (was ~3 per run)

### Qualitative Metrics

1. **Context Awareness**: Future runs can query "what major changes happened?"
2. **Observability**: Clear distinction between automatic and manual tools
3. **Reliability**: Patches properly evaluated before application
4. **Maintainability**: Tool categories documented and enforced

---

## Appendix A: File Reference Index

### Investigation Files
- [run_backlog_maintenance.py](../scripts/run_backlog_maintenance.py) - Backlog maintenance script
- [autonomous_executor.py](../src/autopack/autonomous_executor.py) - Phase execution engine
- [memory_service.py](../src/autopack/memory/memory_service.py) - Vector memory wrapper
- [qdrant_store.py](../src/autopack/memory/qdrant_store.py) - Qdrant backend
- [maintenance_auditor.py](../src/autopack/maintenance_auditor.py) - Patch auditor
- [models.py](../src/autopack/models.py) - Database models (PlanChange, DecisionLog)

### Key Line References
- PlanChange logging: [autonomous_executor.py:1663-1706](../src/autopack/autonomous_executor.py#L1663-L1706)
- Memory init: [memory_service.py:124-134](../src/autopack/memory/memory_service.py#L124-L134)
- Auditor logic: [maintenance_auditor.py:75-100](../src/autopack/maintenance_auditor.py#L75-L100)
- Decision logging: [run_backlog_maintenance.py:141-153](../scripts/run_backlog_maintenance.py#L141-L153)

---

## Appendix B: Database Schema

### PlanChange Table
```python
class PlanChange(Base):
    __tablename__ = "plan_changes"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=True, index=True)
    phase_id = Column(String, nullable=True, index=True)
    project_id = Column(String, nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    author = Column(String, nullable=True)           # "backlog_maintenance", "developer", etc.
    summary = Column(Text, nullable=False)            # Brief description
    rationale = Column(Text, nullable=True)           # Why this change was made
    replaces_version = Column(Integer, nullable=True) # Version tracking
    status = Column(String, default="active")         # active|superseded|archived
    replaced_by = Column(Integer, nullable=True)      # FK to newer version
    vector_id = Column(String, nullable=True)         # Qdrant point ID
```

### DecisionLog Table
```python
class DecisionLog(Base):
    __tablename__ = "decision_log"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, nullable=True, index=True)
    phase_id = Column(String, nullable=True, index=True)
    project_id = Column(String, nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    trigger = Column(String, nullable=True)           # "backlog_maintenance", "replan:flaw", etc.
    alternatives = Column(Text, nullable=True)        # "approve,require_human,reject"
    choice = Column(Text, nullable=False)             # Actual choice made
    rationale = Column(Text, nullable=True)           # Why this choice
    vector_id = Column(String, nullable=True)         # Qdrant point ID
```

---

## Appendix C: Qdrant Collection Schema

### Collection: planning
Used for PlanChange and DecisionLog vector embeddings.

**Payload Schema**:
```json
{
  "type": "plan_change" | "decision_log",
  "project_id": "file-organizer-app-v1",
  "run_id": "backlog-maintenance-1765288552",
  "phase_id": "backlog-6-yaml-repair-utility",
  "timestamp": "2025-12-09T04:28:20.407111+00:00",

  // For plan_change:
  "summary": "Backlog item: yaml-repair-utility",
  "rationale": "Large patch (350 lines) indicates major change",
  "status": "active",

  // For decision_log:
  "trigger": "backlog_maintenance",
  "choice": "audit:require_human",
  "alternatives": "approve,require_human,reject",
  "rationale": "no diff provided"
}
```

**Point ID Format**:
- Plan changes: `plan_change:{project_id}:{run_id}:{phase_id}:{hash}`
- Decisions: `decision:{project_id}:{run_id}:{phase_id}:{hash}`

---

**End of Implementation Plan**
