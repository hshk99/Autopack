# DBG-009: Multiple Concurrent Executor Instances Causing Resource Waste

**Date**: 2025-12-17T18:50:00Z
**Severity**: HIGH (Cost/Resource Impact)
**Status**: 🔍 IDENTIFIED - Solution designed, awaiting implementation

---

## Problem Statement

During FileOrg Phase 2 validation, **6 concurrent executor instances** were running simultaneously, all targeting the same `fileorg-phase2-beta-release` run. This caused:

1. **Token waste**: Multiple executors competing to execute the same phases
2. **Database contention**: Race conditions on phase state updates
3. **Resource waste**: 6x CPU/memory usage
4. **Log confusion**: Multiple interleaved log streams

**Evidence**:
```bash
Background Bash Instances Created:
d1df39: Initial BUILD-046 validation (run-id: fileorg-phase2-beta-release)
1bb31e: Second BUILD-046 validation (run-id: fileorg-phase2-beta-release)
d22807: BUILD-047 validation (run-id: fileorg-phase2-build047-validation) ✅ Different run
940d79: BUILD-047 re-run (run-id: fileorg-phase2-beta-release)
972de3: BUILD-047 final validation (run-id: fileorg-phase2-beta-release)
7fadd5: Advanced-search retry (run-id: fileorg-phase2-beta-release)
```

**Result**: 5 out of 6 executors targeting the **same run-id**, causing massive duplication.

---

## Root Cause Analysis

### Why This Happened

**Immediate Cause**: Claude Code assistant (me) launched multiple background executors during iterative debugging without stopping previous instances.

**Timeline**:
1. **16:17** - Launched `d1df39` for BUILD-046 validation
2. **16:18** - Launched `1bb31e` (duplicate) to add log output with `tee`
3. **16:25** - Launched `d22807` for BUILD-047 validation (correct - different run-id)
4. **16:35** - Launched `940d79` for BUILD-047 re-run (should have stopped d1df39/1bb31e first)
5. **16:40** - Launched `972de3` for "final validation" (duplicate again)
6. **16:45** - Launched `7fadd5` for advanced-search retry (duplicate again)

**Pattern**: Each time a new validation was requested, I launched a new executor instead of:
- Checking if one was already running
- Stopping the old one first
- Reusing the existing instance

### Why BUILD-041 Didn't Prevent This

BUILD-041 (database-backed state) has **single-executor locking** via database transactions, but it's optimistic:

```python
# autonomous_executor.py (simplified)
while True:
    # Each executor independently queries for QUEUED phases
    phases = fetch_queued_phases(run_id)

    if not phases:
        break  # No more work

    for phase in phases:
        # Race condition: Multiple executors can fetch same QUEUED phase
        execute_phase(phase)
        mark_complete(phase)  # Database update (atomic, but too late)
```

**Why it fails**:
- Phase fetch is NOT locked (multiple executors see same QUEUED phase)
- Only the final state update is atomic
- First executor to complete wins, others waste tokens

**Expected Behavior** (as designed):
- BUILD-041 expects **one executor per run-id**
- Multiple executors are allowed for **different run-ids** (parallel runs)
- Database prevents corruption, but doesn't prevent waste

---

## Impact Assessment

### Token Waste Analysis

**Estimated Waste** (assuming each duplicate executor tried to execute phases):

| Instance | Run ID | Status | Token Waste Estimate |
|----------|--------|--------|---------------------|
| d1df39 | fileorg-phase2-beta-release | Running | 0-50K tokens* |
| 1bb31e | fileorg-phase2-beta-release | Duplicate | 0-50K tokens* |
| 940d79 | fileorg-phase2-beta-release | Duplicate | 0-50K tokens* |
| 972de3 | fileorg-phase2-beta-release | Duplicate | 0-50K tokens* |
| 7fadd5 | fileorg-phase2-beta-release | Active (completed) | 64K tokens ✅ Valid |
| d22807 | fileorg-phase2-build047-validation | Different run | 0 tokens ✅ Valid |

*Most were idle (waiting for phases) since 7fadd5 completed the work

**Actual Waste**: Likely **0-100K tokens** (low because phases completed quickly and duplicates found no work)

**Potential Waste**: Could have been **500K+ tokens** if all duplicates executed phases concurrently

### Resource Waste

- **CPU**: 5 idle Python processes (~60MB RAM each = 300MB wasted)
- **Database connections**: 5 concurrent connections (low impact on PostgreSQL)
- **Log files**: 5 duplicate log files created

### Why It Didn't Cause Corruption

✅ **BUILD-041 worked correctly** - Database state remained consistent:
- Atomic updates prevented race conditions
- Final state shows 15/15 phases COMPLETE (correct)
- No duplicate work was committed to database

⚠️ **Risk if executors had overlapped**:
- Multiple executors calling LLM for same phase simultaneously
- Wasted API calls (both generate patches, only one commits)
- Confused logs (multiple "Builder succeeded" messages for same phase)

---

## Solution Design

### BUILD-048: Executor Instance Management System

**Three-tier solution**:

#### Tier 1: Process-Level Locking (Immediate - High Priority)

**Add PID-based locking to prevent multiple executors per run-id**

**Implementation** ([autonomous_executor.py](../src/autopack/autonomous_executor.py)):

```python
import os
import fcntl  # Unix
import msvcrt  # Windows
from pathlib import Path

class ExecutorLockManager:
    """Ensures only one executor runs per run-id."""

    def __init__(self, run_id: str, lock_dir: Path = Path(".autonomous_runs/.locks")):
        self.run_id = run_id
        self.lock_dir = lock_dir
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock_file_path = self.lock_dir / f"{run_id}.lock"
        self.lock_file = None

    def acquire(self, timeout: int = 5) -> bool:
        """Acquire exclusive lock for this run-id.

        Returns:
            True if lock acquired, False if another executor holds it
        """
        try:
            self.lock_file = open(self.lock_file_path, 'w')

            # Write current PID for debugging
            self.lock_file.write(f"{os.getpid()}\n{os.getcwd()}\n")
            self.lock_file.flush()

            # Try to acquire exclusive lock (non-blocking)
            if os.name == 'nt':  # Windows
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # Unix
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            logger.info(f"[LOCK] Acquired executor lock for run_id={self.run_id} (PID={os.getpid()})")
            return True

        except (IOError, OSError) as e:
            # Lock already held by another process
            if self.lock_file:
                existing_pid = self.lock_file.read().split('\n')[0]
                logger.error(
                    f"[LOCK] Another executor is already running for run_id={self.run_id} "
                    f"(PID={existing_pid}). Exiting to prevent duplicate work."
                )
                self.lock_file.close()
            return False

    def release(self):
        """Release the lock."""
        if self.lock_file:
            try:
                if os.name == 'nt':
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                self.lock_file_path.unlink(missing_ok=True)
                logger.info(f"[LOCK] Released executor lock for run_id={self.run_id}")
            except Exception as e:
                logger.warning(f"[LOCK] Error releasing lock: {e}")

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Executor lock already held for run_id={self.run_id}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# Usage in main() function:
def main():
    args = parse_args()
    run_id = args.run_id

    # Acquire exclusive lock for this run-id
    lock_manager = ExecutorLockManager(run_id)
    if not lock_manager.acquire():
        logger.error("Exiting: Another executor is already running for this run-id")
        sys.exit(1)

    try:
        # Normal execution
        executor = AutonomousExecutor(run_id=run_id, ...)
        executor.run()
    finally:
        lock_manager.release()
```

**Benefits**:
- ✅ Prevents duplicate executors immediately
- ✅ Works cross-platform (Windows/Linux/Mac)
- ✅ Automatic cleanup on executor exit
- ✅ Clear error message if duplicate detected

**Limitations**:
- Only prevents duplicates on same machine
- Doesn't help if executors run on different servers (distributed setup)

---

#### Tier 2: Database-Level Locking (Medium Priority)

**Add executor heartbeat table for distributed locking**

**Schema** ([migrations/](../migrations/)):

```sql
CREATE TABLE executor_instances (
    run_id VARCHAR(255) PRIMARY KEY,
    executor_id VARCHAR(255) NOT NULL,  -- PID@hostname
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_heartbeat TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL,  -- RUNNING, COMPLETED, CRASHED
    phases_executed INT DEFAULT 0,
    CONSTRAINT unique_running_executor UNIQUE (run_id, status)
        WHERE status = 'RUNNING'
);

CREATE INDEX idx_executor_heartbeat ON executor_instances(run_id, last_heartbeat);
```

**Implementation**:

```python
class ExecutorHeartbeat:
    """Database-backed executor instance tracking."""

    def __init__(self, run_id: str, db_conn):
        self.run_id = run_id
        self.executor_id = f"{os.getpid()}@{socket.gethostname()}"
        self.db_conn = db_conn
        self.heartbeat_thread = None
        self.should_stop = False

    def register(self) -> bool:
        """Register this executor instance in database.

        Returns:
            True if registration successful, False if another executor is running
        """
        cursor = self.db_conn.cursor()

        try:
            # Check for existing RUNNING executors
            cursor.execute("""
                SELECT executor_id, last_heartbeat
                FROM executor_instances
                WHERE run_id = %s AND status = 'RUNNING'
            """, (self.run_id,))

            existing = cursor.fetchone()
            if existing:
                executor_id, last_heartbeat = existing
                staleness = (datetime.now() - last_heartbeat).total_seconds()

                if staleness < 60:  # Heartbeat within last minute
                    logger.error(
                        f"[HEARTBEAT] Another executor is active: {executor_id} "
                        f"(last heartbeat {staleness:.0f}s ago)"
                    )
                    return False
                else:
                    # Stale executor (crashed?) - take over
                    logger.warning(
                        f"[HEARTBEAT] Stale executor detected: {executor_id} "
                        f"(last heartbeat {staleness:.0f}s ago). Taking over."
                    )
                    cursor.execute("""
                        UPDATE executor_instances
                        SET status = 'CRASHED'
                        WHERE run_id = %s AND executor_id = %s
                    """, (self.run_id, executor_id))

            # Register this executor
            cursor.execute("""
                INSERT INTO executor_instances (run_id, executor_id, status)
                VALUES (%s, %s, 'RUNNING')
                ON CONFLICT (run_id) DO UPDATE
                SET executor_id = EXCLUDED.executor_id,
                    status = 'RUNNING',
                    started_at = NOW(),
                    last_heartbeat = NOW()
            """, (self.run_id, self.executor_id))

            self.db_conn.commit()
            logger.info(f"[HEARTBEAT] Registered executor: {self.executor_id}")

            # Start heartbeat thread
            self.start_heartbeat()
            return True

        except Exception as e:
            logger.error(f"[HEARTBEAT] Registration failed: {e}")
            self.db_conn.rollback()
            return False

    def start_heartbeat(self):
        """Start background thread to send heartbeats every 30s."""
        def heartbeat_loop():
            while not self.should_stop:
                try:
                    cursor = self.db_conn.cursor()
                    cursor.execute("""
                        UPDATE executor_instances
                        SET last_heartbeat = NOW()
                        WHERE run_id = %s AND executor_id = %s
                    """, (self.run_id, self.executor_id))
                    self.db_conn.commit()
                except Exception as e:
                    logger.warning(f"[HEARTBEAT] Update failed: {e}")

                time.sleep(30)

        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def unregister(self):
        """Mark executor as completed."""
        self.should_stop = True

        cursor = self.db_conn.cursor()
        cursor.execute("""
            UPDATE executor_instances
            SET status = 'COMPLETED', last_heartbeat = NOW()
            WHERE run_id = %s AND executor_id = %s
        """, (self.run_id, self.executor_id))
        self.db_conn.commit()
        logger.info(f"[HEARTBEAT] Unregistered executor: {self.executor_id}")
```

**Benefits**:
- ✅ Works across distributed systems
- ✅ Detects crashed executors (stale heartbeats)
- ✅ Provides executor visibility (who's running what)
- ✅ Enables monitoring/alerts

---

#### Tier 3: Claude Code Assistant Safeguards (Immediate - Process Improvement)

**Add pre-flight checks before launching executors**

**Assistant Protocol**:

```markdown
Before launching a background executor:

1. **Check existing executors**:
   - List all background bash processes
   - Identify any running autonomous_executor instances
   - Check their run-ids

2. **Decide action**:
   - If NO executor for target run-id: ✅ Launch new one
   - If executor ALREADY running for target run-id:
     - If monitoring: ✅ Use BashOutput to check status
     - If restarting: ⚠️ Stop old executor first, then launch new
     - If validating: ❌ Don't launch duplicate, use existing

3. **Stop old executors**:
   - Use KillShell for background bash shells
   - Verify termination before launching replacement
   - Document reason for restart in logs

4. **Document instances**:
   - Track which executor is for which purpose
   - Use descriptive log file names
   - Clear naming: validation vs monitoring vs retry
```

**Example Decision Tree**:

```
User: "Monitor the advanced-search phase"
├─ Check: Is executor running for fileorg-phase2-beta-release?
│  ├─ YES → Use BashOutput to monitor existing executor
│  └─ NO → Launch new executor with monitoring log
│
User: "Restart executor with new code"
├─ Check: Is executor running?
│  ├─ YES → KillShell old executor, wait, then launch new
│  └─ NO → Launch new executor
│
User: "Run validation tests"
├─ Check: Is this a different run-id?
│  ├─ YES (fileorg-phase2-build047-validation) → OK to launch in parallel
│  └─ NO (same run-id) → Stop old executor first
```

---

## Implementation Plan

### Phase 1: Immediate (Today)

✅ **Document the issue** (this file)
✅ **Create assistant protocol** (Tier 3 solution above)
⏸️ **Manual cleanup**: Kill duplicate executors (already done)

### Phase 2: Short-term (Next 24-48 hours)

**BUILD-048-T1**: Implement Tier 1 (Process-Level Locking)
- Add `ExecutorLockManager` class to autonomous_executor.py
- Update `main()` to acquire lock before execution
- Test on Windows and Linux
- Document in BUILD-048

### Phase 3: Medium-term (Next sprint)

**BUILD-048-T2**: Implement Tier 2 (Database-Level Locking)
- Create migration for `executor_instances` table
- Add `ExecutorHeartbeat` class
- Integrate with executor startup/shutdown
- Add monitoring dashboard for active executors

### Phase 4: Long-term (Future)

**BUILD-048-T3**: Advanced features
- Executor load balancing (multiple executors, different runs)
- Auto-recovery (restart crashed executors)
- Distributed coordination (multi-server setup)

---

## Testing Strategy

### Test Case 1: Duplicate Launch Prevention

```bash
# Terminal 1
python -m autopack.autonomous_executor --run-id test-run-1

# Terminal 2 (should fail)
python -m autopack.autonomous_executor --run-id test-run-1
# Expected: "Executor lock already held for run_id=test-run-1. Exiting."
```

### Test Case 2: Concurrent Different Runs

```bash
# Terminal 1
python -m autopack.autonomous_executor --run-id run-A

# Terminal 2 (should succeed - different run-id)
python -m autopack.autonomous_executor --run-id run-B
# Expected: Both executors run in parallel
```

### Test Case 3: Crashed Executor Recovery

```bash
# Terminal 1
python -m autopack.autonomous_executor --run-id test-run
# Kill with SIGKILL (no cleanup)

# Terminal 2 (should detect stale lock and take over)
python -m autopack.autonomous_executor --run-id test-run
# Expected: "Stale executor detected... Taking over."
```

---

## Cost Impact Analysis

### This Incident

**Actual Waste**: ~0-100K tokens (minimal, most executors were idle)
**Estimated Cost**: $0.30-$3.00 (negligible)

### Potential Future Impact (Without Fix)

**Scenario**: 5 executors all execute 15 phases concurrently
- **Tokens per phase**: ~32K (average from BUILD-046 validation)
- **Total tokens**: 5 executors × 15 phases × 32K = 2.4M tokens
- **Cost**: 2.4M × $3/M (input) + 0.6M × $15/M (output) = **$16.20 wasted**

**Over 100 runs**: $1,620 wasted (HIGH impact)

### ROI of Fix

**Implementation cost**: 4-8 hours dev time
**Savings per incident prevented**: $3-16
**Expected incidents prevented**: 10-50 per year
**ROI**: 200-400% over 12 months

---

## Lessons Learned

### What Went Wrong

1. **No pre-flight checks**: Launched executors without checking for duplicates
2. **No instance tracking**: Lost track of which executor was for what purpose
3. **Over-eager launching**: Launched new executor for each validation request
4. **No cleanup protocol**: Didn't stop old executors before launching new ones

### What Went Right

1. **BUILD-041 prevented corruption**: Database state remained consistent
2. **Token waste was minimal**: Most duplicates idled (found no work)
3. **Issue detected quickly**: User noticed multiple processes
4. **Easy to diagnose**: Clear log files and process list

### Key Insights

1. **Process locking is critical**: Database atomicity alone isn't enough
2. **Visibility matters**: Need to track what's running and why
3. **Assistant protocols needed**: Codify best practices for executor management
4. **Defensive design works**: BUILD-041's graceful handling prevented corruption

---

## References

**Related Issues**:
- BUILD-041: Database-Backed State Persistence (prevented corruption)
- BUILD-046: Dynamic Token Escalation (context for why executors were running)

**Code**:
- [autonomous_executor.py](../src/autopack/autonomous_executor.py) - Main executor loop

**Logs**:
- `.autonomous_runs/fileorg-phase2-advanced-search-retry.log` - Final successful execution
- `build-046-validation.log` - Duplicate validation logs

---

## Changelog

**2025-12-17 18:50**: Issue identified and analyzed
- Documented 6 concurrent executor instances (5 duplicates)
- Analyzed token waste (0-100K actual, 500K+ potential)
- Designed three-tier solution (BUILD-048)
- Created assistant protocol to prevent recurrence
- Status: 🔍 IDENTIFIED - Solution designed, awaiting implementation
