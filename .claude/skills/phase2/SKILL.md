---
name: phase2
description: Phase 2 Wave Planning - group IMPs into waves and create AUTOPACK_WAVE_PLAN.json
---

# Phase 2: Wave Planning

## CRITICAL: TARGET DIRECTORY CHECK

**THIS COMMAND MUST BE RUN FROM C:\dev\Autopack** (NOT streamdeck_auto_build!)

Before proceeding, verify your current working directory:
1. Check that you are in `C:\dev\Autopack`
2. If you are in `C:\dev\streamdeck_auto_build` - STOP and ask user to open Cursor from Autopack

**Target Repository**: C:\dev\Autopack
**Purpose**: Plan waves for AUTOPACK improvements (NOT streamdeck)

---

Run phase_2.md in C:\Users\hshk9\OneDrive\Backup\Desktop: analyze file conflicts in the newly created AUTOPACK_IMPS_MASTER.json and group IMPs into sequential waves.

**ACTION**: CREATE a new AUTOPACK_WAVE_PLAN.json file at C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_WAVE_PLAN.json

**COMPLETION MARKER** (REQUIRED - AUTOMATION DEPENDS ON THIS EXACT FORMAT):
After wave planning is complete, add this field to the ROOT level of AUTOPACK_WAVE_PLAN.json (NOT inside any nested object):

```json
{
  "metadata": { ... },
  "waves": [ ... ],
  "phase2_complete": "2026-01-28"
}
```

**CRITICAL**: The field must be:
- Named exactly `"phase2_complete"` (lowercase, with underscore)
- At the ROOT level of the JSON (same level as "metadata", "waves", etc.)
- Value is today's date as a string in YYYY-MM-DD format (e.g., `"2026-01-28"`)
- NOT a boolean - must be a DATE STRING
