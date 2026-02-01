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

## ⚠️ KNOWN ISSUES TO AVOID

**Issue 1 - Duplicate Sections**: Previous runs created duplicate wave sections in Prompts_All_Waves.md
- Cause: Multiple edits without deduplication validation
- Prevention: See CRITICAL: HEADER UPDATE LOGIC section (Step 3)

**Issue 2 - Header Count Mismatch**: Header showed wrong counts (e.g., W6: 0/12 instead of 0/6)
- Cause: Header update logic was missing; counts not synchronized with wave plan
- Prevention: Follow Step 4 & 5 in CRITICAL: HEADER UPDATE LOGIC section

**Issue 3 - Status Tags Wrong**: Phases marked [COMPLETED] when they should be [READY]
- Cause: Confusion between "prompts generated" vs "phase completed"
- Prevention: Use [READY] for newly generated phases (not completed), [COMPLETED] only when PRs are merged

---

Run phase_3.md in C:\Users\hshk9\OneDrive\Backup\Desktop to generate workflow prompts.

**IMPORTANT - DETERMINE WAVE NUMBER**:
1. Read AUTOPACK_WAVE_PLAN.json in C:\Users\hshk9\OneDrive\Backup\Desktop to see available waves
2. Read Prompts_All_Waves.md in C:\Users\hshk9\OneDrive\Backup\Desktop header to see which waves already have prompts
3. Generate prompts for the NEXT wave that needs generation

**ACTION - CREATE/UPDATE FILES**:
1. CREATE/UPDATE AUTOPACK_WORKFLOW.md at C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_WORKFLOW.md
2. CREATE/UPDATE Prompts_All_Waves.md at C:\Users\hshk9\OneDrive\Backup\Desktop\Prompts_All_Waves.md

**Prompts_All_Waves.md SIMPLIFIED FORMAT** (registry/status only - no detailed prompts):
- Header line: `W1: 0/X | W2: 0/Y | W3: 0/Z` (per-wave counts - see CRITICAL HEADER UPDATE section below)
- New wave phases: [READY] status
- Other waves: [UNIMPLEMENTED] or [COMPLETED] status
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

---

## 🔴 CRITICAL: HEADER UPDATE LOGIC (MUST IMPLEMENT)

**Problem**: Previous phase3 runs had gaps that caused:
1. Header counts not updated (e.g., W6: 0/12 instead of 0/6)
2. Duplicate wave sections in Prompts_All_Waves.md
3. No deduplication validation

**Solution - MANDATORY VERIFICATION STEPS**:

### Step 1: Count Existing Completed Phases
Before updating header, scan Prompts_All_Waves.md and count [COMPLETED] phases per wave:
```
W1: Count all ## Phase: lines with [COMPLETED] status = X
W2: Count all ## Phase: lines with [COMPLETED] status = Y
... repeat for all waves
```

### Step 2: Add New Wave to File (if generating)
When adding new wave section:
1. Check if wave section already exists (grep "^# WAVE N")
2. If exists: DO NOT append, verify existing section matches plan
3. If not exists: Add new section with [READY] status for new phases

### Step 3: DEDUPLICATION VALIDATION
After any edit to Prompts_All_Waves.md:
```bash
# Check for duplicate wave headers
grep "^# WAVE" Prompts_All_Waves.md | sort | uniq -d
# If output is not empty → STOP and fix duplication before proceeding
```

### Step 4: Calculate Correct Header
From AUTOPACK_WAVE_PLAN.json, for each wave read:
- `wave_N.count` = total phases for that wave
- Completed = count of [COMPLETED] phases from file
- Format: `WN: {completed}/{total}`

Example: If Wave 6 has total=6 and completed=0:
```
W6: 0/6
```

### Step 5: Update Header Line (ATOMIC)
Replace the ENTIRE line 3 in Prompts_All_Waves.md:
```
BEFORE: W1: X/X | W2: Y/Y | W3: 0/12 | ...
AFTER:  W1: X/X | W2: Y/Y | W3: 0/11 | ... (corrected counts from plan)
```

Also update Total Phases metadata:
```
Total Phases: {sum_of_all_totals} ({sum_completed} completed, {sum_pending} pending)
```

### Step 6: FINAL VERIFICATION
Before declaring success:
1. Verify NO duplicate wave sections exist
2. Verify header counts match AUTOPACK_WAVE_PLAN.json
3. Verify new wave count is correct (e.g., W6 total = 6 if that's what plan says)
4. Verify status tags are correct ([READY] for new, [COMPLETED] for done, [UNIMPLEMENTED] for future)
5. Count all phases in file matches total in header

---

**COMPLETION MARKER** (REQUIRED - ONLY after validation passes):
After successfully generating AND validating wave prompts:

1. Verify all validation checks from CRITICAL: HEADER UPDATE LOGIC section passed ✓
2. Add this EXACT marker at the end of AUTOPACK_WORKFLOW.md:

```
<!-- WAVE_N_PROMPTS_GENERATED -->
```

(Replace N with the wave number you generated)

3. Document what was done:
   - Which wave was generated
   - Total phases added
   - Updated header with final counts
   - Deduplication validated
   - No errors encountered

**SMART WAVE GENERATION NOTE**:
For small projects (<=40 phases), all wave prompts are generated upfront in sequence rather than one wave at a time. This means:
- You may be called multiple times in quick succession (once per wave)
- AUTOPACK_WORKFLOW.md will contain ALL wave prompts simultaneously
- Always check for existing `<!-- WAVE_N_PROMPTS_GENERATED -->` markers before generating
- If marker already exists for requested wave, skip generation and report "already generated"
