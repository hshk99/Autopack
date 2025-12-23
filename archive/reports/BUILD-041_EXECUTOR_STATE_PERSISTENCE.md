# BUILD-041: Executor State Persistence Fix

**Status**: Proposed
**Priority**: Critical
**Created**: 2025-12-17
**Issue**: [executor_failure_loop](../docs/project_issue_backlog.json)
**Architecture Doc**: [EXECUTOR_STATE_PERSISTENCE_ARCHITECTURE.md](EXECUTOR_STATE_PERSISTENCE_ARCHITECTURE.md)

---

## Problem Summary

The autonomous executor enters infinite failure loops when `execute_phase()` returns before exhausting `max_attempts` (due to Doctor actions, health checks, or early termination). The phase remains in QUEUED state in the database, causing the main loop to continuously re-select and re-execute it.

**Observed Pattern** (FileOrganizer Phase 2 run):
```
Iteration 1: Attempt 1/5 → fails
           : Attempt 2/5 → fails → execute_phase() returns early
Iteration 2: Main loop finds phase still QUEUED
           : Attempt 2/5 (REPEATED) → same failure → infinite loop
```

**Root Cause**: State management is split between:
- Instance attributes: `_attempt_index_{phase_id}` (attempt counter)
- Database: `phases.state` (QUEUED, EXECUTING, COMPLETE, FAILED)

When `execute_phase()` returns before exhausting attempts, the database state is not updated to FAILED, creating a desynchronization.

---

## Solution: Database-Backed State Persistence

Move attempt tracking from instance attributes to database columns, ensuring single source of truth for all phase execution state.

### Key Changes

1. **Database Schema**: Add attempt tracking columns to `phases` table
2. **Refactor execute_phase()**: Execute ONE attempt per call, update DB atomically
3. **Simplify Main Loop**: Trust database state for phase selection
4. **Feature Flag**: Safe rollout with backward compatibility

---

## Implementation Plan

### Phase 1: Database Schema Migration (1 day)

**File**: `scripts/migrations/add_phase_attempts.py`

Add columns to `phases` table:
- `attempts_used` (Integer, default=0): Current attempt count
- `max_attempts` (Integer, default=5): Maximum attempts allowed
- `last_attempt_timestamp` (DateTime): When last attempt occurred
- `last_failure_reason` (String): Most recent failure status

**Acceptance Criteria**:
- [ ] Migration script creates all four columns with defaults
- [ ] Existing phases get `attempts_used=0, max_attempts=5`
- [ ] Index created: `idx_phase_executable (run_id, state, attempts_used)`
- [ ] Migration tested on development database
- [ ] Rollback script created

### Phase 2: Database Helper Methods (1 day)

**File**: `src/autopack/autonomous_executor.py`

Implement database access methods:
- `_get_phase_from_db(phase_id)` - Fetch phase with attempt state
- `_update_phase_attempts_in_db(phase_id, attempts_used, last_failure_reason, timestamp)` - Update attempt tracking
- `_mark_phase_complete_in_db(phase_id)` - Mark phase COMPLETE
- `_mark_phase_failed_in_db(phase_id, reason)` - Mark phase FAILED with reason

**Acceptance Criteria**:
- [ ] All methods use `get_db()` for database sessions
- [ ] All updates are atomic (single commit)
- [ ] All methods handle missing phases gracefully
- [ ] Unit tests for each method
- [ ] Methods log actions for observability

### Phase 3: Refactor execute_phase() (2 days)

**File**: `src/autopack/autonomous_executor.py:998-1256`

**Current Behavior**: execute_phase() runs retry loop (attempts 0-4), returns when done
**New Behavior**: execute_phase() executes ONE attempt, updates DB, returns

**Key Logic**:
1. Load attempt count from database (not instance attribute)
2. Check if already exhausted (return if `attempts_used >= max_attempts`)
3. Execute single attempt with current model escalation
4. Update database atomically:
   - Success → mark COMPLETE
   - Failure → increment `attempts_used`, check if exhausted
   - Exhausted → mark FAILED

**Acceptance Criteria**:
- [ ] Instance attribute `_attempt_index_{phase_id}` removed
- [ ] Method loads `attempts_used` from database
- [ ] Single attempt executed per call
- [ ] Database updated atomically after every attempt
- [ ] Phase marked FAILED when `attempts_used >= max_attempts`
- [ ] Model escalation still works (based on DB `attempts_used`)
- [ ] Doctor integration preserved (but updates DB instead of attributes)
- [ ] Re-planning integration preserved (resets DB `attempts_used` to 0)
- [ ] All existing tests pass
- [ ] New integration test for database state updates

### Phase 4: Update get_next_executable_phase() (1 day)

**File**: `src/autopack/autonomous_executor.py` (main loop)

**Current**: `get_next_queued_phase()` - finds phases with `state=QUEUED`
**New**: `get_next_executable_phase()` - finds phases with:
- `state=QUEUED` (not yet started), OR
- `state=EXECUTING AND attempts_used < max_attempts` (retries available)

**Acceptance Criteria**:
- [ ] Method queries phases with executable state
- [ ] Sorts by `(tier_index, phase_index)`
- [ ] Excludes phases with `attempts_used >= max_attempts`
- [ ] Unit tests for different phase state combinations
- [ ] Integration test with mixed phase states

### Phase 5: Feature Flag and Testing (1-2 days)

**File**: `src/autopack/config.py`

Add feature flag: `USE_DB_STATE_PERSISTENCE` (default: False)

**Acceptance Criteria**:
- [ ] Feature flag controls which execute_phase() version runs
- [ ] Old code path preserved when flag=False
- [ ] New code path activated when flag=True
- [ ] Config file allows per-run override
- [ ] Integration tests for both code paths
- [ ] FileOrganizer Phase 2 test run with flag=True
- [ ] Test crash/restart recovery (stop executor mid-run, restart)
- [ ] Performance benchmarking (compare old vs new)

### Phase 6: Rollout and Monitoring (1 day)

**Timeline**:
1. Enable flag for test runs (monitor for 1 day)
2. Enable flag for all new runs (monitor for 2 days)
3. Remove old code path and feature flag
4. Clean up instance attribute references

**Monitoring Queries**:
```sql
-- Check attempt distribution
SELECT attempts_used, COUNT(*) FROM phases
WHERE run_id = 'fileorg-phase2-beta-release'
GROUP BY attempts_used;

-- Find stuck phases (EXECUTING > 1 hour)
SELECT phase_id, attempts_used, max_attempts,
       NOW() - last_attempt_timestamp AS stale_duration
FROM phases
WHERE state = 'EXECUTING'
  AND last_attempt_timestamp < NOW() - INTERVAL '1 hour';
```

**Acceptance Criteria**:
- [ ] No infinite loops observed in test runs
- [ ] All phases progress through attempts correctly
- [ ] Phases marked FAILED after max_attempts exhausted
- [ ] Crash recovery works (executor resumes from DB state)
- [ ] Performance within 5% of old implementation
- [ ] All production runs using new code path
- [ ] Old code removed, feature flag deleted

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_executor_state_persistence.py`

Test cases:
1. `test_get_phase_from_db()` - Fetch phase with attempt state
2. `test_update_phase_attempts()` - Atomic attempt counter updates
3. `test_mark_phase_complete()` - Transition to COMPLETE state
4. `test_mark_phase_failed()` - Transition to FAILED state with reason
5. `test_execute_phase_success_first_attempt()` - Happy path
6. `test_execute_phase_failure_increment_attempts()` - Retry path
7. `test_execute_phase_exhausted_marks_failed()` - Max attempts reached
8. `test_get_next_executable_phase_queued()` - Find QUEUED phases
9. `test_get_next_executable_phase_executing_with_retries()` - Find EXECUTING phases
10. `test_get_next_executable_phase_skip_exhausted()` - Skip maxed-out phases

### Integration Tests

**File**: `tests/integration/test_executor_failure_loop_fix.py`

Test scenarios:
1. **Crash Recovery**: Start run, stop executor mid-attempt, restart → resumes correctly
2. **Max Attempts**: Phase fails 5 times → marked FAILED, next phase starts
3. **Doctor Early Return**: Doctor cuts retries short → DB updated, phase marked FAILED
4. **Re-planning**: Phase triggers replan → `attempts_used` reset to 0, new approach used
5. **Mixed States**: Run with QUEUED, EXECUTING, COMPLETE, FAILED phases → correct selection
6. **Model Escalation**: Attempts 0-4 use correct models based on `attempts_used` from DB

### Regression Tests

Run full test suite:
```bash
PYTHONUTF8=1 PYTHONPATH=src pytest tests/ -v --tb=line
```

Expected: All 365+ tests pass

### Load Testing

**Run FileOrganizer Phase 2** (15 phases, 3 tiers) with new code:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://..." \
  python -m autopack.autonomous_executor \
  --run-id fileorg-phase2-test-with-build041 \
  --poll-interval 10
```

Monitor:
- No infinite loops
- Correct phase progression
- Database state accuracy
- Token usage similar to expected

---

## Rollback Plan

If critical issues found after rollout:

1. **Immediate**: Set `USE_DB_STATE_PERSISTENCE=false` in config
2. **Emergency**: Revert commit, restart executor
3. **Data Recovery**: Database columns remain (no data loss), old code ignores them

Migration rollback script:
```sql
ALTER TABLE phases DROP COLUMN attempts_used;
ALTER TABLE phases DROP COLUMN max_attempts;
ALTER TABLE phases DROP COLUMN last_attempt_timestamp;
ALTER TABLE phases DROP COLUMN last_failure_reason;
DROP INDEX idx_phase_executable;
```

---

## Success Metrics

### Phase 1-4 (Development)
- [ ] All unit tests pass (10/10)
- [ ] All integration tests pass (6/6)
- [ ] No regressions in existing test suite
- [ ] Code review approved

### Phase 5 (Testing)
- [ ] FileOrganizer Phase 2 test run completes without infinite loops
- [ ] Crash recovery test passes
- [ ] Performance within 5% of baseline

### Phase 6 (Production)
- [ ] 10 production runs complete successfully with new code
- [ ] Zero infinite loop incidents
- [ ] Average `attempts_used` matches expected distribution
- [ ] No increase in FAILED phases due to state bugs

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| Database schema migration fails | High | Low | Test migration on dev/staging first, rollback script ready |
| Performance degradation | Medium | Low | Benchmark before rollout, database indexes added |
| Lost in-flight work during transition | Medium | Low | Feature flag allows gradual rollout, old runs continue with old code |
| Doctor/re-planning integration breaks | High | Medium | Extensive integration testing, both code paths tested |
| Database deadlocks under concurrent access | High | Low | Use row-level locking, test with parallel executor instances |

---

## Dependencies

**Blocked By**: None (can start immediately)

**Blocks**:
- FileOrganizer Phase 2 Beta Release (currently blocked by infinite loop)
- Any long-running autonomous builds (>10 phases)

**Related Issues**:
- `builder_failure` in project_issue_backlog.json (may be related symptom)

---

## Timeline

**Total Estimated Time**: 5-6 days (1 engineer)

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Schema Migration | 1 day | None |
| Phase 2: Database Helpers | 1 day | Phase 1 |
| Phase 3: Refactor execute_phase() | 2 days | Phase 2 |
| Phase 4: Update Main Loop | 1 day | Phase 3 |
| Phase 5: Feature Flag & Testing | 1-2 days | Phase 4 |
| Phase 6: Rollout & Monitoring | 1 day | Phase 5 |

**Milestones**:
- Day 2: Database schema ready, tested
- Day 4: execute_phase() refactored, unit tests pass
- Day 5: Feature flag working, integration tests pass
- Day 7: Production rollout, monitoring active
- Day 10: Old code removed, BUILD-041 complete

---

## Related Documents

- [Architecture Proposal](EXECUTOR_STATE_PERSISTENCE_ARCHITECTURE.md) - Full technical design
- [Issue Backlog](project_issue_backlog.json) - `executor_failure_loop` entry
- [FileOrganizer Phase 2 Run Logs](./.autonomous_runs/fileorg-phase2-beta-release/executor_fixed.log) - Failure evidence

---

## Approval

**Proposed By**: Claude Sonnet 4.5
**Date**: 2025-12-17
**Approval Status**: Pending User Review

**Next Steps After Approval**:
1. Create feature branch: `fix/build-041-executor-state-persistence`
2. Start Phase 1: Database schema migration
3. Daily standup updates on progress
4. Code review before Phase 6 rollout

---

**END OF BUILD-041 SPECIFICATION**
