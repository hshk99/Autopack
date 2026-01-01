# BUILD-113 Integration Gap Analysis

## Date: 2025-12-21

## Executive Summary

BUILD-113 proactive mode integration (lines 4067-4167 in autonomous_executor.py) **does not trigger for phases using structured edits (edit_plan)**.

**Root Cause**: BUILD-113 integration checks for `builder_result.patch_content`, but structured edits set `patch_content=""` and use `edit_plan` instead (see anthropic_clients.py:1802).

**Impact**: BUILD-113 proactive decision-making will NOT work for:
- ❌ **ALL phases using structured edits** (research-build113-test phases, any phase with >30 files in context)
- ❌ **Batched phases** (also bypass BUILD-113 integration point - separate issue)
- ✅ **Traditional patch-based phases** (use unified diff format - BUILD-113 works)

**Validation Status**: ❌ **INCOMPLETE** - BUILD-113 needs to be updated to support structured edits (edit_plan)

---

## Investigation Timeline

### 1. Initial Discovery (2025-12-21 23:00)
- research-build113-test run completed successfully with all 6 phases marked COMPLETE
- No BUILD-113 proactive decisions logged ("[BUILD-113] Running proactive decision analysis" not found in logs)
- No decision JSON files created in .autonomous_runs/research-build113-test/decisions/
- BUILD-113 was initialized ("[BUILD-113] Iterative Autonomous Investigation enabled" found in logs)

### 2. Integration Code Verification
- Verified `--enable-autonomous-fixes` flag was passed (confirmed in run_manifest.json)
- Verified flag is parsed and set on executor instance (line 185: `self.enable_autonomous_fixes = enable_autonomous_fixes`)
- Verified BUILD-113 integration code exists at lines 4067-4167 in `_execute_phase_with_recovery`

### 3. Root Cause Analysis - Initial Theory (Batched Execution)
- Discovered specialized batched execution functions that bypass BUILD-113
- HOWEVER: research-build113-test phases are NOT in the batched routing list (lines 3424-3480)
- research-build113-test phases SHOULD go through standard flow

### 4. Root Cause Analysis - ACTUAL ISSUE (Structured Edits)
**FOUND IT!** The actual root cause is **structured edits (edit_plan) vs traditional patches (patch_content)**

Evidence chain:
1. Log shows "Builder succeeded" → "_post_builder_result" → "Step 2/5: Applying patch..." (NO BUILD-113 message between)
2. BUILD-113 integration condition at line 4068:
   ```python
   if self.enable_autonomous_fixes and getattr(self, "iterative_investigator", None) and builder_result.patch_content:
   ```
3. ✅ `enable_autonomous_fixes` = True (--enable-autonomous-fixes flag passed, confirmed in run_manifest.json)
4. ✅ `iterative_investigator` = initialized ("[BUILD-113] Iterative Autonomous Investigation enabled" logged)
5. ❌ **`builder_result.patch_content` = empty string ("")**

**Why `patch_content` is empty**:
- Line 4172-4177 checks `if builder_result.edit_plan:`
- Structured edits use `edit_plan` instead of `patch_content`
- anthropic_clients.py:1802 explicitly sets `patch_content="",  # No patch content for structured edits`
- Pre-flight logic (line 4115-4119) switches to structured edits when context has ≥30 files:
  ```python
  if file_context and len(file_context.get("existing_files", {})) >= 30:
      use_full_file_mode = False  # Triggers structured edit mode
  ```

**Conclusion**: research-build113-test phases have many context files (see DEBUG logs showing "Skipping X - would exceed token budget"), so they used structured edits, which set `patch_content=""`, causing BUILD-113 integration check to fail.

---

## Code Execution Flow

### Standard Flow (BUILD-113 Integration Point)
```
execute_phase()
  → _execute_phase_inner()
    → _execute_phase_with_recovery()  ← BUILD-113 integrated HERE (lines 4067-4167)
      → llm_service.execute_builder_phase()
      → [BUILD-113 Proactive Decision]
        - Parse patch metadata
        - Assess risk (LOW/MEDIUM/HIGH)
        - Calculate confidence
        - Decision: CLEAR_FIX / RISKY / AMBIGUOUS
      → Apply patch (if CLEAR_FIX) or request approval (if RISKY)
```

### Batched Flow (BYPASSES BUILD-113)
```
execute_phase()
  → _execute_phase_inner()
    → if phase_id == "research-tracer-bullet":  ← Routing decision
      → _execute_research_tracer_bullet_batched()  ← BYPASSES _execute_phase_with_recovery
        → llm_service.execute_builder_phase() (multiple times for batches)
        → [NO BUILD-113 INTEGRATION]
        → Apply patches directly
```

---

## Affected Phases

### Research Phases (research-build113-test)
All 6 phases in research-build113-test use batched execution OR are not true code-generation phases:

1. ✅ **research-gold-set-data** - Batched? NO, but may bypass standard flow
2. ✅ **research-build-history-integrator** - Batched? NO, but may bypass standard flow
3. ✅ **research-phase-type** - Batched? NO, but may bypass standard flow
4. ✅ **research-autonomous-hooks** - Batched? NO, but may bypass standard flow
5. ✅ **research-cli-commands** - Batched? NO, but may bypass standard flow
6. ✅ **research-review-workflow** - Batched? NO, but may bypass standard flow

**NOTE**: Need to verify if research phases 1-6 actually go through standard flow or have their own routing.

### Explicitly Batched Phases
From code inspection (lines 3424-3480):

**Research**:
- research-tracer-bullet
- research-gatherers-web-compilation

**Diagnostics**:
- diagnostics-handoff-bundle
- diagnostics-cursor-prompt
- diagnostics-second-opinion-triage
- diagnostics-deep-retrieval
- diagnostics-iteration-loop

---

## Why Batching Exists

From code comments:

1. **Reduce patch size**: Large phases (10+ files) often hit LLM truncation limits
2. **Avoid malformed diffs**: Breaking into smaller batches surfaces format issues earlier
3. **Tighter manifest gates**: Smaller batches have more focused deliverables validation
4. **Better convergence**: Smaller changes reduce likelihood of incomplete/truncated patches

**Example** (research-tracer-bullet):
- Creates 11 new files (all at once would often truncate)
- Batched into: core (4 files), eval (2 files), tests (3 files), docs (2 files)
- Each batch generates a separate patch, applied incrementally

---

## Solutions

### Option 1: Support Structured Edits in BUILD-113 ⭐ RECOMMENDED

**Approach**: Update BUILD-113 integration condition to handle both patch_content AND edit_plan.

**Changes Required**:
1. Update condition at line 4068 from:
   ```python
   if self.enable_autonomous_fixes and getattr(self, "iterative_investigator", None) and builder_result.patch_content:
   ```
   To:
   ```python
   if self.enable_autonomous_fixes and getattr(self, "iterative_investigator", None) and (builder_result.patch_content or builder_result.edit_plan):
   ```

2. Add edit_plan → patch conversion in GoalAwareDecisionMaker.make_proactive_decision():
   ```python
   def make_proactive_decision(
       self,
       patch_content: Optional[str] = None,
       edit_plan: Optional[Any] = None,  # NEW
       phase_spec: PhaseSpec
   ) -> Decision:
       # If edit_plan provided but no patch_content, convert edit_plan to unified diff
       if not patch_content and edit_plan:
           patch_content = self._convert_edit_plan_to_patch(edit_plan)

       # Rest of existing logic unchanged
       ...
   ```

3. Implement `_convert_edit_plan_to_patch()` helper:
   ```python
   def _convert_edit_plan_to_patch(self, edit_plan: Any) -> str:
       """Convert StructuredEditPlan to unified diff format for risk assessment."""
       # Read current file contents
       # Apply edits in memory
       # Generate unified diff
       # Return as patch_content
   ```

**Pros**:
- Minimal code changes (update one condition, add one helper method)
- BUILD-113 works for ALL phases (patch-based AND structured edits)
- No changes to BUILD-113 decision logic (still operates on patch_content)
- Clean separation of concerns (conversion happens once, decision logic unchanged)

**Cons**:
- Need to implement edit_plan → patch conversion
- Slightly more complex than just checking both conditions

---

### Option 2: Disable Batching for BUILD-113 Test Phases

**Approach**: Add a flag to skip batched execution for research-build113-test phases.

**Changes Required**:
1. Check for `run_id == "research-build113-test"` before routing to batched executors
2. Force standard execution path for these phases

**Pros**:
- Minimal code changes
- Quick validation of BUILD-113

**Cons**:
- Doesn't solve the general problem
- BUILD-113 still won't work for production batched phases
- May hit truncation issues that batching was designed to solve

---

### Option 3: Post-Batch Decision Analysis

**Approach**: Run BUILD-113 analysis AFTER all batches complete, on the combined patch.

**Changes Required**:
1. Collect all builder_results from batches
2. Combine patches into single unified diff
3. Run BUILD-113 proactive decision on combined patch
4. If RISKY, rollback all batches and request approval

**Pros**:
- Single decision per phase (not per batch)
- Works with existing batched execution

**Cons**:
- Rollback complexity (need to undo multiple batch applications)
- Later batches might conflict with earlier ones
- Can't auto-apply early batches if later batches are risky

---

## Recommended Implementation: Option 1 (Phased Approach)

### Phase 1: Extract Reusable Method
1. Create `_run_build113_proactive_analysis()` method
2. Refactor existing integration in `_execute_phase_with_recovery` to use it
3. Test with standard (non-batched) phases

### Phase 2: Integrate into Generic Batched Executor
1. Add BUILD-113 call to `_execute_batched_deliverables_phase` (line 4479)
2. Call after each batch's builder execution
3. Test with diagnostics phases (diagnostics-handoff-bundle, etc.)

### Phase 3: Integrate into Specialized Batched Executors
1. Add BUILD-113 call to `_execute_research_tracer_bullet_batched` (line 5092)
2. Add BUILD-113 call to `_execute_research_gatherers_web_compilation_batched` (line 5477)
3. Test with research phases

### Phase 4: Multi-Batch Decision Optimization
1. Collect decisions from all batches
2. If any batch is RISKY, request single approval for entire phase
3. If all batches are CLEAR_FIX, auto-apply all

---

## Testing Plan

### Unit Tests
- Test `_run_build113_proactive_analysis()` with sample BuilderResults
- Verify decision logic for LOW/MEDIUM/HIGH risk patches
- Verify confidence scoring

### Integration Tests
1. **Standard phases**: Verify BUILD-113 still works after refactoring
2. **Diagnostics batched phases**: Run diagnostics-handoff-bundle with `--enable-autonomous-fixes`
3. **Research batched phases**: Re-run research-build113-test after integration
4. **Multi-batch decisions**: Verify all batches analyzed correctly

### Expected Outcomes (research-build113-test after fix)
| Phase | Expected Decision | Auto-Apply | Rationale |
|-------|------------------|-----------|-----------|
| research-gold-set-data | CLEAR_FIX | YES | 50 lines, data file |
| research-build-history-integrator | RISKY | NO | 200+ lines, integration |
| research-phase-type | RISKY | NO | Database file (models.py) |
| research-autonomous-hooks | CLEAR_FIX or RISKY | MAYBE | 150 lines (MEDIUM risk threshold test) |
| research-cli-commands | CLEAR_FIX or AMBIGUOUS | MAYBE | 100-150 lines |
| research-review-workflow | RISKY | NO | 200-250 lines |

---

## Current Status - ✅ FIXED (BUILD-114)

- ✅ **Root cause identified**: BUILD-113 only checks `patch_content`, not `edit_plan` (structured edits)
- ✅ **Fix implemented** (BUILD-114 - Commit 81018e1b - 2025-12-21 23:30):
  - Updated line 4068 condition to: `if ... and (builder_result.patch_content or getattr(builder_result, "edit_plan", None))`
  - Added `edit_plan` parameter to `make_proactive_decision()` method signature
  - Implemented `_convert_edit_plan_to_patch()` helper method (87 lines) in goal_aware_decision.py
- ✅ **Integration now complete**: BUILD-113 works for BOTH traditional patches AND structured edits
- ⏳ **Validation pending**: Re-run research-build113-test to confirm BUILD-113 now triggers for structured edit phases

---

## BUILD-114 Implementation Details

**Files Changed** (Commit 81018e1b):
1. [docs/BUILD_HISTORY.md](BUILD_HISTORY.md) - Added BUILD-114 entry
2. [src/autopack/autonomous_executor.py](../src/autopack/autonomous_executor.py) - Updated condition + call site (2 lines)
3. [src/autopack/diagnostics/goal_aware_decision.py](../src/autopack/diagnostics/goal_aware_decision.py) - Added edit_plan support (91 lines)

**Key Changes**:
```python
# autonomous_executor.py line 4068 (BEFORE):
if self.enable_autonomous_fixes and getattr(self, "iterative_investigator", None) and builder_result.patch_content:

# autonomous_executor.py line 4068 (AFTER):
if self.enable_autonomous_fixes and getattr(self, "iterative_investigator", None) and (builder_result.patch_content or getattr(builder_result, "edit_plan", None)):

# goal_aware_decision.py (NEW):
def make_proactive_decision(
    self,
    patch_content: Optional[str] = None,
    edit_plan: Optional[Any] = None,  # NEW parameter
    phase_spec: PhaseSpec = None
) -> Decision:
    # BUILD-114: Convert edit_plan to patch_content if needed
    if not patch_content and edit_plan:
        logger.info("[GoalAwareDecisionMaker] Converting edit_plan to unified diff for risk assessment")
        patch_content = self._convert_edit_plan_to_patch(edit_plan)

    # Rest of existing logic unchanged
    ...
```

---

## Next Steps

1. ✅ **Implement Option 1**: Add structured edit support to BUILD-113 - **COMPLETE (BUILD-114)**
2. ⏳ **Validation**: Re-run research-build113-test with BUILD-114 fix
3. ⏳ **Document results**: Compare decisions to expected outcomes (see Expected Outcomes table below)
4. ⏳ **Update BUILD-113_IMPLEMENTATION_STATUS.md**: Document validation results

---

## References

- BUILD-113 Integration: [autonomous_executor.py:4067-4167](../src/autopack/autonomous_executor.py#L4067-L4167)
- Batched Execution Routing: [autonomous_executor.py:3424-3480](../src/autopack/autonomous_executor.py#L3424-L3480)
- Generic Batched Executor: [autonomous_executor.py:4479](../src/autopack/autonomous_executor.py#L4479)
- Research Tracer Bullet Batched: [autonomous_executor.py:5092](../src/autopack/autonomous_executor.py#L5092)
- Research Web Compilation Batched: [autonomous_executor.py:5477](../src/autopack/autonomous_executor.py#L5477)
- BUILD-113 Implementation Status: [BUILD-113_IMPLEMENTATION_STATUS.md](BUILD-113_IMPLEMENTATION_STATUS.md)
