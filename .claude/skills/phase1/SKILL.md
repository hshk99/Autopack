---
name: phase1
description: Phase 1 Discovery - scan Autopack codebase for improvements and create AUTOPACK_IMPS_MASTER.json
---

# Phase 1: Discovery

## CRITICAL: TARGET DIRECTORY CHECK

**THIS COMMAND MUST BE RUN FROM C:\dev\Autopack** (NOT streamdeck_auto_build!)

Before proceeding, verify your current working directory:
1. Check that you are in `C:\dev\Autopack`
2. If you are in `C:\dev\streamdeck_auto_build` - STOP and ask user to open Cursor from Autopack

**Target Repository**: C:\dev\Autopack
**Purpose**: Scan AUTOPACK codebase for improvements (NOT streamdeck)

---

Using phase_1.md in C:\Users\hshk9\OneDrive\Backup\Desktop, scan for critical/high priority improvements only. Focus on gaps blocking Autopack's self-improvement architecture (telemetry -> memory -> task generation loop).

**NOTE**: This is a NEW project. CREATE fresh files.

**ACTION**: CREATE a new AUTOPACK_IMPS_MASTER.json file at C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_IMPS_MASTER.json

**COMPLETION MARKER** (REQUIRED - AUTOMATION DEPENDS ON THIS EXACT FORMAT):
After discovery is complete, add this field to the ROOT level of AUTOPACK_IMPS_MASTER.json (NOT inside metadata or any nested object):

```json
{
  "metadata": { ... },
  "statistics": { ... },
  "unimplemented_imps": [ ... ],
  "implemented_imps": [ ... ],
  "phase1_complete": "2026-01-28"
}
```

**CRITICAL**: The field must be:
- Named exactly `"phase1_complete"` (lowercase, with underscore)
- At the ROOT level of the JSON (same level as "metadata", "statistics", etc.)
- Value is today's date as a string in YYYY-MM-DD format (e.g., `"2026-01-28"`)
- NOT a boolean - must be a DATE STRING
