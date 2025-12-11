# Tidy Scripts - Autopack Workspace Organization

This folder contains all scripts related to workspace organization, cleanup, and Source of Truth (SOT) synchronization.

## Quick Start

### Daily SOT Sync (After any changes)
```bash
# Quick sync - just update CONSOLIDATED_*.md files
python scripts/tidy/sync_sot.py --quick

# Full verification
python scripts/tidy/sync_sot.py
```

### Full Workspace Cleanup
```bash
# Dry-run first (safe)
python scripts/tidy/corrective_cleanup_v2.py --dry-run

# Execute cleanup (6 phases)
python scripts/tidy/corrective_cleanup_v2.py --execute
```

## Scripts Overview

### 1. `sync_sot.py` - Source of Truth Synchronization
**Purpose**: Keep all SOT files up-to-date regardless of who made changes (Cursor, Autopack, manual edits)

**What it syncs**:
- CONSOLIDATED_*.md files (via consolidate_docs.py)
- ARCHIVE_INDEX.md
- Verifies all docs/ SOT files

**Usage**:
```bash
python scripts/tidy/sync_sot.py              # Full sync + verification
python scripts/tidy/sync_sot.py --quick      # Just CONSOLIDATED_*.md
python scripts/tidy/sync_sot.py --dry-run    # Preview changes
python scripts/tidy/sync_sot.py --full-cleanup  # Run all 6 cleanup phases
```

**When to run**:
- After Cursor makes implementation changes
- After manual edits to docs/
- After any structural changes
- Before committing major work
- **Recommended**: Add to pre-commit hook or run daily

---

### 2. `corrective_cleanup_v2.py` - Full Workspace Cleanup
**Purpose**: Complete workspace organization following WORKSPACE_ORGANIZATION_SPEC.md

**6 Phases**:
1. **Root Cleanup** - Move truth sources to docs/
2. **Archive Restructuring** - Flatten nesting, group by project
3. **.autonomous_runs Cleanup** - Organize project files
4. **Documentation Restoration** - Move CONSOLIDATED_*.md to docs/
5. **Cleanup Artifacts** - Group tidy docs in archive/tidy_v7/
6. **SOT Synchronization** - Update all truth sources

**Usage**:
```bash
python scripts/tidy/corrective_cleanup_v2.py --dry-run    # Safe preview
python scripts/tidy/corrective_cleanup_v2.py --execute    # Full cleanup
python scripts/tidy/corrective_cleanup_v2.py --validate-only  # Just check
```

**When to run**:
- Major workspace reorganization needed
- After merging large features
- Monthly maintenance
- When validation fails

---

### 3. `tidy_workspace.py` - Incremental Tidy
**Purpose**: Lightweight cleanup for daily use

**Usage**:
```bash
python scripts/tidy/tidy_workspace.py
```

---

### 4. `tidy_docs.py` - Documentation Organization
**Purpose**: Organize documentation files

---

### 5. `run_tidy_all.py` - Run All Tidy Operations
**Purpose**: Convenience script to run all tidy operations

---

## Source of Truth (SOT) Files

### What are SOT files?
Files that contain the current, authoritative state of the project. These must always be up-to-date.

### Autopack SOT files (in `docs/`):
- `README.md` - Project overview (quick-start)
- `WORKSPACE_ORGANIZATION_SPEC.md` - Organization principles
- `WHATS_LEFT_TO_BUILD.md` - Current roadmap
- `WHATS_LEFT_TO_BUILD_MAINTENANCE.md` - Maintenance tasks
- `SETUP_GUIDE.md` - Setup instructions
- `DEPLOYMENT_GUIDE.md` - Deployment guide
- `project_ruleset_Autopack.json` - Auto-updated project rules
- `project_issue_backlog.json` - Auto-updated issue backlog
- `autopack_phase_plan.json` - Auto-updated phase plan
- `CONSOLIDATED_*.md` - Auto-generated consolidation files
- `openapi.json` - API specification (in docs/api/)

### File-organizer SOT files (in `.autonomous_runs/file-organizer-app-v1/docs/`):
- `README.md` - Project documentation
- `WHATS_LEFT_TO_BUILD.md` - Roadmap
- `ARCHITECTURE.md` - Architecture docs
- `project_learned_rules.json` - Learned rules
- `autopack_phase_plan.json` - Phase plan
- `plan_maintenance*.json` - Maintenance plans

### Auto-Update Behavior:

#### Files that auto-update during Autopack runs:
- `project_ruleset_Autopack.json` (when rules change)
- `project_issue_backlog.json` (via issue_tracker.py)
- `autopack_phase_plan.json` (when planning occurs)

#### Files that need manual sync (via `sync_sot.py`):
- `CONSOLIDATED_*.md` (after doc changes)
- `ARCHIVE_INDEX.md` (after archive changes)

## Workflow Recommendations

### For Cursor-based Development:
1. Make changes in Cursor
2. Run `python scripts/tidy/sync_sot.py --quick`
3. Commit changes including updated CONSOLIDATED files

### For Autopack-based Development:
- SOT files auto-update during runs
- Run `sync_sot.py` if you made manual edits

### For Major Refactoring:
1. Run full cleanup: `python scripts/tidy/corrective_cleanup_v2.py --execute`
2. Verify: `python scripts/tidy/corrective_cleanup_v2.py --validate-only`
3. Commit all changes

### Pre-Commit Hook (Recommended):
```bash
# In .git/hooks/pre-commit
#!/bin/bash
python scripts/tidy/sync_sot.py --quick
git add docs/CONSOLIDATED_*.md
```

## Archive Structure

```
archive/
├── tidy_v7/                    # Tidy documentation (this cleanup session)
│   ├── CLEANUP_V2_SUMMARY.md
│   ├── FILE_RELOCATION_MAP.md
│   └── ...
├── reports/                    # Report documents
├── research/                   # Research notes
└── diagnostics/                # Diagnostic runs and data
```

## Troubleshooting

### "CONSOLIDATED_*.md files not updated"
- Check `scripts/consolidate_docs.py` exists
- Run manually: `python scripts/consolidate_docs.py`
- Check for Python errors in output

### "SOT files missing from docs/"
- Run: `python scripts/tidy/corrective_cleanup_v2.py --execute`
- This moves all truth sources to correct locations

### "Validation fails"
- Run: `python scripts/tidy/corrective_cleanup_v2.py --validate-only`
- Review specific issues listed
- Run full cleanup if needed

## Future Enhancements

Ideas for automation:
- [ ] Git pre-commit hook for automatic SOT sync
- [ ] GitHub Actions workflow for weekly cleanup
- [ ] Database schema sync to docs/
- [ ] Automatic changelog generation from SOT changes
- [ ] VS Code task for one-click sync

## Related Documentation

- [WORKSPACE_ORGANIZATION_SPEC.md](../../docs/WORKSPACE_ORGANIZATION_SPEC.md) - Organization principles
- [archive/tidy_v7/](../../archive/tidy_v7/) - This cleanup session's documentation
- [scripts/consolidate_docs.py](../consolidate_docs.py) - CONSOLIDATED_*.md generator
