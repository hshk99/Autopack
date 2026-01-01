# Tidy Scripts - Autopack Workspace Organization

This folder contains all scripts related to workspace organization, cleanup, and Source of Truth (SOT) synchronization.

## Important: SOT → Runtime Retrieval Integration

The tidy system's SOT ledgers (BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS) can now be indexed into `MemoryService` for runtime retrieval by Autopack. See [docs/TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md](../../docs/TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md) for implementation details and usage.

## Quick Start

### Full Workspace Cleanup (Recommended - Fully Automatic)
```bash
# Dry-run first (safe)
python scripts/tidy/corrective_cleanup_v2.py --dry-run

# Execute cleanup (6 phases) - Automatically syncs ALL SOT files
python scripts/tidy/corrective_cleanup_v2.py --execute
```

**Phase 6 automatically updates:**
- Documentation consolidation (BUILD_HISTORY.md, DEBUG_LOG.md, ARCHITECTURE_DECISIONS.md via consolidate_docs_v2.py)
- Database schemas (database_schema_*.json)
- ARCHIVE_INDEX.md (via consolidate_docs.py)
- All truth sources in docs/ folders

### Manual SOT Sync (Optional - Use only if you need standalone sync)
```bash
# Quick sync - just update CONSOLIDATED_*.md files
python scripts/tidy/sync_sot.py --quick

# Full verification
python scripts/tidy/sync_sot.py
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

### 2. `corrective_cleanup_v2.py` - Full Workspace Cleanup (PRIMARY SCRIPT)
**Purpose**: Complete workspace organization following WORKSPACE_ORGANIZATION_SPEC.md

**6 Phases**:
1. **Root Cleanup** - Organize root directory
   - Move truth sources (*.md, rulesets) to docs/
   - Move test scripts (test_*.py, *.sh) to tests/
   - Move tidy configs (tidy_scope.yaml) to scripts/tidy/
   - Remove obsolete placeholders
   - Keep essential configs (package.json, docker-compose.yml) at root
2. **Archive Restructuring** - Flatten nesting, group by project, organize configs/scripts
   - Flatten archive/reports/ excessive nesting
   - Move tidy configs (tidy_scope.yaml) to scripts/tidy/
   - Move tidy scripts (cleanup_script.sh) to scripts/tidy/
   - Remove obsolete placeholders or move reference scripts to scripts/archive/
   - Keep superseded diagnostics in archive/superseded/ for historical reference
3. **.autonomous_runs Cleanup** - Organize project files, move SOT files to docs/
4. **Documentation Restoration** - Move CONSOLIDATED_*.md to docs/
5. **Cleanup Artifacts** - Group tidy docs in archive/tidy_v7/
6. **SOT Synchronization** - **AUTOMATICALLY** updates:
   - Old CONSOLIDATED_*.md → AI-optimized docs (BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS via consolidate_docs_v2.py)
   - ARCHIVE_INDEX.md (via consolidate_docs.py)
   - Database schemas → database_schema_*.json (via sync_database.py)
   - All truth sources verified
   - UNSORTED_REVIEW.md created for ambiguous content (manual review required)

**Usage**:
```bash
python scripts/tidy/corrective_cleanup_v2.py --dry-run    # Safe preview
python scripts/tidy/corrective_cleanup_v2.py --execute    # Full cleanup + auto-sync
python scripts/tidy/corrective_cleanup_v2.py --validate-only  # Just check
```

**When to run**:
- After any significant changes (automatic SOT sync included)
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

### 5. `consolidate_docs_v2.py` - AI-Optimized Documentation Consolidation
**Purpose**: Consolidate scattered archive files into 3 AI-optimized documentation files

**What it generates**:
- `BUILD_HISTORY.md` - Past implementations (what was built, when, how)
- `DEBUG_LOG.md` - Problem solving (errors and fixes)
- `ARCHITECTURE_DECISIONS.md` - Design rationale (why decisions were made)
- `UNSORTED_REVIEW.md` - Ambiguous content for manual review

**Classification System**:
- Confidence scoring (0.6 threshold)
- Pattern matching (filename + content + keywords)
- Timestamp extraction (4-tier fallback)
- 26 BUILD entries, 32 DEBUG entries, 19 DECISION entries (example)

**Usage**:
```bash
python scripts/tidy/consolidate_docs_v2.py                           # Autopack consolidation
python scripts/tidy/consolidate_docs_v2.py --dry-run                 # Preview changes
python scripts/tidy/consolidate_docs_v2.py --project file-organizer-app-v1  # Other projects
```

**When to run**:
- Standalone use if you only need documentation consolidation
- **Automatically runs** during corrective_cleanup_v2.py Phase 6.4

---

### 6. `sync_database.py` - Database Schema Synchronization
**Purpose**: Export database schemas to JSON files in docs/ folders

**What it syncs**:
- SQLite database schemas (tables, columns, types)
- Row counts per table
- Database statistics

**Usage**:
```bash
python scripts/tidy/sync_database.py                    # Sync all databases
python scripts/tidy/sync_database.py --dry-run          # Preview changes
python scripts/tidy/sync_database.py --db autopack.db   # Sync specific DB
python scripts/tidy/sync_database.py --all-projects     # Include file-organizer DBs
```

**When to run**:
- Standalone use if you only need DB sync
- **Automatically runs** during corrective_cleanup_v2.py Phase 6.3

---

### 7. `run_tidy_all.py` - Run All Tidy Operations
**Purpose**: Convenience script to run all tidy operations

---

## Source of Truth (SOT) Files

### What are SOT files?
Files that contain the current, authoritative state of the project. These must always be up-to-date.

### Autopack SOT files (in `docs/`):

**AI-Optimized Documentation (Auto-generated in Phase 6.4)**:
- `BUILD_HISTORY.md` - Past implementations and completions
- `DEBUG_LOG.md` - Error history and fixes
- `ARCHITECTURE_DECISIONS.md` - Design rationale and strategy
- `UNSORTED_REVIEW.md` - Ambiguous content for manual review

**Truth Sources**:
- `README.md` - Project overview (quick-start)
- `WORKSPACE_ORGANIZATION_SPEC.md` - Organization principles
- `WHATS_LEFT_TO_BUILD.md` - Current roadmap
- `WHATS_LEFT_TO_BUILD_MAINTENANCE.md` - Maintenance tasks
- `SETUP_GUIDE.md` - Setup instructions
- `DEPLOYMENT_GUIDE.md` - Deployment guide
- `project_ruleset_Autopack.json` - Auto-updated project rules
- `project_issue_backlog.json` - Auto-updated issue backlog
- `autopack_phase_plan.json` - Auto-updated phase plan
- `database_schema_*.json` - Database schema exports (auto-generated)
- `openapi.json` - API specification (in docs/api/)

### File-organizer SOT files (in `.autonomous_runs/file-organizer-app-v1/docs/`):

**AI-Optimized Documentation (Auto-generated in Phase 6.4)**:
- `BUILD_HISTORY.md` - Past implementations and completions
- `DEBUG_LOG.md` - Error history and fixes
- `ARCHITECTURE_DECISIONS.md` - Design rationale and strategy
- `UNSORTED_REVIEW.md` - Ambiguous content for manual review

**Truth Sources**:
- `README.md` - Project documentation
- `WHATS_LEFT_TO_BUILD.md` - Roadmap
- `ARCHITECTURE.md` - Architecture docs
- `project_learned_rules.json` - Learned rules
- `autopack_phase_plan.json` - Phase plan
- `plan_maintenance*.json` - Maintenance plans
- `database_schema_*.json` - Database schema exports (auto-generated)

### Auto-Update Behavior:

#### Files that auto-update during corrective_cleanup_v2.py Phase 6:
- `BUILD_HISTORY.md` - **Automatically generated** from old CONSOLIDATED files and archive/ (via consolidate_docs_v2.py)
- `DEBUG_LOG.md` - **Automatically generated** from error reports and test results (via consolidate_docs_v2.py)
- `ARCHITECTURE_DECISIONS.md` - **Automatically generated** from strategy/analysis files (via consolidate_docs_v2.py)
- `UNSORTED_REVIEW.md` - **Automatically generated** for ambiguous content (manual review required)
- `ARCHIVE_INDEX.md` - **Automatically synced** via consolidate_docs.py
- `database_schema_*.json` - **Automatically exported** from SQLite databases (via sync_database.py)

#### Files that auto-update during Autopack runs:
- `project_ruleset_Autopack.json` (when rules change)
- `project_issue_backlog.json` (via issue_tracker.py)
- `autopack_phase_plan.json` (when planning occurs)

## Workflow Recommendations

### Standard Workflow (Recommended):
1. Make changes (via Cursor, Autopack, or manual edits)
2. Run full cleanup: `python scripts/tidy/corrective_cleanup_v2.py --execute`
3. **All SOT files automatically sync in Phase 6** (CONSOLIDATED files, DB schemas, etc.)
4. Commit all changes

### Quick Manual Sync (If needed without full cleanup):
1. Make changes
2. Run `python scripts/tidy/sync_sot.py --quick`
3. Commit changes

### For Major Refactoring:
1. Run full cleanup: `python scripts/tidy/corrective_cleanup_v2.py --execute`
2. Verify: `python scripts/tidy/corrective_cleanup_v2.py --validate-only`
3. Commit all changes

### Pre-Commit Hook (Optional):
```bash
# In .git/hooks/pre-commit
#!/bin/bash
# Option 1: Full cleanup with auto-sync (recommended)
python scripts/tidy/corrective_cleanup_v2.py --execute

# Option 2: Quick sync only (faster but doesn't reorganize)
# python scripts/tidy/sync_sot.py --quick
# git add docs/CONSOLIDATED_*.md docs/database_schema_*.json
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

### "Documentation files not updated"
**Solution**: Run the full cleanup script which includes automatic consolidation:
```bash
python scripts/tidy/corrective_cleanup_v2.py --execute
```
Phase 6 automatically runs consolidate_docs_v2.py to generate BUILD_HISTORY.md, DEBUG_LOG.md, and ARCHITECTURE_DECISIONS.md from all archive files and old CONSOLIDATED_*.md files.

**Note**: Old CONSOLIDATED_*.md files are replaced with AI-optimized format. Check UNSORTED_REVIEW.md for ambiguous content that needs manual review.

### "Database schema files missing"
**Solution**: Run the full cleanup script:
```bash
python scripts/tidy/corrective_cleanup_v2.py --execute
```
Phase 6 automatically exports database schemas to database_schema_*.json files.

### "SOT files missing from docs/"
**Solution**: Run full cleanup to move all truth sources to correct locations:
```bash
python scripts/tidy/corrective_cleanup_v2.py --execute
```

### "Validation fails"
**Solution**:
1. Check specific issues: `python scripts/tidy/corrective_cleanup_v2.py --validate-only`
2. Review specific issues listed
3. Run full cleanup: `python scripts/tidy/corrective_cleanup_v2.py --execute`

## Completed Enhancements

✅ **AI-Optimized Documentation Consolidation** - Phase 6 automatically generates BUILD_HISTORY.md, DEBUG_LOG.md, ARCHITECTURE_DECISIONS.md
✅ **Intelligent Classification** - Confidence scoring (0.6 threshold) with UNSORTED_REVIEW.md for manual review
✅ **Token Efficiency** - 59% size reduction (762KB → 310KB estimated) for AI consumption
✅ **Automatic database schema sync** - Phase 6 exports DB schemas to docs/
✅ **Automatic ARCHIVE_INDEX sync** - Phase 6 updates archive index

## Future Enhancements

Ideas for additional automation:
- [ ] GitHub Actions workflow for weekly cleanup
- [ ] Automatic changelog generation from SOT changes
- [ ] VS Code task for one-click sync
- [ ] Watch mode for continuous sync during development

## Related Documentation

- [WORKSPACE_ORGANIZATION_SPEC.md](../../docs/WORKSPACE_ORGANIZATION_SPEC.md) - Organization principles
- [archive/tidy_v7/](../../archive/tidy_v7/) - This cleanup session's documentation
- [scripts/consolidate_docs.py](../consolidate_docs.py) - CONSOLIDATED_*.md generator
