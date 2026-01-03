# BUILD-158: Tidy Lock/Lease + Doc Link Checker

**Date**: 2026-01-03
**Status**: ✅ **COMPLETE**
**Scope**: Cross-process safety via lease primitive + documentation link drift detection

---

## Overview

This build implements the highest-ROI safety improvement for the tidy system: **cross-process locking** via a lease primitive. It also adds lightweight documentation link drift checking to prevent "two truths" problems where navigation docs reference non-existent files.

**Key Achievement**: Tidy can now safely run concurrently without race conditions on queue files, archive operations, or `.autonomous_runs/` cleanup.

---

## Changes Implemented

### 1. Cross-Process Lease Primitive ✅

**Problem**: No protection against concurrent tidy runs → potential queue corruption, file conflicts, data loss.

**Solution**: Filesystem-based lease with atomic acquisition, TTL-based stale lock detection, and heartbeat renewal.

**New File**: [scripts/tidy/lease.py](../scripts/tidy/lease.py)

**Features**:
- **Atomic acquisition** using `os.O_CREAT | os.O_EXCL` (Windows/Unix compatible)
- **TTL-based expiry** (default: 30 min) with configurable grace period (default: 2 min)
- **Heartbeat renewal** for long-running operations (prevents premature expiry)
- **Ownership verification** (prevents accidental renewal of stolen locks)
- **Stale lock detection** and automatic breaking (crashed process recovery)
- **Malformed lock handling** (corrupt lock files treated as immediately stale)

**Implementation Details**:

```python
from lease import Lease

lease = Lease(
    lock_path=Path(".autonomous_runs/.locks/tidy.lock"),
    owner="tidy_up",
    ttl_seconds=1800  # 30 minutes
)

lease.acquire(timeout_seconds=30)
try:
    # ... long-running tidy work ...
    lease.renew()  # Heartbeat at phase boundaries
finally:
    lease.release()
```

**Lock Payload** ([scripts/tidy/lease.py:64-78](../scripts/tidy/lease.py#L64-L78)):
```json
{
  "owner": "tidy_up",
  "token": "uuid-for-ownership-verification",
  "pid": 12345,
  "created_at": "2026-01-03T12:00:00Z",
  "expires_at": "2026-01-03T12:30:00Z",
  "last_renewed_at": "2026-01-03T12:15:00Z"
}
```

---

### 2. Tidy Integration ✅

**File Modified**: [scripts/tidy/tidy_up.py](../scripts/tidy/tidy_up.py)

**CLI Flags Added** ([scripts/tidy/tidy_up.py:1286-1292](../scripts/tidy/tidy_up.py#L1286-L1292)):
```bash
--lease-timeout 30        # Seconds to wait for lease acquisition (default: 30)
--lease-ttl 1800          # Lease time-to-live before stale (default: 1800 = 30 min)
--no-lease                # Skip lease (unsafe, allows concurrent runs)
```

**Acquisition** ([scripts/tidy/tidy_up.py:1313-1331](../scripts/tidy/tidy_up.py#L1313-L1331)):
- Lease acquired **before** any file operations (even dry-run)
- Timeout after 30 seconds with clear error message
- Wrapped in `try/finally` to guarantee release

**Heartbeat Renewal** (at phase boundaries):
- Before Phase 1 (root routing): [scripts/tidy/tidy_up.py:1496-1498](../scripts/tidy/tidy_up.py#L1496-L1498)
- Before Phase 2 (docs hygiene): [scripts/tidy/tidy_up.py:1524-1526](../scripts/tidy/tidy_up.py#L1524-L1526)
- Before Phase 3 (archive consolidation): [scripts/tidy/tidy_up.py:1546-1548](../scripts/tidy/tidy_up.py#L1546-L1548)

**Release** ([scripts/tidy/tidy_up.py:1706-1709](../scripts/tidy/tidy_up.py#L1706-L1709)):
- Always released in `finally` block (even on exceptions)
- Idempotent (safe to call multiple times)

**Design Decision**: Dry-run **also acquires lease** to prevent concurrent dry-run + execute conflicts (prevents confusing mixed output).

---

### 3. Atomic Write Helper ✅

**Problem**: Inconsistent file write patterns across queue, reports, lock renewals.

**Solution**: Unified atomic write helper with retry tolerance for antivirus/indexing locks.

**New File**: [scripts/tidy/io_utils.py](../scripts/tidy/io_utils.py)

**Functions**:
- `atomic_write(path, content)`: Temp-file + replace pattern with retry logic
- `atomic_write_json(path, data)`: JSON wrapper with consistent formatting
- `safe_read_json(path, default)`: Read with fallback on corruption

**Retry Logic** ([scripts/tidy/io_utils.py:38-61](../scripts/tidy/io_utils.py#L38-L61)):
- Up to 3 retry attempts on replace failure
- Exponential backoff (100ms, 200ms, 300ms)
- Windows antivirus/indexing tolerance

**Integration**:
- Queue save refactored: [scripts/tidy/pending_moves.py:165-185](../scripts/tidy/pending_moves.py#L165-L185)
- Lock renewal uses atomic replace: [scripts/tidy/lease.py:130-143](../scripts/tidy/lease.py#L130-L143)

---

### 4. Documentation Link Drift Checker ✅

**Problem**: Navigation docs (README.md, INDEX.md, BUILD_HISTORY.md) reference files that have been moved/archived → "two truths" confusion.

**Solution**: Lightweight script to validate file references in core navigation docs.

**New File**: [scripts/check_doc_links.py](../scripts/check_doc_links.py)

**Scope (BUILD-158 v1)**:
- `README.md`
- `docs/INDEX.md`
- `docs/BUILD_HISTORY.md`

**Patterns Detected**:
- Markdown links: `[text](path/to/file.md)`
- Backtick paths: ``path/to/file.txt``
- Direct refs: `file.md`

**Usage**:
```bash
# Check for broken links
python scripts/check_doc_links.py

# Verbose mode (show valid links too)
python scripts/check_doc_links.py --verbose
```

**Exit Codes**:
- 0: All links valid
- 1: Broken links detected

**Future Extensions** (deferred to P2/P3):
- `--deep` mode: Scan all BUILD_*.md files
- External URL validation (HTTP HEAD requests)
- Link graph analysis (detect circular refs, orphans)

---

## Acceptance Criteria Met

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Lease acquisition is atomic (no race conditions) | ✅ PASS | Uses `os.O_CREAT \| os.O_EXCL` |
| Stale locks auto-broken after TTL + grace period | ✅ PASS | Test: `test_stale_lock_is_broken` |
| Malformed locks handled gracefully | ✅ PASS | Test: `test_malformed_lock_is_broken` |
| Heartbeat renewal extends TTL | ✅ PASS | Test: `test_renew_extends_ttl` |
| Ownership verification prevents stolen lock renewal | ✅ PASS | Test: `test_renew_detects_ownership_change` |
| Tidy acquires lease even for dry-run | ✅ PASS | Lines 1313-1331 |
| Lease released in finally block | ✅ PASS | Lines 1706-1709 |
| Atomic writes tolerate antivirus/indexing locks | ✅ PASS | Retry logic with 3 attempts |
| Doc link checker detects broken references | ✅ PASS | Found 43 broken links in navigation docs |
| All tests pass (16/16) | ✅ PASS | See test results below |

---

## Files Modified/Created

### New Files

1. **scripts/tidy/lease.py** (+310 lines)
   - Lease class with acquire/renew/release
   - Stale lock detection + breaking
   - Ownership verification
   - Heartbeat renewal

2. **scripts/tidy/io_utils.py** (+122 lines)
   - `atomic_write()` with retry tolerance
   - `atomic_write_json()` wrapper
   - `safe_read_json()` with corruption fallback

3. **scripts/check_doc_links.py** (+220 lines)
   - File reference extraction (markdown links, backticks)
   - Validation against repo filesystem
   - Summary reporting

4. **tests/tidy/test_lease.py** (+430 lines)
   - 16 comprehensive tests covering all scenarios
   - Edge cases: stale locks, malformed locks, concurrent access
   - 100% pass rate

### Modified Files

1. **scripts/tidy/tidy_up.py** (+50 lines)
   - Lease acquisition before execution ([lines 1313-1331](../scripts/tidy/tidy_up.py#L1313-L1331))
   - Heartbeat renewal at phase boundaries (3 locations)
   - Lease release in finally block ([lines 1706-1709](../scripts/tidy/tidy_up.py#L1706-L1709))
   - CLI flags for lease configuration ([lines 1286-1292](../scripts/tidy/tidy_up.py#L1286-L1292))

2. **scripts/tidy/pending_moves.py** (+5 lines, -12 lines net)
   - Refactored `save()` to use `atomic_write_json()` ([lines 165-185](../scripts/tidy/pending_moves.py#L165-L185))
   - Import io_utils module

---

## Testing & Validation

### Test Suite Results

```bash
$ pytest tests/tidy/test_lease.py -v
========================== 16 passed, 87 warnings in 22.86s ==========================

Test Coverage:
- Basic acquire/release: 4 tests ✅
- Stale lock detection: 3 tests ✅
- Heartbeat renewal: 4 tests ✅
- Concurrent access: 2 tests ✅
- Edge cases: 3 tests ✅
```

**Key Tests**:
1. `test_acquire_and_release`: Basic lifecycle works
2. `test_acquire_timeout`: Concurrent acquisition times out correctly
3. `test_stale_lock_is_broken`: Expired locks auto-broken
4. `test_malformed_lock_is_broken`: Corrupt locks treated as stale
5. `test_renew_extends_ttl`: Heartbeat extends expiry
6. `test_renew_detects_ownership_change`: Ownership verification works
7. `test_serial_acquisition`: Multiple processes can acquire serially
8. `test_zero_ttl`: Edge case of immediate expiry handled

### Manual Validation

1. **Concurrent Tidy Test**:
   ```bash
   # Terminal 1
   python scripts/tidy/tidy_up.py --execute &

   # Terminal 2 (started 1 second later)
   python scripts/tidy/tidy_up.py --execute
   ```
   ✅ Second process waits for lease or times out with clear message

2. **Dry-Run Lease Test**:
   ```bash
   python scripts/tidy/tidy_up.py --dry-run
   ```
   ✅ Shows `Lease acquired: True` in output

3. **Doc Link Checker Test**:
   ```bash
   python scripts/check_doc_links.py
   ```
   ✅ Detected 43 broken links (historical references that moved)

---

## Architecture Decisions

### AD-26: Fail-Open vs Fail-Closed for Malformed Locks

**Decision**: Treat malformed/unreadable locks as **immediately stale** (fail-open).

**Rationale**:
- Corrupt lock files are rare (disk errors, manual editing, crashes mid-write)
- Waiting for age threshold (TTL + grace) would deadlock legitimate operations
- Risk of breaking a "valid but unreadable" lock is low vs cost of deadlock
- Ownership token prevents accidental renewal of stolen locks (defense-in-depth)

**Alternatives Considered**:
- Wait for age threshold → rejected (deadlock risk too high)
- Require manual intervention → rejected (breaks automation)

### AD-27: Dry-Run Acquires Lease

**Decision**: Dry-run mode acquires lease (same as execute mode).

**Rationale**:
- Prevents concurrent dry-run + execute conflicts (confusing mixed output)
- Dry-run reads queue state, which could be corrupted by concurrent execute
- Enables future parallelism planning (dry-run for reporting while execute runs)
- Escape hatch: `--no-lease` for users who need concurrent dry-run (rare)

**Alternatives Considered**:
- Dry-run skips lease → rejected (race condition on queue reads)
- Dry-run uses separate read-only lock → deferred to P2 (added complexity)

### AD-28: Heartbeat Renewal at Phase Boundaries

**Decision**: Renew lease at the start of each major phase (Phase 1, 2, 3).

**Rationale**:
- Phases can be long (Phase 3 consolidation = 5-10 min on large archives)
- Phase-boundary renewal is simple (3 callsites vs timer thread)
- Best-effort renewal (failure logged but not fatal)
- 30-min TTL covers typical tidy runs even without renewal

**Alternatives Considered**:
- Timer-based renewal (every N seconds) → rejected (threading complexity)
- Renewal inside long loops → rejected (tight coupling, performance)
- No renewal (rely on 30-min TTL) → rejected (first-run can exceed 30 min)

### AD-29: Atomic Write Retry Count (3 attempts)

**Decision**: 3 retry attempts with exponential backoff (100ms, 200ms, 300ms).

**Rationale**:
- Windows antivirus/indexing typically releases locks within 500ms
- 3 attempts = ~600ms max delay (acceptable for tidy operations)
- More retries risk hiding real permission issues (infinite loops)

**Alternatives Considered**:
- Unlimited retries → rejected (masks real errors)
- Zero retries → rejected (fails on transient antivirus locks)
- 10+ retries → rejected (excessive delay for user-facing tool)

### AD-30: Doc Link Checker Scope (Navigation Files Only)

**Decision**: v1 scans only README.md + docs/INDEX.md + docs/BUILD_HISTORY.md.

**Rationale**:
- These are the primary entry points for users/AI agents
- Broken links in BUILD_*.md are less critical (historical archives)
- Bounded runtime (~1 second vs 10+ seconds for all docs)
- Future `--deep` mode can add full-repo scanning

**Alternatives Considered**:
- Scan all docs/ + archive/ → rejected (too slow, too many false positives)
- README.md only → rejected (misses INDEX.md navigation drift)

---

## Deferred Work (P2/P3)

### P2: Per-Subsystem Locks

**Not implemented** in this build. Current lease locks entire tidy operation.

**Future work**: Separate locks for queue, archive, autonomous_runs cleanup to enable safe parallelism.

**Design**:
```python
queue_lease = Lease(lock_path=".autonomous_runs/.locks/queue.lock", ...)
archive_lease = Lease(lock_path=".autonomous_runs/.locks/archive.lock", ...)
# Acquire in deterministic order to prevent deadlocks
```

### P3: Lock Ordering for Parallelism

**Not implemented**. No parallelism in BUILD-158.

**Future work**: Define canonical lock acquisition order:
1. `tidy.lock` (coarse-grained, whole-tidy)
2. `queue.lock` (queue operations)
3. `archive.lock` (archive consolidation)

**Deadlock prevention**: Always acquire in order 1→2→3, release in reverse 3→2→1.

### P3: Doc Link Checker --deep Mode

**Not implemented**. v1 scans only navigation files.

**Future extensions**:
- `--deep`: Scan all BUILD_*.md, ARCHITECTURE_*.md, etc.
- `--check-urls`: Validate external URLs (HTTP HEAD requests)
- `--fix-mode`: Auto-update broken links with archive/ equivalents

---

## Impact Summary

**Before BUILD-158**:
- ❌ No protection against concurrent tidy runs
- ❌ Potential queue corruption from race conditions
- ❌ No visibility into documentation link drift
- ❌ Inconsistent atomic write patterns (queue vs reports vs locks)

**After BUILD-158**:
- ✅ **Cross-process safety**: Lease prevents concurrent tidy runs
- ✅ **Stale lock recovery**: Crashed processes don't block future runs
- ✅ **Long-run resilience**: Heartbeat renewal prevents premature expiry
- ✅ **Doc link hygiene**: Detects broken references in navigation docs
- ✅ **Unified atomic writes**: Consistent + retry-tolerant file operations

**User Experience Improvement**:
1. **Safety**: Can run tidy in CI + locally without coordination
2. **Reliability**: Crashed tidy doesn't deadlock future runs (auto-recovery)
3. **Visibility**: Clear error message when lease unavailable ("another process running")
4. **Documentation**: Automated detection of stale file references

---

## Next Steps

### Immediate (P2)
- [ ] Fix broken links detected by doc link checker (43 references in navigation docs)
- [ ] Add lease metrics (acquisition time, renewal count) to profiling output

### Future (P3)
- [ ] Per-subsystem locks (queue, archive, autonomous_runs) for safe parallelism
- [ ] Lock ordering for deadlock prevention
- [ ] Doc link checker --deep mode (scan all BUILD_*.md files)
- [ ] External URL validation (HTTP HEAD requests)

---

## Summary

✅ **BUILD-158 COMPLETE**: Tidy system now has **cross-process safety** via lease primitive.

**Core Achievement**: Atomic lease acquisition + stale lock detection + heartbeat renewal = **safe concurrent tidy operations**.

**Foundation for Future Parallelism**: With lease infrastructure in place, future builds can safely introduce:
- Parallel phase execution (Phase 1 + Phase 2 concurrent)
- Background consolidation (archive processing while build continues)
- CI integration (safe tidy runs during automated testing)

**All acceptance criteria met. All tests passing (16/16). Ready for production use.**
