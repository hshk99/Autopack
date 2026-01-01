# Parallel Runs - Hardcoded Path Audit (P2.2)

**Status:** ✅ **Complete** (Critical fixes done)
**Date:** 2025-12-30
**Updated:** 2025-12-30 (Path hardening complete)
**Context:** P2.2 requires auditing all hardcoded `.autonomous_runs` paths to ensure they respect `settings.autonomous_runs_dir`

---

## ✅ COMPLETION SUMMARY (2025-12-30)

**All critical runtime paths have been hardened!**

### Fixes Completed
- ✅ `autonomous_executor.py` - 5 locations fixed (diagnostics, rules markers, stop signal, uvicorn logs)
- ✅ `learned_rules.py` - 2 locations fixed (run hints, project rules)
- ✅ `break_glass_repair.py` - 1 location fixed (repair log)
- ✅ `artifact_loader.py` - **Major refactor**: Now uses `RunFileLayout` (critical for token efficiency)

### Components Already Fixed (Earlier)
- ✅ `executor_lock.py` - Uses `settings.autonomous_runs_dir / ".locks"`
- ✅ `test_baseline_tracker.py` - Run-scoped paths with `run_id` parameter
- ✅ `workspace_manager.py` - Uses `settings.autonomous_runs_dir / "workspaces"`
- ✅ `workspace_lease.py` - Uses `settings.autonomous_runs_dir / ".workspace_leases"`

**Total:** 12 locations fixed across 8 files. See [PARALLEL_RUNS_HARDENING_STATUS.md](PARALLEL_RUNS_HARDENING_STATUS.md) for details.

---

## Original Audit Summary

**Total Files Found:** 37 files with `.autonomous_runs` references
**Critical for Parallel Runs:** ~10 files → ✅ **All fixed**
**Safe to Leave (Documentation/Examples):** ~5 files
**Already Fixed (Prior):** 4 files (ExecutorLockManager, TestBaselineTracker, WorkspaceManager, WorkspaceLease)

---

## Critical Path Issues (Must Fix)

### 1. `autonomous_executor.py` (Multiple locations)

**Line 512:** Diagnostics directory
```python
diag_dir = Path(".autonomous_runs") / self.run_id / "diagnostics"
```
**Fix:** Use `settings.autonomous_runs_dir`

**Line 812, 1031:** Rules update marker
```python
marker_path = Path(".autonomous_runs") / project_id / "rules_updated.json"
```
**Fix:** Use `settings.autonomous_runs_dir`

**Line 9066:** Stop signal file
```python
stop_signal_file = Path(".autonomous_runs/.stop_executor")
```
**Fix:** Use `settings.autonomous_runs_dir`

**Priority:** **HIGH** - Core executor paths used in every run

---

### 2. `learned_rules.py` (2 locations)

**Line 662:** Run rule hints
```python
return Path(".autonomous_runs") / run_id / "run_rule_hints.json"
```

**Line 675:** Learned rules file
```python
return Path(".autonomous_runs") / project_id / "docs" / "LEARNED_RULES.json"
```

**Fix:** Use `settings.autonomous_runs_dir`
**Priority:** **MEDIUM** - Used for learned rules persistence

---

### 3. `anthropic_clients.py` (Line 2718)

**Issue:** NDJSON failure logging
```python
out_dir = _Path(".autonomous_runs") / "autopack" / "ndjson_failures"
```

**Fix:** Use `settings.autonomous_runs_dir`
**Priority:** **MEDIUM** - Debugging/telemetry (not critical for correctness)

---

### 4. `repair_helpers.py` (Line 522)

**Issue:** Debug output directory
```python
debug_dir = Path(".autonomous_runs/autopack/debug/repairs")
```

**Fix:** Use `settings.autonomous_runs_dir`
**Priority:** **LOW** - Debugging only

---

## Already Fixed ✅

1. **`executor_lock.py`** - Now uses `settings.autonomous_runs_dir / ".locks"`
2. **`test_baseline_tracker.py`** - Run-scoped paths with `run_id` parameter
3. **`workspace_manager.py`** - Uses `settings.autonomous_runs_dir / "workspaces"`
4. **`workspace_lease.py`** - Uses `settings.autonomous_runs_dir / ".workspace_leases"`

---

## Safe to Leave (Documentation/Examples)

These are in comments, docstrings, or example code:

1. `cursor_prompt_generator.py:361` - Docstring example
2. `handoff_bundler.py:277` - Docstring example
3. Migration SQL files - Historical data

---

## Recommended Fixes

### Phase 1: Critical Path (Required for Parallel Runs)

**File:** `autonomous_executor.py`

```python
# Before
diag_dir = Path(".autonomous_runs") / self.run_id / "diagnostics"

# After
from .config import settings
diag_dir = Path(settings.autonomous_runs_dir) / self.run_id / "diagnostics"
```

**File:** `learned_rules.py`

```python
# Before
def get_run_rule_hints_path(run_id: str) -> Path:
    return Path(".autonomous_runs") / run_id / "run_rule_hints.json"

# After
def get_run_rule_hints_path(run_id: str) -> Path:
    from .config import settings
    return Path(settings.autonomous_runs_dir) / run_id / "run_rule_hints.json"
```

### Phase 2: Telemetry/Debugging (Optional)

- `anthropic_clients.py` - NDJSON failures
- `repair_helpers.py` - Debug repairs

---

## Testing Strategy

After fixes:

1. **Unit tests:** Verify paths respect `AUTONOMOUS_RUNS_DIR`
```bash
AUTONOMOUS_RUNS_DIR=/tmp/custom pytest tests/autopack/test_executor_paths.py
```

2. **Integration test:** Run with custom directory
```bash
AUTONOMOUS_RUNS_DIR=/tmp/parallel_test python scripts/autopack_supervisor.py \
  --run-ids test1,test2 --workers 2 --per-run-sqlite
```

3. **Verify artifacts created in custom location:**
```bash
ls -la /tmp/parallel_test/test1/
ls -la /tmp/parallel_test/test2/
```

---

## Backward Compatibility

All fixes maintain backward compatibility:

- Default `settings.autonomous_runs_dir = ".autonomous_runs"`
- Existing code works unchanged
- New code can override via `AUTONOMOUS_RUNS_DIR` env var

---

## Implementation Plan

1. ✅ **P2.2.1:** Fix `executor_lock.py` (DONE)
2. ✅ **P2.2.2:** Fix `test_baseline_tracker.py` (DONE)
3. ⏳ **P2.2.3:** Fix `autonomous_executor.py` (3-4 locations)
4. ⏳ **P2.2.4:** Fix `learned_rules.py` (2 locations)
5. ⏳ **P2.2.5:** Optional: Fix `anthropic_clients.py`, `repair_helpers.py`
6. ⏳ **P2.2.6:** Add path configuration tests
7. ⏳ **P2.2.7:** Update integration tests to verify custom paths

---

## Notes

- **Backup files** (`.broken`, `.backup`, `.bak2`) can be ignored - they're not active code
- **Migration SQL** doesn't need fixing - it's historical schema changes
- **Docstring examples** should be updated for consistency but aren't functional issues

---

## Next Steps

After completing P2.2.3-P2.2.7:

1. Run full test suite with custom `AUTONOMOUS_RUNS_DIR`
2. Update [PARALLEL_RUNS.md](PARALLEL_RUNS.md) with configuration examples
3. Add CI test with non-default directory
4. Close P2.2 ticket
