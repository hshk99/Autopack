# Workspace Organization Structure - V2 (CORRECTED)

**Version:** 2.0
**Date:** 2025-12-11
**Status:** PROPOSED

This document supersedes PROPOSED_CLEANUP_STRUCTURE.md with corrections based on critical issues identified.

---

## Guiding Principles

### 1. No Redundancy
- Don't duplicate folder purposes (e.g., `src/` at root AND `archive/src/`)
- Delete truly obsolete code; archive only if historical reference value

### 2. Flatten Excessive Nesting
- Maximum 3 levels deep in archive (e.g., `archive/diagnostics/runs/PROJECT/`)
- NO paths like `runs/archive/.autonomous_runs/archive/runs/`

### 3. Group by Project
- All runs grouped under project name in `archive/diagnostics/runs/PROJECT/`
- NO loose run folders

###4. Truth vs Archive Distinction
- **Truth sources:** Active, current documentation at root or project `docs/`
- **Archive:** Historical, superseded files in `archive/`
- Every `docs/` folder must have active truth source files

### 5. Complete Scope
- Address ALL file types: `.md`, `.log`, `.json`, `.txt`, `.ts`, etc.
- Not just markdown and logs

---

## Root Directory Structure

```
C:\dev\Autopack\
├── README.md                           # Quick start (links to docs/)
│
├── package.json                        # npm config (KEEP)
├── tsconfig.json                       # TypeScript config (KEEP)
├── tsconfig.node.json                  # TypeScript config (KEEP)
├── requirements.txt                    # pip config (KEEP)
├── requirements-dev.txt                # pip config (KEEP)
│
├── src/                                # Active source code
├── scripts/                            # Utility scripts
├── tests/                              # Pytest test suite (NOT scripts - standard Python)
│
├── docs/                               # ALL TRUTH SOURCE DOCUMENTATION
│   ├── README.md                       # Project overview (main docs)
│   ├── WORKSPACE_ORGANIZATION_SPEC.md  # Workspace organization spec
│   ├── WHATS_LEFT_TO_BUILD.md         # Roadmap
│   ├── WHATS_LEFT_TO_BUILD_MAINTENANCE.md # Maintenance roadmap
│   ├── ARCHITECTURE.md                 # System architecture
│   ├── API_REFERENCE.md                # API documentation
│   ├── DEPLOYMENT_GUIDE.md             # Deployment instructions
│   ├── SETUP_GUIDE.md                  # Setup instructions
│   ├── CONTRIBUTING.md                 # Contribution guidelines
│   ├── project_ruleset_Autopack.json   # Project rules (auto-updated)
│   ├── project_issue_backlog.json      # Issue backlog (auto-updated)
│   ├── autopack_phase_plan.json        # Phase plan (auto-updated)
│   └── api/
│       └── openapi.json                # API spec
│
├── archive/                            # Historical files ONLY
└── .autonomous_runs/                   # Project-specific autonomous runs
```

**Key Change:** All truth source files consolidated in `docs/` folder. Root README.md is a simple quick-start that links to docs/README.md.

---

## Files to MOVE from Root

### Truth Source Documentation → `docs/`
- `WORKSPACE_ORGANIZATION_SPEC.md` → `docs/`
- `WHATS_LEFT_TO_BUILD.md` → `docs/`
- `WHATS_LEFT_TO_BUILD_MAINTENANCE.md` → `docs/`

### Configuration/Ruleset Files → `docs/`
- `project_ruleset_Autopack.json` → `docs/` (auto-updated)
- `project_issue_backlog.json` → `docs/` (auto-updated)
- `autopack_phase_plan.json` → `docs/` (auto-updated)

### API Specifications → `docs/api/`
- `openapi.json` → `docs/api/`

### Diagnostic Data → `archive/diagnostics/`
- `test_run.json` → `archive/diagnostics/`
- `builder_fullfile_failure_latest.json` → `archive/diagnostics/`

### Documentation → Archive or Delete
- `RUN_COMMAND.txt` → `archive/docs/` or DELETE if obsolete
- `STRUCTURE_VERIFICATION_FINAL.md` → `archive/reports/`

### Root README.md
- Keep at root as quick-start guide
- Create comprehensive `docs/README.md` with full documentation

---

## Archive Structure (REVISED)

```
C:\dev\Autopack\archive/
├── plans/                      # Implementation plans
├── reports/                    # Guides, checklists, assessments
├── analysis/                   # Analysis, reviews
├── research/                   # Research documents
├── prompts/                    # Prompt templates
│
├── diagnostics/                # Diagnostic data
│   ├── logs/                   # All .log files
│   ├── runs/                   # Run outputs (GROUPED BY PROJECT)
│   │   ├── Autopack/           # All Autopack runs
│   │   ├── file-organizer/     # All file-organizer runs
│   │   └── unknown/            # Unclassified runs
│   ├── docs/                   # CONSOLIDATED_DEBUG.md, etc.
│   └── data/                   # Diagnostic data files (model_selections, etc.)
│
├── superseded/                 # Truly obsolete code/docs
│   └── diagnostics_v1/         # Old diagnostics implementation
│
├── unsorted/                   # Temporary inbox
├── configs/                    # Historical configs
├── docs/                       # Superseded documentation
├── exports/                    # Export archives
├── patches/                    # Code patches
└── refs/                       # Reference materials
```

### Key Changes from V1:

1. **NO `archive/src/`** - Move to `archive/superseded/` with descriptive name OR delete
2. **Grouped runs** - All runs under `diagnostics/runs/PROJECT/`
3. **Flatten nesting** - Extract actual run data, discard nested folder structures
4. **`diagnostics/data/`** - For model_selections and other diagnostic data files

---

## .autonomous_runs Structure (REVISED)

```
C:\dev\Autopack\.autonomous_runs/
├── tidy_checkpoints/                      # RENAMED from checkpoints/
│   └── tidy_checkpoint_YYYYMMDD-HHMMSS.zip
│
├── file-organizer-app-v1/                 # File organizer project
│   ├── README.md                          # Quick start (links to docs/)
│   │
│   ├── src/                               # Source code
│   ├── scripts/                           # Scripts
│   ├── packs/                             # Packs
│   │
│   ├── docs/                              # ALL TRUTH SOURCE DOCUMENTATION
│   │   ├── README.md                      # Project overview (main docs)
│   │   ├── WHATS_LEFT_TO_BUILD.md        # Roadmap
│   │   ├── ARCHITECTURE.md                # Architecture (if exists)
│   │   ├── project_learned_rules.json     # Learned rules (auto-updated)
│   │   └── guides/                        # How-to guides
│   │
│   └── archive/                           # Historical files
│       ├── plans/
│       ├── reports/
│       │   ├── CONSOLIDATED_DEBUG.md      # Auto-generated
│       │   └── ...
│       ├── research/
│       │   ├── CONSOLIDATED_RESEARCH.md   # Auto-generated
│       │   └── ...
│       ├── prompts/
│       ├── superseded/
│       └── diagnostics/
│           ├── logs/
│           └── runs/                      # File-organizer specific runs
│
├── Autopack/                              # Autopack autonomous runs (if active)
│   ├── README.md                          # Purpose: "Autopack self-improvement runs"
│   ├── docs/
│   └── archive/                           # Move to main archive/
│
├── file-organizer-phase2-run.json         # Run configuration (OK)
└── tidy_semantic_cache.json               # Tidy system cache (OK)
```

### Key Changes from V1:

1. **Rename `checkpoints/` → `tidy_checkpoints/`** - Explicit purpose
2. **Add truth sources to project docs/** - README.md, ARCHITECTURE.md minimum
3. **Clean up Autopack folder** - Add README or DELETE if unused
4. **Documented .json files** - Explained their purpose

---

## Cleanup Actions

### Phase 1: Root Cleanup - Consolidate Truth Sources to docs/
1. Move truth source .md files to `docs/`:
   - `WORKSPACE_ORGANIZATION_SPEC.md` → `docs/`
   - `WHATS_LEFT_TO_BUILD.md` → `docs/`
   - `WHATS_LEFT_TO_BUILD_MAINTENANCE.md` → `docs/`
2. Move config/ruleset files to `docs/`:
   - `project_ruleset_Autopack.json` → `docs/`
   - `project_issue_backlog.json` → `docs/`
   - `autopack_phase_plan.json` → `docs/`
3. Move `openapi.json` to `docs/api/`
4. Move diagnostic .json files to `archive/diagnostics/`:
   - `test_run.json` → `archive/diagnostics/`
   - `builder_fullfile_failure_latest.json` → `archive/diagnostics/`
5. Archive obsolete documentation:
   - `STRUCTURE_VERIFICATION_FINAL.md` → `archive/reports/`
   - `RUN_COMMAND.txt` → archive or delete
6. Keep root `README.md` as quick-start (links to docs/README.md)

### Phase 2: Archive Restructuring
1. **Eliminate `archive/src/`:**
   - Review files in `archive/src/autopack/diagnostics/`
   - If obsolete: DELETE
   - If historical reference: Move to `archive/superseded/diagnostics_v1/`
   - If still relevant: Move to actual `src/`

2. **Group runs by project:**
   ```bash
   # Create project folders
   mkdir -p archive/diagnostics/runs/Autopack
   mkdir -p archive/diagnostics/runs/file-organizer
   mkdir -p archive/diagnostics/runs/unknown

   # Move fileorg-* runs
   mv archive/diagnostics/runs/fileorg-* archive/diagnostics/runs/file-organizer/

   # Move Autopack runs
   [identify and move Autopack runs]

   # Move unknown runs
   [move remaining to unknown/]
   ```

3. **Flatten excessive nesting:**
   - Extract run data from `runs/Autopack/.autonomous_runs/Autopack/archive/unknowns/`
   - Flatten to `runs/Autopack/unknowns/` or `runs/unknown/`
   - Delete empty nested folders

4. **Rename diagnostic data:**
   - Move `archive/diagnostics/autopack_data/` to `archive/diagnostics/data/`

### Phase 3: .autonomous_runs Cleanup
1. Rename `checkpoints/` to `tidy_checkpoints/`
2. Consolidate file-organizer truth sources to `file-organizer-app-v1/docs/`:
   - Move `README.md` from project root → `docs/README.md` (comprehensive)
   - Move `WHATS_LEFT_TO_BUILD.md` from project root → `docs/`
   - Keep project root `README.md` as quick-start (links to docs/)
   - `project_learned_rules.json` already in docs/ (verify)
3. Handle `Autopack/` folder:
   - If active: Add README.md explaining purpose
   - If inactive: Move archive/ to main archive, DELETE folder

### Phase 4: Restore & Consolidate Documentation
1. Restore archived Autopack docs to `C:\dev\Autopack\docs/`:
   - Restore `DEPLOYMENT_GUIDE.md` from archive/reports/
   - Create comprehensive `docs/README.md` (project overview)
   - `SETUP_GUIDE.md` already in docs/
   - Search for `ARCHITECTURE.md`, `API_REFERENCE.md`, `CONTRIBUTING.md` in archive

2. Verify all truth sources in `docs/`:
   - Documentation files
   - Ruleset .json files (moved in Phase 1)
   - CONSOLIDATED_*.md files (auto-generated, in archive/)

3. Create quick-start root READMEs (if needed):
   - Root `README.md` → links to docs/README.md
   - file-organizer root `README.md` → links to docs/README.md

---

## Validation Checklist (V2 - REVISED)

A properly organized workspace has:

### Root Level:
- [ ] Only 1 truth source file: `README.md` (quick-start, links to docs/)
- [ ] Only standard config files (package.json, tsconfig.json, requirements.txt)
- [ ] NO loose .md files (WORKSPACE_ORGANIZATION_SPEC.md, WHATS_LEFT_TO_BUILD.md, etc. → moved to docs/)
- [ ] NO loose .json config files (project_ruleset_Autopack.json, etc. → moved to docs/)
- [ ] NO diagnostic .json files at root

### Autopack docs/:
- [ ] ALL truth source documentation consolidated here:
  - [ ] `README.md` (comprehensive project overview)
  - [ ] `WORKSPACE_ORGANIZATION_SPEC.md`
  - [ ] `WHATS_LEFT_TO_BUILD.md`
  - [ ] `WHATS_LEFT_TO_BUILD_MAINTENANCE.md`
  - [ ] `SETUP_GUIDE.md`
  - [ ] `DEPLOYMENT_GUIDE.md` (restored from archive)
  - [ ] `project_ruleset_Autopack.json`
  - [ ] `project_issue_backlog.json`
  - [ ] `autopack_phase_plan.json`
  - [ ] `api/openapi.json`
  - [ ] (Optional: ARCHITECTURE.md, API_REFERENCE.md, CONTRIBUTING.md if they exist)

### Archive:
- [ ] NO `archive/src/` folder
- [ ] All runs grouped under `diagnostics/runs/PROJECT/`
- [ ] Max 3 levels deep (e.g., `runs/file-organizer/RUN_NAME/`)
- [ ] NO nested `runs/*/archive/.autonomous_runs/archive/runs/`
- [ ] `diagnostics/data/` for diagnostic data files

### .autonomous_runs/file-organizer-app-v1:
- [ ] Root has quick-start `README.md` (links to docs/)
- [ ] `docs/` has ALL truth sources consolidated:
  - [ ] `README.md` (comprehensive)
  - [ ] `WHATS_LEFT_TO_BUILD.md`
  - [ ] `project_learned_rules.json`
  - [ ] (Optional: `ARCHITECTURE.md` if exists)
- [ ] `checkpoints/` renamed to `tidy_checkpoints/`
- [ ] `Autopack/` either has README.md or is deleted

### Truth Sources - ALL in docs/ folders:
- [ ] `C:\dev\Autopack\docs/` - ALL Autopack truth sources here (not scattered at root)
- [ ] `.autonomous_runs/file-organizer-app-v1/docs/` - ALL file-organizer truth sources here
- [ ] Root README.md files are quick-starts that link to docs/

---

## Appendix: Answers to Specific Questions

### Q: "Why no source of truth files in `C:\dev\Autopack\docs`?"
**A:** PROPOSED_CLEANUP_STRUCTURE.md V1 was incomplete. V2 requires active documentation in `docs/`.

### Q: "Why `archive/src/` when root has `src/`?"
**A:** This was a mistake. V2 eliminates `archive/src/` - superseded code goes to `archive/superseded/` with descriptive names.

### Q: "Why aren't runs grouped?"
**A:** V1 didn't specify grouping. V2 requires all runs under `diagnostics/runs/PROJECT/`.

### Q: "What's with `runs/Autopack/.autonomous_runs/Autopack/archive/unknowns`?"
**A:** Excessive nesting from blind copy. V2 requires flattening to max 3 levels.

### Q: "What's with `runs/archive/.autonomous_runs/archive/runs`?"
**A:** Same issue - V2 extracts run data and flattens structure.

### Q: "What's with loose config files at root?"
**A:** V1 only addressed .md/.log files. V2 addresses ALL file types with specific destinations.

### Q: "What's `file-organizer-phase2-run.json` doing in `.autonomous_runs`?"
**A:** It's a run configuration - this is correct. V2 documents this explicitly.

### Q: "What's `.autonomous_runs/Autopack` for?"
**A:** Likely historical. V2 requires either README.md explaining purpose or deletion.

### Q: "Shouldn't `tests/` be in `scripts/`?"
**A:** No - `tests/` is standard Python project structure for pytest. V2 clarifies this.

### Q: "Rename `checkpoints/` to `tidy_checkpoints/`?"
**A:** YES - V2 implements this for clarity.

### Q: "No truth sources in `file-organizer-app-v1/docs/`?"
**A:** Correct observation. V2 requires README.md and ARCHITECTURE.md at minimum.

---

**Generated:** 2025-12-11
**Supersedes:** PROPOSED_CLEANUP_STRUCTURE.md
