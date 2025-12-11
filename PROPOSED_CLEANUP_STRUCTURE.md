# Proposed Cleanup Structure - FINAL REVISION

## Assessment Results

### Question 1: Do we need scripts/ folder if source is in src/?
**Answer:** YES - Keep scripts/ folder
- `src/` = application source code (backend/, frontend/ apps)
- `scripts/` = utility scripts (deploy.sh, automation, etc.)
- **Different purposes**, both needed

### Question 2: Purpose of delegations/ folder?
**Answer:** MERGE delegations/ → reports/
- Delegations contain Claude/GPT assessment reports
- Not plans, but historical review/feedback documents
- **Belong in reports/ folder**

### Question 3: Keep diagnostics/ layer over logs/?
**Answer:** YES - Keep diagnostics/ layer
- diagnostics/ contains MORE than just logs:
  - **issues/** folders (JSON issue tracking)
  - **run_rule_hints.json** (rule metadata)
  - Various diagnostic JSON files
  - PLUS .log files
- **diagnostics/runs/** is correct structure

---

## What Will Change

### ROOT DIRECTORY (C:\dev\Autopack)

#### Files/Folders to MOVE:

1. **.cursor/** → **archive/prompts/**
   - PROMPT_REQUEST_GPT_REVIEW.md
   - PROMPT_SUBMIT_GPT_RESPONSE.md
   - README_PROMPTS.md

2. **planning/** → **archive/prompts/**
   - kickoff_prompt.md

3. **templates/** → **config/templates/**
   - hardening_phases.json
   - phase_defaults.json

4. **integrations/** → **scripts/integrations/**
   - cursor_integration.py
   - codex_integration.py
   - supervisor.py
   - __init__.py
   - requirements.txt
   - README.md

5. **logs/** → **archive/diagnostics/logs/**
   - All log files and subdirectories

6. **Loose .md/.log files at root** → **archive/** (classified by type)

#### Files/Folders to KEEP at root:
- README.md
- WORKSPACE_ORGANIZATION_SPEC.md
- WHATS_LEFT_TO_BUILD.md
- WHATS_LEFT_TO_BUILD_MAINTENANCE.md
- src/
- scripts/
- tests/
- docs/
- config/
- archive/
- .autonomous_runs/

---

### DOCS/ FOLDER (C:\dev\Autopack\docs)

#### Files to MOVE FROM docs/ TO archive/:

**TO archive/plans/** (Implementation plans - historical):
- DASHBOARD_IMPLEMENTATION_PLAN.md
- CRITICAL_ISSUES_IMPLEMENTATION_PLAN.md
- IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md
- IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT_PHASE2.md
- TOKEN_EFFICIENCY_IMPLEMENTATION.md

**TO archive/reports/** (Guides, checklists - historical):
- AUTOPACK_TIDY_SYSTEM_COMPREHENSIVE_GUIDE.md
- DEPLOYMENT_GUIDE.md
- DASHBOARD_WIRING_GUIDE.md
- directory_routing_qdrant_schema.md
- phase_spec_schema.md
- stage2_structured_edits.md
- PRE_PUBLICATION_CHECKLIST.md
- TEST_RUN_CHECKLIST.md
- QDRANT_INTEGRATION_VERIFIED.md
- QDRANT_SETUP_COMPLETE.md
- QDRANT_TRANSITION_COMPLETE.md
- IMPLEMENTATION_STATUS_AND_MONITORING_PLAN.md

**TO archive/analysis/** (Analysis documents):
- EFFICIENCY_ANALYSIS.md
- TROUBLESHOOTING_AUTONOMY_PLAN.md

**TO archive/research/** (Research documents):
- QUOTA_AWARE_ROUTING.md

#### Files to KEEP in docs/ (Truth sources - auto-updated):
- **SETUP_GUIDE.md** (active setup documentation)
- **README.md** (if exists - auto-updated)
- **consolidated_*.md** (auto-updated consolidated docs)
- **debug logs or ruleset files** (auto-updated)
- Any other files actively auto-updated by the system

---

### AUTOPACK ARCHIVE (C:\dev\Autopack\archive)

#### Current Problem:
- Stranded .log files at archive root (api_server_*.log, etc.)
- archive/logs/ folder not properly organized
- archive/superseded/ needs to be flattened
- archive/delegations/ should merge into reports/

#### Cleanup Actions:

1. **Move stranded .log files** at archive root → **archive/diagnostics/logs/**
   - api_server_final.log
   - api_server_fixed.log
   - api_server_fresh.log
   - api_server_fullfile_test.log
   - api_server_fullfile_test2.log
   - api_server_test.log
   - api_server_test3.log
   - ... (all loose .log files)

2. **Organize archive/logs/** → **merge into archive/diagnostics/logs/**
   - All log files should be under diagnostics/logs/
   - Remove empty logs/ folder after merge

3. **Merge archive/delegations/** → **archive/reports/**
   - Delegations are Claude/GPT assessment reports
   - Belong in reports/ folder
   - Remove empty delegations/ folder after merge

4. **Flatten archive/superseded/** folder
   - Move contents up to archive/ (following same bucket structure)
   - Remove empty superseded/ folder

5. **Remove nested folders**:
   - archive/archive/ (if exists)
   - archive/.autonomous_runs/ (if exists)

6. **Diagnostics truth handling**
   - `CONSOLIDATED_DEBUG.md` in archive/diagnostics is a truth candidate: review and merge into active docs (`C:\dev\Autopack\docs` or project docs), then archive or discard if superseded.
   - `ENHANCED_ERROR_LOGGING.md` should be routed to diagnostics/docs after review (not left stranded in archive root).

#### Final Autopack Archive Structure:
```
C:\dev\Autopack\archive/
├── plans/                (implementation plans)
├── reports/              (guides, checklists, assessment reports, delegations)
├── analysis/             (analysis, reviews)
├── research/             (research documents)
├── prompts/              (prompt templates from .cursor/, planning/)
├── diagnostics/          (logs + issues + run metadata)
│   ├── logs/             (all .log files)
│   └── runs/             (if any old runs here)
├── unsorted/             (last-resort inbox; tidy_up will bucket)
├── configs/              (config archives)
├── docs/                 (archived documentation)
├── exports/              (export archives)
├── patches/              (patch archives)
├── refs/                 (reference materials)
└── src/                  (archived source code if any)
```

---

### .AUTONOMOUS_RUNS ROOT (C:\dev\Autopack\.autonomous_runs)

#### Current Problem:
- Loose files/folders at .autonomous_runs root (delegate_to_openai.py, setup_new_project.py, etc.)
- runs/ folder not placed under specific project
- archive/, docs/, exports/, patches/ folders at wrong location

#### Cleanup Actions:

1. **Move loose Python scripts** → **scripts/** (or appropriate location)
   - delegate_to_openai.py
   - setup_new_project.py
   - task_format_converter.py

2. **Organize loose folders** → **move under appropriate projects**
   - .autonomous_runs/runs/ → move to project-specific location
   - .autonomous_runs/archive/ → organize/distribute to projects
   - .autonomous_runs/docs/ → organize/distribute to projects
   - .autonomous_runs/exports/ → organize/distribute to projects
   - .autonomous_runs/patches/ → organize/distribute to projects
   - .autonomous_runs/openai_delegations/ → merge into archive/reports/

3. **Keep project-specific folders**:
   - .autonomous_runs/Autopack/
   - .autonomous_runs/file-organizer-app-v1/
   - .autonomous_runs/checkpoints/ (if active)

---

### FILE-ORGANIZER PROJECT (C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1)

#### Current Structure Issues:
1. fileorganizer/ folder contains source code - should be in src/
2. Nested .autonomous_runs/autopack/ folder needs organization
3. patches/ and exports/ folders unused
4. Not following same organization as Autopack project
5. codex_delegations/ should merge into reports/

#### Cleanup Actions:

1. **Reorganize source code**:
   - **fileorganizer/** → **src/**
     - fileorganizer/backend/ → src/backend/
     - fileorganizer/frontend/ → src/frontend/
     - fileorganizer/deploy.sh → scripts/deploy.sh
     - fileorganizer/docker-compose.yml → keep at src level or move to root

2. **Keep scripts/ folder** (utility scripts separate from application code)

3. **Organize archive/ folder** (following Autopack archive structure):
   ```
   .autonomous_runs/file-organizer-app-v1/archive/
   ├── plans/
   ├── reports/              ← MERGE codex_delegations/ here
   ├── analysis/
   ├── research/
   ├── prompts/              (existing)
   └── diagnostics/          ← KEEP this layer (has issues/, metadata, logs/)
       ├── logs/             (loose log files)
       └── runs/             (137 runs grouped by family)
           ├── autopack-phase-plan/      (9 runs)
           ├── backlog-maintenance/      (10 runs)
           ├── fileorg-country-uk/       (22 runs)
           ├── fileorg-docker/           (3 runs)
           ├── fileorg-docker-build/     (10 runs)
           ├── fileorg-frontend-build/   (4 runs)
           ├── fileorg-p2/               (19 runs)
           ├── fileorg-phase2/           (5 runs)
           ├── fileorg-test-suite-fix/   (26 runs)
           ├── fileorg-test/             (4 runs)
           ├── phase3-delegated/         (10 runs)
           ├── backend-fixes/            (4 runs)
           ├── demo-run-002/             (1 run)
           ├── escalation-test-20251130-232314/  (1 run)
           ├── escalation-validation-20251130/   (1 run)
           ├── run-20251207-01/          (1 run)
           ├── run-20251208-01/          (1 run)
           ├── scope-smoke-20251206184302/       (1 run)
           ├── start/                    (1 run)
           ├── test-goal-anchoring/      (2 runs)
           └── test-run/                 (3 runs)
   ```

4. **Flatten archive/superseded/** folder (if exists):
   - Move contents up to archive/ following bucket structure
   - Remove empty superseded/ folder

5. **Organize nested .autonomous_runs/autopack/** folder:
   - Review contents and move to appropriate location
   - Could be archive/diagnostics/runs/autopack/ or separate location

6. **Remove unused folders** (if truly unused):
   - **patches/** (delete if not actively used)
   - **exports/** (delete if not actively used)
   - **archive/__pycache__/** (delete Python cache)
   - **.faiss/** (review if needed)

7. **Remove nested folders**:
   - archive/archive/ (if exists)
   - archive/.autonomous_runs/ (if exists)
   - archive/docs/ → move up to parent docs/

8. **Organize docs/ folder**:
   - docs/guides/ (for WHATS_LEFT_TO_BUILD*.md)
   - docs/architecture/ (for future use)
   - docs/api/ (for future use)
   - docs/research/ → archive/research/

#### Final File-Organizer Structure:
```
.autonomous_runs/file-organizer-app-v1/
├── src/                              ← RENAMED from fileorganizer/
│   ├── backend/
│   ├── frontend/
│   └── docker-compose.yml            (application-level config)
│
├── scripts/                          ← KEEP (utility scripts)
│   └── deploy.sh                     ← moved from fileorganizer/
│
├── packs/                            [KEEP - country packs]
│
├── docs/                             [Truth sources only]
│   ├── guides/
│   │   ├── WHATS_LEFT_TO_BUILD.md
│   │   └── WHATS_LEFT_TO_BUILD_MAINTENANCE.md
│   ├── architecture/                 [for future use]
│   └── api/                          [for future use]
│
└── archive/                          [Historical files]
    ├── plans/
    ├── reports/                      ← MERGED codex_delegations/ here
    ├── analysis/
    ├── research/
    ├── prompts/
    └── diagnostics/                  ← KEEP layer (has issues/, metadata)
        ├── logs/                     (loose log files)
        └── runs/                     (137 runs grouped into 31 families)
            ├── autopack-phase-plan/      (9 runs grouped)
            ├── backlog-maintenance/      (10 runs grouped)
            ├── fileorg-country-uk/       (22 runs grouped)
            └── ... (31 families total, 137 runs)
```

---

## Run Family Grouping Details

### 137 Run Directories → 31 Families

**Structure:** `archive/diagnostics/runs/[family]/[run-id]/`

Each run directory contains:
- **issues/** folders (JSON issue tracking)
- **run_rule_hints.json** (rule metadata)
- **.log** files
- Other diagnostic files

#### Major Families (2+ runs):

1. **fileorg-country-uk/** (22 runs)
2. **fileorg-test-suite-fix/** (26 runs)
3. **fileorg-p2/** (19 runs)
4. **phase3-delegated/** (10 runs)
5. **backlog-maintenance/** (10 runs)
6. **fileorg-docker-build/** (10 runs)
7. **autopack-phase-plan/** (9 runs)
8. **fileorg-phase2/** (5 runs)
9. **fileorg-frontend-build/** (4 runs)
10. **fileorg-test/** (4 runs)
11. **fileorg-docker/** (3 runs)
12. **test-run/** (3 runs)
13. **test-goal-anchoring/** (2 runs)
14. **fileorg-p2-20251206/** (2 runs)
15. **fileorg-phase2-beta/** (2 runs)

#### Single-Run Families (16 families with 1 run each)

---

## Classification Rules

### Files going to archive/plans/:
- Contain: "PLAN", "IMPLEMENTATION", "ROADMAP", "STRATEGY", "DESIGN"
- NOT containing: "COMPLETE", "SUMMARY", "STATUS"
- Examples: DASHBOARD_IMPLEMENTATION_PLAN.md

### Files going to archive/reports/:
- Contain: "GUIDE", "CHECKLIST", "COMPLETE", "VERIFIED", "STATUS", "SUMMARY"
- **INCLUDES**: Claude/GPT delegations (assessment reports)
- Examples: DEPLOYMENT_GUIDE.md, CLAUDE_ASSESSMENT_OF_GPT_FEEDBACK.md

### Files going to archive/analysis/:
- Contain: "ANALYSIS", "REVIEW", "TROUBLESHOOTING"
- Examples: EFFICIENCY_ANALYSIS.md

### Files going to archive/research/:
- Contain: "RESEARCH", "MARKET", "INVESTIGATION"
- Examples: QUOTA_AWARE_ROUTING.md

### Files to KEEP in docs/:
- SETUP_GUIDE.md (active documentation)
- README.md (auto-updated)
- consolidated_*.md (auto-updated)
- debug logs, ruleset files (auto-updated)

### Run family grouping:
- Extract family name by removing timestamps
- Examples:
  - `fileorg-country-uk-20251204-212535` → family: `fileorg-country-uk`
  - `fileorg-p2-20251208h` → family: `fileorg-p2`
  - `backlog-maintenance-1765286879` → family: `backlog-maintenance`

---

## Summary Statistics

### Autopack Project:
- **Root cleanup:** 5 folders + loose files to move
- **Docs cleanup:** 20 files to move to archive, 1+ to keep (truth sources)
- **Archive cleanup:** ~10 stranded .log files to organize, flatten superseded/, merge delegations/ → reports/

### .autonomous_runs Root:
- **Cleanup:** Move loose scripts, organize loose folders to projects

### File-Organizer Project:
- **Major reorganization:** fileorganizer/ → src/
- **Keep scripts/ folder** (utility scripts, not application code)
- **Merge codex_delegations/** → **reports/**
- **Keep diagnostics/ layer** (contains issues/, metadata, logs/)
- **Run grouping:** 137 runs → 31 families under diagnostics/runs/
- **Cleanup:** Remove patches/, exports/ if unused, organize nested .autonomous_runs/autopack/
- **Total operations:** ~150+ file/folder moves

---

## FINAL QUESTIONS FOR YOUR CONFIRMATION

**Please confirm or revise:**

1. ✅ **Keep scripts/ folder separate from src/**
   - src/ = application code (backend/frontend)
   - scripts/ = utility scripts (deploy.sh, etc.)

2. ✅ **Merge delegations/ → reports/**
   - Delegations are assessment/review reports
   - Belong in reports/ folder

3. ✅ **Keep diagnostics/ layer**
   - Contains issues/, run metadata, AND logs/
   - Structure: archive/diagnostics/runs/[family]/[run-id]/

4. ✅ **Root directory cleanup** (move .cursor, logs, planning, templates, integrations)

5. ✅ **docs/ - Files to KEEP:**
   - SETUP_GUIDE.md
   - README.md, consolidated_*.md (auto-updated)
   - debug logs/ruleset files (auto-updated)

6. ✅ **Autopack archive cleanup:**
   - Move stranded .log files to diagnostics/logs/
   - Merge archive/logs/ into diagnostics/logs/
   - Merge archive/delegations/ into reports/
   - Flatten archive/superseded/

7. ✅ **.autonomous_runs root cleanup:**
   - Move loose scripts to scripts/
   - Organize loose folders to projects
   - Merge openai_delegations/ into reports/

8. ✅ **File-organizer reorganization:**
   - fileorganizer/ → src/
   - Keep scripts/ folder
   - Merge codex_delegations/ → reports/
   - Keep diagnostics/ layer: archive/diagnostics/runs/[family]/
   - Delete patches/, exports/ if unused

**Any changes or final approval?**
