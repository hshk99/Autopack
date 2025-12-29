# Telemetry Collection Unblock - Prompt for Other Cursor Session

## Context

**Location**: `C:\dev\Autopack`

**BUILD-141 Status**: ✅ COMPLETE - Database identity drift fixed. Executor and API server now use the same database, database persistence verified.

**Current Blocker**: Builder returning empty `files: []` array (~41 output tokens), causing telemetry seeding to fail. TokenEstimationV2 DB writes are skipped due to `actual_output_tokens < 50` validity guard.

**Goal**: Unblock `success=True` telemetry samples with minimal token burn.

---

## Evidence of Current Failure

### Phase Execution Log
```
[2025-12-28 23:19:23] INFO: [TOKEN_BUDGET] phase=telemetry-p1-string-util complexity=low input=3669 output=41/16384 total=3710 utilization=0.3% model=claude-sonnet-4-5
[2025-12-28 23:19:23] INFO: [TokenEstimationV2] predicted_output=5200 actual_output=41 smape=196.9% selected_budget=8192 category=implementation complexity=low deliverables=1 success=False stop_reason=end_turn truncated=False model=claude-sonnet-4-5
[2025-12-28 23:19:23] WARNING: [TELEMETRY] Skipping invalid event for telemetry-p1-string-util: actual_output_tokens=41 < 50 (likely error)
[2025-12-28 23:19:23] ERROR: [telemetry-p1-string-util] Builder failed: LLM returned empty files array
```

### Diagnosis
- **Output tokens**: 41 (expected: 5200) → 99% reduction
- **Root cause**: Builder JSON response contains `files: []` (empty array)
- **Failure location**: [src/autopack/anthropic_clients.py:1533-1548](../src/autopack/anthropic_clients.py#L1533-L1548)
- **Impact**: Zero telemetry samples collected, blocks calibration workflow

### Parser Code
```python
# anthropic_clients.py lines 1533-1548
files = result_json.get("files", [])
if not files:
    error_msg = "LLM returned empty files array"
    ...
    return BuilderResult(... success=False, error=error_msg ...)
```

---

## Root Cause Analysis

### Likely Cause: Prompt Ambiguity for Directory-Scoped Phases

**Phase Configuration**:
```python
{
    "phase_id": "telemetry-p1-string-util",
    "scope": {
        "paths": ["examples/telemetry_utils/"],  # Directory with trailing /
        "deliverables": ["examples/telemetry_utils/string_helper.py"]
    }
}
```

**Ambiguity**:
- `scope.paths` contains `examples/telemetry_utils/` (directory prefix with trailing `/`)
- Current prompt does not explicitly state: "paths ending with `/` are directory prefixes; creating files under them is allowed"
- Cautious model interprets this as "only that exact path may be modified" → chooses "do nothing" → `files: []`

**Additional Issues**:
1. User prompt does not strongly require emitting deliverables (exact file paths)
2. User prompt does not forbid `files: []` in "create" phases
3. No explicit deliverables list in prompt contract

---

## Investigation Required

### Question 1: Output Format Mode
**Was the failed phase running in `full_file` mode or `NDJSON` mode?**

Check the Builder prompt logs for telemetry-p1-string-util to determine:
- Format requested in system prompt
- This determines the recommended retry format switch (NDJSON vs structured_edit)

**Location to check**:
- `.autonomous_runs/telemetry-collection-v4/` (diagnostics, logs)
- Search for: `[telemetry-p1-string-util]` + `format` or `NDJSON` or `full_file`

**Expected**: Likely was `full_file` mode (default for simple phases)

---

## High-Impact Tasks (Prioritized)

### T1 — Fix Prompt Ambiguity for Directory-Scoped Phases (UNBLOCK SUCCESS)

**File**: [src/autopack/anthropic_clients.py](../src/autopack/anthropic_clients.py)
**Function**: `_build_user_prompt()` (search for where scope paths are formatted)

**Changes Required**:

1. **Clarify directory prefix semantics**:
   ```python
   # Example enhancement:
   scope_text = "Allowed modification paths:\n"
   for path in allowed_paths:
       if path.endswith('/'):
           scope_text += f"  - {path} (directory prefix - files under this path are allowed)\n"
       else:
           scope_text += f"  - {path} (exact file path)\n"
   ```

2. **Add explicit deliverables list**:
   ```python
   # Extract deliverables from phase_spec or scope
   deliverables = phase_spec.get("deliverables") or scope.get("deliverables", [])

   if deliverables:
       prompt += "\n\nREQUIRED DELIVERABLES:\n"
       for file_path in deliverables:
           prompt += f"  - {file_path}\n"
       prompt += "\nYour output MUST include at least these files. Empty files array is NOT allowed.\n"
   ```

3. **Add hard requirement for non-empty output**:
   ```python
   if deliverables:
       prompt += "\n⚠️ CRITICAL: This phase has deliverables. The 'files' array in your JSON output MUST contain at least one file and MUST cover all deliverables listed above.\n"
   ```

**Expected Impact**: Builder will understand that creating files under `examples/telemetry_utils/` is explicitly allowed and required.

---

### T2 — Add Targeted Retry Strategy for "Empty Files Array"

**File**: [src/autopack/autonomous_executor.py](../src/autopack/autonomous_executor.py)
**Location**: Builder error handling (search for `BuilderResult` error processing)

**Changes Required**:

1. **Detect "empty files array" error**:
   ```python
   if builder_result.error and "empty files array" in builder_result.error.lower():
       # Trigger targeted retry
   ```

2. **Single retry with stronger emphasis**:
   ```python
   if retry_count == 0:  # Only retry ONCE
       logger.warning("[Builder] Empty files array detected - retrying with stronger deliverables emphasis")

       # Option A: Retry with enhanced prompt (deliverables emphasized)
       # Option B: Switch to NDJSON format (if was full_file)
       # Option C: Switch to structured_edit (if NDJSON fails)

       # Re-invoke builder with modified phase_spec
       # phase_spec["_retry_mode"] = "deliverables_emphasis"
       builder_result = self._retry_builder_with_deliverables_emphasis(...)
   ```

3. **Fail fast after 1 retry**:
   ```python
   else:
       logger.error("[Builder] Empty files array persists after retry - failing fast to avoid token waste")
       return BuilderResult(success=False, error="Persistent empty files array after targeted retry")
   ```

**Token Safety**: Capped to 1 retry (~5-10k tokens) vs unlimited retries.

---

### T3 — Make Telemetry Seeding Runs Token-Cheap

**Changes**:

1. **Disable dual auditor** (saves ~4k tokens/phase):
   ```bash
   # When running telemetry seeding:
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
       TELEMETRY_DB_ENABLED=1 timeout 300 \
       python scripts/drain_one_phase.py --run-id telemetry-collection-v4 \
       --phase-id telemetry-p1-string-util --force --no-dual-auditor
   ```

2. **Use small timeouts** (300s instead of 600s)

3. **Stop after first deterministic failure**:
   - Don't drain all 10 phases until phase 1 succeeds
   - Validate DB telemetry rows are increasing before continuing

---

### T4 — Add "Telemetry Probe" Command (OPTIONAL)

**File**: New script `scripts/probe_telemetry_phase.py`

**Purpose**: One-liner that runs exactly one seeded phase and reports:
- Builder output token count
- Whether `files` array was empty
- Whether DB telemetry row count increased

**Example Output**:
```
[PROBE] Phase: telemetry-p1-string-util
[PROBE] Builder output tokens: 41
[PROBE] Files array: EMPTY ❌
[PROBE] DB telemetry rows (before): 0
[PROBE] DB telemetry rows (after): 0 (NO INCREASE ❌)
[PROBE] Verdict: FAILED - empty files array, no telemetry collected
```

**Usage**:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    TELEMETRY_DB_ENABLED=1 \
    python scripts/probe_telemetry_phase.py --run-id telemetry-collection-v4 --phase-id telemetry-p1-string-util
```

This becomes the **go/no-go gate** before draining remaining phases.

---

## Watchouts

### 1. Token Safety
- **Keep retries capped**: 1 retry max for "empty files array" error
- **Don't drain all 10 phases** until we see success on phase 1
- **Use `--no-dual-auditor`** for seeding runs

### 2. Database Identity (Already Fixed in BUILD-141)
- **Always set DATABASE_URL explicitly**: `sqlite:///autopack_telemetry_seed.db`
- **Always enable telemetry**: `TELEMETRY_DB_ENABLED=1`
- **Verify DB persistence** after each drain

### 3. Telemetry Validity Guard
- **Do NOT relax the `< 50 tokens` guard** in telemetry collection
- **Instead, make Builder produce real outputs** (fix prompt ambiguity)

---

## Testing Strategy

### Step 1: Verify Current Format Mode
```bash
# Check what format was used
grep -r "full_file\|NDJSON\|structured_edit" .autonomous_runs/telemetry-collection-v4/
```

### Step 2: Test Prompt Fix (T1)
```bash
# After implementing T1, test single phase
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
    TELEMETRY_DB_ENABLED=1 timeout 300 \
    python scripts/drain_one_phase.py --run-id telemetry-collection-v4 \
    --phase-id telemetry-p1-string-util --force --no-dual-auditor
```

**Success Criteria**:
- Builder output tokens > 500 (not 41)
- `files` array NOT empty
- DB telemetry rows increase by 1
- `success=True` in TokenEstimationV2Event

### Step 3: Verify DB Persistence
```bash
# Before drain
PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack_telemetry_seed.db" python scripts/db_identity_check.py

# After drain
PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack_telemetry_seed.db" python scripts/db_identity_check.py
# Should show: Runs: 1, Phases: 10, LLM events: >0, TokenEstimationV2Event: >0
```

### Step 4: If Still Failing - Try Format Switch (T2)
```python
# In retry logic, switch format based on original attempt:
if original_format == "full_file":
    retry_format = "NDJSON"  # Try NDJSON
elif original_format == "NDJSON":
    retry_format = "structured_edit"  # Try structured edits
```

---

## Expected Outcomes

### After T1 Implementation
- ✅ Builder produces non-empty `files` array
- ✅ Output tokens ~800-2000 (realistic for 1-file phase)
- ✅ Telemetry events recorded (`success=True`)
- ✅ Database preserved (BUILD-141 fixes working)

### After T2 Implementation (if needed)
- ✅ Single retry recovers from transient "empty files" errors
- ✅ Token burn capped at 1 extra attempt
- ✅ Fail-fast for persistent errors

### After T3 Implementation
- ✅ Token-efficient seeding runs (~5k tokens/phase vs 15k)
- ✅ No wasted LLM calls on deterministic failures

---

## Files to Modify

1. **[src/autopack/anthropic_clients.py](../src/autopack/anthropic_clients.py)** (T1: Prompt fixes)
   - `_build_user_prompt()` - Add directory prefix clarification + deliverables contract

2. **[src/autopack/autonomous_executor.py](../src/autopack/autonomous_executor.py)** (T2: Retry strategy)
   - Builder error handling - Add "empty files array" detection + targeted retry

3. **[scripts/drain_one_phase.py](../scripts/drain_one_phase.py)** (T3: Add `--no-dual-auditor` flag)
   - CLI argument parsing - Add flag to disable auditor

4. **[scripts/probe_telemetry_phase.py](../scripts/probe_telemetry_phase.py)** (T4: New file, optional)
   - Standalone probe script for go/no-go testing

---

## Current Database State

```
DATABASE_URL: sqlite:///autopack_telemetry_seed.db
Runs: 1 (telemetry-collection-v4)
Phases: 10 (1 FAILED, 9 QUEUED)
LLM usage events: 0
TokenEstimationV2Event: 0
```

**Next Action**: Fix T1 (prompt ambiguity), test phase 1, verify telemetry collection works before draining remaining 9 phases.

---

## Questions for Investigation

1. **Was telemetry-p1-string-util running in `full_file` mode or `NDJSON` mode?**
   - Check: `.autonomous_runs/telemetry-collection-v4/` logs
   - Answer determines retry format switch strategy

2. **Does the phase have explicit `deliverables` in phase_spec?**
   - Check: `scripts/create_telemetry_collection_run.py` phase definitions
   - Answer: YES - `deliverables: ["examples/telemetry_utils/string_helper.py"]`

3. **Is the current prompt showing deliverables to the model?**
   - Check: Builder prompt construction in `_build_user_prompt()`
   - Likely answer: NO - this is the core issue

---

## Success Metrics

- **Immediate**: Phase 1 succeeds with `success=True` telemetry event
- **Short-term**: 5 phases drained with ≥5 `success=True` samples
- **Medium-term**: Calibration job runs successfully with representative data
- **Long-term**: Token estimation accuracy improves (target: <30% SMAPE)

---

**Priority**: HIGH - Telemetry collection is blocked, preventing calibration workflow
**Estimated Effort**: T1 (30 min), T2 (45 min), T3 (15 min), T4 (30 min, optional)
**Risk**: LOW - Changes are localized, well-scoped, with clear rollback path

---

Generated: 2025-12-28T23:40:00Z
Session: BUILD-141 Database Identity Drift Resolution
Status: Ready for implementation in other Cursor session
