# Truth Sources Consolidation to docs/ - Summary

**Date:** 2025-12-11
**Status:** SPECIFICATIONS UPDATED, SCRIPT UPDATES IN PROGRESS

---

## Overview

**Change:** Consolidate ALL truth source files into project `docs/` folders instead of having them scattered at root or in `config/`.

**Rationale:** Centralize all documentation and truth sources in one logical location per project.

---

## Completed Updates

### 1. [PROPOSED_CLEANUP_STRUCTURE_V2.md](PROPOSED_CLEANUP_STRUCTURE_V2.md)

**Updated:**
- Root structure: Only README.md (quick-start) stays at root
- docs/ structure: ALL truth sources now in docs/
  - Documentation .md files
  - Ruleset .json files (moved from config/)
  - API specs in docs/api/
- file-organizer structure: docs/ has all truth sources
- Cleanup Actions (Phase 1-4)
- Validation Checklist

###2. [scripts/corrective_cleanup_v2.py](scripts/corrective_cleanup_v2.py)

**Phase 1 Updated** ✅:
- [1.1] Move truth source .md files to docs/ (WORKSPACE_ORGANIZATION_SPEC.md, WHATS_LEFT_TO_BUILD.md, etc.)
- [1.2] Move ruleset .json files to docs/ (project_ruleset_Autopack.json, etc.)
- [1.3] Move API specs to docs/api/
- [1.4] Move diagnostic data to archive/
- [1.5] Archive obsolete documentation

### 3. [CLEANUP_V2_SUMMARY.md](CLEANUP_V2_SUMMARY.md)

**Updated:**
- Phase 1 description (consolidate to docs/)
- Phase 3 description (file-organizer consolidation)

### 4. [FILE_RELOCATION_MAP.md](FILE_RELOCATION_MAP.md) ✅ Created

Complete mapping of all file relocations and scripts that need updates.

---

## Remaining Script Updates Needed

### CRITICAL - Auto-Update Scripts (Break if not updated)

These scripts auto-update the truth source files and MUST be updated:

#### 1. **scripts/run_backlog_maintenance.py**
**Current:** Writes to `REPO_ROOT / "project_issue_backlog.json"`
**Change to:** `REPO_ROOT / "docs" / "project_issue_backlog.json"`

#### 2. **scripts/plan_from_markdown.py**
**Current:** Writes to `REPO_ROOT / "autopack_phase_plan.json"`
**Change to:** `REPO_ROOT / "docs" / "autopack_phase_plan.json"`

#### 3. **scripts/plan_hardening.py**
**Current:** Reads `REPO_ROOT / "project_ruleset_Autopack.json"`
**Change to:** `REPO_ROOT / "docs" / "project_ruleset_Autopack.json"`

#### 4. **scripts/tidy_workspace.py**
**May reference:** Multiple truth source files
**Action:** Search and update all paths

#### 5. **scripts/tidy_docs.py**
**May reference:** WHATS_LEFT_TO_BUILD.md
**Action:** Search and update paths

### MEDIUM PRIORITY - Reference Scripts

#### 6. **scripts/task_format_converter.py**
May reference roadmaps - update if needed

#### 7. **scripts/create_fileorg_*.py** (multiple files)
May reference WHATS_LEFT_TO_BUILD.md - update if needed

#### 8. **scripts/setup_new_project.py**
May reference specs - update if needed

### CLEANUP SCRIPTS - Update Validation

#### 9. **scripts/corrective_cleanup_v2.py**
- ✅ Phase 1 updated
- ⏳ Phase 3 needs file-organizer consolidation logic
- ⏳ Phase 4 needs path updates
- ⏳ validate_v2_structure() needs updates

#### 10. **scripts/corrective_cleanup.py**
Validation may need updates for new paths

#### 11. **scripts/comprehensive_cleanup.py**
May reference files - update if needed

---

## New File Paths Reference

### Autopack Truth Sources

| File | Old Path | New Path |
|------|----------|----------|
| README.md | Root (stays) | Root (quick-start) + docs/README.md (comprehensive) |
| WORKSPACE_ORGANIZATION_SPEC.md | Root | docs/ |
| WHATS_LEFT_TO_BUILD.md | Root | docs/ |
| WHATS_LEFT_TO_BUILD_MAINTENANCE.md | Root | docs/ |
| SETUP_GUIDE.md | docs/ | docs/ (already there) |
| DEPLOYMENT_GUIDE.md | archive/reports/ | docs/ (restore) |
| project_ruleset_Autopack.json | Root | docs/ |
| project_issue_backlog.json | Root | docs/ |
| autopack_phase_plan.json | Root | docs/ |
| openapi.json | Root | docs/api/ |

### file-organizer-app-v1 Truth Sources

| File | Old Path | New Path |
|------|----------|----------|
| README.md | Project root | Root (quick-start) + docs/README.md (comprehensive) |
| WHATS_LEFT_TO_BUILD.md | Project root | docs/ |
| project_learned_rules.json | docs/ | docs/ (already there) |

---

## Python Code Pattern Changes

### Old Pattern (Root)
```python
REPO_ROOT = Path(__file__).parent.parent

ruleset_path = REPO_ROOT / "project_ruleset_Autopack.json"
backlog_path = REPO_ROOT / "project_issue_backlog.json"
plan_path = REPO_ROOT / "autopack_phase_plan.json"
roadmap_path = REPO_ROOT / "WHATS_LEFT_TO_BUILD.md"
spec_path = REPO_ROOT / "WORKSPACE_ORGANIZATION_SPEC.md"
```

### New Pattern (docs/)
```python
REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"

ruleset_path = DOCS_DIR / "project_ruleset_Autopack.json"
backlog_path = DOCS_DIR / "project_issue_backlog.json"
plan_path = DOCS_DIR / "autopack_phase_plan.json"
roadmap_path = DOCS_DIR / "WHATS_LEFT_TO_BUILD.md"
spec_path = DOCS_DIR / "WORKSPACE_ORGANIZATION_SPEC.md"
```

---

## Next Steps

### Phase 1: Update Critical Auto-Update Scripts
1. Update scripts/run_backlog_maintenance.py
2. Update scripts/plan_from_markdown.py
3. Update scripts/plan_hardening.py
4. Update scripts/tidy_workspace.py
5. Update scripts/tidy_docs.py

### Phase 2: Update Cleanup Script Validation
1. Update corrective_cleanup_v2.py Phase 3
2. Update corrective_cleanup_v2.py Phase 4
3. Update corrective_cleanup_v2.py validate_v2_structure()

### Phase 3: Update Reference Scripts (if needed)
1. Search and update create_fileorg_*.py
2. Search and update task_format_converter.py
3. Search and update setup_new_project.py

### Phase 4: Test
1. Run corrective_cleanup_v2.py --dry-run
2. Verify all paths work
3. Execute cleanup

---

## Testing Checklist

After all updates:
- [ ] Run dry-run: `python scripts/corrective_cleanup_v2.py --dry-run`
- [ ] Verify Phase 1 moves files to docs/
- [ ] Verify Phase 3 consolidates file-organizer docs/
- [ ] Verify Phase 4 paths are correct
- [ ] Test backlog maintenance script (dry-run)
- [ ] Test plan creation script (dry-run)
- [ ] Execute cleanup: `python scripts/corrective_cleanup_v2.py --execute`
- [ ] Verify all auto-update scripts work with new paths

---

**Generated:** 2025-12-11
**Status:** Specifications complete, Phase 1 script updated, remaining scripts need updates
