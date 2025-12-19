# Next Cursor Takeover Prompt — Autopack Research System Stabilization (as of 2025-12-19)

## Mission

You are taking over an ongoing **Autopack research-system stabilization effort**. Your mission is to **let Autopack converge autonomously** on the research-system phases defined in the requirements YAMLs, intervening only to fix **system bugs that prevent convergence**. If you apply any manual fix, you **MUST** log it to SOT docs immediately.

## Primary runbook (follow it)

- `PROMPT_FOR_OTHER_CURSOR_FILEORG.md` (updated to prefer backend **8001**)

## Requirements (phases/chunks)

Directory:
- `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/`

Key files:
- `chunk0-tracer-bullet.yaml` → `phase_id: research-tracer-bullet`
- `chunk1a-foundation-orchestrator.yaml` → `phase_id: research-foundation-orchestrator`
- `chunk1b-foundation-intent-discovery.yaml` → `phase_id: research-foundation-intent-discovery`
- `chunk2a-gatherers-social.yaml` → `phase_id: research-gatherers-social`
- `chunk2b-gatherers-web-compilation.yaml` → `phase_id: research-gatherers-web-compilation`
- `chunk3-meta-analysis.yaml` → `phase_id: research-meta-analysis`
- `chunk4-integration.yaml` → `phase_id: research-integration`
- `chunk5-testing-polish.yaml` → `phase_id: research-testing-polish`

## Mandatory SOT logging (for ANY manual fix)

If you manually change any code/config/docs/scripts/YAML (i.e. not produced autonomously by Autopack), log it to BOTH:
- `docs/DEBUG_LOG.md`
- `docs/BUILD_HISTORY.md`

## “What changed since the last capability-gap report”

An older report `docs/RESEARCH_SYSTEM_CAPABILITY_GAP_ANALYSIS.md` was written before the most recent stabilization fixes. It has now been updated to reflect current reality.

### System-level convergence fixes that were applied manually (already logged)

These are the key changes that removed deterministic convergence blockers:

- **Chunk 2B truncation fix**: in-phase batching for `research-gatherers-web-compilation`
  - File: `src/autopack/autonomous_executor.py`
  - SOT: BUILD-081 / DBG-040

- **Deliverables sanitization**: strip parenthetical annotations from deliverables strings (`path (10+ tests)` → `path`)
  - File: `src/autopack/deliverables_validator.py`
  - SOT: BUILD-082 / DBG-041

- **Chunk 4 isolation fix**: allow safe subtrees under `src/autopack/` required by integration deliverables
  - `src/autopack/integrations/`
  - `src/autopack/phases/`
  - `src/autopack/autonomous/`
  - `src/autopack/workflow/`
  - File: `src/autopack/governed_apply.py`
  - SOT: BUILD-083 / DBG-042

- **Chunk 5 directory deliverables**: treat `/`-suffixed deliverables as prefix requirements and also support prefix entries in manifest enforcement
  - File: `src/autopack/deliverables_validator.py`
  - SOT: BUILD-084 / DBG-043 and BUILD-085 / DBG-044

### Important note

CI/test failures (e.g. pytest exit code 2 from missing dependencies) are usually **deliverable correctness**, not a system/mechanics blocker, unless they prevent any phase from ever converging.

## Current status at takeover time

### Backend

Use backend **8001**:

- Health: `curl.exe -s http://127.0.0.1:8001/health`

Start command (PowerShell):

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONPATH='src'; $env:DATABASE_URL='sqlite:///autopack.db';
python -m uvicorn backend.main:app --app-dir src --host 127.0.0.1 --port 8001
```

### Runs that were executed to validate convergence fixes

- `research-system-v25`: Chunk 2B (`research-gatherers-web-compilation`) converged (deliverables applied).
- `research-system-v27`: Chunk 4 (`research-integration`) converged after allowlisting safe `src/autopack/*` subtrees.
- `research-system-v28`: Chunk 5 (`research-testing-polish`) converged; backend shows **DONE_SUCCESS**.

### Where I was / what I was doing right before finishing

- I was unblocking **Chunk 5** deliverables validation failures caused by:
  - annotated deliverables strings, and
  - directory-style deliverables (paths ending in `/`), plus
  - manifest enforcement treating directory entries as exact matches.
- I implemented validator support for directory/prefix deliverables and manifest prefix entries and validated it by seeding and running `research-system-v28` until it reached DONE_SUCCESS.
- I updated `docs/RESEARCH_SYSTEM_CAPABILITY_GAP_ANALYSIS.md` and `PROMPT_FOR_OTHER_CURSOR_FILEORG.md` to match current status and operational protocol (prefer backend 8001).

## How to continue

1) Confirm backend 8001 is healthy:

```powershell
curl.exe -s http://127.0.0.1:8001/health
```

2) Identify if any executor is still running (should not be necessary for v28):

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select ProcessId,CommandLine |
  ? { $_.CommandLine -match 'autonomous_executor|uvicorn' } |
  ft -AutoSize
```

3) If you need to run a specific run-id:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='src'
$env:DATABASE_URL='sqlite:///autopack.db'
python -m autopack.autonomous_executor --run-id <run-id> --api-url http://127.0.0.1:8001 --max-iterations 120
```

4) If you need to inspect run state:

```powershell
curl.exe -s http://127.0.0.1:8001/runs/<run-id>
```

## High-signal reference files (read these first)

- Runbook / monitoring + SOT hygiene rules: `PROMPT_FOR_OTHER_CURSOR_FILEORG.md`
- Updated capability gap report: `docs/RESEARCH_SYSTEM_CAPABILITY_GAP_ANALYSIS.md`
- SOT:
  - `docs/BUILD_HISTORY.md` (BUILD-081..085)
  - `docs/DEBUG_LOG.md` (DBG-040..044)
- Core mechanisms:
  - `src/autopack/autonomous_executor.py` (batching paths, phase execution)
  - `src/autopack/deliverables_validator.py` (deliverables extraction/validation, manifest logic)
  - `src/autopack/governed_apply.py` (protected paths + allowlists, patch validation)


