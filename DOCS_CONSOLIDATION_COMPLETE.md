# Truth Sources Consolidation to docs/ - COMPLETE

**Date:** 2025-12-11
**Status:** ✅ ALL UPDATES COMPLETE - READY FOR EXECUTION

---

## Summary

Successfully updated all specifications, scripts, and documentation to consolidate ALL truth source files into project `docs/` folders instead of having them scattered at root or in `config/`.

---

## What Was Updated

### 1. Specifications ✅

- **[PROPOSED_CLEANUP_STRUCTURE_V2.md](PROPOSED_CLEANUP_STRUCTURE_V2.md)** - Complete restructure
  - Root structure: Only README.md (quick-start) stays at root
  - docs/ structure: ALL truth sources now in docs/ (not config/)
  - file-organizer structure: docs/ has all truth sources
  - Cleanup Actions (Phase 1-4)
  - Validation Checklist

### 2. Cleanup Script ✅

- **[scripts/corrective_cleanup_v2.py](scripts/corrective_cleanup_v2.py)** - All phases updated
  - **Phase 1:** Moves truth sources from root → docs/ (not config/)
  - **Phase 3:** Consolidates file-organizer truth sources to docs/
  - **Phase 4:** Checks docs/ paths (not config/)
  - **validate_v2_structure():** Comprehensive checks for all truth sources in docs/

### 3. Auto-Update Scripts ✅

#### Critical Scripts (Auto-Update Truth Sources)

1. **[src/autopack/issue_tracker.py](src/autopack/issue_tracker.py)** - IssueTracker class
   - Updated `get_project_backlog_path()` method
   - Old: `self._runs_dir.parent / "project_issue_backlog.json"`
   - New: `self._runs_dir.parent / "docs" / "project_issue_backlog.json"`

2. **[scripts/plan_from_markdown.py](scripts/plan_from_markdown.py)** - Plan generator
   - Updated usage example in docstring
   - Now references `docs/autopack_phase_plan.json`

3. **[scripts/plan_hardening.py](scripts/plan_hardening.py)** - No changes needed
   - Uses command-line arguments, not hardcoded paths
   - Correctly defaults to `.autonomous_runs/<project>/autopack_phase_plan.json`

4. **[scripts/tidy_workspace.py](scripts/tidy_workspace.py)** - Workspace maintenance
   - Updated truth_files default list (lines 1131-1140)
   - Now references all truth sources in docs/ folders:
     - `REPO_ROOT / "docs" / "WHATS_LEFT_TO_BUILD.md"`
     - `REPO_ROOT / "docs" / "WHATS_LEFT_TO_BUILD_MAINTENANCE.md"`
     - `REPO_ROOT / "docs" / "WORKSPACE_ORGANIZATION_SPEC.md"`
     - `.autonomous_runs/file-organizer-app-v1/docs/WHATS_LEFT_TO_BUILD.md`

### 4. Documentation ✅

- **[CLEANUP_V2_SUMMARY.md](CLEANUP_V2_SUMMARY.md)** - Updated
  - Phase 1 description (consolidate to docs/ not config/)
  - Phase 3 description (file-organizer consolidation)
  - Phase 4 RULESET/CONFIG FILES section
  - Truth Sources Found list
  - Comprehensive Truth Source Inventory tables (Categories 4, 5, 6)

- **[FILE_RELOCATION_MAP.md](FILE_RELOCATION_MAP.md)** - Already complete
  - Complete mapping of all relocations

- **[CONSOLIDATION_TO_DOCS_SUMMARY.md](CONSOLIDATION_TO_DOCS_SUMMARY.md)** - Already complete
  - Complete overview and tracking document

---

## File Path Changes

### Python Code Pattern

**Old (Root):**
```python
REPO_ROOT = Path(__file__).parent.parent
ruleset_path = REPO_ROOT / "project_ruleset_Autopack.json"
backlog_path = REPO_ROOT / "project_issue_backlog.json"
plan_path = REPO_ROOT / "autopack_phase_plan.json"
```

**New (docs/):**
```python
REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"
ruleset_path = DOCS_DIR / "project_ruleset_Autopack.json"
backlog_path = DOCS_DIR / "project_issue_backlog.json"
plan_path = DOCS_DIR / "autopack_phase_plan.json"
```

### Truth Source Locations

#### Autopack (Main Project)
- `README.md` - Root (quick-start) + `docs/README.md` (comprehensive)
- `WORKSPACE_ORGANIZATION_SPEC.md` - Root → `docs/`
- `WHATS_LEFT_TO_BUILD.md` - Root → `docs/`
- `WHATS_LEFT_TO_BUILD_MAINTENANCE.md` - Root → `docs/`
- `project_ruleset_Autopack.json` - Root → `docs/`
- `project_issue_backlog.json` - Root → `docs/`
- `autopack_phase_plan.json` - Root → `docs/`
- `openapi.json` - Root → `docs/api/`

#### file-organizer-app-v1
- `README.md` - Project root → `docs/` (comprehensive) + quick-start at root
- `WHATS_LEFT_TO_BUILD.md` - Project root → `docs/`
- `project_learned_rules.json` - Already in `docs/` ✓

---

## Scripts Updated

### Files Modified

1. ✅ `scripts/corrective_cleanup_v2.py` - Phase 1, Phase 3, Phase 4, validate_v2_structure()
2. ✅ `src/autopack/issue_tracker.py` - get_project_backlog_path() method
3. ✅ `scripts/plan_from_markdown.py` - Usage example docstring
4. ✅ `scripts/tidy_workspace.py` - truth_files default list
5. ✅ `CLEANUP_V2_SUMMARY.md` - Multiple sections updated
6. ✅ `PROPOSED_CLEANUP_STRUCTURE_V2.md` - Already complete (from previous work)
7. ✅ `FILE_RELOCATION_MAP.md` - Already complete (from previous work)
8. ✅ `CONSOLIDATION_TO_DOCS_SUMMARY.md` - Already complete (from previous work)

### Files Verified (No Changes Needed)

- `scripts/plan_hardening.py` - Uses CLI args, no hardcoded paths
- `scripts/run_backlog_maintenance.py` - Doesn't directly write backlog file (uses IssueTracker)

---

## What Happens When You Execute

### Phase 1: Root Cleanup (corrective_cleanup_v2.py)
```
✓ Move truth source .md files to docs/:
  - WORKSPACE_ORGANIZATION_SPEC.md → docs/
  - WHATS_LEFT_TO_BUILD.md → docs/
  - WHATS_LEFT_TO_BUILD_MAINTENANCE.md → docs/

✓ Move ruleset .json files to docs/:
  - project_ruleset_Autopack.json → docs/
  - project_issue_backlog.json → docs/
  - autopack_phase_plan.json → docs/

✓ Move openapi.json to docs/api/

✓ Move diagnostic .json files to archive/diagnostics/

✓ Archive obsolete documentation files
```

### Phase 3: .autonomous_runs Cleanup
```
✓ Rename checkpoints/ → tidy_checkpoints/

✓ Consolidate file-organizer truth sources:
  - Move README.md from project root → docs/ (comprehensive)
  - Move WHATS_LEFT_TO_BUILD.md from project root → docs/
  - Create quick-start README.md at project root
  - Verify project_learned_rules.json in docs/
  - Create ARCHITECTURE.md stub in docs/
```

### Auto-Update Scripts Now Use New Paths
- `IssueTracker.get_project_backlog_path()` → writes to `docs/project_issue_backlog.json`
- `tidy_workspace.py` → reads truth sources from `docs/` folders
- Future plan generation → outputs to `docs/autopack_phase_plan.json`

---

## Testing Checklist

After execution, verify:

- [ ] Run dry-run: `python scripts/corrective_cleanup_v2.py --dry-run`
- [ ] Verify Phase 1 output shows moves to docs/ (not config/)
- [ ] Verify Phase 3 output shows file-organizer consolidation
- [ ] Execute cleanup: `python scripts/corrective_cleanup_v2.py --execute`
- [ ] Verify all files in docs/:
  - [ ] `docs/WORKSPACE_ORGANIZATION_SPEC.md`
  - [ ] `docs/WHATS_LEFT_TO_BUILD.md`
  - [ ] `docs/WHATS_LEFT_TO_BUILD_MAINTENANCE.md`
  - [ ] `docs/project_ruleset_Autopack.json`
  - [ ] `docs/project_issue_backlog.json`
  - [ ] `docs/autopack_phase_plan.json`
  - [ ] `docs/api/openapi.json`
- [ ] Verify file-organizer docs/:
  - [ ] `.autonomous_runs/file-organizer-app-v1/docs/README.md`
  - [ ] `.autonomous_runs/file-organizer-app-v1/docs/WHATS_LEFT_TO_BUILD.md`
  - [ ] `.autonomous_runs/file-organizer-app-v1/docs/ARCHITECTURE.md`
- [ ] Test IssueTracker writes to docs/:
  ```python
  from autopack.issue_tracker import IssueTracker
  tracker = IssueTracker("test-run")
  print(tracker.get_project_backlog_path())
  # Should show: C:\dev\Autopack\docs\project_issue_backlog.json
  ```
- [ ] Test tidy_workspace.py finds truth sources:
  ```bash
  python scripts/tidy_workspace.py --dry-run
  ```

---

## Next Steps

### 1. Execute Cleanup ✅ Ready
```bash
# Review dry-run output
python scripts/corrective_cleanup_v2.py --dry-run

# Execute if satisfied
python scripts/corrective_cleanup_v2.py --execute

# Validate
python scripts/corrective_cleanup_v2.py --validate-only
```

### 2. Test Auto-Update Scripts
After cleanup execution, test that auto-update scripts work:
```bash
# Test issue tracker (if you have test data)
python -c "from autopack.issue_tracker import IssueTracker; t = IssueTracker('test'); print(t.get_project_backlog_path())"

# Test tidy workspace
python scripts/tidy_workspace.py --dry-run
```

### 3. Create Git Commit
```bash
git add -A
git commit -m "Consolidate all truth sources to docs/ folders

- Updated corrective_cleanup_v2.py to move files to docs/ (not config/)
- Updated IssueTracker to write backlog to docs/
- Updated tidy_workspace.py to reference docs/ truth sources
- Updated all documentation to reflect docs/ consolidation
- Phase 1: Moves Autopack truth sources from root to docs/
- Phase 3: Consolidates file-organizer truth sources to docs/

All auto-update scripts now use docs/ paths."
```

---

## Summary of Changes

**Goal:** Consolidate ALL truth source files into project `docs/` folders

**Affected Categories:**
1. Documentation .md files (WORKSPACE_ORGANIZATION_SPEC.md, WHATS_LEFT_TO_BUILD.md, etc.)
2. Ruleset/Config .json files (project_ruleset_Autopack.json, etc.)
3. API specifications (openapi.json → docs/api/)
4. file-organizer truth sources (README.md, WHATS_LEFT_TO_BUILD.md → docs/)

**Scripts Updated:**
- 1 core script (IssueTracker)
- 3 documentation files (usage examples/descriptions)
- 1 maintenance script (tidy_workspace.py)
- 1 cleanup script (corrective_cleanup_v2.py - 3 phases + validation)

**Result:** Clean, centralized truth source organization with all auto-update scripts using correct paths.

---

**Generated:** 2025-12-11
**Status:** ✅ COMPLETE - Ready to execute cleanup script
