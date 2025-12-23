# BUILD-048-T1: Linux/Unix Testing Requirements

**Date**: 2025-12-17
**Status**: ⏸️ PENDING (Linux environment needed)
**Related**: [BUILD-048_EXECUTOR_INSTANCE_MANAGEMENT.md](BUILD-048_EXECUTOR_INSTANCE_MANAGEMENT.md)

---

## Overview

BUILD-048-T1 (Process-Level Locking) has been implemented and tested on Windows. This document outlines the testing requirements for Linux/Unix platforms to ensure cross-platform compatibility.

**Current Status**:
- ✅ Windows testing complete (8/12 tests passing, 4 platform-specific skips)
- ⏸️ Linux/Unix testing pending (no Linux environment available)

---

## Test Plan for Linux/Unix

### Prerequisites

1. **Linux/Unix Environment**:
   - Ubuntu 20.04+ (recommended)
   - macOS 10.15+ (alternative)
   - Any Unix-like OS with Python 3.11+

2. **Dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. **PostgreSQL** (for integration testing):
   ```bash
   # Ubuntu/Debian
   sudo apt-get install postgresql

   # macOS
   brew install postgresql
   ```

### Test Execution

**Unit Tests**:
```bash
cd /path/to/Autopack
PYTHONUTF8=1 PYTHONPATH=src python -m pytest src/autopack/tests/test_executor_lock.py -v
```

**Expected Results**:
- ✅ 10/12 tests should PASS
- ⏸️ 1 test should SKIP (test_lock_survives_process_fork - Unix-specific, requires manual testing)
- ⏸️ 1 test should SKIP (test_duplicate_executor_prevented - integration test)

**Platform-Specific Tests** (should NOT skip on Unix):
- `test_force_unlock` - Should PASS (Unix allows reading locked files)
- `test_lock_file_contains_executor_info` - Should PASS (Unix fcntl allows concurrent reads)

---

## Test Cases to Verify

### 1. Basic Lock Acquisition

```bash
# Test 1: Single executor lock
python -c "
from autopack.executor_lock import ExecutorLockManager
lock = ExecutorLockManager('test-run-id')
assert lock.acquire()
print('✅ Lock acquired')
lock.release()
print('✅ Lock released')
"
```

**Expected**: Both assertions pass, no errors

### 2. Duplicate Prevention

```bash
# Terminal 1
python -c "
from autopack.executor_lock import ExecutorLockManager
import time
lock = ExecutorLockManager('test-run-id')
assert lock.acquire()
print('✅ Terminal 1: Lock acquired')
time.sleep(30)  # Hold lock for 30 seconds
lock.release()
print('✅ Terminal 1: Lock released')
" &

# Terminal 2 (run immediately after Terminal 1)
python -c "
from autopack.executor_lock import ExecutorLockManager
lock = ExecutorLockManager('test-run-id')
result = lock.acquire()
if not result:
    print('✅ Terminal 2: Lock acquisition failed (expected)')
else:
    print('❌ Terminal 2: Lock acquisition succeeded (UNEXPECTED - BUG!)')
    lock.release()
"
```

**Expected**:
- Terminal 1: Lock acquired, held for 30s, released
- Terminal 2: Lock acquisition fails (lock already held)

### 3. Lock File Content

```bash
python -c "
from autopack.executor_lock import ExecutorLockManager
from pathlib import Path
lock = ExecutorLockManager('test-run-id')
assert lock.acquire()

# Read lock file (should work on Unix)
lock_file = Path('.autonomous_runs/.locks/test-run-id.lock')
content = lock_file.read_text()
print('Lock file content:')
print(content)

assert str(lock.pid) in content
assert lock.hostname in content
print('✅ Lock file contains correct executor info')

lock.release()
"
```

**Expected**: Lock file content includes PID, hostname, working directory

### 4. Force Unlock (Stale Lock Recovery)

```bash
# Terminal 1: Create lock and simulate crash (don't release)
python -c "
from autopack.executor_lock import ExecutorLockManager
lock = ExecutorLockManager('test-run-id')
assert lock.acquire()
print('✅ Lock acquired (simulating crash - not releasing)')
# Exit without releasing (simulate crash)
" &

sleep 2  # Wait for lock to be acquired

# Terminal 2: Force unlock stale lock
python -c "
from autopack.executor_lock import ExecutorLockManager
lock = ExecutorLockManager('test-run-id')

# Try normal acquisition (should fail)
if not lock.acquire():
    print('✅ Lock already held (expected)')

    # Force unlock
    if lock.force_unlock():
        print('✅ Stale lock force-unlocked')

        # Now acquire should succeed
        if lock.acquire():
            print('✅ Lock acquired after force unlock')
            lock.release()
        else:
            print('❌ Lock acquisition failed after force unlock (BUG!)')
    else:
        print('❌ Force unlock failed (BUG!)')
else:
    print('❌ Lock acquisition succeeded despite existing lock (BUG!)')
"
```

**Expected**: Force unlock succeeds, subsequent lock acquisition succeeds

### 5. Process Fork Handling (Unix-only)

```bash
python -c "
import os
import sys
from autopack.executor_lock import ExecutorLockManager

lock = ExecutorLockManager('test-run-id')
assert lock.acquire()
print(f'Parent ({os.getpid()}): ✅ Lock acquired')

# Fork child process
pid = os.fork()

if pid == 0:  # Child process
    # Child should NOT be able to acquire same lock
    lock2 = ExecutorLockManager('test-run-id')
    can_acquire = lock2.acquire()

    if not can_acquire:
        print(f'Child ({os.getpid()}): ✅ Lock acquisition failed (expected)')
        sys.exit(0)
    else:
        print(f'Child ({os.getpid()}): ❌ Lock acquisition succeeded (BUG!)')
        lock2.release()
        sys.exit(1)
else:  # Parent process
    _, status = os.waitpid(pid, 0)
    exit_code = os.WEXITSTATUS(status)

    if exit_code == 0:
        print(f'Parent ({os.getpid()}): ✅ Child correctly failed to acquire lock')
    else:
        print(f'Parent ({os.getpid()}): ❌ Child unexpectedly acquired lock (BUG!)')

    lock.release()
    print(f'Parent ({os.getpid()}): ✅ Lock released')
"
```

**Expected**: Child process cannot acquire parent's lock

### 6. Integration Test: Real Executor Duplicate Prevention

```bash
# Terminal 1: Launch executor
DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
PYTHONUTF8=1 PYTHONPATH=src \
python -m autopack.autonomous_executor --run-id test-duplicate-prevention &

EXECUTOR1_PID=$!
echo "Executor 1 PID: $EXECUTOR1_PID"

sleep 5  # Let executor start and acquire lock

# Terminal 2: Try launching duplicate executor (should fail)
DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
PYTHONUTF8=1 PYTHONPATH=src \
python -m autopack.autonomous_executor --run-id test-duplicate-prevention

# Check exit code
if [ $? -eq 1 ]; then
    echo "✅ Duplicate executor prevented (exit code 1)"
else
    echo "❌ Duplicate executor allowed (BUG!)"
fi

# Clean up
kill $EXECUTOR1_PID
```

**Expected**: Second executor exits with code 1, error message logged

---

## Platform-Specific Differences

### Windows (msvcrt.locking)
- **Exclusive locks**: Other processes CANNOT read locked files
- **File deletion**: Locked files cannot be deleted until unlocked
- **Impact**: 2 tests skipped due to read restrictions

### Unix/Linux/Mac (fcntl.flock)
- **Exclusive locks**: Other processes CAN read locked files (shared read access)
- **File deletion**: Locked files CAN be deleted (file persists until handle closes)
- **Impact**: All tests should pass (no platform-specific limitations)

---

## Expected Test Results

### Pytest Output (Linux/Unix)

```
============================= test session starts =============================
platform linux -- Python 3.11.x, pytest-8.2.1, pluggy-1.5.0
collected 12 items

test_acquire_lock_success PASSED                                        [  8%]
test_acquire_lock_twice_fails PASSED                                    [ 16%]
test_release_allows_reacquire PASSED                                    [ 25%]
test_context_manager_success PASSED                                     [ 33%]
test_context_manager_fails_on_duplicate PASSED                          [ 41%]
test_different_run_ids_independent PASSED                               [ 50%]
test_force_unlock PASSED                                                [ 58%]  ✅ Should PASS on Unix
test_lock_file_contains_executor_info PASSED                            [ 66%]  ✅ Should PASS on Unix
test_lock_file_cleaned_up_on_release PASSED                             [ 75%]
test_is_locked_before_acquire PASSED                                    [ 83%]
test_lock_survives_process_fork PASSED                                  [ 91%]  ✅ Should PASS on Unix (was skipped on Windows)
test_duplicate_executor_prevented SKIPPED (Integration test)            [100%]

======================== 11 passed, 1 skipped in 0.25s =========================
```

**Key Differences from Windows**:
- ✅ `test_force_unlock` - PASSED (was skipped on Windows)
- ✅ `test_lock_file_contains_executor_info` - PASSED (was skipped on Windows)
- ✅ `test_lock_survives_process_fork` - PASSED (was skipped on Windows - Unix-only)

---

## Validation Checklist

- [ ] Unit tests: 11/12 passing (1 integration test skipped)
- [ ] Manual test #1: Basic lock acquisition/release works
- [ ] Manual test #2: Duplicate lock acquisition fails
- [ ] Manual test #3: Lock file contains correct executor info
- [ ] Manual test #4: Force unlock recovers from stale locks
- [ ] Manual test #5: Process fork does not inherit locks
- [ ] Manual test #6: Real executor prevents duplicates
- [ ] Performance: Lock overhead < 1ms
- [ ] No file descriptor leaks (check with `lsof -p $PID`)
- [ ] No permission errors in logs
- [ ] Lock directory `.autonomous_runs/.locks/` created automatically

---

## Known Platform Issues

### None Expected on Linux/Unix

The implementation uses standard `fcntl.flock()` which is well-supported on all Unix-like platforms. No platform-specific issues are anticipated.

**If issues are discovered**, please document them here with:
- Platform details (OS, version, Python version)
- Error message
- Steps to reproduce
- Workaround (if any)

---

## Reporting Test Results

After completing Linux/Unix testing, please update this document with:

1. **Test Results**: Paste pytest output
2. **Platform Details**: OS, version, Python version
3. **Issues Found**: Any bugs or unexpected behavior
4. **Validation Status**: Check all items in the validation checklist

**Format**:
```markdown
## Test Results - [OS Name] [Version]

**Date**: YYYY-MM-DD
**Tester**: [Name]
**Platform**: [OS] [Version]
**Python**: [Version]

### Pytest Output
\`\`\`
[paste pytest output]
\`\`\`

### Manual Test Results
- [ ] Test #1: [PASS/FAIL] - [notes]
- [ ] Test #2: [PASS/FAIL] - [notes]
...

### Issues Found
[Describe any bugs or unexpected behavior]

### Overall Status
✅ PASSED / ⚠️ PASSED WITH ISSUES / ❌ FAILED
```

---

## Next Steps

1. **Find Linux/Unix environment**:
   - Ubuntu VM / WSL2
   - macOS laptop
   - Cloud Linux instance (AWS, DigitalOcean, etc.)

2. **Run tests**: Execute all unit tests and manual tests

3. **Report results**: Update this document with findings

4. **Fix issues** (if any): Create BUILD-048-T1-FIX if bugs found

5. **Mark complete**: Update BUILD-048 documentation with Linux validation status

---

**Status**: ⏸️ AWAITING LINUX/UNIX ENVIRONMENT FOR TESTING

