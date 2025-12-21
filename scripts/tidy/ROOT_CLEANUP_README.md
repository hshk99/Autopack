# .autonomous_runs Root Cleanup

## Overview

The `.autonomous_runs` root cleanup script organizes loose files and folders that were created directly at the `.autonomous_runs/` root level (typically by Cursor when running Autopack from command line) and moves them to their proper locations within the project structure.

## Problem

When running Autopack from the command line (often via Cursor), files and folders sometimes get created at the `.autonomous_runs/` root level instead of within the proper project structure:

```
.autonomous_runs/
├── build-047-validation.log              ❌ Loose log file
├── build-complete-runs-api/              ❌ Loose run directory
├── fileorg-phase2-plan.json              ❌ Loose plan file
├── autopack/                             ✅ Proper project structure
│   ├── runs/
│   │   └── build-complete-runs-api/      ✅ Complete run (duplicate)
│   └── archive/diagnostics/
└── file-organizer-app-v1/                ✅ Proper project structure
    ├── runs/
    └── archive/
```

## Solution

The cleanup script:
1. **Identifies duplicates**: Detects when a run directory exists in both locations
2. **Moves unique items**: Relocates files/folders to their proper project locations
3. **Deletes duplicates**: Removes incomplete duplicates (keeping complete versions)
4. **Protects important items**: Never touches essential directories and files

## Protected Items (Never Moved/Deleted)

The following items are **always protected**:
- `autopack/` - Autopack project structure
- `file-organizer-app-v1/` - File organizer project structure
- `_shared/` - Shared runtime state (tidy semantic cache)
- `.locks/` - Run lock files (prevents duplicate executions)
- `tidy_checkpoints/` - Tidy process checkpoints
- `README.md` - Root documentation
- `STRUCTURE.md` - Directory structure documentation
- `api_server.log` - Active API server log (currently in use)

## Usage

### Standalone Script

```bash
# Preview what would be cleaned up (recommended first step)
python scripts/tidy/cleanup_autonomous_runs_root.py --dry-run

# Execute the cleanup
python scripts/tidy/cleanup_autonomous_runs_root.py --execute
```

### Integrated with Autonomous Tidy

The cleanup runs automatically when tidying `.autonomous_runs`:

```bash
# This will clean up the root AND tidy all sub-projects
python scripts/tidy/autonomous_tidy.py .autonomous_runs --dry-run
python scripts/tidy/autonomous_tidy.py .autonomous_runs --execute
```

## What Gets Moved

### Run Directories
**From:** `.autonomous_runs/{run-name}/`
**To:** `.autonomous_runs/{project}/runs/{run-name}/`

**Logic:**
- If duplicate exists in proper location and is complete → Delete loose version
- If duplicate exists but loose version is more complete → Replace with loose version
- If no duplicate exists → Move to proper location

### Log Files
**From:** `.autonomous_runs/{run-name}.log`
**To:** `.autonomous_runs/{project}/archive/diagnostics/{run-name}.log`

### JSON Plan Files
**From:** `.autonomous_runs/{plan-name}.json`
**To:** `.autonomous_runs/{project}/archive/plans/{plan-name}.json`

## Project Detection

The script automatically detects which project a file/folder belongs to:

**File-organizer patterns:**
- Contains: `fileorg`, `file-org`, `immigration`, `visa`, `evidence`
- Goes to: `file-organizer-app-v1`

**Autopack patterns (default):**
- Everything else
- Goes to: `autopack`

## Run Directory Analysis

The script analyzes run directories to determine completeness:

- **Stub**: Only contains `phase_plan.json` (incomplete initialization)
- **Complete**: Contains multiple files (full run execution)

This prevents accidentally deleting complete runs in favor of incomplete stubs.

## Example Output

```bash
$ python scripts/tidy/cleanup_autonomous_runs_root.py --dry-run

================================================================================
.autonomous_runs ROOT CLEANUP
================================================================================
Mode: DRY-RUN (preview only)
================================================================================

📊 Analysis:
   Protected items: 8
   Loose run directories: 8
   Loose log files: 5
   Loose JSON files: 1

🔒 Protected (will not touch):
   ✅ autopack
   ✅ file-organizer-app-v1
   ✅ _shared
   ✅ .locks
   ✅ tidy_checkpoints
   ✅ README.md
   ✅ STRUCTURE.md
   ✅ api_server.log

📁 Processing loose run directories:
   build-041-045-validation → autopack
   🗑️  DELETE (duplicate): Complete version exists in autopack/runs/

   fileorg-phase2-build041-test → file-organizer-app-v1
   📦 MOVE: .autonomous_runs\fileorg-phase2-build041-test
           → .autonomous_runs\file-organizer-app-v1\runs\fileorg-phase2-build041-test

📄 Processing loose log files:
   build-047-validation.log → autopack
   📦 MOVE: .autonomous_runs\build-047-validation.log
           → .autonomous_runs\autopack\archive\diagnostics\build-047-validation.log

================================================================================
CLEANUP SUMMARY
================================================================================
   Items moved: 14
   Items skipped: 0
   Protected items: 8

🔍 This was a dry-run. No changes were made.
   Run with --execute to apply these changes.
================================================================================
```

## Safety Features

1. **Dry-run by default**: Always preview before executing
2. **Duplicate detection**: Smart handling of files that exist in multiple locations
3. **Protected items**: Essential directories/files are never touched
4. **Completeness checking**: Prefers complete runs over stubs
5. **Skip existing**: Won't overwrite files that already exist in destination

## When to Use

Run this cleanup:
1. **After Cursor/CLI runs**: When you notice loose files at `.autonomous_runs/` root
2. **Before major tidy**: Clean up the root before running full tidy workflow
3. **Periodically**: As part of regular maintenance
4. **Automatically**: Integrated into autonomous tidy when targeting `.autonomous_runs`

## Integration with Autonomous Tidy

The cleanup script is automatically called when running autonomous tidy on `.autonomous_runs`:

```bash
# This workflow:
# 1. Organizes root scripts (Step 0)
# 2. Cleans up .autonomous_runs root (Step 0.5) ← NEW
# 3. Runs pre-tidy auditor (Step 1)
# 4. Consolidates docs (Step 2)
# 5. Cleans up obsolete files (Step 2.5)
# 6. Post-tidy verification (Step 3)
# 7. Database sync (Step 4)
python scripts/tidy/autonomous_tidy.py .autonomous_runs --execute
```

## Technical Details

- **Script location**: `scripts/tidy/cleanup_autonomous_runs_root.py`
- **Integration point**: `scripts/tidy/autonomous_tidy.py` (Step 0.5)
- **Language**: Python 3
- **Dependencies**: Standard library only (pathlib, shutil, argparse)
- **Encoding**: UTF-8 (use `PYTHONUTF8=1` on Windows if needed)
