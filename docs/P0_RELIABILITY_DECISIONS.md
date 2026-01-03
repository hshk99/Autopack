# P0 Reliability Track - Implementation Summary

**Date**: 2026-01-04
**Focus**: Prevent cascading failures through determinism, isolation, and contract enforcement
**Status**: ✅ Complete (4/4 items)

---

## Overview

This document records the P0 reliability decisions and implementations completed to address the current bottleneck: **system reliability**. All changes prioritize fail-fast behavior, deterministic outputs, and clear API contracts to prevent runtime surprises.

---

## P0.3: Workspace Hygiene - Stray Executor Copies

**Problem**: Multiple stray copies of `autonomous_executor.py` existed (.backup, .bak, .broken) causing import confusion, packaging issues, and debugging hazards.

**Solution**:
- Deleted stray files after verifying canonical file is newer and more complete
- Added CI enforcement via GitHub Actions workflow

**Files Changed**:
- Deleted: `src/autopack/autonomous_executor.py.{backup,bak,broken}`
- Modified: [.github/workflows/verify-workspace-structure.yml:126-143](../.github/workflows/verify-workspace-structure.yml#L126-L143)

**CI Check Added**:
```yaml
- name: Check for stray backup files in src/
  run: |
    stray_files=$(find src/ -type f \( -name "*.backup" -o -name "*.bak" -o -name "*.broken" \) 2>/dev/null || true)
    if [ -n "$stray_files" ]; then
      echo "::error::Found stray backup files under src/ (reliability hazard - P0.3)"
      exit 1
    fi
```

**Result**: Clean workspace with CI enforcement preventing recurrence.

---

## P0.1: Baseline Tracker Run-Scoping and Determinism

**Problem**:
1. Baseline artifacts not scoped by run_id → parallel-run collisions
2. Non-deterministic delta output → unstable CI decisions on retry

**Solution**:
- Pass `run_id` to `TestBaselineTracker` for isolated artifacts
- Sort delta lists (newly_failing, newly_passing, new_collection_errors)

**Files Changed**:
- [autonomous_executor.py:453-457](../src/autopack/autonomous_executor.py#L453-L457) - Pass run_id to baseline tracker
- [test_baseline_tracker.py:295-305](../src/autopack/test_baseline_tracker.py#L295-L305) - Sort delta computation

**Tests Created**:
- [tests/autopack/test_baseline_tracker_replay.py](tests/autopack/test_baseline_tracker_replay.py) - 9 tests validating:
  - JSON serialization determinism
  - Sorted delta output
  - Run-scoped artifacts (`.autonomous_runs/{run_id}/baselines/`, `.autonomous_runs/{run_id}/ci/`)
  - Legacy mode backward compatibility
  - Collection error detection

- [tests/autopack/test_collection_error_blocking.py](tests/autopack/test_collection_error_blocking.py) - 4 tests validating:
  - Blocking without baseline (zero tests → block)
  - Persistent collection errors → block
  - Zero tests detection (exitcode=2)
  - Legitimate zero tests allowed (with baseline)

**Test Results**: ✅ All 13 tests pass

**Result**: Parallel runs isolated, CI decisions stable across retries.

---

## P0.2: Protocol Contract Tests (Executor ↔ FastAPI)

**Problem**: Executor sends custom payload format that doesn't match Pydantic schemas, causing silent data loss.

**Solution**: Create contract tests exposing schema drift between executor payloads and FastAPI endpoint schemas.

**Files Changed**:
- None (tests only - actual fix deferred to P1)

**Tests Created**:
- [tests/autopack/test_api_contract_builder.py](tests/autopack/test_api_contract_builder.py) - 6 tests exposing:
  - Executor sends `output` instead of `patch_content`
  - Executor sends `files_modified` instead of `files_changed`
  - Executor packs data in `metadata` dict instead of top-level fields
  - Executor uses `SUCCESS` instead of `success`
  - Result: Fields validate but data is lost (patch_content=None, files_changed=[], tokens_used=0)

- [tests/autopack/test_api_contract_auditor_422.py](tests/autopack/test_api_contract_auditor_422.py) - 7 tests validating:
  - Auditor result schema compatibility
  - 422 fallback logic (when backend expects BuilderResultRequest at auditor_result endpoint)
  - Missing 'success' field detection
  - Recommendation field values (approve/revise/escalate)
  - Suggested patch schema

**Test Results**: ✅ All 13 tests pass (exposing schema mismatch as intended)

**Key Finding**:
```python
# Executor sends (lines 7977-7996):
{
  "status": "SUCCESS",
  "success": True,
  "output": "diff ...",
  "files_modified": ["foo.py"],
  "metadata": {...}  # All other fields buried here
}

# Schema expects:
{
  "status": "success",
  "patch_content": "diff ...",
  "files_changed": ["foo.py"],
  "tokens_used": 1500,  # Top-level
  # ... other top-level fields
}
```

**Result**: Schema drift documented and tested. Actual fix deferred (requires updating executor payload construction).

---

## P0.4: DB Safety Guardrails

**Problem**: `init_db()` silently creates missing schema via `create_all()` in all environments, risking SQLite/Postgres drift.

**Solution**: Add explicit opt-in flag (`AUTOPACK_DB_BOOTSTRAP`) required for schema creation. Default behavior: fail-fast if schema missing.

**Files Changed**:
- [config.py:51-59](../src/autopack/config.py#L51-L59) - Add `db_bootstrap_enabled` setting
- [database.py:29-76](../src/autopack/database.py#L29-L76) - Add guardrail logic to `init_db()`

**Configuration**:
```python
# config.py
db_bootstrap_enabled: bool = Field(
    default=False,
    validation_alias=AliasChoices("AUTOPACK_DB_BOOTSTRAP", "DB_BOOTSTRAP_ENABLED"),
    description="Allow automatic DB schema creation (disable in production)"
)
```

**Behavior**:
- **Bootstrap DISABLED (default)**:
  - Inspects database for existing tables
  - Fails fast with `RuntimeError` if `runs` table missing
  - Error message instructs: "To bootstrap schema, set environment variable: AUTOPACK_DB_BOOTSTRAP=1"

- **Bootstrap ENABLED** (`AUTOPACK_DB_BOOTSTRAP=1`):
  - Logs warning: "This should ONLY be used in dev/test environments"
  - Calls `Base.metadata.create_all()` to create missing tables

**Tests Created**:
- [tests/autopack/test_db_init_guardrails.py](tests/autopack/test_db_init_guardrails.py) - 5 tests validating:
  - Fail-fast on missing schema (bootstrap disabled)
  - Bootstrap mode creates tables (bootstrap enabled)
  - Validates existing schema (bootstrap disabled)
  - Env variable aliases work (AUTOPACK_DB_BOOTSTRAP + DB_BOOTSTRAP_ENABLED)
  - Missing 'runs' table triggers error (even if other tables exist)

**Test Results**: ✅ All 5 tests pass

**Result**: Production-safe DB initialization. Schema creation requires explicit opt-in.

---

## Test Coverage Summary

| P0 Item | Tests | Status |
|---------|-------|--------|
| P0.3: Stray executor copies | CI enforcement | ✅ Enforced |
| P0.1: Baseline tracker | 13 tests | ✅ All pass |
| P0.2: Protocol contracts | 13 tests | ✅ All pass |
| P0.4: DB guardrails | 5 tests | ✅ All pass |
| **Total** | **31 tests** | **✅ 100% pass** |

---

## Documentation Updates

**README.md** - Clarified:
- Terminology: "parallelism" preferred over "concurrent runs" (no ambiguity with async/await)
- Database intentions: Postgres canonical for production, SQLite for dev/test

---

## Deferred to P1

**P0.2 Schema Mismatch Fix**: Contract tests expose schema drift but don't fix it. Actual fix requires:
- Updating `autonomous_executor.py` lines 7977-7996 (builder payload)
- Updating `autonomous_executor.py` lines 8093-8103 (auditor payload)
- Changing field names and structure to match Pydantic schemas
- Recommended: Create adapter layer to prevent future drift

**P1 Backlog** (not currently requested):
- P1.1: Deterministic changed-files extraction and persistence
- P1.2: Wire in worktree isolation (workspace_manager.py integration)
- P1.3: DB migration discipline (introduce Alembic)

---

## Policy Decisions

1. **Stray File Prevention**: CI enforces zero tolerance for .backup/.bak/.broken files in src/
2. **Run Isolation**: All artifacts must be scoped by run_id to prevent parallel-run collisions
3. **Deterministic Outputs**: All lists/sets used in CI decisions must be sorted
4. **Schema Safety**: Schema creation requires explicit opt-in (`AUTOPACK_DB_BOOTSTRAP=1`)
5. **Contract Testing**: Protocol boundaries require Pydantic schema validation tests
6. **Fail-Fast Philosophy**: Detect problems at initialization time, not runtime

---

## References

- [BUILD_HISTORY.md](BUILD_HISTORY.md) - Historical build phases and decisions
- [README.md](../README.md) - North Star architecture and terminology
- [.github/workflows/verify-workspace-structure.yml](../.github/workflows/verify-workspace-structure.yml) - CI enforcement

---

**Next Steps**: See P1 backlog in main README for deterministic file extraction, worktree isolation, and migration discipline.
