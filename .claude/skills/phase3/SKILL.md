---
name: phase3
description: Phase 3 Wave Generation - generate workflow prompts for the next wave
---

# Phase 3: Wave Workflow Generation

## CRITICAL: TARGET DIRECTORY CHECK

**THIS COMMAND MUST BE RUN FROM C:\dev\Autopack** (NOT streamdeck_auto_build!)

Before proceeding, verify your current working directory:
1. Check that you are in `C:\dev\Autopack`
2. If you are in `C:\dev\streamdeck_auto_build` - STOP and ask user to open Cursor from Autopack

**Target Repository**: C:\dev\Autopack
**Purpose**: Generate prompts for AUTOPACK improvements (NOT streamdeck)

---

Run phase_3.md in C:\Users\hshk9\OneDrive\Backup\Desktop to generate workflow prompts.

**IMPORTANT - DETERMINE WAVE NUMBER**:
1. Read AUTOPACK_WAVE_PLAN.json in C:\Users\hshk9\OneDrive\Backup\Desktop\Archive to see available waves
2. Read Prompts_All_Waves.md in C:\Users\hshk9\OneDrive\Backup\Desktop\Archive header to see which waves already have prompts
3. Generate prompts for the NEXT wave that needs generation

**ACTION - CREATE/UPDATE FILES**:
1. CREATE/UPDATE AUTOPACK_WORKFLOW.md at C:\Users\hshk9\OneDrive\Backup\Desktop\Archive\AUTOPACK_WORKFLOW.md
2. CREATE/UPDATE Prompts_All_Waves.md at C:\Users\hshk9\OneDrive\Backup\Desktop\Archive\Prompts_All_Waves.md

**Prompts_All_Waves.md SIMPLIFIED FORMAT** (registry/status only - no detailed prompts):
- Header line: `W1: 0/X | W2: 0/Y | W3: 0/Z` (per-wave counts)
- New wave phases: [READY] status
- Other waves: [UNIMPLEMENTED] status
- Each phase only needs registry fields (NO detailed prompts - those are in AUTOPACK_WORKFLOW.md):
  - `**IMP**: <IMP-XXX-NNN>`
  - `**Wave**: <number>` (required for wave boundary enforcement)
  - `**Path**: <worktree_path>` (NOT **Worktree** - automation requires **Path**)
  - `**Branch**: <branch_name>`

Example phase structure (minimal registry format):
```
## Phase: loop002 [READY]
**IMP**: IMP-LOOP-002
**Wave**: 1
**Path**: C:\dev\Autopack_w1_loop002
**Branch**: wave1/loop002-telemetry-feedback
```

**NOTE**: Detailed prompts and context are in AUTOPACK_WORKFLOW.md only. Workers receive simple references to that file.

**COMPLETION MARKER** (REQUIRED):
After successfully generating wave prompts, add this EXACT marker at the end of AUTOPACK_WORKFLOW.md:

```
<!-- WAVE_N_PROMPTS_GENERATED -->
```

(Replace N with the wave number you generated)

**SMART WAVE GENERATION NOTE**:
For small projects (<=40 phases), all wave prompts are generated upfront in sequence rather than one wave at a time. This means:
- You may be called multiple times in quick succession (once per wave)
- AUTOPACK_WORKFLOW.md will contain ALL wave prompts simultaneously
- Always check for existing `<!-- WAVE_N_PROMPTS_GENERATED -->` markers before generating
- If marker already exists for requested wave, skip generation and report "already generated"
