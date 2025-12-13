# Manual Tidy Function - Complete Guide

**Purpose**: Reusable manual tidy-up function that works on ANY directory within Autopack workspace
**Supports**: ALL file types (.md, .py, .log, .json, .yaml, .txt, .csv, .sql, and more)
**Mode**: Manual (on-demand) - NOT automatic

---

## Quick Start

### Basic Usage

```bash
# Step 1: Preview what will happen (SAFE - no changes)
python scripts/tidy/unified_tidy_directory.py <directory> --docs-only --dry-run

# Step 2: Execute docs consolidation only
python scripts/tidy/unified_tidy_directory.py <directory> --docs-only --execute

# Step 3: Preview full cleanup (all file types)
python scripts/tidy/unified_tidy_directory.py <directory> --full --dry-run

# Step 4: Execute full cleanup
python scripts/tidy/unified_tidy_directory.py <directory> --full --execute
```

### Example Directories

```bash
# Clean up archive directory
python scripts/tidy/unified_tidy_directory.py archive --full --dry-run

# Clean up a specific autonomous run
python scripts/tidy/unified_tidy_directory.py .autonomous_runs/test-goal-anchoring-20251203 --docs-only --dry-run

# Clean up archived runs
python scripts/tidy/unified_tidy_directory.py .autonomous_runs/archive --full --dry-run

# Any other directory
python scripts/tidy/unified_tidy_directory.py research/papers --docs-only --dry-run
```

---

## Two-Phase System

### Phase 1: Documentation Consolidation (.md files only)
**Always runs** - Processes all `.md` files in target directory and subdirectories

**What it does**:
- ✅ Recursively finds ALL `.md` files
- ✅ Categorizes into BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS
- ✅ Sorts chronologically (most recent first)
- ✅ Consolidates into SOT files at `docs/`

**SOT Files**:
- `docs/BUILD_HISTORY.md` - Implementation plans, feature builds, run reports
- `docs/DEBUG_LOG.md` - Bug fixes, error analyses, debugging sessions
- `docs/ARCHITECTURE_DECISIONS.md` - Strategic analyses, market research, schemas, reference docs

**Safe to run**: Yes - always use `--dry-run` first to preview

---

### Phase 2: All File Types (Optional)
**Runs only with `--full` flag** - Organizes ALL remaining file types

#### File Type Routing

| File Type | Destination | Purpose |
|-----------|------------|---------|
| `.md` | `docs/` (SOT files) | Already handled in Phase 1 |
| `.py` | `scripts/superseded/` | Old/outdated Python scripts |
| `.log` | `archive/diagnostics/logs/` | Centralized log storage |
| `.json` | `config/legacy/` or `docs/schemas/` | Config files or schema files |
| `.yaml`/`.yml` | `config/legacy/` | Configuration files |
| `.txt` | `archive/diagnostics/logs/` or `data/archive/notes/` | Log-formatted or note files |
| `.csv`/`.xlsx` | `data/archive/csv/` or `data/archive/xlsx/` | Data files |
| `.sql` | `archive/sql/schemas/` or `archive/sql/scripts/` | SQL schemas or scripts |
| Other | Flagged for review | Listed in output for manual decision |

#### How Files Are Classified

**Python files (.py)**:
- `test*.py` → `scripts/superseded/old_tests/`
- `*cleanup*.py`, `*tidy*.py` → `scripts/superseded/old_tidy_scripts/`
- `*diagnostic*.py`, `*debug*.py` → `scripts/superseded/old_diagnostic_scripts/`
- Other → `scripts/superseded/other/`

**JSON files (.json)**:
- Files with "schema", "spec" in name → `docs/schemas/`
- Files with "$schema" or "properties" in content → `docs/schemas/`
- Files with "config", "settings" in name → `config/legacy/`
- `package.json` → `config/legacy/`
- Other → `data/archive/json/`

**Text files (.txt)**:
- Files with "log" in name → `archive/diagnostics/logs/`
- Content matching log patterns (ERROR, WARN, timestamps) → `archive/diagnostics/logs/`
- Files with "note", "readme" in name → `data/archive/notes/`
- `requirements.txt` → `config/legacy/`

**SQL files (.sql)**:
- Files with "schema", "migration" in name → `archive/sql/schemas/`
- Other → `archive/sql/scripts/`

**YAML files (.yaml, .yml)**:
- All → `config/legacy/`

**Data files (.csv, .xlsx, .xls, .parquet, .pkl)**:
- All → `data/archive/<extension>/`

---

## Usage Modes

### Docs Only (Default, Safe)
```bash
python scripts/tidy/unified_tidy_directory.py <directory> --docs-only --dry-run
python scripts/tidy/unified_tidy_directory.py <directory> --docs-only --execute
```

**What happens**:
- ✅ Consolidates `.md` files only
- ❌ Leaves all other file types untouched
- ✅ Fully reversible (git checkout)

**Use when**: You want to consolidate documentation but leave scripts/logs/data alone

---

### Full Cleanup
```bash
python scripts/tidy/unified_tidy_directory.py <directory> --full --dry-run
python scripts/tidy/unified_tidy_directory.py <directory> --full --execute
```

**What happens**:
- ✅ Consolidates `.md` files (Phase 1)
- ✅ Organizes ALL other file types (Phase 2)
- ✅ Moves scripts to superseded/
- ✅ Centralizes logs
- ✅ Archives data files
- ✅ Flags unknown file types for review

**Use when**: You want complete directory cleanup

---

### Interactive Mode
```bash
python scripts/tidy/unified_tidy_directory.py <directory> --interactive
```

**What happens**:
- ✅ Runs Phase 1 (docs consolidation)
- ⏸️  Prompts: "Proceed with Phase 2 (all file types cleanup)? [y/N]"
- ✅ Continues only if you type 'y'

**Use when**: You want to review Phase 1 results before committing to full cleanup

---

## Directory Structure After Cleanup

### Before (Example: archive/)
```
archive/
├── plans/ (21 .md files, 3 .py scripts, 2 .json configs)
├── reports/ (100+ .md files, 15 .log files)
├── analysis/ (15 .md files, 5 .csv data files)
├── research/ (misc files)
├── diagnostics/ (nested mess of scripts, logs, data)
└── tidy_v7/ (active docs - PRESERVED)
```

### After Phase 1 (Docs Only)
```
archive/
├── plans/ (3 .py scripts, 2 .json configs remaining)
├── reports/ (15 .log files remaining)
├── analysis/ (5 .csv data files remaining)
├── diagnostics/ (scripts, logs, data remaining)
└── tidy_v7/ (active docs - PRESERVED)

docs/
├── BUILD_HISTORY.md (125 entries, chronologically sorted)
├── DEBUG_LOG.md (35 entries)
└── ARCHITECTURE_DECISIONS.md (68 entries)
```

### After Phase 2 (Full Cleanup)
```
archive/
├── tidy_v7/ (active docs - PRESERVED)
├── prompts/ (reference - PRESERVED)
├── diagnostics/
│   └── logs/ (ALL .log files centralized here)
└── sql/
    ├── schemas/
    └── scripts/

scripts/
├── tidy/ (active scripts - PRESERVED)
└── superseded/
    ├── README.md (documentation)
    ├── old_tidy_scripts/ (cleanup/tidy scripts)
    ├── old_diagnostic_scripts/ (diagnostic scripts)
    └── other/ (misc scripts)

config/
└── legacy/ (all .json, .yaml config files)

data/
└── archive/
    ├── csv/ (.csv files)
    ├── xlsx/ (.xlsx files)
    ├── json/ (JSON data files)
    └── notes/ (text notes)

docs/
├── BUILD_HISTORY.md (consolidated)
├── DEBUG_LOG.md (consolidated)
├── ARCHITECTURE_DECISIONS.md (consolidated)
└── schemas/ (JSON schema files)
```

---

## File Exclusions

The tidy function **PRESERVES** these directories (never touches them):

### Always Preserved
- `archive/tidy_v7/` - Active tidy documentation
- `archive/prompts/` - Reference prompt templates
- `scripts/tidy/` - Active tidy scripts
- `.git/` - Git repository data
- `venv/` - Virtual environment
- `node_modules/` - Node dependencies
- `__pycache__/` - Python cache

### Configurable Exclusions
You can add exclusions by modifying the scripts:
- `enhanced_file_cleanup.py` - Edit `keep_dirs` set (line ~214)
- `consolidate_docs_v2.py` - Edit exclusion patterns

---

## Safety Features

### Dry-Run Mode (Default)
```bash
# Without --execute flag, nothing changes
python scripts/tidy/unified_tidy_directory.py archive --full --dry-run
```

**Shows**:
- What files would be moved
- Where they would go
- Why they're being moved
- Total file counts

**Does NOT**:
- Modify any files
- Move any files
- Delete anything

### Rollback Plan

#### Rollback Phase 1 (Docs)
```bash
git checkout HEAD -- docs/BUILD_HISTORY.md docs/DEBUG_LOG.md docs/ARCHITECTURE_DECISIONS.md
```

#### Rollback Phase 2 (All Files)
```bash
git checkout HEAD -- scripts/superseded/ config/legacy/ data/archive/ archive/ docs/schemas/
```

#### Complete Rollback
```bash
git reset --hard HEAD
```

---

## Advanced Usage

### Standalone Scripts

You can also run each phase independently:

#### Phase 1 Only (Docs Consolidation)
```bash
# Consolidate docs from archive/
python scripts/tidy/consolidate_docs_directory.py --directory archive --dry-run
python scripts/tidy/consolidate_docs_directory.py --directory archive

# Consolidate docs from any directory
python scripts/tidy/consolidate_docs_directory.py --directory .autonomous_runs/my-project --dry-run
```

#### Phase 2 Only (Enhanced File Cleanup)
```bash
# Organize all file types in archive/
python scripts/tidy/enhanced_file_cleanup.py archive --dry-run
python scripts/tidy/enhanced_file_cleanup.py archive --execute

# Organize files in any directory
python scripts/tidy/enhanced_file_cleanup.py .autonomous_runs/my-project --dry-run
```

---

## Real-World Examples

### Example 1: Clean Up Archive Directory
```bash
# Step 1: Preview docs consolidation
python scripts/tidy/unified_tidy_directory.py archive --docs-only --dry-run

# Step 2: Execute docs consolidation
python scripts/tidy/unified_tidy_directory.py archive --docs-only --execute

# Step 3: Review SOT files
head -100 docs/BUILD_HISTORY.md

# Step 4: Preview full cleanup
python scripts/tidy/unified_tidy_directory.py archive --full --dry-run

# Step 5: Execute full cleanup
python scripts/tidy/unified_tidy_directory.py archive --full --execute

# Step 6: Commit
git add -A
git commit -m "tidy: complete archive consolidation and cleanup"
```

### Example 2: Clean Up Old Autonomous Run
```bash
# Step 1: Preview
python scripts/tidy/unified_tidy_directory.py .autonomous_runs/old-run-20241201 --full --dry-run

# Step 2: Execute
python scripts/tidy/unified_tidy_directory.py .autonomous_runs/old-run-20241201 --full --execute

# Result:
# - .md files → docs/BUILD_HISTORY.md, DEBUG_LOG.md, ARCHITECTURE_DECISIONS.md
# - .py scripts → scripts/superseded/
# - .log files → archive/diagnostics/logs/
# - Empty directory removed
```

### Example 3: Interactive Cleanup (Cautious)
```bash
# Interactive mode - prompts before Phase 2
python scripts/tidy/unified_tidy_directory.py archive --interactive

# Output:
# [PHASE 1] Documentation Consolidation
# ... (consolidates .md files)
# ✅ Phase 1 complete: Documentation consolidated
#
# Proceed with Phase 2 (all file types cleanup)? [y/N]:
# (Type 'y' to continue, 'N' to stop)
```

---

## Troubleshooting

### Issue: "Directory not found"
**Solution**: Use relative path from project root
```bash
# ❌ Wrong
python scripts/tidy/unified_tidy_directory.py C:\dev\Autopack\archive --docs-only

# ✅ Correct
python scripts/tidy/unified_tidy_directory.py archive --docs-only
```

### Issue: Files requiring manual review
**Solution**: Check Phase 2 output for flagged files
```bash
⚠️  Files requiring manual review:
  - archive/data.bin: Unhandled file type: .bin
  - archive/custom.xyz: Unhandled file type: .xyz
```

Manually decide what to do with these files.

### Issue: Name conflicts
**Solution**: Script automatically handles conflicts by prefixing parent directory name
```bash
# If archive/reports/run.log and archive/plans/run.log both exist:
# → archive/diagnostics/logs/reports_run.log
# → archive/diagnostics/logs/plans_run.log
```

---

## Future Enhancements

### Potential Future Features
1. **CLI Integration**: Add `autopack tidy <directory>` command
2. **Config File**: `~/.autopack/tidy_config.yaml` for directory-specific rules
3. **Undo Command**: `autopack tidy undo` to rollback last tidy operation
4. **Custom Routing**: User-defined file type → destination mappings
5. **Tidy History**: Log all tidy operations for audit trail

---

## Summary

**✅ What You Have Now**:
- Reusable manual tidy function for ANY directory
- Handles ALL file types (.md, .py, .log, .json, .yaml, .txt, .csv, .sql, and more)
- Two-phase system (docs → all files)
- Dry-run mode for safe previews
- Fully reversible via git
- Works on archive/, .autonomous_runs/, or any custom directory

**🚀 How to Use**:
1. Start with `--docs-only --dry-run` to preview
2. Execute `--docs-only --execute` to consolidate docs
3. Preview `--full --dry-run` to see all file movements
4. Execute `--full --execute` to complete cleanup
5. Review and commit changes

**📋 Scripts**:
- `unified_tidy_directory.py` - User-facing interface (RECOMMENDED)
- `consolidate_docs_directory.py` - Phase 1 standalone
- `enhanced_file_cleanup.py` - Phase 2 standalone

**📍 Current Status**: ✅ Ready to use on ANY directory!
