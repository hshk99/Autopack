# File Relocation Map - Truth Sources Consolidation

**Date:** 2025-12-11
**Purpose:** Track all file path changes for truth source consolidation to docs/

## Summary

**Goal:** Consolidate ALL truth source files into project `docs/` folders

---

## Autopack Truth Source Files

### Documentation Files (.md)

| Old Path (Root) | New Path (docs/) | Status |
|-----------------|------------------|--------|
| `README.md` | Keep at root (quick-start) + create `docs/README.md` (comprehensive) | Split |
| `WORKSPACE_ORGANIZATION_SPEC.md` | `docs/WORKSPACE_ORGANIZATION_SPEC.md` | Move |
| `WHATS_LEFT_TO_BUILD.md` | `docs/WHATS_LEFT_TO_BUILD.md` | Move |
| `WHATS_LEFT_TO_BUILD_MAINTENANCE.md` | `docs/WHATS_LEFT_TO_BUILD_MAINTENANCE.md` | Move |
| `docs/SETUP_GUIDE.md` | `docs/SETUP_GUIDE.md` | Already there |
| `archive/reports/DEPLOYMENT_GUIDE.md` | `docs/DEPLOYMENT_GUIDE.md` | Restore |

### Ruleset/Config Files (.json)

| Old Path (Root) | New Path (docs/) | Auto-Updated By |
|-----------------|------------------|-----------------|
| `project_ruleset_Autopack.json` | `docs/project_ruleset_Autopack.json` | Multiple scripts |
| `project_issue_backlog.json` | `docs/project_issue_backlog.json` | Backlog maintenance |
| `autopack_phase_plan.json` | `docs/autopack_phase_plan.json` | Phase planning |
| `openapi.json` | `docs/api/openapi.json` | API generation |

---

## file-organizer-app-v1 Truth Source Files

### Project Root → docs/

| Old Path | New Path | Status |
|----------|----------|--------|
| `.autonomous_runs/file-organizer-app-v1/README.md` | Keep at root (quick-start) + move to `docs/README.md` | Split |
| `.autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md` | `.autonomous_runs/file-organizer-app-v1/docs/WHATS_LEFT_TO_BUILD.md` | Move |
| `.autonomous_runs/file-organizer-app-v1/docs/project_learned_rules.json` | `.autonomous_runs/file-organizer-app-v1/docs/project_learned_rules.json` | Already there |

---

## Scripts Requiring Path Updates

### High Priority (Auto-Update Truth Sources)

1. **`scripts/run_backlog_maintenance.py`** - Updates `project_issue_backlog.json`
   - Change: Root → `docs/project_issue_backlog.json`

2. **`scripts/plan_from_markdown.py`** - Updates `autopack_phase_plan.json`
   - Change: Root → `docs/autopack_phase_plan.json`

3. **`scripts/plan_hardening.py`** - References `project_ruleset_Autopack.json`
   - Change: Root → `docs/project_ruleset_Autopack.json`

4. **`scripts/tidy_workspace.py`** - May reference multiple files
   - Change: Update all root → docs/ paths

5. **`scripts/consolidate_docs.py`** - Generates `ARCHIVE_INDEX.md`
   - No change needed (generates to archive/)

6. **`src/autopack/archive_consolidator.py`** - Auto-updates CONSOLIDATED files
   - No change needed (already outputs to archive/)

### Medium Priority (Reference Truth Sources)

7. **`scripts/tidy_docs.py`** - May move WHATS_LEFT_TO_BUILD
8. **`scripts/create_fileorg_*.py`** - May reference WHATS_LEFT_TO_BUILD
9. **`scripts/task_format_converter.py`** - May reference roadmaps
10. **`scripts/setup_new_project.py`** - May reference specs

### Low Priority (Cleanup Scripts - Will Be Updated Anyway)

11. **`scripts/corrective_cleanup_v2.py`** - Phase 1 & 4 need updates
12. **`scripts/corrective_cleanup.py`** - Validation may need updates
13. **`scripts/comprehensive_cleanup.py`** - May reference files

---

## Path Change Constants

### Python Scripts - Update These Patterns

**Old:**
```python
REPO_ROOT / "project_ruleset_Autopack.json"
REPO_ROOT / "project_issue_backlog.json"
REPO_ROOT / "autopack_phase_plan.json"
REPO_ROOT / "WHATS_LEFT_TO_BUILD.md"
REPO_ROOT / "WORKSPACE_ORGANIZATION_SPEC.md"
REPO_ROOT / "openapi.json"
```

**New:**
```python
REPO_ROOT / "docs" / "project_ruleset_Autopack.json"
REPO_ROOT / "docs" / "project_issue_backlog.json"
REPO_ROOT / "docs" / "autopack_phase_plan.json"
REPO_ROOT / "docs" / "WHATS_LEFT_TO_BUILD.md"
REPO_ROOT / "docs" / "WORKSPACE_ORGANIZATION_SPEC.md"
REPO_ROOT / "docs" / "api" / "openapi.json"
```

---

## Validation Updates Needed

### corrective_cleanup_v2.py - validate_v2_structure()

**Check 4: Config files moved**
- Old: Check root for `project_ruleset_Autopack.json`, etc.
- New: Check `docs/` for these files

**Check 5: Truth source docs exist**
- Old: Check only docs/SETUP_GUIDE.md, DEPLOYMENT_GUIDE.md
- New: Check ALL truth sources in docs/:
  - README.md (comprehensive)
  - WORKSPACE_ORGANIZATION_SPEC.md
  - WHATS_LEFT_TO_BUILD.md
  - WHATS_LEFT_TO_BUILD_MAINTENANCE.md
  - SETUP_GUIDE.md
  - DEPLOYMENT_GUIDE.md
  - project_ruleset_Autopack.json
  - project_issue_backlog.json
  - autopack_phase_plan.json

---

## Migration Checklist

- [ ] Update Phase 1 in corrective_cleanup_v2.py
- [ ] Update Phase 4 in corrective_cleanup_v2.py
- [ ] Update validation in corrective_cleanup_v2.py
- [ ] Update scripts/run_backlog_maintenance.py
- [ ] Update scripts/plan_from_markdown.py
- [ ] Update scripts/plan_hardening.py
- [ ] Update scripts/tidy_workspace.py
- [ ] Update scripts/tidy_docs.py
- [ ] Update create_fileorg scripts (if needed)
- [ ] Update CLEANUP_V2_SUMMARY.md
- [ ] Test dry-run after all updates

---

**Generated:** 2025-12-11
