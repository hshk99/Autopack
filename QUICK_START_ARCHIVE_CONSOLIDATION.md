# Quick Start: Full Archive Consolidation

**Goal**: Consolidate 150+ archive documentation files into chronologically-sorted SOT files

**Time**: 45 minutes total
**Risk**: LOW (dry-run available, fully reversible)

---

## Phase 1: Documentation Consolidation (30 min)

### Step 1: Dry-Run Test
```bash
python scripts/tidy/consolidate_docs_directory.py --directory archive --dry-run
```

**Check**: Should show ~155 files processed from `archive/plans/`, `archive/reports/`, `archive/analysis/`, `archive/research/`

### Step 2: Execute Consolidation
```bash
python scripts/tidy/consolidate_docs_directory.py --directory archive
```

**Result**:
- `docs/BUILD_HISTORY.md` - 125 entries (chronologically sorted)
- `docs/DEBUG_LOG.md` - 35 entries (chronologically sorted)
- `docs/ARCHITECTURE_DECISIONS.md` - 68 entries (chronologically sorted)

### Step 3: Commit
```bash
git add docs/*.md scripts/tidy/consolidate_docs_v2.py
git commit -m "tidy: consolidate archive documentation into SOT files

- Consolidated 155+ .md files from archive/ subdirectories
- All entries chronologically sorted (most recent first)
- Fixed recursive glob bug for comprehensive processing

🤖 Generated with Claude Code"
```

---

## Phase 2: Archive Restructuring (15 min)

### Step 1: Dry-Run Test
```bash
python scripts/tidy/phase2_archive_cleanup.py --dry-run
```

**Check**: Should show scripts moving to `superseded/`, logs centralizing, empty dirs removing

### Step 2: Execute Cleanup
```bash
python scripts/tidy/phase2_archive_cleanup.py --execute
```

**Result**:
- Outdated scripts → `scripts/superseded/`
- Log files → `archive/diagnostics/logs/`
- Empty directories removed
- Documentation created

### Step 3: Commit
```bash
git add -A
git commit -m "tidy: restructure archive after documentation consolidation

Phase 2 cleanup:
- Moved outdated scripts to scripts/superseded/
- Centralized log files to archive/diagnostics/logs/
- Removed empty directories
- Created superseded scripts documentation

🤖 Generated with Claude Code"
```

---

## Verification

### Check SOT Files
```bash
# Verify chronological sorting (most recent first)
head -50 docs/BUILD_HISTORY.md | grep "^| 202"

# Count entries
grep -c "^### BUILD-" docs/BUILD_HISTORY.md
grep -c "^### DEBUG-" docs/DEBUG_LOG.md
grep -c "^### DECISION-" docs/ARCHITECTURE_DECISIONS.md
```

### Check Archive Structure
```bash
tree archive -L 2
```

**Expected**:
```
archive/
├── tidy_v7/      # Active docs
├── prompts/      # Reference
└── diagnostics/
    ├── logs/     # Centralized logs
    └── runs/     # Old runs (optional)
```

---

## Rollback (If Needed)

### Rollback Phase 1
```bash
git checkout HEAD -- docs/*.md scripts/tidy/consolidate_docs_v2.py
```

### Rollback Phase 2
```bash
git checkout HEAD -- scripts/superseded/ archive/ scripts/tidy/phase2_archive_cleanup.py
```

---

## Documentation

**Full Details**: [archive/tidy_v7/IMPLEMENTATION_PLAN_FULL_ARCHIVE_CLEANUP.md](archive/tidy_v7/IMPLEMENTATION_PLAN_FULL_ARCHIVE_CLEANUP.md)

**Summary**: [archive/tidy_v7/IMPLEMENTATION_SUMMARY.md](archive/tidy_v7/IMPLEMENTATION_SUMMARY.md)

**Assessments**:
- [archive/tidy_v7/ARCHIVE_PLANS_ASSESSMENT.md](archive/tidy_v7/ARCHIVE_PLANS_ASSESSMENT.md)
- [archive/tidy_v7/ARCHIVE_REPORTS_ASSESSMENT.md](archive/tidy_v7/ARCHIVE_REPORTS_ASSESSMENT.md)
- [archive/tidy_v7/ARCHIVE_ANALYSIS_ASSESSMENT.md](archive/tidy_v7/ARCHIVE_ANALYSIS_ASSESSMENT.md)

---

## Status: ✅ READY TO EXECUTE

All fixes applied, assessments complete, scripts tested.
