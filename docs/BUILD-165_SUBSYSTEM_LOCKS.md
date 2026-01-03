# BUILD-165: Per-Subsystem Locks with Canonical Ordering

**Status**: ✅ Complete
**Date**: 2026-01-03
**Related**: [BUILD-158 (Tidy Lock/Lease)](BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md), [BUILD-162 (Lock Status UX)](archive/superseded/reports/BUILD-162_LOCK_STATUS_UX.md)

---

## Executive Summary

Implemented fine-grained subsystem locks for tidy operations to enable safe concurrent mutations and prevent deadlocks as parallelism grows. The system maintains umbrella `tidy.lock` as a safety net while introducing per-subsystem locks with canonical acquisition ordering.

**Key Results**:
- ✅ Created `scripts/tidy/locks.py` with `MultiLock` implementation
- ✅ Integrated into `scripts/tidy/tidy_up.py` with strategic lock acquisition
- ✅ 12 comprehensive tests (100% pass rate)
- ✅ Canonical ordering: `queue → runs → archive → docs`
- ✅ Escape hatch: `--no-subsystem-locks` flag

---

## Problem Statement

As tidy operations grow in complexity and we prepare for eventual parallelism:
1. **Umbrella lock too coarse**: Single `tidy.lock` prevents any concurrent tidy operations
2. **Deadlock risk**: Without canonical ordering, multiple processes could deadlock
3. **Future-proofing**: Need infrastructure for safe concurrent mutations before scheduling/parallelism

---

## Design Decisions

### Canonical Lock Ordering

Locks are **always acquired in this order**, regardless of request order:

```
queue → runs → archive → docs
```

This prevents deadlocks by construction:
- Process A wants `["archive", "queue"]` → acquires `queue`, then `archive`
- Process B wants `["docs", "archive"]` → acquires `archive`, then `docs`
- No circular wait possible

### Release Order

Locks are released in **reverse order** (LIFO):
```
docs → archive → runs → queue
```

Maintains proper nesting semantics.

### Umbrella Lock Retained

- Umbrella `tidy.lock` still acquired for entire run
- Subsystem locks acquired/released around specific mutation phases
- Umbrella provides safety net until subsystem locks proven stable
- Can be disabled with `--no-subsystem-locks` (escape hatch)

---

## Implementation

### File Structure

```
scripts/tidy/locks.py          # MultiLock implementation
scripts/tidy/tidy_up.py         # Integration points
tests/tidy/test_subsystem_locks.py  # 12 comprehensive tests
```

### Lock Acquisition Points

| **Phase** | **Subsystem Locks** | **Rationale** |
|-----------|---------------------|---------------|
| Phase -1 (Queue retry) | `queue` | Retrying pending moves modifies queue state |
| Phase 0.5 (.autonomous_runs cleanup) | `runs`, `archive` | Cleanup touches both run dirs and archive |
| Phase 1-2 (Execute moves) | `queue`, `archive`, `docs` | Moves affect all three subsystems |
| Phase 3 (Archive consolidation) | `archive`, `docs` | Consolidation touches archive and docs |

### Usage Example

```python
from locks import MultiLock

multi_lock = MultiLock(
    repo_root=repo_root,
    owner="tidy_up:phase1",
    ttl_seconds=1800,
    timeout_seconds=30,
    enabled=True  # Set to False to disable
)

# Acquire locks in canonical order
multi_lock.acquire(["archive", "queue"])  # → queue, archive

try:
    # ... mutation work ...
    multi_lock.renew()  # Renew all held locks
finally:
    multi_lock.release()  # Release in reverse: archive, queue
```

### Command-Line Interface

```bash
# Default: subsystem locks enabled
python scripts/tidy/tidy_up.py --execute

# Disable subsystem locks (escape hatch)
python scripts/tidy/tidy_up.py --execute --no-subsystem-locks
```

---

## Test Coverage

**12 tests, 100% pass rate**:

| **Test** | **Purpose** |
|----------|-------------|
| `test_canonical_order_enforcement` | Verifies locks acquired in canonical order |
| `test_reverse_release_order` | Verifies LIFO release order |
| `test_lock_contention_timeout` | Timeout behavior when locks held |
| `test_disabled_mode` | No-op when `enabled=False` |
| `test_renew_all_locks` | TTL renewal for all held locks |
| `test_partial_acquisition_cleanup` | Cleanup on partial acquisition failure |
| `test_held_locks_reporting` | Correct reporting of held locks |
| `test_double_acquire_raises` | Error on double acquisition |
| `test_unknown_lock_names_warning` | Warning for unknown subsystems |
| `test_integration_with_umbrella_lock` | Compatibility with umbrella lock |
| `test_canonical_order_constant` | LOCK_ORDER definition correct |
| `test_lock_path_generation` | Lock path generation correct |

Run tests:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///:memory:" \
  python -m pytest tests/tidy/test_subsystem_locks.py -v
```

---

## Safety Features

### 1. Partial Acquisition Cleanup

If lock acquisition fails mid-sequence, all previously acquired locks are released:

```python
# Attempting ["queue", "archive", "docs"]
# If "archive" acquisition fails:
#   → "queue" is automatically released
#   → Exception raised with clear message
```

### 2. Ownership Verification

Locks track ownership and verify on renewal:
```python
lease.owner = "tidy_up:phase1:queue"
```

If lock is stolen or expired, renewal fails with clear error.

### 3. Timeout Configuration

```python
MultiLock(
    timeout_seconds=30,  # Wait up to 30s for each lock
    ttl_seconds=1800     # Locks expire after 30 minutes
)
```

### 4. Disabled Mode

When `enabled=False`, all operations are no-ops:
- No lock files created
- No blocking waits
- Safe escape hatch for debugging

---

## Future Enhancements

### Eventual Subsystem Lock Migration

Once proven stable, consider:
1. **Phase-specific umbrella removal**: Some phases could run without umbrella lock
2. **Fine-grained queue locks**: Separate locks for different queue types
3. **Read/write lock distinction**: Allow concurrent reads, exclusive writes

### Monitoring

Add metrics for:
- Lock acquisition times
- Lock contention frequency
- Subsystem lock usage patterns

---

## Migration Path

**Current (BUILD-165)**:
```
[Umbrella tidy.lock]
  ↳ [Phase -1: queue lock]
  ↳ [Phase 0.5: runs + archive locks]
  ↳ [Phase 1-2: queue + archive + docs locks]
  ↳ [Phase 3: archive + docs locks]
```

**Future (when proven stable)**:
```
[No umbrella lock]
  ↳ [Independent phase execution with subsystem locks only]
  ↳ [Parallel phase execution where safe]
```

---

## Acceptance Criteria

✅ **All criteria met**:
- ✅ Canonical acquisition order enforced
- ✅ Reverse release order (LIFO)
- ✅ Lock contention handled with clear timeouts
- ✅ Umbrella lock compatibility maintained
- ✅ Escape hatch (`--no-subsystem-locks`)
- ✅ Comprehensive test coverage (12 tests)
- ✅ No deadlocks by construction
- ✅ `--lock-status --all` shows subsystem locks

---

## References

- [Lease Implementation](../scripts/tidy/lease.py)
- [MultiLock Implementation](../scripts/tidy/locks.py)
- [Tidy Up Integration](../scripts/tidy/tidy_up.py)
- [Test Suite](../tests/tidy/test_subsystem_locks.py)
- [BUILD-158: Tidy Lock/Lease](BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md)
