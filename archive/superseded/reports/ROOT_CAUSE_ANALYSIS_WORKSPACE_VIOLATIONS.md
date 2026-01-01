# Root Cause Analysis: Workspace Structure Violations

**Date**: 2026-01-01
**Analyst**: Claude (BUILD-147 Phase A P11+)
**Scope**: 93 errors, 333 warnings in Autopack workspace

---

## Executive Summary

**Current State**:
- ❌ 93 structural errors (all root directory violations)
- ⚠️ 333 warnings (95% missing project structures)
- ✅ Core SOT intact (docs/ has required 6-file structure)
- ✅ Archive buckets exist

**Root Causes Identified**:
1. **Historical accumulation** - No systematic root cleanup for 6+ months
2. **Workflow gaps** - Cursor creates files at root, no automated routing
3. **Test/dev artifacts** - Development processes leave residual files
4. **Legacy run directories** - 70+ old runs lacking docs/archive structure
5. **Documentation sprawl** - 159 markdown files in docs/ (only 6 should be SOT)

**Impact**:
- Repo root has 80+ stray files (should have ~10 config files)
- docs/ has 25x more files than needed (159 vs 6 core SOT)
- .autonomous_runs has 70+ run directories missing SOT structure
- Knowledge retrieval may miss consolidated docs
- Developer onboarding confusion ("where do files go?")

---

## Part 1: Error Analysis (93 Errors - All Root Violations)

### 1.1 Error Breakdown by File Type

| File Type | Count | % of Errors | Destination |
|-----------|-------|-------------|-------------|
| Log files (*.log) | 32 | 34.4% | archive/diagnostics/logs/ |
| Python test scripts (test_*.py) | 4 | 4.3% | scripts/test/ |
| JSON phase files (phase_*.json) | 7 | 7.5% | archive/plans/ |
| Markdown docs (*.md) | 6 | 6.5% | archive/reports/ or unsorted/ |
| Shell scripts (*.sh) | 2 | 2.2% | scripts/utility/ |
| Config/other files | 42 | 45.2% | Various |

**Total**: 93 disallowed files at repo root

### 1.2 Root Cause Categories

#### Category A: Development/Testing Artifacts (41 files, 44%)

**Pattern**: Files created during manual testing, debugging, or experimental runs

**Examples**:
- `test_build113.py`, `test_build113_integration.py`, `test_build113_proactive.py`, `test_build113_real_world.py`
- `probe_debug_output.txt`, `probe_final_output.txt`, `probe_success.txt`, `run_A_probe_output.txt`
- `token_estimator_calibration_20251229_140313.json`
- `builder_fullfile_failure_latest.json`

**Root Cause**:
- Developers/AI creating test files at repo root during development
- No cleanup after testing/probing sessions
- Test scripts not organized into tests/ directory

**Why it happened**:
- Natural developer workflow: create test file in root, run it, forget to clean up
- Cursor AI creates files at root by default when asked to "create a test"
- No automated cleanup reminder or git pre-commit hook

**Evidence of scale**:
- 4 test_build113*.py files (should be in tests/)
- 7 probe output files (should be in archive/diagnostics/)
- Multiple calibration JSON files

#### Category B: Execution Logs (32 files, 34%)

**Pattern**: Log files from various runs, builds, and telemetry collections

**Examples**:
- `build129-p3-batch.log`, `build130_telemetry_run.log`, `build132_execution.log`
- `telemetry_collection.log`, `telemetry_collection_v2.log`, `telemetry_collection_v3.log`
- `lovable_phase0_execution.log`, `lovable_phase1_execution.log`
- `api_server_fullrun.log`, `backend.log`, `drain_all_output.log`

**Root Cause**:
- Scripts/processes writing logs to repo root instead of archive/diagnostics/logs/
- No centralized logging configuration enforcing log directory
- Ad-hoc logging during development

**Why it happened**:
- Python scripts default to current working directory for log files
- Manual runs from repo root → logs end up at root
- No logging configuration specifying archive/diagnostics/logs/

**Evidence of scale**:
- 32 log files at root
- Multiple log generations per build (build132_execution.log, build132_final_attempt.log, build132_with_fix.log)
- Telemetry collection logs v1-v8

#### Category C: Phase/Run Configuration Files (7 files, 7.5%)

**Pattern**: JSON files defining phases or run configurations

**Examples**:
- `phase_a_p11_observability.json`
- `phase_b_p12_embedding_cache.json`
- `phase_c_p13_expand_artifacts.json`
- `phase_d_research_imports.json`
- `phase_e_initdb_completeness.json`
- `phase_true_autonomy_p0_p1_intention_and_plan_normalization.json`
- `run_request.json`

**Root Cause**:
- Phase planning workflow creates JSON configs at root
- Cursor creates phase definitions at root when asked
- No automated move to archive/plans/

**Why it happened**:
- Natural workflow: plan phase → create JSON → run → forget to archive
- Cursor AI doesn't know to put phase files in archive/plans/
- No post-run cleanup automation

#### Category D: Documentation Files (6 files, 6.5%)

**Pattern**: Markdown documentation created at root

**Examples**:
- `BUILD_HISTORY.md`, `BUILD_LOG.md`, `DEBUG_LOG.md` (duplicates of docs/ files!)
- `BUILD_146_P6_BENCHMARK_REPORT.md`
- `BATCH_DRAIN_QUICKSTART.md`
- `NEXT_SESSION_TECHNICAL_PROMPT.md`, `NEXT_SESSION_USER_PROMPT.md`
- `README_BACKUP.md`

**Root Cause**:
- **Critical finding**: `BUILD_HISTORY.md` and `DEBUG_LOG.md` exist at BOTH root and docs/
- Cursor creates docs at root instead of docs/ directory
- Manual file creation during sessions

**Why it happened**:
- Cursor's default behavior: create files at workspace root
- User asks "create a BUILD_HISTORY.md" → Cursor creates at root, not docs/
- Potential conflict: root versions may diverge from docs/ versions

**Impact**: HIGH - Duplicate SOT files could cause confusion about which is authoritative

#### Category E: Infrastructure/Config Files (7 files, 7.5%)

**Pattern**: Docker, nginx, development configs

**Examples**:
- `docker-compose.dev.yml`, `Dockerfile.frontend`
- `nginx.conf`
- `pytest.ini`, `requirements-dev.txt`
- `Makefile`
- `ngrok.exe`

**Root Cause**:
- Some legitimate (pytest.ini, requirements-dev.txt should be allowed)
- Others should be in config/ or archive/

**Why it happened**:
- Allowlist too restrictive (pytest.ini, requirements-dev.txt are standard Python project files)
- Dev-specific infrastructure files not organized

**Action needed**: Update allowlist + route others

### 1.3 Temporal Analysis

**When did this happen?**

Based on file naming patterns:
- **Phase 0-2 (Lovable project)**: lovable_phase0/1/2_execution.log → Late 2025
- **Build 129-132**: build129-132 logs → December 2025
- **Telemetry collection**: v1-v8 → Multiple iterations over weeks
- **Build 113 testing**: test_build113*.py → Recent (Dec 2025)
- **Build 146**: BUILD_146_P6_BENCHMARK_REPORT.md → Very recent (Dec 2025)

**Pattern**: Continuous accumulation over 2-3 months with no cleanup

### 1.4 Critical Duplicate Files

**CRITICAL ISSUE**: Duplicate SOT files at root and docs/

| File | Root | Docs | Status |
|------|------|------|--------|
| BUILD_HISTORY.md | ✅ Exists | ✅ Exists | ⚠️ CONFLICT |
| DEBUG_LOG.md | ✅ Exists | ✅ Exists | ⚠️ CONFLICT |
| BUILD_LOG.md | ✅ Exists | ❌ Not standard | ⚠️ Orphan |

**Root Cause**: User or AI created these files at root, not realizing docs/ versions exist

**Impact**:
- Potential content divergence
- Confusion about which is authoritative
- Tidy system must resolve: which version wins?

**Recommendation**:
1. Compare content of root vs docs/ versions
2. If root versions are newer/different, merge into docs/ versions
3. Delete root versions
4. Prevent future duplicates via validation

---

## Part 2: Warning Analysis (333 Warnings)

### 2.1 Warning Breakdown

| Warning Type | Count | % of Warnings |
|--------------|-------|---------------|
| Missing project docs/ | 167 | 50.2% |
| Missing project archive/ | 166 | 49.8% |
| Docs non-SOT files | 0 | 0% (conservative mode) |
| Unexpected root directories | ~7 | <1% |

**Pattern**: Almost all warnings are missing project structures

### 2.2 Missing Project Structures

**Total projects in .autonomous_runs**: ~70-80 directories

**Projects missing docs/ and archive/** (both): ~83 projects

**Examples**:
- `autopack-onephase-*` (multiple phases)
- `research-system-v1` through `v29`
- `telemetry-collection-v4` through `v8b`
- `build*` runs
- `test-*` runs
- `retry-*` runs

**Root Cause**: These are **run directories**, not **projects** in the SOT sense

#### What are these directories?

**Type A: Autopack Core Runs** (not subprojects)
- `build129-p3-week1-telemetry`
- `build130-schema-validation-prevention`
- `build132-coverage-delta-integration`
- `p10-validation-test`
- `research-system-v1` through `v29`
- `telemetry-collection-v4` through `v8b`

**Nature**: These are **execution runs of Autopack itself**, not separate projects
- They shouldn't have their own docs/ (they contribute to main docs/)
- They shouldn't have their own archive/ (artifacts go to main archive/)

**Type B: Actual Subprojects**
- `file-organizer-app-v1` (real project, HAS docs/ and archive/)
- `lovable-*` (may be subproject or runs)

**Type C: Infrastructure/Utility Directories**
- `tidy_checkpoints` (checkpoint storage, not a project)
- `_shared` (shared resources, not a project)
- `checkpoints` (backup storage, not a project)
- `errors`, `logs` (artifact storage, not projects)

### 2.3 Root Cause: Conceptual Mismatch

**The Issue**: Verifier assumes every directory in `.autonomous_runs` is a "project" needing SOT structure

**Reality**:
- `.autonomous_runs` contains a mix:
  - **1 real subproject**: file-organizer-app-v1
  - **70+ run directories**: Autopack core execution runs
  - **Infrastructure directories**: checkpoints, _shared, etc.

**Why verifier warns**:
```python
# verify_workspace_structure.py lines ~280
for project_dir in autonomous_runs.iterdir():
    if project_dir.is_dir() and not project_dir.name.startswith("."):
        # Assumes every dir is a "project" → checks for docs/archive
        results[f"project:{project_dir.name}"] = verify_project_structure(project_dir)
```

**Fix needed**: Distinguish between:
1. **Projects** (need docs/archive SOT structure) - e.g., file-organizer-app-v1
2. **Runs** (execution artifacts, don't need SOT) - e.g., build129-*, research-system-v*
3. **Infrastructure** (system directories, skip verification) - e.g., checkpoints, _shared

### 2.4 Docs Non-SOT Files (Hidden by Conservative Mode)

**Current**: Verifier runs in conservative mode → doesn't report non-SOT files as warnings

**Actual state** (from earlier analysis):
- docs/ has **159 markdown files**
- Only 6 should be core SOT
- ~150 files are non-SOT documentation

**Why hidden**: Conservative mode only reports violations, doesn't suggest moves

**Impact**: Warnings undercount the actual docs/ sprawl

---

## Part 3: Systemic Root Causes

### 3.1 Workflow Gaps

**Gap 1: No Post-Session Cleanup**
- User/AI works on feature
- Creates test files, logs, docs at root
- Session ends, files remain
- No reminder to run tidy

**Gap 2: Cursor Default Behavior**
- Cursor creates files at workspace root by default
- User must explicitly specify subdirectory
- Most users don't know file organization rules

**Gap 3: No Automated Routing**
- Files accumulate at root
- Tidy exists but isn't run automatically
- No git pre-commit hook to remind/enforce

**Gap 4: No Logging Configuration**
- Python scripts default to writing logs in current working directory
- No centralized config directing logs to archive/diagnostics/logs/

### 3.2 Process Failures

**Failure 1: Tidy Not Part of Standard Workflow**
- README mentions tidy exists
- But it's not part of standard "end of session" checklist
- No automation or prompting

**Failure 2: Incomplete Specification**
- WORKSPACE_ORGANIZATION_SPEC.md created today
- Previously, no canonical reference for "what goes where"
- Developers/AI lacked clear guidance

**Failure 3: Verification Not in CI**
- verify_workspace_structure.py created today
- Previously, no automated check
- Violations accumulate unnoticed

### 3.3 Technical Debt

**Debt 1: Duplicate SOT Files**
- BUILD_HISTORY.md, DEBUG_LOG.md exist at both root and docs/
- Potential content divergence
- No merge/conflict resolution process

**Debt 2: Run Directory Proliferation**
- 70+ run directories in .autonomous_runs
- Many are old/complete
- No archival strategy for completed runs

**Debt 3: Allowlist Incompleteness**
- pytest.ini, requirements-dev.txt should be allowed at root
- Allowlist needs refinement

---

## Part 4: Impact Assessment

### 4.1 Severity Matrix

| Issue | Severity | Impact | Effort to Fix |
|-------|----------|--------|---------------|
| Duplicate SOT files | 🔴 HIGH | Content divergence, confusion | Medium (manual merge) |
| 80+ root files | 🟡 MEDIUM | Clutter, onboarding confusion | Low (automated tidy) |
| 159 docs/ files (vs 6 SOT) | 🟡 MEDIUM | Knowledge retrieval issues | Low-Medium (tidy + reduce) |
| 70+ run dirs missing structure | 🟢 LOW | False warnings (not real issue) | Low (fix verifier logic) |
| No centralized logging | 🟡 MEDIUM | Logs scattered at root | Medium (config + refactor) |
| No automated enforcement | 🟡 MEDIUM | Continuous re-accumulation | Medium (CI + hooks) |

### 4.2 User-Facing Impacts

**Impact 1: Developer Confusion**
- "Where do I put this file?"
- "Which BUILD_HISTORY.md is correct?"
- "Why are there 159 files in docs/?"

**Impact 2: Retrieval Inefficiency**
- SOT retrieval may miss relevant docs if they're at root, not consolidated
- Knowledge buried in 159 docs/ files instead of 6 SOT files
- Archive not consolidated → executor can't find historical context

**Impact 3: Onboarding Friction**
- New developers see messy repo root
- Unclear organization → harder to contribute
- "This doesn't match the README" → credibility loss

**Impact 4: Maintenance Overhead**
- Manual cleanup needed every few months
- Time spent hunting for "where did I put that file?"

---

## Part 5: Comprehensive Implementation Plan

### Phase A: Immediate Cleanup (Execute Today)

**A1: Resolve Duplicate SOT Files** (30 min)

Priority: 🔴 CRITICAL

```bash
# 1. Compare root vs docs versions
diff c:/dev/Autopack/BUILD_HISTORY.md c:/dev/Autopack/docs/BUILD_HISTORY.md
diff c:/dev/Autopack/DEBUG_LOG.md c:/dev/Autopack/docs/DEBUG_LOG.md

# 2. If different, manually merge
# 3. Keep docs/ versions as authoritative
# 4. Delete root versions after merge confirmation
```

**Action Items**:
- [ ] Read both versions of BUILD_HISTORY.md
- [ ] Merge any unique content from root → docs version
- [ ] Repeat for DEBUG_LOG.md
- [ ] Handle BUILD_LOG.md (non-standard, decide disposition)
- [ ] Delete root versions
- [ ] Commit with message: "fix: resolve duplicate SOT files, establish docs/ as authoritative"

**A2: Execute Unified Tidy** (10 min)

```bash
# Create git checkpoint before changes
python scripts/tidy/tidy_up.py --execute --git-checkpoint

# Review moved files
git diff --name-status HEAD~1

# If satisfied, push
git push
```

**Expected outcome**:
- 80+ files moved from root to proper locations
- archive/ buckets populated
- Root clean (only ~10 config files remain)

**A3: Update Allowlist** (5 min)

Add legitimate Python project files to allowlist:

```python
# In scripts/tidy/tidy_up.py and verify_workspace_structure.py
ROOT_ALLOWED_FILES = {
    # ... existing ...
    "pytest.ini",           # Pytest configuration
    "requirements-dev.txt", # Dev dependencies
    "Makefile",             # Build automation (common in Python projects)
}
```

**A4: Verify Clean State** (2 min)

```bash
python scripts/tidy/verify_workspace_structure.py

# Expected: ~10 errors (allowlist updates), 330 warnings (run dirs)
# Errors should be legitimate files only
```

---

### Phase B: Fix Verifier Logic (1-2 hours)

**B1: Distinguish Projects from Runs**

**Root Cause**: Verifier treats all `.autonomous_runs/*` dirs as projects

**Fix**: Add project detection logic

```python
# In verify_workspace_structure.py

KNOWN_PROJECTS = {
    "file-organizer-app-v1",  # Real subproject
    # Add others as they're created
}

INFRASTRUCTURE_DIRS = {
    "checkpoints", "tidy_checkpoints", "_shared", "errors", "logs"
}

def is_project_directory(dir_path: Path) -> bool:
    """Determine if directory is a project (needs SOT) vs run/infrastructure."""
    name = dir_path.name

    # Explicit project list
    if name in KNOWN_PROJECTS:
        return True

    # Infrastructure directories
    if name in INFRASTRUCTURE_DIRS:
        return False

    # Heuristic: if has docs/ or archive/, treat as project
    if (dir_path / "docs").exists() or (dir_path / "archive").exists():
        return True

    # Otherwise, assume it's a run directory (no SOT needed)
    return False

# Update verification loop
for project_dir in autonomous_runs.iterdir():
    if project_dir.is_dir() and not project_dir.name.startswith("."):
        if is_project_directory(project_dir):
            # Real project, verify SOT structure
            results[f"project:{project_dir.name}"] = verify_project_structure(project_dir)
        else:
            # Run or infrastructure, skip verification
            pass
```

**Expected impact**: Warnings drop from 333 to ~10-20 (only real projects checked)

**B2: Add Run Directory Verification** (optional)

Instead of checking for docs/archive, check run dirs have expected structure:

```python
def verify_run_directory(run_path: Path) -> Tuple[bool, List[str], List[str]]:
    """Verify run directory has expected artifacts."""
    errors = []
    warnings = []

    # Runs should have phases/ or logs/ or similar
    expected_subdirs = ["phases", "logs", "errors"]
    has_expected = any((run_path / subdir).exists() for subdir in expected_subdirs)

    if not has_expected:
        warnings.append(f"Run directory has no expected subdirs: {run_path.name}")

    return True, errors, warnings  # Runs don't fail verification
```

---

### Phase C: Prevent Recurrence (2-4 hours)

**C1: Centralized Logging Configuration**

Create `src/autopack/logging_config.py`:

```python
"""
Centralized logging configuration for Autopack.
Ensures all logs go to archive/diagnostics/logs/, not repo root.
"""

import logging
from pathlib import Path
from datetime import datetime

def get_logger(name: str, repo_root: Path) -> logging.Logger:
    """
    Get configured logger that writes to archive/diagnostics/logs/.

    Usage:
        from autopack.logging_config import get_logger
        logger = get_logger(__name__, Path(__file__).parent.parent.parent)
        logger.info("Message")
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        # Ensure log directory exists
        log_dir = repo_root / "archive" / "diagnostics" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{name.replace('.', '_')}_{timestamp}.log"

        # Configure handler
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger
```

**Migration**: Update scripts to use centralized logging:

```python
# Before:
# logging.basicConfig(filename="build129.log", ...)

# After:
from autopack.logging_config import get_logger
logger = get_logger("build129", Path(__file__).parent.parent)
logger.info("Build started")
```

**C2: Git Pre-Commit Hook** (optional, for enforcement)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Pre-commit hook: warn about files at root

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT" || exit 1

# Check for disallowed files at root
python scripts/tidy/verify_workspace_structure.py --json-output /tmp/verify.json

if [ $? -ne 0 ]; then
    echo "⚠️  WARNING: Workspace structure violations detected"
    echo "   Run: python scripts/tidy/tidy_up.py --execute"
    echo ""
    echo "   Continue commit anyway? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
```

**C3: Post-Session Checklist in CURSOR_PROMPT_TIDY.md**

Update docs/CURSOR_PROMPT_TIDY.md to add:

```markdown
## End-of-Session Checklist

Before ending your development session:

1. [ ] Check for stray files at repo root: `ls *.log *.py *.md *.json 2>/dev/null | wc -l`
   - If count > 0, run tidy

2. [ ] Run tidy if you created new files:
   ```bash
   python scripts/tidy/tidy_up.py --execute
   ```

3. [ ] Verify structure is clean:
   ```bash
   python scripts/tidy/verify_workspace_structure.py
   ```

4. [ ] Commit and push:
   ```bash
   git add -A
   git commit -m "chore: end-of-session tidy"
   git push
   ```
```

**C4: CI Integration**

Create `.github/workflows/verify-structure.yml`:

```yaml
name: Verify Workspace Structure

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Verify workspace structure
        run: python scripts/tidy/verify_workspace_structure.py --json-output verify_report.json
        continue-on-error: true  # Non-blocking initially

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: workspace-verification-report
          path: verify_report.json
```

**Promotion plan**:
- Week 1-2: Non-blocking (continue-on-error: true)
- Week 3+: Blocking after workspace is clean

---

### Phase D: Documentation Sprawl (2 hours)

**D1: Analyze docs/ Files**

```bash
# Count files by type in docs/
find docs/ -maxdepth 1 -type f -name "*.md" | wc -l  # 159 files

# Categorize them
find docs/ -maxdepth 1 -type f -name "BUILD-*.md" | wc -l      # Build reports
find docs/ -maxdepth 1 -type f -name "DBG-*.md" | wc -l        # Debug reports
find docs/ -maxdepth 1 -type f -name "*PLAN*.md" | wc -l       # Plans
find docs/ -maxdepth 1 -type f -name "*REPORT*.md" | wc -l     # Reports
```

**D2: Execute Docs Reduction**

```bash
# Aggressive cleanup: reduce docs/ to SOT-only
python scripts/tidy/tidy_up.py --execute --docs-reduce-to-sot --git-checkpoint

# This will move ~150 files from docs/ to archive/
```

**Expected outcome**:
- docs/ has ~20 files (6 SOT + 14 allowed truth sources)
- ~140 files moved to archive/reports, archive/plans, etc.

**D3: Consolidate Archive to SOT**

After reduction, run full consolidation:

```bash
# This will consolidate archive markdown into SOT ledgers
python scripts/tidy/tidy_up.py --execute --git-checkpoint

# Archive files will be summarized into BUILD_HISTORY.md, DEBUG_LOG.md, etc.
# Then moved to archive/superseded/
```

---

### Phase E: Long-Term Improvements (4-8 hours)

**E1: Run Directory Archival Policy**

Create script to archive old completed runs:

```python
# scripts/archive_old_runs.py
"""
Archive old completed runs from .autonomous_runs to archive/runs/.
"""

from pathlib import Path
from datetime import datetime, timedelta
import shutil

REPO_ROOT = Path(__file__).parent.parent
AUTONOMOUS_RUNS = REPO_ROOT / ".autonomous_runs"
ARCHIVE_RUNS = REPO_ROOT / "archive" / "runs"

# Runs older than 90 days and not in KEEP_RUNS
KEEP_RUNS = {"file-organizer-app-v1"}  # Active projects
AGE_THRESHOLD_DAYS = 90

def get_run_age(run_dir: Path) -> int:
    """Get age of run in days based on last modification time."""
    mtime = run_dir.stat().st_mtime
    age = datetime.now() - datetime.fromtimestamp(mtime)
    return age.days

def archive_old_runs(dry_run=True):
    """Archive runs older than threshold."""
    for run_dir in AUTONOMOUS_RUNS.iterdir():
        if not run_dir.is_dir() or run_dir.name.startswith("."):
            continue

        if run_dir.name in KEEP_RUNS:
            continue

        age = get_run_age(run_dir)
        if age > AGE_THRESHOLD_DAYS:
            dest = ARCHIVE_RUNS / run_dir.name
            if dry_run:
                print(f"[DRY-RUN] Would archive: {run_dir.name} (age: {age} days)")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(run_dir), str(dest))
                print(f"[ARCHIVED] {run_dir.name} → archive/runs/")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    archive_old_runs(dry_run=not args.execute)
```

**E2: Cursor AI Context Files**

Create `.cursor/rules` to guide Cursor:

```markdown
# Cursor AI Rules for Autopack

## File Creation Rules

1. **Never create files at repo root** unless it's a standard config file
   - Test files → tests/
   - Scripts → scripts/
   - Docs → docs/ (only if SOT) or archive/
   - Logs → archive/diagnostics/logs/

2. **When creating documentation:**
   - Check if it updates SOT → append to docs/BUILD_HISTORY.md or docs/DEBUG_LOG.md
   - If new document → create in archive/reports/ or archive/plans/

3. **When creating phase definitions:**
   - Create in archive/plans/phase_<name>.json

4. **When creating test files:**
   - Create in tests/autopack/test_<feature>.py

## End of Session

Before ending session, ask user:
"Should we run tidy to organize any new files? (y/N)"

If yes:
```bash
python scripts/tidy/tidy_up.py --execute
```
```

**E3: Automated Tidy Scheduler** (optional)

For active development, run tidy weekly via cron/Task Scheduler:

```bash
# Linux/Mac: Add to crontab
0 0 * * 0 cd /c/dev/Autopack && python scripts/tidy/tidy_up.py --execute

# Windows: Use Task Scheduler
# Action: python
# Arguments: C:\dev\Autopack\scripts\tidy\tidy_up.py --execute
# Start in: C:\dev\Autopack
# Trigger: Weekly, Sunday 00:00
```

---

## Part 6: Execution Roadmap

### Immediate Actions (Today, 1 hour)

1. **Resolve duplicate SOT files** (30 min)
   - Compare BUILD_HISTORY.md, DEBUG_LOG.md at root vs docs/
   - Merge unique content
   - Delete root versions

2. **Run unified tidy** (10 min)
   ```bash
   python scripts/tidy/tidy_up.py --execute --git-checkpoint
   ```

3. **Update allowlist** (10 min)
   - Add pytest.ini, requirements-dev.txt, Makefile

4. **Verify clean state** (10 min)
   ```bash
   python scripts/tidy/verify_workspace_structure.py
   ```

### Short-Term (This Week, 2-4 hours)

5. **Fix verifier logic** (1-2 hours)
   - Implement is_project_directory()
   - Distinguish projects from runs
   - Re-run verification → expect ~10 warnings

6. **Execute docs reduction** (30 min)
   ```bash
   python scripts/tidy/tidy_up.py --execute --docs-reduce-to-sot --git-checkpoint
   ```

7. **Create centralized logging** (1 hour)
   - Implement logging_config.py
   - Migrate 2-3 high-traffic scripts as examples

8. **Add post-session checklist** (30 min)
   - Update CURSOR_PROMPT_TIDY.md
   - Create .cursor/rules

### Medium-Term (Next Sprint, 4-8 hours)

9. **CI integration** (2 hours)
   - Create .github/workflows/verify-structure.yml
   - Run non-blocking for 2 weeks
   - Promote to blocking after clean

10. **Run archival policy** (2 hours)
    - Implement scripts/archive_old_runs.py
    - Test on old runs
    - Document in README

11. **Git hook** (1 hour, optional)
    - Implement pre-commit hook
    - Test and document

12. **Logging migration** (2-3 hours)
    - Migrate all remaining scripts to centralized logging
    - Remove hardcoded log file paths

### Long-Term (Ongoing)

13. **Monitoring & enforcement**
    - Weekly structure verification reports
    - Monthly review of archive growth
    - Quarterly cleanup sessions

14. **Documentation maintenance**
    - Keep WORKSPACE_ORGANIZATION_SPEC.md updated
    - Update allowlists as project evolves
    - Refine classification rules based on patterns

---

## Part 7: Success Metrics

### Before (Current State)

- ❌ 93 errors (root violations)
- ⚠️ 333 warnings (missing structures)
- 📁 ~80 files at repo root (should be ~10)
- 📄 159 files in docs/ (should be ~20)
- 🏃 70+ run directories lacking organization

### After Phase A (Immediate Cleanup)

- ✅ 0-10 errors (only legitimate edge cases)
- ⚠️ 330 warnings (still counting runs as projects)
- 📁 ~15 files at repo root (configs + allowed files)
- 📄 159 files in docs/ (unchanged until Phase D)
- 🏃 70+ run directories (unchanged, not real issue)

### After Phase B (Fix Verifier)

- ✅ 0-5 errors
- ⚠️ 10-20 warnings (only real issues)
- 📁 ~15 files at repo root
- 📄 159 files in docs/
- 🏃 70+ run directories (now correctly ignored)

### After Phase D (Docs Reduction)

- ✅ 0 errors
- ⚠️ 5-10 warnings
- 📁 ~12 files at repo root
- 📄 ~20 files in docs/ (6 SOT + 14 allowed)
- 🏃 70+ run directories (correctly ignored)

### After Phase E (Long-Term)

- ✅ 0 errors (maintained via CI)
- ⚠️ 0-5 warnings (maintained via hooks)
- 📁 ~10 files at repo root (stable)
- 📄 ~15 files in docs/ (stable, SOT + guides)
- 🏃 20-30 active run directories (old ones archived)

---

## Part 8: Risk Assessment & Mitigation

### Risk 1: Data Loss During Tidy

**Probability**: Low
**Impact**: High
**Mitigation**:
- ✅ Git checkpoints before/after
- ✅ Zip checkpoints in .autonomous_runs/checkpoints/
- ✅ Dry-run mode default
- ✅ All moves reversible via git

### Risk 2: Breaking Active Workflows

**Probability**: Medium
**Impact**: Medium
**Mitigation**:
- ✅ Communicate changes to team
- ✅ Update documentation
- ✅ Test on branch first
- ✅ Gradual rollout (Phase A → B → D → E)

### Risk 3: Duplicate SOT File Conflicts

**Probability**: High (already exists)
**Impact**: High
**Mitigation**:
- ✅ Manual review of root vs docs/ versions
- ✅ Careful merge process
- ✅ Backup before deletion
- ✅ Document which version wins (docs/ is authoritative)

### Risk 4: Over-Aggressive Docs Reduction

**Probability**: Medium
**Impact**: Medium
**Mitigation**:
- ✅ Review reduction plan before executing
- ✅ Git checkpoint enables rollback
- ✅ Allowlist refinement based on feedback
- ✅ Two-phase approach: conservative → reduction

### Risk 5: CI Blocks Valid Commits

**Probability**: Medium
**Impact**: Low
**Mitigation**:
- ✅ Non-blocking mode initially
- ✅ 2-week buffer for workspace cleanup
- ✅ Clear error messages with remediation steps
- ✅ Override mechanism for emergencies

---

## Conclusion

**Root Causes Summary**:
1. **Historical accumulation**: No systematic cleanup for months
2. **Workflow gaps**: Cursor creates files at root, no routing
3. **Duplicate SOT files**: Critical issue needing immediate resolution
4. **Verifier conceptual mismatch**: Treats runs as projects
5. **Documentation sprawl**: 159 files in docs/ vs 6 needed
6. **No enforcement**: No CI, hooks, or automation

**Recommended Priority**:
1. 🔴 **CRITICAL**: Resolve duplicate SOT files (Phase A1)
2. 🔴 **HIGH**: Execute unified tidy (Phase A2-A4)
3. 🟡 **MEDIUM**: Fix verifier logic (Phase B)
4. 🟡 **MEDIUM**: Docs reduction (Phase D)
5. 🟢 **LOW**: Long-term automation (Phase E)

**Estimated Total Effort**: 8-16 hours spread over 2-3 weeks

**Expected Outcome**: Clean, maintainable workspace with automated enforcement preventing regression

---

**Document Version**: BUILD-147 Phase A P11+ (2026-01-01)
**Related Docs**:
- [WORKSPACE_ORGANIZATION_SPEC.md](WORKSPACE_ORGANIZATION_SPEC.md)
- [TIDY_SYSTEM_USAGE.md](TIDY_SYSTEM_USAGE.md)
- [IMPLEMENTATION_PLAN_TIDY_GAP_CLOSURE.md](IMPLEMENTATION_PLAN_TIDY_GAP_CLOSURE.md)
