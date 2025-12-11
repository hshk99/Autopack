# Implementation Plan: Workspace Cleanup V2

**Date:** 2025-12-11
**Target:** Implement PROPOSED_CLEANUP_STRUCTURE_V2.md
**Estimated Effort:** Medium (2-3 hours manual + script execution)

---

## Overview

This plan addresses all issues identified in WORKSPACE_ISSUES_ANALYSIS.md by implementing the corrected structure from PROPOSED_CLEANUP_STRUCTURE_V2.md.

---

## Phase 1: Root Directory Cleanup

### 1.1 Move Configuration Files
```bash
# Create config directory if needed
mkdir -p config

# Move project configs
mv project_ruleset_Autopack.json config/
mv project_issue_backlog.json config/
mv autopack_phase_plan.json config/
```

**Files affected:** 3
**Risk:** Low - these are config files

### 1.2 Move API Specifications
```bash
# Create docs/api directory
mkdir -p docs/api

# Move OpenAPI spec
mv openapi.json docs/api/
```

**Files affected:** 1
**Risk:** Low

### 1.3 Move Diagnostic Data
```bash
# Move to archive/diagnostics/
mv test_run.json archive/diagnostics/
mv builder_fullfile_failure_latest.json archive/diagnostics/
```

**Files affected:** 2
**Risk:** Low

### 1.4 Archive Documentation
```bash
# Move verification doc to archive
mv STRUCTURE_VERIFICATION_FINAL.md archive/reports/

# Handle RUN_COMMAND.txt (review first, then either archive or delete)
# DECISION NEEDED: Review content first
```

**Files affected:** 1-2
**Risk:** Low

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 1 - organize root directory files"`

---

## Phase 2: Archive Restructuring

### 2.1 Eliminate archive/src/

**Step 1: Review files**
```bash
# List all files
find archive/src -type f

# Current files:
# - command_runner.py
# - diagnostics_agent.py
# - hypothesis.py
# - probes.py
# - __init__.py
```

**Step 2: Check if obsolete**
```bash
# Compare with current src/
diff -r archive/src/autopack/diagnostics src/autopack/diagnostics/ 2>/dev/null
# OR check if diagnostics/ even exists in current src/
ls src/autopack/diagnostics/ 2>/dev/null
```

**Step 3: Decision**
- **If obsolete:** Move to `archive/superseded/diagnostics_v1/`
- **If still relevant:** Move to actual `src/`
- **If duplicate:** DELETE

**Commands:**
```bash
# Option A: Move to superseded (if historical reference)
mkdir -p archive/superseded/diagnostics_v1
mv archive/src/autopack/diagnostics/* archive/superseded/diagnostics_v1/
rmdir -p archive/src/autopack/diagnostics archive/src/autopack archive/src

# Option B: Delete (if truly obsolete)
rm -rf archive/src/

# Option C: Restore to src/ (if still relevant)
mkdir -p src/autopack/diagnostics
mv archive/src/autopack/diagnostics/* src/autopack/diagnostics/
rm -rf archive/src/
```

**Files affected:** 5
**Risk:** Medium - requires review
**DECISION POINT:** Manual review required

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 2.1 - eliminate archive/src"`

### 2.2 Group Runs by Project

**Step 1: Create project folders**
```bash
mkdir -p archive/diagnostics/runs/Autopack
mkdir -p archive/diagnostics/runs/file-organizer
mkdir -p archive/diagnostics/runs/unknown
```

**Step 2: Move file-organizer runs**
```bash
cd archive/diagnostics/runs/

# Move all fileorg-* runs
for dir in fileorg-*; do
  if [ -d "$dir" ]; then
    mv "$dir" file-organizer/
  fi
done
```

**Step 3: Handle nested project folders**
```bash
# Current nested folders:
# - archive/ (folder)
# - Autopack/ (folder)
# - file-organizer-app-v1/ (folder)

# Flatten Autopack/ if it contains runs
if [ -d "Autopack" ]; then
  # Check what's in there
  ls -la Autopack/
  # Move actual runs to Autopack/
  # Delete excessive nesting
fi

# Same for file-organizer-app-v1/
# Same for archive/
```

**Step 4: Flatten excessive nesting**
```bash
# Handle runs/Autopack/.autonomous_runs/Autopack/archive/unknowns/
# Extract to runs/Autopack/unknowns/ or runs/unknown/

# Handle runs/archive/.autonomous_runs/archive/runs/
# Flatten to appropriate location
```

**Files affected:** 50+ run folders
**Risk:** Medium - complex restructuring
**DECISION POINT:** Manual review of nested folders required

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 2.2 - group runs by project"`

### 2.3 Rename Diagnostic Data Folder
```bash
# Rename autopack_data to data
mv archive/diagnostics/autopack_data archive/diagnostics/data
```

**Files affected:** 1 folder
**Risk:** Low

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 2.3 - rename diagnostic data folder"`

---

## Phase 3: .autonomous_runs Cleanup

### 3.1 Rename Checkpoints Folder
```bash
mv .autonomous_runs/checkpoints .autonomous_runs/tidy_checkpoints
```

**Files affected:** 1 folder
**Risk:** Low
**Note:** May need to update references in tidy scripts

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 3.1 - rename checkpoints to tidy_checkpoints"`

### 3.2 Add Truth Sources to file-organizer-app-v1/docs/

**Step 1: Create README.md**
```bash
cat > .autonomous_runs/file-organizer-app-v1/docs/README.md <<'EOF'
# FileOrganizer - Documentation

This folder contains documentation for the FileOrganizer project.

## Contents

- [Architecture](ARCHITECTURE.md) - System architecture and design
- [Guides](guides/) - How-to guides and tutorials
- [Research](research/) - Research and analysis documents

## Quick Start

[Link to main setup guide]

## Project Status

See [WHATS_LEFT_TO_BUILD.md](../WHATS_LEFT_TO_BUILD.md) for current roadmap.
EOF
```

**Step 2: Check for existing architecture docs in guides/**
```bash
ls .autonomous_runs/file-organizer-app-v1/docs/guides/ | grep -i arch
# If exists, promote to top level
# If not, create basic ARCHITECTURE.md
```

**Step 3: Create or promote ARCHITECTURE.md**
```bash
# If found in guides/
mv .autonomous_runs/file-organizer-app-v1/docs/guides/ARCHITECTURE.md .autonomous_runs/file-organizer-app-v1/docs/

# If not found, create basic one
cat > .autonomous_runs/file-organizer-app-v1/docs/ARCHITECTURE.md <<'EOF'
# FileOrganizer Architecture

## Overview

[To be documented]

## Components

[To be documented]

## Data Flow

[To be documented]
EOF
```

**Files affected:** 2 new files
**Risk:** Low

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 3.2 - add truth sources to file-organizer docs"`

### 3.3 Handle Autopack Folder

**Step 1: Check contents**
```bash
find .autonomous_runs/Autopack -type f
```

**Step 2: Decision**
- **If only has archive/:** Move archive to main archive/, delete folder
- **If active/intended for future use:** Add README.md explaining purpose

**Commands:**

Option A: Delete (if unused)
```bash
# Move archive contents to main archive
# (Handle merging with existing archive structure)
# Then delete
rm -rf .autonomous_runs/Autopack
```

Option B: Add README (if keeping)
```bash
cat > .autonomous_runs/Autopack/README.md <<'EOF'
# Autopack Autonomous Runs

This folder contains autonomous execution runs for Autopack self-improvement.

## Purpose

Autopack uses this folder for self-directed development and improvements.

## Structure

- `archive/` - Historical runs and outputs
EOF
```

**Files affected:** 1 folder or 1 README
**Risk:** Low
**DECISION POINT:** Determine if folder is active

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 3.3 - handle Autopack folder"`

---

## Phase 4: Documentation Creation

### 4.1 Create Active Documentation in docs/

**Files to create:**

**ARCHITECTURE.md**
```bash
cat > docs/ARCHITECTURE.md <<'EOF'
# Autopack Architecture

## Overview

Autopack is an autonomous development system...

## Core Components

### 1. Autonomous Executor
[Description]

### 2. Task Decomposition
[Description]

### 3. Pack System
[Description]

## Data Flow

[Diagram or description]

## Directory Structure

See [WORKSPACE_ORGANIZATION_SPEC.md](../WORKSPACE_ORGANIZATION_SPEC.md)
EOF
```

**API_REFERENCE.md**
```bash
cat > docs/API_REFERENCE.md <<'EOF'
# Autopack API Reference

## OpenAPI Specification

See [openapi.json](api/openapi.json) for complete API specification.

## Endpoints

### Task Management
[Document key endpoints]

### Pack Management
[Document key endpoints]

### Execution
[Document key endpoints]
EOF
```

**DEPLOYMENT_GUIDE.md**
```bash
cat > docs/DEPLOYMENT_GUIDE.md <<'EOF'
# Autopack Deployment Guide

## Prerequisites

- Python 3.10+
- PostgreSQL
- Qdrant (optional)

## Installation

[Steps]

## Configuration

[Environment variables, configs]

## Running

[Commands to start services]
EOF
```

**CONTRIBUTING.md**
```bash
cat > docs/CONTRIBUTING.md <<'EOF'
# Contributing to Autopack

## Development Setup

See [SETUP_GUIDE.md](SETUP_GUIDE.md)

## Code Style

- Python: Black formatter
- TypeScript: Prettier

## Testing

```bash
pytest tests/
```

## Pull Requests

[Guidelines]
EOF
```

**Files affected:** 4 new files
**Risk:** Low

**Git Checkpoint:** `git commit -m "cleanup-v2: phase 4.1 - create active documentation"`

---

## Phase 5: Final Validation

### 5.1 Run Validation Script

Create updated validator in `corrective_cleanup_v2.py`:

```python
def validate_v2_structure():
    """Validate against PROPOSED_CLEANUP_STRUCTURE_V2.md"""
    issues = []

    # Check 1: No archive/src/
    if (REPO_ROOT / "archive" / "src").exists():
        issues.append("[X] archive/src/ still exists")

    # Check 2: Runs grouped by project
    runs_dir = REPO_ROOT / "archive" / "diagnostics" / "runs"
    expected_projects = ["Autopack", "file-organizer", "unknown"]
    loose_runs = [d for d in runs_dir.iterdir() if d.is_dir()
                  and d.name not in expected_projects]
    if loose_runs:
        issues.append(f"[X] {len(loose_runs)} ungrouped runs")

    # Check 3: Checkpoints renamed
    if (REPO_ROOT / ".autonomous_runs" / "checkpoints").exists():
        issues.append("[X] checkpoints/ not renamed to tidy_checkpoints/")

    # Check 4: Config files moved
    root_configs = ["project_ruleset_Autopack.json",
                    "project_issue_backlog.json",
                    "autopack_phase_plan.json"]
    loose_configs = [f for f in root_configs if (REPO_ROOT / f).exists()]
    if loose_configs:
        issues.append(f"[X] {len(loose_configs)} config files still at root")

    # Check 5: Active docs exist
    required_docs = ["ARCHITECTURE.md", "API_REFERENCE.md",
                     "DEPLOYMENT_GUIDE.md", "CONTRIBUTING.md"]
    docs_dir = REPO_ROOT / "docs"
    missing_docs = [d for d in required_docs if not (docs_dir / d).exists()]
    if missing_docs:
        issues.append(f"[X] Missing docs: {', '.join(missing_docs)}")

    # Check 6: file-organizer docs have truth sources
    fo_docs = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs"
    fo_required = ["README.md"]  # ARCHITECTURE.md optional
    fo_missing = [d for d in fo_required if not (fo_docs / d).exists()]
    if fo_missing:
        issues.append(f"[X] file-organizer docs missing: {', '.join(fo_missing)}")

    return len(issues) == 0, issues
```

**Run validation:**
```bash
python scripts/corrective_cleanup_v2.py --validate
```

### 5.2 Manual Verification

Check each issue from WORKSPACE_ISSUES_ANALYSIS.md:

1. ✅ Truth source files in docs/
2. ✅ No archive/src/
3. ✅ Runs grouped by project
4. ✅ No excessive nesting
5. ✅ Config files in config/
6. ✅ .json files documented
7. ✅ Autopack folder handled
8. ✅ tests/ clarified (not moved)
9. ✅ checkpoints renamed
10. ✅ file-organizer docs have truth sources

---

## Execution Strategy

### Option A: Automated Script
Create `scripts/corrective_cleanup_v2.py` that:
1. Performs all phases automatically
2. Creates git checkpoints between phases
3. Validates at the end
4. Dry-run mode available

### Option B: Manual Execution
Follow phases step-by-step:
1. Execute each phase commands
2. Review changes
3. Git commit after each phase
4. Validate at end

### Option C: Hybrid
1. Automate low-risk phases (1, 3.1, 3.2, 4)
2. Manual review for medium-risk (2.1, 2.2, 3.3)
3. Validate and adjust

**Recommendation:** Option C (Hybrid)

---

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| 1. Root cleanup | Low | Standard file moves |
| 2.1 archive/src | Medium | Manual review required |
| 2.2 Group runs | Medium | Complex restructuring - test in dry-run |
| 2.3 Rename data | Low | Simple rename |
| 3.1 Rename checkpoints | Low | May need script updates |
| 3.2 Add docs | Low | Creating new files |
| 3.3 Autopack folder | Low | Needs decision |
| 4. Create docs | Low | Creating new files |

**Overall Risk:** Medium (due to phases 2.1 and 2.2)

---

## Rollback Plan

If issues occur:
1. Each phase has git checkpoint
2. Rollback: `git reset --hard <previous-checkpoint>`
3. Review what went wrong
4. Adjust and retry

---

## Timeline

- **Phase 1:** 15 minutes
- **Phase 2:** 45-60 minutes (includes manual review)
- **Phase 3:** 30 minutes
- **Phase 4:** 30 minutes
- **Phase 5:** 15 minutes (validation)

**Total:** ~2-3 hours

---

## Next Steps

1. Review this plan
2. Get user approval
3. Create `scripts/corrective_cleanup_v2.py`
4. Execute in dry-run mode
5. Review dry-run output
6. Execute for real
7. Validate

---

**Generated:** 2025-12-11
**Target Spec:** PROPOSED_CLEANUP_STRUCTURE_V2.md
