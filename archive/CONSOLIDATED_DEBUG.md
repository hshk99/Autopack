# Consolidated Debug and Error Reference

**Last Updated**: 2025-11-30
**Auto-generated** by scripts/consolidate_docs.py

## Purpose
Single source of truth for all errors, fixes, prevention rules, and troubleshooting.

---

## Prevention Rules

21. ALWAYS use StaticPool when using SQLite in-memory databases with SQLAlchemy in tests

1. NEVER swallow exceptions silently - always log to debug journal via `log_error()`
2. ALWAYS run executor with `PYTHONPATH=src` to ensure module imports work
3. NEVER assume file_context is a plain dict - use `.get('existing_files', file_context)` to handle both formats
4. ALWAYS set `PYTHONUTF8=1` on Windows to prevent Unicode encoding errors with emojis
5. NEVER commit API keys to git - use environment variables or `.env` files

---

## Resolved Issues


### Timeline

**Date**: 2025-11-29
**Initial Status**: ⚠️ SEPARATE ISSUE - Under Investigation
**Final Status**: ✅ RESOLVED

**Source**: [AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md](C:\dev\Autopack\archive\superseded\AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md)

---


### System Architecture (Post-Fix)

```
autonomous_executor.py
  └─> LlmService.execute_builder_phase()
        └─> ModelRouter.select_model()
        └─> AnthropicBuilderClient.execute_phase()
              └─> _build_user_prompt()  [FIX IS HERE at line 240]
                    └─> files = file_context.get("existing_files", file_context)
                    └─> Debug logging (lines 242-262)
                    └─> Safe iteration over files.items()
```

---

## Issue #3: OpenAI API Key Dependency in Anthropic-Only Configuration

### Timeline

**Date**: 2025-11-29
**Error**: `OpenAIError: The api_key client option must be set either by passing api_key to the client or by setting the OPENAI_API_KEY environment variable`
**First Occurrence**: During test run `fileorg-test-verification-2025-11-29`
**Status**: ✅ RESOLVED

**Source**: [AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md](C:\dev\Autopack\archive\superseded\AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md)

---


## Open Issues

_(No open issues at this time)_

---


### Test isolation: sqlite3.OperationalError no such table
**Status**: OPEN
**Priority**: HIGH
**First Observed**: 2025-11-30
**Run ID**: test-session-2025-11-30
**Phase ID**: conftest-fixture

**Symptom**:
```
Tests failing with sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: runs. In-memory SQLite database tables were being created but lost when connections closed.
```

**Suspected Root Cause**:
In-memory SQLite databases are connection-specific. When using default connection pooling, each new connection gets a fresh empty database.

**Actions Taken**:
- None yet - just discovered

**Next Steps**:
1. Investigate root cause
2. Implement fix
3. Test on a FRESH run (not reusing old run)

---

## Issue #6: Silent Debug Journal Failure - Errors Not Captured


**Fix Applied** (2025-11-30 16:05:00):
Used StaticPool in SQLAlchemy engine creation to ensure all connections share the same in-memory database. Split db_session fixture into db_engine (creates tables) and db_session (creates sessions). Client fixture creates new sessions bound to same engine.

**Files Changed**:
- tests/conftest.py

**Test Run**: pytest-2025-11-30
**Result**: success


**Resolution** (2025-11-30):
Fixed test isolation by using StaticPool for SQLite in-memory database. This ensures all connections in the test share the same database with tables created.

**Verified On Run**: pytest-2025-11-30
**Status**: ✅ RESOLVED

### Timeline

**Date**: 2025-11-30
**Status**: ✅ RESOLVED

**Symptom**: Errors occurring during executor runs (database connection issues, test isolation failures) were not being logged to the debug journal, making post-mortem debugging impossible.

**Root Cause Analysis**:
1. The `debug_journal.py` module redirects to `archive_consolidator.py` which writes to `CONSOLIDATED_DEBUG.md`
2. The `error_recovery.py` system only logs errors with severity != TRANSIENT (line 137)
3. Many exception handlers in `autonomous_executor.py` used bare `except Exception` without calling `log_error()`
4. Silent failures: lines 526-529, 662-663, 706-707 just logged to Python logger, not debug journal

**Files Changed**:
- `src/autopack/autonomous_executor.py` - Added `log_error()` calls to all exception handlers

**Fix Applied** (2025-11-30):
Added `log_error()` calls to capture:
- Phase inner execution failures (line 530-537)
- Patch validation failures (422 errors) (line 658-666)
- API POST builder_result failures (line 677-684)
- API POST auditor_result failures (line 731-738)
- Stale phase reset failures (line 353-360)

**Prevention Rule**: NEVER swallow exceptions silently - always log to debug journal via `log_error()`

---

## Issue #7: Patch Application Pipeline - Corrupt Patch Errors

### Timeline

**Date**: 2025-11-30
**Status**: ✅ RESOLVED

**Symptom**: Phases failing with "corrupt patch at line X" errors when applying LLM-generated patches.

**Root Causes Identified**:
1. LLM-generated patches have incorrect line numbers in @@ hunk headers
2. Empty file diffs (e.g., `__init__.py`) missing `--- /dev/null` and `+++ b/path` headers
3. New file patches failing with "already exists in working directory" errors
4. Line counts in hunk headers don't match actual content
5. Trailing empty lines causing mismatches

**Files Changed**:
- `src/autopack/governed_apply.py` - Added comprehensive patch repair pipeline

**Fix Applied** (2025-11-30):
Added repair methods to `GovernedApplyPath`:
- `_repair_hunk_headers()`: Fixes incorrect @@ line numbers and counts by parsing actual content
- `_fix_empty_file_diffs()`: Adds missing headers for empty files (e69de29 hash detection)
- `_remove_existing_files_for_new_patches()`: Deletes conflicting files before applying "new file" patches
- `_sanitize_patch()`: Fixes missing +/- prefixes in hunk content
- `_apply_patch_directly()`: Fallback direct file write when git apply fails

**Fallback Chain**: strict → lenient (`--ignore-whitespace -C1`) → 3-way merge (`-3`) → direct file write

**Prevention**: LLM prompts updated to output raw git diff format without JSON wrapping or markdown fences

---

## Troubleshooting: Executor Stuck Phases and Self-Healing

**Source**: [ref1.md](C:\dev\Autopack\archive\superseded\ref1.md)
**Date**: 2025-11-30

### Issue: Stuck Phases in EXECUTING State

**Symptom**: Phases remain in EXECUTING state indefinitely, preventing run progression.

**Root Causes Identified**:
1. **Silent Executor Crash**: Background executor crashes due to `ModuleNotFoundError: No module named 'autopack'` when `PYTHONPATH` is not set to include `src/`.
2. **Missing Timestamps**: Phases without `updated_at` timestamps cannot be detected as stale by the auto-reset logic.
3. **API Endpoint Mismatch**: The `_update_phase_status` method was using incorrect endpoint (now fixed).

**Resolution**:
- ✅ Fixed `_update_phase_status` to use correct endpoint: `/runs/{run_id}/phases/{phase_id}/update_status`
- ✅ Enhanced stale phase detection to reset phases with missing timestamps
- ✅ Improved error logging to surface API failures
- ✅ Executor now properly resets stuck phases and continues execution

**Prevention**:
- Always run executor with `PYTHONPATH="src"` or ensure `src/autopack` is importable
- Executor automatically detects and resets stale phases on startup
- Enhanced error handling provides clear diagnostics when phase status updates fail

---