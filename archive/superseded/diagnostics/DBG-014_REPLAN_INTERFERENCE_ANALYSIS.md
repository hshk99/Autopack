# DBG-014: Doctor Re-Planning Interferes with Self-Correction

**Date**: 2025-12-18
**Severity**: HIGH
**Status**: 🔍 Investigating (Systemic Issue)
**Related**: BUILD-049, DBG-012, DBG-013

## Executive Summary

After successfully implementing deliverables validation and learning hints system (DBG-012, DBG-013), discovered that Doctor's re-planning feature interferes with autonomous self-correction, creating conflicting guidance and preventing reliable file path error correction.

**Key Finding**: Two autonomy systems (Doctor Re-Planning + Learning Hints) operate independently and create conflicts when both are active during deliverables validation failures.

## Problem Statement

**Observed Behavior**:
- Executor Attempt 8, Attempt 1: Builder creates file in CORRECT location (`src/autopack/research/evaluation/evaluator.py`) ✅
- Executor Attempt 8, Attempt 2: Builder reverts to WRONG location (`tracer_bullet/`) despite having same hints ❌

**Expected Behavior**:
- Learning hints should guide Builder to self-correct consistently across retry attempts
- Each retry should get closer to correct solution (monotonic improvement)

**Actual Behavior**:
- Non-deterministic results across attempts even with identical hints
- Regression after re-planning occurs
- Success followed by failure with no clear pattern

## Root Cause Analysis

### Architecture: Two Independent Autonomy Systems

#### 1. Learning Hints System (Stage 0A)
**Purpose**: Tactical feedback for retry self-correction
**Mechanism**:
```python
# In deliverables_validator.py
if not is_valid:
    self._record_learning_hint(
        phase=phase,
        hint_type="deliverables_validation_failed",
        details="Wrong: research/tracer_bullet/evaluator.py → Correct: src/autopack/research/evaluation/evaluator.py"
    )
```

**Assumption**: Attempts counter increments monotonically, hints accumulate

#### 2. Doctor Re-Planning System
**Purpose**: Strategic goal revision when repeated failures indicate fundamental misunderstanding
**Mechanism**:
```python
# In autonomous_executor.py:2652-2665
elif action == "replan":
    revised_phase = self._revise_phase_approach(
        phase,
        f"doctor_replan:{response.rationale[:50]}",
        error_history
    )
    if revised_phase:
        # PROBLEM: Resets attempts to 0
        self._run_replan_count += 1
```

**Side Effects**:
1. **Resets attempts counter to 0** (line 2664)
2. **Triggers model de-escalation** (Opus → Sonnet because attempt=0)
3. **Revises phase description** (may narrow/broaden scope)

### The Conflict

When deliverables validation fails:

**Learning Hints say**:
```
"Wrong: research/tracer_bullet/evaluator.py → Correct: src/autopack/research/evaluation/evaluator.py"
```
(Tactical: fix this specific path issue)

**Doctor Re-Plan says**:
```
"Build minimal pipeline with complete deliverable structure"
```
(Strategic: revise overall approach)

**Builder receives**:
- Revised phase description (from Doctor)
- Learning hints (from validation)
- Reset attempt counter = 0 (model de-escalation)

**Result**: Mixed signals, non-deterministic behavior

## Evidence

### Timeline: Executor Attempt 8

**04:20:39 - Attempt 1 Fails**:
```
[research-tracer-bullet] Builder succeeded (47287 tokens)
[research-tracer-bullet] Deliverables validation FAILED
FILES CREATED:
  • docs/research/TRACER_BULLET_LEARNINGS.md ✅
  • docs/research/TRACER_BULLET_RESULTS.md ✅
  • research/tracer_bullet/evaluator.py ❌
```

**04:21:27 - Doctor Triggers Re-Planning**:
```
[Re-Plan] Revising approach for research-tracer-bullet due to doctor_replan:Auditor rejected deliverables after 2 Builder atte (attempt 1)
[GoalAnchor] WARNING: Revision appears to narrow scope
[Re-Plan] Original: Tracer Bullet - Build minimal end-to-end pipeline to validate feasibility.
[Re-Plan] Revised: Build minimal pipeline with complete deliverable structure. Creat...
[research-tracer-bullet] Doctor triggered re-planning, resetting attempts to 0
```

**04:21:55 - Attempt 1 Post-Replan (with improved hints)**:
```
[research-tracer-bullet] Learning context: 0 rules, 5 hints
[ModelSelector] Selected claude-sonnet-4-5 (attempt=0, de-escalated from Opus)
FILES CREATED:
  • docs/research/TRACER_BULLET_LEARNINGS.md ✅
  • docs/research/TRACER_BULLET_RESULTS.md ✅
  • src/autopack/research/evaluation/evaluator.py ✅ CORRECT PATH!
```
**✅ SUCCESS**: Only 3 files but ONE is in CORRECT location - proves hints work!

**04:24:50 - Attempt 2 (Opus escalated)**:
```
[ModelSelector] Selected claude-opus-4-5 (attempt=1, escalated)
FILES CREATED (all wrong):
  • tracer_bullet/__init__.py ❌
  • tracer_bullet/calculators.py ❌
  • ... (6 files in root-level tracer_bullet/)
```
**❌ REGRESSION**: Back to wrong paths despite same hints

### Key Observations

1. **Proof of Concept Works**: Attempt 1 post-replan created file in CORRECT location
2. **Non-Determinism**: Same hints, escalated model → worse results
3. **Attempt Reset Impact**: De-escalation to Sonnet may reduce consistency
4. **Revised Goal Confusion**: "Build minimal pipeline" might contradict "create all deliverables"

## Impact Analysis

### Immediate Impact
- **Prevents reliable autonomous self-correction** for file path errors
- **Creates unpredictable behavior** even with correct technical fixes
- **Undermines BUILD-049 achievements** (DBG-012, DBG-013)

### Systemic Impact
- Highlights **coordination gap** between autonomy systems
- Questions when Doctor should intervene vs let tactical systems work
- Suggests need for **hierarchy of autonomy** (tactical before strategic)

## Proposed Solutions

### Option 1: Disable Re-Planning for Deliverables Validation Failures ⭐ **RECOMMENDED**

**Implementation**:
```python
# In autonomous_executor.py:2424 (_should_invoke_doctor)
def _should_invoke_doctor(self, phase_id: str, builder_attempts: int, error_category: str) -> bool:
    """Determine if Doctor should be invoked for this failure."""

    # NEW: Skip Doctor for deliverables validation failures
    # Let learning hints system handle tactical file path corrections
    if error_category == "DELIVERABLES_VALIDATION_FAILED":
        logger.info(
            f"[Doctor] Not invoking for deliverables validation failure - "
            f"deferring to learning hints system (attempts={builder_attempts})"
        )
        # Only invoke if hints have exhausted all retry attempts
        phase = self._get_phase_from_db(phase_id)  # Helper to fetch phase
        max_attempts = getattr(phase, 'max_attempts', 5)
        if builder_attempts >= max_attempts:
            logger.info(
                f"[Doctor] Max attempts reached ({builder_attempts}/{max_attempts}), "
                f"now invoking Doctor for deliverables failure"
            )
            # Allow Doctor as last resort
        else:
            return False  # Skip Doctor, let hints work

    is_infra = error_category == "infra_error"
    # ... rest of existing logic
```

**Rationale**:
- **Clean separation of concerns**: Deliverables validation = tactical error (hints), not strategic (Doctor)
- **Preserves learning hints efficacy**: No attempt resets, no conflicting guidance
- **Doctor as fallback**: Still available after all retry attempts exhausted
- **Minimal code changes**: Single check in existing method

**Pros**:
- ✅ Allows learning hints system to work unimpeded
- ✅ Maintains model escalation (Sonnet → Opus)
- ✅ Simple to implement and test
- ✅ Clear ownership: hints for tactical, Doctor for strategic

**Cons**:
- ❌ Doctor can't help if phase description itself is unclear about paths
- ❌ Requires max_attempts to be sensible (if too high, wastes tokens)

### Option 2: Coordinate Re-Planning with Learning Hints

**Implementation**:
```python
# In autonomous_executor.py:2657 (_handle_doctor_action, replan branch)
elif action == "replan":
    # Check if learning hints are active
    deliverables_hints = self._get_deliverables_hints_for_phase(phase_id)

    if deliverables_hints:
        # Incorporate hints into revised description
        hint_summary = "; ".join([h.hint_text for h in deliverables_hints[:2]])
        revised_phase = self._revise_phase_approach_with_hints(
            phase,
            f"doctor_replan:{response.rationale[:50]}",
            error_history,
            hint_context=hint_summary  # NEW parameter
        )
    else:
        revised_phase = self._revise_phase_approach(phase, ...)
```

**Pros**:
- ✅ Combines strategic and tactical guidance
- ✅ Doctor still available for strategic issues

**Cons**:
- ❌ More complex implementation
- ❌ May create overly long prompts
- ❌ Hints might be stale or contradictory to revision
- ❌ Still resets attempts counter (loses escalation)

### Option 3: Preserve Learning Context During Re-Planning

**Implementation**:
```python
# In autonomous_executor.py:2662 (_handle_doctor_action)
elif action == "replan":
    revised_phase = self._revise_phase_approach(
        phase,
        f"doctor_replan:{response.rationale[:50]}",
        error_history,
        preserve_attempts=True,  # NEW: Don't reset attempts
        preserve_hints=True       # NEW: Keep learning hints active
    )
```

**Pros**:
- ✅ Both systems work together
- ✅ Maintains model escalation
- ✅ Hints remain effective

**Cons**:
- ❌ Complex to implement correctly
- ❌ May create confusion: "replan" usually means "start fresh"
- ❌ Harder to reason about system state

### Option 4: Hierarchical Autonomy (Phased Intervention)

**Implementation**:
```python
# In autonomous_executor.py:2424 (_should_invoke_doctor)
def _should_invoke_doctor(self, phase_id: str, builder_attempts: int, error_category: str) -> bool:
    """Determine if Doctor should be invoked using hierarchical autonomy."""

    # Tier 1: Tactical corrections (learning hints)
    if error_category in ["DELIVERABLES_VALIDATION_FAILED", "PATCH_FORMAT_ERROR"]:
        # Only invoke Doctor after hints have tried (80% of max attempts)
        phase = self._get_phase_from_db(phase_id)
        max_attempts = getattr(phase, 'max_attempts', 5)
        threshold = int(max_attempts * 0.8)  # e.g., 4 out of 5

        if builder_attempts < threshold:
            logger.info(f"[Doctor] Tier 1 (tactical): Deferring to learning hints ({builder_attempts}/{threshold})")
            return False
        else:
            logger.info(f"[Doctor] Tier 1 exhausted, escalating to Tier 2 (strategic)")
            # Fall through to Doctor invocation

    # Tier 2: Strategic intervention (Doctor)
    # ... existing logic
```

**Pros**:
- ✅ Explicit hierarchy: tactical → strategic
- ✅ Configurable threshold (not all-or-nothing)
- ✅ Doctor still available when hints fail
- ✅ Generalizes to other tactical vs strategic errors

**Cons**:
- ❌ Requires defining "tactical" vs "strategic" error categories
- ❌ Magic number (0.8 threshold)

## Recommended Approach

**Option 1** (Disable re-planning for deliverables validation failures) with **Option 4** principles:

```python
# In autonomous_executor.py:2424
def _should_invoke_doctor(self, phase_id: str, builder_attempts: int, error_category: str) -> bool:
    """
    Determine if Doctor should be invoked for this failure.

    Uses hierarchical autonomy: tactical corrections first, strategic intervention as fallback.
    """

    # TACTICAL ERRORS: Let learning hints handle self-correction first
    TACTICAL_ERROR_CATEGORIES = [
        "DELIVERABLES_VALIDATION_FAILED",  # File path errors
        # Future: Add other tactical errors here
    ]

    if error_category in TACTICAL_ERROR_CATEGORIES:
        # Defer to learning hints system unless near max attempts
        phase = self._get_phase_from_db(phase_id)
        max_attempts = getattr(phase, 'max_attempts', 5)

        # Give hints 100% of attempts before Doctor intervenes
        if builder_attempts < max_attempts:
            logger.info(
                f"[Doctor] Tactical error ({error_category}) - "
                f"deferring to learning hints system (attempt {builder_attempts}/{max_attempts})"
            )
            return False
        else:
            logger.info(
                f"[Doctor] Learning hints exhausted ({max_attempts} attempts), "
                f"invoking Doctor as fallback for {error_category}"
            )
            # Fall through to invoke Doctor as last resort

    # STRATEGIC ERRORS: Invoke Doctor immediately (existing logic)
    is_infra = error_category == "infra_error"

    # ... rest of existing checks (min attempts, call limits, health budget)
```

**Rationale**:
1. **Minimal changes**: One conditional check in existing method
2. **Clear semantics**: Tactical errors → hints, strategic errors → Doctor
3. **Safety net**: Doctor still invoked if hints fail after all attempts
4. **Extensible**: Easy to add more tactical error categories
5. **No attempt resets**: Hints system works as designed

## Implementation Plan

### Phase 1: Implement Fix (30 min)
1. Add TACTICAL_ERROR_CATEGORIES constant to autonomous_executor.py
2. Modify `_should_invoke_doctor()` with hierarchical logic
3. Add helper `_get_phase_from_db()` if not exists
4. Add logging for tactical vs strategic decision path

### Phase 2: Testing (1 hour)
1. Reset research-tracer-bullet phase to QUEUED
2. Start executor with deliverables validation failure scenario
3. Verify Doctor NOT invoked on attempts 1-4
4. Verify learning hints guide self-correction
5. Verify Doctor invoked as fallback on attempt 5 if still failing

### Phase 3: Documentation (15 min)
1. Update BUILD-049_DELIVERABLES_VALIDATION.md with resolution
2. Update DEBUG_LOG.md DBG-014 status to "✅ Resolved"
3. Add architectural note about hierarchical autonomy

## Success Criteria

1. ✅ Builder creates files in correct locations consistently across retry attempts
2. ✅ No Doctor re-planning during deliverables validation failures (attempts 1-4)
3. ✅ Model escalation preserved (Sonnet → Opus) across attempts
4. ✅ Learning hints remain effective without conflicting guidance
5. ✅ Doctor still available as fallback after max attempts

## Open Questions

1. **Should we apply this pattern to other error types?**
   - Example: PATCH_FORMAT_ERROR might also be tactical
   - Need to catalog error categories as tactical vs strategic

2. **What's the right threshold?**
   - Currently: 100% of max_attempts
   - Could be configurable: 80%, 90%, 100%

3. **Should re-planning preserve some context when it does run?**
   - Even as fallback, should Doctor see learning hints?

## References

- [BUILD-049_DELIVERABLES_VALIDATION.md](BUILD-049_DELIVERABLES_VALIDATION.md) - Parent feature
- [DEBUG_LOG.md](DEBUG_LOG.md#dbg-014) - DBG-014 entry
- autonomous_executor.py:2424 - `_should_invoke_doctor()` method
- autonomous_executor.py:2652 - Doctor re-planning logic
- learned_rules.py:166 - `get_relevant_hints_for_phase()` (DBG-012 fix)
