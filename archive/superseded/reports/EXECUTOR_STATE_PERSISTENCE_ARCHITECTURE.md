# Autopack Executor State Persistence Architecture

**Status**: Proposal
**Date**: 2025-12-17
**Problem**: Failure loop caused by split state management between instance attributes and database
**Solution**: Database-backed state persistence for phase execution attempts

---

## Problem Statement

### Observed Failure Pattern

During FileOrganizer Phase 2 autonomous run, the executor entered an infinite failure loop:

```
[2025-12-17 01:45:46] INFO: [fileorg-p2-test-fixes] Attempt 1/5 (model escalation enabled)
[2025-12-17 01:46:27] ERROR: LLM output invalid format (stop_reason=max_tokens)

[2025-12-17 01:47:52] INFO: [fileorg-p2-test-fixes] Attempt 2/5 (model escalation enabled)
[2025-12-17 01:49:10] ERROR: LLM output invalid format (stop_reason=max_tokens)

[2025-12-17 01:50:18] INFO: Iteration 2: Fetching run status...
[2025-12-17 01:50:20] INFO: [fileorg-p2-test-fixes] Attempt 2/5 (model escalation enabled)  ⚠️ REPEATED!
```

**Pattern**: After Attempt 2 failed, executor entered Iteration 2 but **reset to "Attempt 2/5"** instead of progressing to Attempt 3/5.

### Root Cause Analysis

The issue stems from **architectural design conflict between two state machines**:

#### 1. execute_phase() Retry Loop ([autonomous_executor.py:998-1256](file:///c:/dev/Autopack/src/autopack/autonomous_executor.py#L998-L1256))

```python
def execute_phase(self, phase: Dict) -> Tuple[bool, str]:
    # Track attempt index as INSTANCE ATTRIBUTE
    attempt_key = f"_attempt_index_{phase_id}"
    attempt_index = getattr(self, attempt_key, 0)

    # Retry loop with model escalation
    while attempt_index < max_attempts:
        logger.info(f"[{phase_id}] Attempt {attempt_index + 1}/{max_attempts}")

        success, status = self._execute_phase_with_recovery(...)

        if success:
            return success, status  # EXIT ON SUCCESS ✓

        # ⚠️ EARLY RETURN: Doctor can cut retries short
        if doctor_response and not should_continue:
            return False, status  # RETURNS WITHOUT EXHAUSTING RETRIES!

        # Increment and continue
        attempt_index += 1
        setattr(self, attempt_key, attempt_index)
        continue

    # All attempts exhausted
    return False, "FAILED"
```

**Problem**: Method can return `False` **BEFORE exhausting max_attempts** due to:
- Doctor actions (lines 1114-1124)
- Health budget limits
- Re-planning logic (lines 1143-1150)

#### 2. run_autonomous_loop() Main Loop ([autonomous_executor.py:4456-4649](file:///c:/dev/Autopack/src/autopack/autonomous_executor.py#L4456-L4649))

```python
def run_autonomous_loop(self, ...):
    while True:
        # Get next QUEUED phase from database
        next_phase = self.get_next_queued_phase(run_data)

        if not next_phase:
            break

        # Execute phase
        success, status = self.execute_phase(next_phase)

        if not success:
            # ⚠️ PROBLEM: Main loop doesn't know if retries were exhausted!
            # Phase might still be QUEUED in database
            # Next iteration will pick it up again
            phases_failed += 1

        time.sleep(poll_interval)
```

**Problem**: Main loop can't distinguish between:
1. Phase exhausted max_attempts (should be FAILED in DB)
2. Phase hit early return (should continue retrying)

### Why the Infinite Loop Occurs

**Iteration 1:**
1. execute_phase() runs Attempt 1, Attempt 2 (both fail)
2. Doctor action causes early return: `return False, "PATCH_FAILED"`
3. Instance attribute stores: `_attempt_index_fileorg-p2-test-fixes = 2`
4. **Phase state in database: STILL QUEUED** (not marked FAILED)

**Iteration 2:**
1. Main loop fetches phases from database
2. get_next_queued_phase() finds `fileorg-p2-test-fixes` (still QUEUED)
3. execute_phase() called again
4. Retrieves `attempt_index = getattr(self, attempt_key, 0)` → gets 2
5. Loop continues from attempt_index=2 (logs "Attempt 3/5")
6. **BUT**: Same failure occurs, Doctor causes early return again
7. **Loop repeats**: Phase never exhausts attempts, never marked FAILED

---

## Architectural Solution

### Design Principles

1. **Single Source of Truth**: Database stores authoritative phase state
2. **Transactional State Updates**: Every attempt updates database atomically
3. **Idempotent Execution**: If process crashes/restarts, can resume from DB
4. **Observable State**: Can query database for exact attempt counts
5. **No State Leakage**: Critical state never stored in instance attributes

### Solution: Database-Backed State Persistence

Move attempt tracking from instance attributes to database schema.

---

## Implementation Plan

### Phase 1: Extend Database Schema

**File**: `src/autopack/models.py`

Add fields to `Phase` model:

```python
class Phase(Base):
    __tablename__ = "phases"

    # ... existing fields ...

    # New fields for attempt tracking
    attempts_used = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)
    last_attempt_timestamp = Column(DateTime(timezone=True), nullable=True)
    last_failure_reason = Column(String, nullable=True)

    # Index for efficient querying
    __table_args__ = (
        Index('idx_phase_executable', 'run_id', 'state', 'attempts_used'),
    )
```

**Migration Script**: `scripts/migrations/add_phase_attempts.py`

```python
def upgrade():
    """Add attempt tracking columns to phases table."""
    op.add_column('phases', sa.Column('attempts_used', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('phases', sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('phases', sa.Column('last_attempt_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.add_column('phases', sa.Column('last_failure_reason', sa.String(), nullable=True))

    op.create_index('idx_phase_executable', 'phases', ['run_id', 'state', 'attempts_used'])
```

---

### Phase 2: Refactor execute_phase() to Use Database State

**File**: `src/autopack/autonomous_executor.py`

**Key Changes:**
1. Remove instance attribute state management
2. Load attempt count from database
3. Execute **single attempt** per call (not a loop)
4. Update database atomically after each attempt

```python
def execute_phase(self, phase: Dict) -> Tuple[bool, str]:
    """Execute a single attempt of a phase, using database for state persistence.

    This method is called by the main loop for each attempt. It executes ONE attempt,
    updates the database, and returns. The main loop decides whether to retry.

    Args:
        phase: Phase specification dict from API

    Returns:
        (success: bool, status: str)
    """
    phase_id = phase.get("phase_id")

    # 1. Load current state from DATABASE (Single Source of Truth)
    db_phase = self._get_phase_from_db(phase_id)

    if not db_phase:
        logger.error(f"[{phase_id}] Phase not found in database")
        return False, "NOT_FOUND"

    attempt_index = db_phase.attempts_used
    max_attempts = db_phase.max_attempts

    # 2. Check if already exhausted
    if attempt_index >= max_attempts:
        logger.error(f"[{phase_id}] Already exhausted {max_attempts} attempts (DB state)")
        self._mark_phase_failed_in_db(phase_id, reason="MAX_ATTEMPTS_EXHAUSTED")
        return False, "FAILED"

    # 3. Mark phase as EXECUTING (if QUEUED)
    if db_phase.state == "QUEUED":
        self._update_phase_state_in_db(phase_id, "EXECUTING")

    # 4. Execute SINGLE attempt
    logger.info(f"[{phase_id}] Attempt {attempt_index + 1}/{max_attempts} (model escalation enabled)")

    try:
        success, status = self._execute_single_attempt(
            phase=phase,
            attempt_index=attempt_index
        )

        # 5. Update database atomically
        if success:
            # SUCCESS: Mark phase as COMPLETE
            self._mark_phase_complete_in_db(phase_id)
            logger.info(f"[{phase_id}] Completed successfully on attempt {attempt_index + 1}")
            return True, "COMPLETE"
        else:
            # FAILURE: Increment attempt counter
            new_attempt_count = attempt_index + 1

            self._update_phase_attempts_in_db(
                phase_id=phase_id,
                attempts_used=new_attempt_count,
                last_failure_reason=status,
                last_attempt_timestamp=datetime.now(timezone.utc)
            )

            # Check if exhausted max attempts
            if new_attempt_count >= max_attempts:
                logger.error(f"[{phase_id}] Exhausted {max_attempts} attempts. Marking as FAILED.")
                self._mark_phase_failed_in_db(phase_id, reason=status)
                return False, "FAILED"
            else:
                # More attempts available - keep phase as EXECUTING
                logger.warning(f"[{phase_id}] Attempt {new_attempt_count} failed: {status}. Will retry with model escalation.")
                return False, status

    except Exception as e:
        logger.error(f"[{phase_id}] Exception during attempt {attempt_index + 1}: {e}")

        # Update database with exception
        new_attempt_count = attempt_index + 1
        self._update_phase_attempts_in_db(
            phase_id=phase_id,
            attempts_used=new_attempt_count,
            last_failure_reason=f"EXCEPTION: {str(e)[:200]}",
            last_attempt_timestamp=datetime.now(timezone.utc)
        )

        if new_attempt_count >= max_attempts:
            self._mark_phase_failed_in_db(phase_id, reason="MAX_ATTEMPTS_WITH_EXCEPTIONS")
            return False, "FAILED"
        else:
            return False, f"EXCEPTION: {type(e).__name__}"


def _execute_single_attempt(
    self,
    phase: Dict,
    attempt_index: int
) -> Tuple[bool, str]:
    """Execute a single build/audit/gate cycle for a phase.

    This is the core execution logic, extracted from the old retry loop.

    Args:
        phase: Phase specification dict
        attempt_index: Current attempt number (0-indexed)

    Returns:
        (success: bool, status: str)
    """
    phase_id = phase.get("phase_id")

    # Initialize goal anchoring (if first attempt)
    if attempt_index == 0:
        self._initialize_phase_goal_anchor(phase)

    # Reload project rules mid-run if updated
    self._refresh_project_rules_if_updated()

    # Execute Builder → Auditor → QualityGate pipeline
    # (Existing _execute_phase_with_recovery logic goes here)
    return self._execute_phase_with_recovery(
        phase=phase,
        attempt_index=attempt_index,
        allowed_paths=self._get_allowed_scope_paths(phase)
    )


# Database helper methods
def _get_phase_from_db(self, phase_id: str):
    """Fetch phase from database by phase_id."""
    db = next(get_db())
    return db.query(Phase).filter(Phase.phase_id == phase_id).first()


def _update_phase_attempts_in_db(
    self,
    phase_id: str,
    attempts_used: int,
    last_failure_reason: str,
    last_attempt_timestamp: datetime
):
    """Update phase attempt tracking in database."""
    db = next(get_db())
    phase = db.query(Phase).filter(Phase.phase_id == phase_id).first()

    if phase:
        phase.attempts_used = attempts_used
        phase.last_failure_reason = last_failure_reason
        phase.last_attempt_timestamp = last_attempt_timestamp
        db.commit()

        logger.debug(f"[{phase_id}] Updated DB: attempts_used={attempts_used}")


def _mark_phase_complete_in_db(self, phase_id: str):
    """Mark phase as COMPLETE in database."""
    db = next(get_db())
    phase = db.query(Phase).filter(Phase.phase_id == phase_id).first()

    if phase:
        phase.state = "COMPLETE"
        phase.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"[{phase_id}] Marked COMPLETE in database")


def _mark_phase_failed_in_db(self, phase_id: str, reason: str):
    """Mark phase as FAILED in database."""
    db = next(get_db())
    phase = db.query(Phase).filter(Phase.phase_id == phase_id).first()

    if phase:
        phase.state = "FAILED"
        phase.last_failure_reason = reason
        phase.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.error(f"[{phase_id}] Marked FAILED in database: {reason}")
```

---

### Phase 3: Simplify Main Loop

**File**: `src/autopack/autonomous_executor.py`

**Key Changes:**
1. Remove failure tracking logic (now in database)
2. Trust database state for phase selection
3. Simplify retry logic

```python
def run_autonomous_loop(
    self,
    poll_interval: int = 10,
    max_iterations: Optional[int] = None,
    stop_on_first_failure: bool = False
):
    """Main autonomous execution loop.

    Polls database for executable phases (QUEUED or EXECUTING with attempts < max),
    executes one attempt per iteration, and trusts database for state management.
    """
    logger.info("Starting autonomous execution loop...")

    # Initialize infrastructure
    self._init_infrastructure()

    iteration = 0
    phases_completed = 0
    phases_failed = 0

    while True:
        # Check iteration limit
        if max_iterations and iteration >= max_iterations:
            logger.info(f"Reached max iterations ({max_iterations}), stopping")
            break

        iteration += 1
        logger.info(f"Iteration {iteration}: Fetching executable phases...")

        # Fetch run status
        try:
            run_data = self.get_run_status()
        except Exception as e:
            logger.error(f"Failed to fetch run status: {e}")
            time.sleep(poll_interval)
            continue

        # Get next executable phase from database
        # (QUEUED or EXECUTING with attempts_used < max_attempts)
        next_phase = self.get_next_executable_phase(run_data)

        if not next_phase:
            logger.info("No more executable phases, run complete")
            break

        phase_id = next_phase.get("phase_id")
        logger.info(f"Next phase: {phase_id}")

        # Execute ONE attempt
        # Database state is updated atomically by execute_phase()
        success, status = self.execute_phase(next_phase)

        if success:
            logger.info(f"Phase {phase_id} completed successfully")
            phases_completed += 1
        elif status == "FAILED":
            # Phase exhausted max attempts
            logger.error(f"Phase {phase_id} failed after max attempts")
            phases_failed += 1

            if stop_on_first_failure:
                logger.critical(f"[STOP_ON_FAILURE] Stopping execution")
                break
        else:
            # Attempt failed but more retries available
            logger.warning(f"Phase {phase_id} attempt failed: {status}. Will retry next iteration.")

        # Wait before next iteration
        time.sleep(poll_interval)

    logger.info(f"Autonomous execution loop finished. Completed: {phases_completed}, Failed: {phases_failed}")


def get_next_executable_phase(self, run_data: Dict) -> Optional[Dict]:
    """Find next executable phase (QUEUED or EXECUTING with remaining attempts).

    Args:
        run_data: Run data from API

    Returns:
        Phase dict if found, None otherwise
    """
    phases = run_data.get("phases", [])
    tiers = run_data.get("tiers", [])

    # Sort by tier_index and phase_index
    sorted_phases = sorted(phases, key=lambda p: (
        self._get_tier_index(p.get("tier_id"), tiers),
        p.get("phase_index", 0)
    ))

    for phase in sorted_phases:
        state = phase.get("state")
        attempts_used = phase.get("attempts_used", 0)
        max_attempts = phase.get("max_attempts", 5)

        # Phase is executable if:
        # 1. State is QUEUED (not yet started), OR
        # 2. State is EXECUTING and hasn't exhausted attempts
        if state == "QUEUED" or (state == "EXECUTING" and attempts_used < max_attempts):
            return phase

    return None
```

---

## Benefits

### 1. Process Restart Safety
If executor crashes, can resume from database state. No lost progress.

**Example:**
```
Iteration 42: Phase fileorg-p2-auth at Attempt 3/5
[CRASH - executor killed]
[RESTART]
Iteration 1: Fetch phases from DB
Found phase fileorg-p2-auth (EXECUTING, attempts_used=3)
Continue with Attempt 4/5  ✓
```

### 2. No State Leakage
Critical state never stored in instance attributes. Database is single source of truth.

**Before (broken):**
- Attempt counter: Instance attribute `_attempt_index_{phase_id}`
- Phase state: Database `phases.state`
- **CONFLICT**: Two sources of truth

**After (fixed):**
- Attempt counter: Database `phases.attempts_used`
- Phase state: Database `phases.state`
- **UNIFIED**: One source of truth

### 3. Observable State
Can query database to see exact state of all phases.

**Query:**
```sql
SELECT phase_id, state, attempts_used, max_attempts, last_failure_reason
FROM phases
WHERE run_id = 'fileorg-phase2-beta-release'
ORDER BY tier_id, phase_index;
```

**Output:**
```
phase_id                    | state      | attempts_used | max_attempts | last_failure_reason
----------------------------|------------|---------------|--------------|--------------------
fileorg-p2-test-fixes      | EXECUTING  | 2             | 5            | PATCH_FAILED
fileorg-p2-frontend-build  | QUEUED     | 0             | 5            | NULL
fileorg-p2-docker          | QUEUED     | 0             | 5            | NULL
```

### 4. No Infinite Loops
Database prevents re-executing phases that exhausted attempts.

**Before (broken):**
- Phase stuck in QUEUED even after attempts exhausted
- Main loop keeps picking it up
- Infinite loop

**After (fixed):**
- Phase marked FAILED in DB when attempts exhausted
- `get_next_executable_phase()` skips FAILED phases
- Loop terminates cleanly

### 5. Project Agnostic
Solution works for any project type - state is in database, not code.

**Reusable for:**
- FileOrganizer Phase 2 (15 phases, 3 tiers)
- Research System phases (citation validation, etc.)
- Any future Autopack project

### 6. Long-Run Reliable
State persists across executor restarts, network failures, database reconnects.

**Resilience:**
- Executor crashes → Resume from DB
- Network blip → Retry fetch, state intact
- Database restart → Executor reconnects, no data loss

---

## Migration Strategy

### Step 1: Add Database Schema (Non-Breaking)
- Add columns with default values
- Existing runs continue to work
- New columns default to `attempts_used=0, max_attempts=5`

**Timeline:** 1 day
**Risk:** Low

### Step 2: Implement New Methods (Feature Flag)
- Add new database-backed methods
- Keep old instance attribute logic
- Add feature flag `USE_DB_STATE_PERSISTENCE=true/false`
- Test with FileOrganizer Phase 2 run

**Timeline:** 2-3 days
**Risk:** Medium (requires thorough testing)

### Step 3: Switch to New Logic
- Enable feature flag for all runs
- Monitor for regressions
- Collect telemetry on attempt tracking

**Timeline:** 1 day
**Risk:** Low (can roll back feature flag)

### Step 4: Remove Old Code
- Delete instance attribute state management
- Remove feature flag
- Clean up retry loop logic

**Timeline:** 1 day
**Risk:** Low

**Total Timeline:** 5-6 days

---

## Testing Plan

### Unit Tests
1. Test `_get_phase_from_db()` with various phase states
2. Test `_update_phase_attempts_in_db()` atomicity
3. Test `get_next_executable_phase()` sorting and filtering
4. Test attempt exhaustion logic

### Integration Tests
1. Run FileOrganizer Phase 2 with new logic
2. Simulate executor crash and restart
3. Test with max_attempts=2 (fast failure)
4. Test with stop_on_first_failure=True

### Regression Tests
1. Verify existing runs still work with default columns
2. Test with both feature flags (old and new logic)
3. Verify attempt counters match between DB and logs

---

## Rollout Plan

### Week 1: Schema Migration
- Day 1: Add database columns
- Day 2: Run migration script
- Day 3: Verify schema in production

### Week 2: Implementation
- Day 1-2: Implement new methods
- Day 3: Add feature flag
- Day 4: Write unit tests
- Day 5: Integration testing

### Week 3: Testing
- Day 1-2: FileOrganizer Phase 2 test run
- Day 3: Crash/restart testing
- Day 4: Performance testing
- Day 5: Telemetry review

### Week 4: Rollout
- Day 1: Enable feature flag for test runs
- Day 2-3: Monitor for regressions
- Day 4: Enable for all runs
- Day 5: Remove old code

---

## Open Questions

1. **Should max_attempts be configurable per phase?**
   - Current: Global setting from LlmService config
   - Proposed: Per-phase `max_attempts` column
   - **Decision**: Yes, allow per-phase overrides

2. **How to handle Doctor actions that cut retries short?**
   - Current: Doctor can return early (causes loop)
   - Proposed: Doctor sets `should_skip_remaining_attempts` flag
   - **Decision**: Update database state to FAILED if Doctor recommends skip

3. **What to do with in-flight EXECUTING phases when executor restarts?**
   - Option A: Resume from last attempt
   - Option B: Reset to QUEUED
   - **Decision**: Resume from last attempt (attempts_used is checkpoint)

4. **Should we add phase-level metrics (total_time, avg_attempt_time)?**
   - **Decision**: Yes, add in Phase 2 of rollout

---

## References

- **Failure loop logs**: [.autonomous_runs/fileorg-phase2-beta-release/executor_fixed.log](file:///c:/dev/Autopack/.autonomous_runs/fileorg-phase2-beta-release/executor_fixed.log)
- **execute_phase() method**: [autonomous_executor.py:998-1256](file:///c:/dev/Autopack/src/autopack/autonomous_executor.py#L998-L1256)
- **Main loop**: [autonomous_executor.py:4456-4649](file:///c:/dev/Autopack/src/autopack/autonomous_executor.py#L4456-L4649)
- **Phase model**: [models.py](file:///c:/dev/Autopack/src/autopack/models.py)

---

## Appendix A: Comparison Table

| Aspect | Current (Broken) | Proposed (Fixed) |
|--------|------------------|------------------|
| **Attempt Counter Storage** | Instance attribute | Database column |
| **State Persistence** | In-memory only | Database-backed |
| **Process Restart** | ❌ Loses state | ✅ Resumes from DB |
| **Infinite Loop Risk** | ❌ High | ✅ Eliminated |
| **Observability** | ❌ Opaque | ✅ Query DB for state |
| **Retry Logic** | Multi-level loop | Single-level loop |
| **State Transitions** | Implicit | Explicit (DB updates) |
| **Doctor Integration** | Causes early return | Updates DB state |
| **Project Agnostic** | ❌ Code-dependent | ✅ DB-driven |

---

## Appendix B: SQL Queries for Monitoring

### Check Phase Attempt Status
```sql
SELECT
    phase_id,
    state,
    attempts_used,
    max_attempts,
    last_failure_reason,
    last_attempt_timestamp
FROM phases
WHERE run_id = 'fileorg-phase2-beta-release'
ORDER BY tier_id, phase_index;
```

### Find Stuck Phases (EXECUTING for > 1 hour)
```sql
SELECT
    phase_id,
    state,
    attempts_used,
    last_attempt_timestamp,
    NOW() - last_attempt_timestamp AS time_since_last_attempt
FROM phases
WHERE
    run_id = 'fileorg-phase2-beta-release'
    AND state = 'EXECUTING'
    AND last_attempt_timestamp < NOW() - INTERVAL '1 hour';
```

### Attempt Distribution
```sql
SELECT
    attempts_used,
    COUNT(*) AS phase_count,
    ARRAY_AGG(phase_id) AS phase_ids
FROM phases
WHERE run_id = 'fileorg-phase2-beta-release'
GROUP BY attempts_used
ORDER BY attempts_used;
```

---

**End of Document**
