# Implementation Plan: ref5.md Recommendations

**Date Created**: 2025-11-29
**Purpose**: Complete implementation of all ref5.md recommendations to prevent recurring bugs and enable true autonomous operation
**Source**: Based on comprehensive analysis of [ref5.md](./ref5.md)

---

## Executive Summary

**Current Status**: 50% implementation - logging layer complete, prevention & self-healing layers missing

**What Works**:
- ✅ Debug journal logs errors automatically
- ✅ Error classification and categorization
- ✅ Manual journal review by humans

**What's Missing** (Critical Gap):
- ❌ System doesn't read journal back to update behavior
- ❌ Fixes aren't enforced programmatically in future runs
- ❌ No automatic self-healing based on past errors
- ❌ No proactive environment validation

**Impact**: "Revised code doesn't register and errors resurface in next run" - User's concern is 100% valid due to missing prevention layer.

---

## COMPREHENSIVE VERIFICATION: ref5.md Recommendations vs. Current Implementation

### Part A: Run Analysis & Required Behavior Changes

| Recommendation | Status | Evidence | Priority |
|---|---|---|---|
| **Orchestration-level error recovery** | ✅ IMPLEMENTED | [error_recovery.py](../../src/autopack/error_recovery.py):136-149, 201-226<br>[autonomous_executor.py](../../src/autopack/autonomous_executor.py):277-284 | - |
| **Automatic detection of crashes** (no progress + zero tokens) | ⚠️ PARTIAL | Debug journal logs errors<br>BUT: No automatic zero-token detection logic | HIGH |
| **Automatic `EXECUTING → QUEUED` reset** for stale phases | ❌ NOT IMPLEMENTED | No stale phase detection<br>No automatic state reset | CRITICAL |
| **End-to-end testing** (Build → Review → Gate → Apply) | ❌ NOT IMPLEMENTED | No E2E test exists | MEDIUM |

### Part A Section 5: Settings Improvements for Token Efficiency

| Recommendation | Status | Evidence | Priority |
|---|---|---|---|
| **Context engineering** (file selection patterns per phase type) | ❌ NOT IMPLEMENTED | No context filtering by phase type | LOW |
| **Per-phase token limits** (`expected_tokens_min/max/hard_cap`) | ❌ NOT IMPLEMENTED | No per-phase token configuration | LOW |
| **Model selection by complexity** | ⚠️ PARTIAL | [model_router.py](../../src/autopack/model_router.py) exists<br>BUT: Not linked to phase complexity | LOW |
| **Token budget alerts** (50%, 80%, 90% thresholds) | ❌ NOT IMPLEMENTED | No budget alert system | LOW |

### Part A Section 6: CI Flow and Main-Branch Merge Strategy

| Recommendation | Status | Evidence | Priority |
|---|---|---|---|
| **Dedicated branch per run** (`autonomous/<project>-<run_id>`) | ❌ NOT IMPLEMENTED | No auto-branching logic | MEDIUM |
| **Run tests after each phase** | ❌ NOT IMPLEMENTED | No test automation | MEDIUM |
| **Mark phase FAILED if tests fail** | ❌ NOT IMPLEMENTED | No test-failure detection | MEDIUM |
| **Auto-merge to main** when all conditions met | ❌ NOT IMPLEMENTED | No merge automation | LOW |

### Part A Section 7: Troubleshooting Efficiency Improvements

| Recommendation | Status | Evidence | Priority |
|---|---|---|---|
| **Central debug journal** | ✅ IMPLEMENTED | [debug_journal.py](../../src/autopack/debug_journal.py)<br>[DEBUG_JOURNAL.md](./DEBUG_JOURNAL.md) | - |
| **Automatic error classification and logging** | ✅ IMPLEMENTED | [error_recovery.py](../../src/autopack/error_recovery.py):134-151 | - |
| **Run-level dashboards** | ❌ NOT IMPLEMENTED | No dashboard exists | LOW |
| **Stale phase reset logic** | ❌ NOT IMPLEMENTED | Same as Part A critical issue | CRITICAL |

### Part C: Debug Journal & Error Tracking System

| Requirement | Status | Evidence | Priority |
|---|---|---|---|
| **C.1: Avoid re-trying failed approaches** | ✅ IMPLEMENTED | DEBUG_JOURNAL.md tracks resolved issues | - |
| **C.2: Data model** (timestamp, run_id, phase_id, etc.) | ✅ IMPLEMENTED | [debug_journal.py](../../src/autopack/debug_journal.py) `log_error_event()` | - |
| **C.3: File location** (`.autonomous_runs/<slug>/DEBUG_JOURNAL.md`) | ✅ IMPLEMENTED | File exists at correct path | - |
| **C.4.1: Integration - Autonomous Executor** | ✅ IMPLEMENTED | [autonomous_executor.py](../../src/autopack/autonomous_executor.py):277-284 | - |
| **C.4.2: Integration - Error Recovery** | ✅ IMPLEMENTED | [error_recovery.py](../../src/autopack/error_recovery.py):136-149, 201-226 | - |
| **C.4.3: Integration - Supervisor / API** (phase → FAILED logging) | ❌ NOT IMPLEMENTED | No API integration for journal logging | MEDIUM |
| **C.4.4: Cursor session protocol** (read journal at start) | ⚠️ MANUAL PROCESS | Instructions exist in DEBUG_JOURNAL.md<br>BUT: Not enforced programmatically | LOW |
| **C.5: Process protocol** (new vs. known error classification) | ⚠️ PARTIAL | Journal can log errors<br>BUT: No automatic deduplication logic | MEDIUM |

### Part D: GPT2's Additional Suggestions (Durable Memory & Self-Healing)

| Recommendation | Status | Evidence | Priority |
|---|---|---|---|
| **Phase A: Error & Fix Journal** | ✅ IMPLEMENTED | debug_journal.py module exists | - |
| **Phase A: Dynamic Prompt Injection** (read prevention rules from journal) | ❌ NOT IMPLEMENTED | **CRITICAL GAP**: No prompt auto-updating | **CRITICAL** |
| **Phase A: Procedural Check** (startup environment fixes) | ⚠️ PARTIAL | [error_recovery.py](../../src/autopack/error_recovery.py) applies fixes reactively<br>BUT: Not proactive on startup | **HIGH** |
| **Phase B: Pre-Apply Validation** (validate patch before accepting) | ❌ NOT IMPLEMENTED | No patch validation in API | **HIGH** |
| **Phase B: Decouple Error Codes** (422 for validation, not 500) | ❌ NOT IMPLEMENTED | API still returns 500 for bad patches | **HIGH** |
| **Phase B: Auditor Wrapper Review** | ❌ NOT INVESTIGATED | DualAuditor not reviewed | MEDIUM |
| **Phase C: Self-Correction Retry** (422 → retry with hardened prompt) | ❌ NOT IMPLEMENTED | No retry logic based on 422 | MEDIUM |
| **Phase C: Bypass Auditor** (400 → disable DualAuditor, retry single) | ❌ NOT IMPLEMENTED | No auditor bypass logic | MEDIUM |

---

## CRITICAL GAPS ANALYSIS

### Gap #1: Dynamic Prompt Injection from Journal (CRITICAL)

**The Problem**: We log errors to the journal, but **we don't read the journal back** to update prompts for future runs.

**Example**:
- Issue #4 (patch corruption) is logged with fix "NEVER use literal `...`"
- Builder prompts in [openai_clients.py](../../src/autopack/openai_clients.py) and [anthropic_clients.py](../../src/autopack/anthropic_clients.py) **don't automatically get updated**
- LLM doesn't know about the fix
- Error resurfaces

**Impact**: **THIS IS WHY "REVISED CODE DOESN'T REGISTER"**

**Solution Required**:
1. Create `src/autopack/journal_reader.py` module
2. Add function `get_prevention_rules(project_slug) -> List[str]`
3. Parse DEBUG_JOURNAL.md for resolved issues with "Prevention Rule" tags
4. Inject these rules into Builder/Auditor system prompts before every LLM call

---

### Gap #2: Proactive Environment Checks (HIGH)

**The Problem**: Environment fixes (like `PYTHONUTF8=1`) are applied **reactively** after error, not **proactively** at startup.

**Example**:
- Unicode error happens
- Error recovery applies `PYTHONUTF8=1`
- Next run in clean environment → Unicode error happens again

**Impact**: Repeated environment errors across runs

**Solution Required**:
1. Add `startup_checks()` function in `autonomous_executor.py`
2. Run before any LLM calls
3. Check: Windows platform → apply `PYTHONUTF8=1`
4. Check: API keys available
5. Check: Required packages installed
6. Log all applied fixes to journal

---

### Gap #3: Pre-Apply Patch Validation (HIGH)

**The Problem**: Bad patches from Builder reach API and cause 500 errors. No validation gate.

**Example**:
- Builder generates truncated patch with literal `...`
- API receives patch, tries to apply
- `git apply` fails with "corrupt patch"
- API returns 500 Internal Server Error (misleading)

**Impact**: Poor error messages, no prevention, repeated failures

**Solution Required**:
1. Add `validate_patch(patch_content: str) -> ValidationResult` in API
2. Check patch syntax (starts with `diff --git`)
3. Check for truncation markers (regex for `...` at EOF or mid-line)
4. Return 422 Unprocessable Entity (not 500) with clear error
5. Executor can retry with enhanced prompt based on 422

---

### Gap #4: Stale Phase Reset Logic (CRITICAL)

**The Problem**: Phases stuck in `EXECUTING` block new runs. No automatic reset.

**Example**:
- Phase starts executing
- Crash occurs (Unicode error, network failure, etc.)
- Phase remains `EXECUTING` forever
- New runs can't pick it up
- Manual DB edit required

**Impact**: **BLOCKS AUTONOMOUS OPERATION**

**Solution Required**:
1. Add `stale_phase_detector()` in `autonomous_executor.py`
2. Before each iteration: Check for phases in `EXECUTING` with no activity for >N minutes
3. Automatically reset to `QUEUED` with note in journal
4. Add `last_heartbeat` timestamp to phase records for detection

---

## RECOMMENDED IMPLEMENTATION PLAN

### Phase 1: Critical Prevention Layer (Priority 1-2)

**Goal**: Stop errors from recurring by enforcing learned fixes

**Tasks**:
1. ✅ **Dynamic Prompt Injection** (Gap #1)
   - Create `journal_reader.py` module
   - Parse DEBUG_JOURNAL.md for prevention rules
   - Inject into Builder/Auditor system prompts
   - Test: Verify patch truncation rule is enforced

2. ✅ **Proactive Environment Setup** (Gap #2)
   - Add `startup_checks()` in autonomous_executor.py
   - Apply Windows Unicode fix proactively
   - Validate API keys before execution
   - Log all startup fixes to journal

3. ✅ **Stale Phase Reset Logic** (Gap #4)
   - Add stale phase detection (>10 min no activity)
   - Auto-reset `EXECUTING → QUEUED`
   - Log resets to journal with reason

**Verification**: Create new run, verify:
- ✓ Prevention rules from journal appear in LLM prompts
- ✓ Unicode fix applied before any errors
- ✓ Stale phases auto-reset

**Estimated Time**: 4-6 hours

---

### Phase 2: API Quality Gates (Priority 3-4)

**Goal**: Catch bad data at API boundary, provide clear errors

**Tasks**:
1. ✅ **Pre-Apply Patch Validation** (Gap #3)
   - Add patch validation in API endpoint
   - Check syntax, detect truncation markers
   - Return 422 (not 500) with validation details

2. ✅ **Decouple Error Codes** (ref5.md Part D, Phase B)
   - Audit all API endpoints for misleading 500s
   - Use 422 for validation failures
   - Use 400 for client errors
   - Use 500 only for true server errors

3. ✅ **Self-Correction Retry** (ref5.md Part D, Phase C)
   - Executor detects 422 response
   - Retrieves prevention rule from journal
   - Forces Builder retry with enhanced prompt
   - Logs retry attempt

**Verification**: Test with deliberately bad patch:
- ✓ API returns 422 with clear message
- ✓ Executor retries with enhanced prompt
- ✓ Second attempt succeeds

**Estimated Time**: 3-4 hours

---

### Phase 3: Autonomous Reliability (Priority 5-6)

**Goal**: Enable fully autonomous operation without manual intervention

**Tasks**:
1. ✅ **Automatic Crash Detection** (ref5.md Part A)
   - Detect runs with zero tokens + no progress
   - Auto-log to journal as "suspected crash"
   - Alert for investigation

2. ✅ **API Journal Integration** (ref5.md Part C.4.3)
   - When phase transitions to FAILED, log to journal
   - Include last error, phase context, recommendation

3. ✅ **Auditor Wrapper Review** (ref5.md Part D, Phase B)
   - Investigate DualAuditor 400 errors
   - Fix parameter passing and payload construction
   - Add validation tests

**Verification**: Run full 9-phase FileOrganizer test:
- ✓ All crashes logged automatically
- ✓ All FAILED phases logged to journal
- ✓ No 400 errors from DualAuditor

**Estimated Time**: 2-3 hours

---

### Phase 4: Optimization & Polish (Priority 7+)

**Goal**: Improve efficiency and reduce costs

**Tasks**:
1. ⬜ **Context Engineering** (ref5.md Part A.5)
   - Map phase types to file patterns (backend → `src/autopack/**`)
   - Filter context by phase type
   - Reduce token usage 40-60%

2. ⬜ **Token Budget Alerts** (ref5.md Part A.5)
   - Log warnings at 50%, 80%, 90% of budget
   - Prevent runaway token usage

3. ⬜ **CI/CD Integration** (ref5.md Part A.6)
   - Auto-branch for each run
   - Run tests after each phase
   - Auto-merge when all green

4. ⬜ **Run-Level Dashboard** (ref5.md Part A.7)
   - Web UI showing run progress
   - Phase states, errors, token usage
   - Real-time log streaming

**Verification**: Production readiness checklist

**Estimated Time**: 8-12 hours (deferred)

---

## SOURCE OF TRUTH STRATEGY

### Current Documentation Status

**Primary Sources** (KEEP UPDATED):
1. **IMPLEMENTATION_PLAN_REF5.md** (THIS FILE)
   - Overall strategy and priorities
   - Verification checklist
   - Task breakdown

2. **DEBUG_JOURNAL.md**
   - Runtime error tracking
   - Resolved issues and fixes
   - Prevention rules for LLM prompts

3. **WHATS_LEFT_TO_BUILD.md**
   - **STATUS: OUTDATED** ❌
   - Contains original 9 FileOrganizer tasks
   - Does NOT reflect new infrastructure tasks from ref5.md
   - **NEEDS REVISION** to separate:
     - Infrastructure fixes (this plan)
     - Feature development (original tasks)

**Legacy Sources** (REFERENCE ONLY):
- AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md (comprehensive but no longer updated)
- ref1.md, ref2.md, ref3.md, ref4.md (historical analysis)
- ref5.md (GPT analysis - implemented via this plan)

### Documentation Maintenance Protocol

**Rule**: Every new error discovery or fix MUST update:
1. **DEBUG_JOURNAL.md** (immediate - log error/fix)
2. **IMPLEMENTATION_PLAN_REF5.md** (weekly - update status)
3. **WHATS_LEFT_TO_BUILD.md** (when scope changes - revise tasks)

**Workflow**:
```
Error Occurs
  ↓
Log to DEBUG_JOURNAL.md (automatic via debug_journal.py)
  ↓
Investigation reveals missing infrastructure?
  ↓
Add task to IMPLEMENTATION_PLAN_REF5.md (manual)
  ↓
Major scope change to FileOrganizer tasks?
  ↓
Revise WHATS_LEFT_TO_BUILD.md (manual)
```

---

## WHATS_LEFT_TO_BUILD.md REVISION REQUIRED

### Current Issues

**Problem**: WHATS_LEFT_TO_BUILD.md lists 9 FileOrganizer feature tasks, but **infrastructure is not ready** for autonomous execution.

**Example**:
- Task: "Implement Canada Pack template"
- Blocker: Patch corruption bug (infrastructure issue)
- Result: Can't proceed with features until infrastructure fixed

### Recommended Structure Revision

**NEW: Split into two files**

1. **WHATS_LEFT_TO_BUILD_INFRASTRUCTURE.md** (this plan file)
   - All ref5.md tasks
   - Priority: CRITICAL (must complete first)
   - Prevents: "revised code doesn't register" problem

2. **WHATS_LEFT_TO_BUILD_FEATURES.md** (rename existing)
   - Original 9 FileOrganizer tasks
   - Priority: NORMAL (do after infrastructure stable)
   - Blocked by: Infrastructure tasks

**Dependency Chain**:
```
Infrastructure Ready (Phase 1-3 of this plan)
  ↓
  └─> Features Can Execute Autonomously (WHATS_LEFT_TO_BUILD_FEATURES.md)
```

---

## RUN STRATEGY: Resume vs. New Run?

### Analysis

**Option 1: Resume Existing Run** ❌ **NOT RECOMMENDED**

**Problems**:
- Phases defined at run creation time (immutable)
- Fixes require code deployment (doesn't update existing run)
- No "hot-reload" support
- Stale `EXECUTING` phases block progress

**Use Case**: Never use for testing infrastructure fixes

---

**Option 2: Create New Run** ✅ **RECOMMENDED**

**Benefits**:
- Fresh phase definitions
- Clean state (all phases `QUEUED`)
- Tests latest code
- Clear verification

**Protocol**:
1. Implement fix (e.g., dynamic prompt injection)
2. Create NEW run with descriptive ID: `fileorg-test-prompt-injection-2025-11-29`
3. Run with limited phases (1-2) for quick validation
4. Verify fix works
5. Log result to DEBUG_JOURNAL.md
6. Mark issue as RESOLVED if verified

**Efficiency**: Use `--max-iterations 1` for quick testing, then expand

---

**Option 3: Incremental Testing** ✅ **RECOMMENDED FOR PHASE 1-3**

**Strategy**: Create targeted micro-runs for each fix

**Example Workflow**:
```bash
# Fix #1: Dynamic Prompt Injection
python scripts/create_test_run.py --run-id test-prompt-injection --phases 1
python src/autopack/autonomous_executor.py --run-id test-prompt-injection --max-iterations 1

# Fix #2: Proactive Environment
python scripts/create_test_run.py --run-id test-env-checks --phases 1
python src/autopack/autonomous_executor.py --run-id test-env-checks --max-iterations 1

# Fix #3: Stale Phase Reset
python scripts/create_test_run.py --run-id test-phase-reset --phases 1
# (manually create EXECUTING phase, verify auto-reset)

# All Fixes Together: Comprehensive Test
python scripts/create_fileorg_run_v2.py  # All 9 phases
python src/autopack/autonomous_executor.py --run-id fileorg-phase2-final --max-iterations 10
```

**Rationale**: Fast iteration, clear cause-effect, easy debugging

---

**FINAL RECOMMENDATION**:

✅ **Use NEW RUNS for all infrastructure fix testing (Phase 1-3)**
✅ **Use incremental micro-runs for fast validation**
✅ **Use comprehensive run (9 phases) ONLY after Phase 1-3 complete**
❌ **NEVER reuse old runs for testing new fixes**

---

## SUCCESS CRITERIA

### Phase 1 Complete When:
- [ ] New run shows prevention rules in LLM prompts (verified in logs)
- [ ] No Unicode errors occur (proactive fix applied)
- [ ] Stale phases auto-reset without manual intervention
- [ ] Test run completes without infrastructure failures

### Phase 2 Complete When:
- [ ] Bad patch returns 422 (not 500) with clear message
- [ ] Executor successfully retries after 422 with enhanced prompt
- [ ] No 500 errors from API validation failures

### Phase 3 Complete When:
- [ ] Zero-token runs logged automatically as "suspected crash"
- [ ] All FAILED phases logged to DEBUG_JOURNAL.md automatically
- [ ] No 400 errors from DualAuditor

### Overall Success:
- [ ] FileOrganizer 9-phase run completes with 0 infrastructure failures
- [ ] All errors are NEW feature bugs, not recurring infrastructure bugs
- [ ] User confirms: "revised code registers and errors don't resurface"

---

## NEXT SESSION CHECKLIST

When starting work on this plan:

- [ ] Read this IMPLEMENTATION_PLAN_REF5.md file completely
- [ ] Read DEBUG_JOURNAL.md for latest open issues
- [ ] Pick highest-priority task from Phase 1 (or current phase)
- [ ] Implement fix
- [ ] Create NEW test run (don't reuse old runs)
- [ ] Verify fix works
- [ ] Update DEBUG_JOURNAL.md with results
- [ ] Update this plan's status checkboxes
- [ ] Commit changes with clear message

---

## REFERENCES

- **System Design**: [ref5.md](./ref5.md) - GPT analysis and recommendations
- **Error Tracking**: [DEBUG_JOURNAL.md](./DEBUG_JOURNAL.md) - Runtime error log
- **Legacy History**: [AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md](./AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md)
- **Code Modules**:
  - [debug_journal.py](../../src/autopack/debug_journal.py) - Logging implementation
  - [error_recovery.py](../../src/autopack/error_recovery.py) - Error classification
  - [autonomous_executor.py](../../src/autopack/autonomous_executor.py) - Orchestration
  - [anthropic_clients.py](../../src/autopack/anthropic_clients.py) - Builder/Auditor (Anthropic)
  - [openai_clients.py](../../src/autopack/openai_clients.py) - Builder/Auditor (OpenAI)

---

**Last Updated**: 2025-11-29
**Status**: DRAFT - Ready for Phase 1 implementation
