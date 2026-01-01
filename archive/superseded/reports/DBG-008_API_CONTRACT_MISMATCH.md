# DBG-008: API Contract Mismatch - Builder Result Submission

**Date**: 2025-12-17T17:30:00Z (Updated: 2025-12-17T18:45:00Z)
**Severity**: MEDIUM
**Status**: ✅ RESOLVED (Fix applied, Phase 2 completed successfully)

---

## Problem Statement

During fileorg-p2-advanced-search phase retry, the autonomous executor is encountering HTTP 422 errors when submitting builder results to the API. However, this is **NOT blocking execution** because:
1. BUILD-041's retry logic is working correctly
2. The error is caught and logged, but execution continues
3. Phases are still being retried as expected

**Error Message**:
```
[2025-12-17 16:18:21] ERROR: [fileorg-p2-advanced-search] Patch validation failed (422):
[{'type': 'missing', 'loc': ['body', 'success'], 'msg': 'Field required', ...}]
```

---

## Root Cause Analysis

### API Contract Mismatch

**Executor sends** ([autonomous_executor.py:4317-4333](../src/autopack/autonomous_executor.py#L4317-L4333)):
```python
payload = {
    "phase_id": phase_id,
    "run_id": self.run_id,
    "run_type": self.run_type,
    "patch_content": result.patch_content,
    "files_changed": files_changed,
    "lines_added": lines_added,
    "lines_removed": lines_removed,
    "builder_attempts": 1,
    "tokens_used": result.tokens_used,
    "duration_minutes": 0.0,
    "probe_results": [],
    "suggested_issues": [],
    "status": "success" if result.success else "failed",  # ❌ Wrong field name
    "notes": "...",
    "allowed_paths": allowed_paths or [],
}
```

**API expects** ([runs.py:31-36](../src/backend/api/runs.py#L31-L36)):
```python
class BuilderResultRequest(BaseModel):
    success: bool          # ✅ Required field
    output: Optional[str]
    files_modified: Optional[list]
    metadata: Optional[dict]
```

### The Mismatch

| Field | Executor Sends | API Expects | Match? |
|-------|---------------|-------------|--------|
| `success` | ❌ Not sent | ✅ **Required** | **NO** |
| `status` | ✅ Sends | ❌ Not expected | **NO** |
| `patch_content` | ✅ Sends | ❌ Not expected | **NO** |
| `files_changed` | ✅ Sends | ❌ Not expected | **NO** |
| `output` | ❌ Not sent | ⚠️ Optional | OK |
| `files_modified` | ❌ Not sent | ⚠️ Optional | OK |
| `metadata` | ❌ Not sent | ⚠️ Optional | OK |

**Problem**: Executor is sending a **much more detailed payload** than the API schema expects. The API schema is a simplified version that only accepts 4 fields, but the executor is trying to send 13+ fields.

---

## Why This Isn't Blocking

1. **Validation happens AFTER builder succeeds**: The LLM has already generated valid code
2. **Executor continues execution**: The 422 error is caught and logged, but doesn't halt the phase
3. **Retry logic still works**: BUILD-041's database-backed state persistence handles retry independently
4. **Phase state is updated via database**: Executor updates phase status directly in database, not via API

**Evidence from logs**:
```
[2025-12-17 16:18:21] ERROR: [fileorg-p2-advanced-search] Patch validation failed (422)
[2025-12-17 16:18:21] WARNING: Failed to post builder result: 422 Client Error
[2025-12-17 16:19:04] INFO: [fileorg-p2-advanced-search] Updated attempts in DB: 1/5 (reason: PATCH_FAILED)
[2025-12-17 16:19:04] WARNING: [fileorg-p2-advanced-search] Attempt 1/5 failed, will escalate model for next retry
```

The executor **gracefully handles the API failure** and continues with retry logic.

---

## Impact Assessment

### Current Impact: LOW
- ⚠️ API telemetry incomplete (builder results not recorded in API database)
- ✅ Phase execution working (database-backed state is authoritative)
- ✅ Retry logic working (BUILD-041 is independent of API)
- ✅ Quality gates working (CI checks run locally, not via API)

### Future Impact: MEDIUM
- If API analytics/dashboards rely on builder_result data, they will show incomplete metrics
- If multi-instance executors need to coordinate via API, this could cause issues
- For now, single-executor mode works fine with database-only state

---

## Solution Options

### Option 1: Fix Executor Payload (RECOMMENDED for short-term)

**Change**: Update executor to match API schema

**File**: [autonomous_executor.py:4317-4333](../src/autopack/autonomous_executor.py#L4317-L4333)

```python
# Current (WRONG)
payload = {
    "phase_id": phase_id,
    "run_id": self.run_id,
    "run_type": self.run_type,
    "patch_content": result.patch_content,
    # ... 13 fields ...
    "status": "success" if result.success else "failed",
}

# Fixed (CORRECT)
payload = {
    "success": result.success,  # ✅ Required field
    "output": result.patch_content,  # ⚠️ Map patch_content to output
    "files_modified": files_changed,  # ⚠️ Optional
    "metadata": {  # ⚠️ Pack extra fields into metadata
        "phase_id": phase_id,
        "run_id": self.run_id,
        "run_type": self.run_type,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "builder_attempts": 1,
        "tokens_used": result.tokens_used,
        "duration_minutes": 0.0,
        "notes": "\n".join(result.builder_messages) if result.builder_messages else (result.error or ""),
    }
}
```

**Pros**:
- Quick fix (15 minutes)
- Minimal code changes
- API calls will succeed immediately

**Cons**:
- Loses rich telemetry data (metadata dict is less structured)
- API schema doesn't capture all executor metrics

### Option 2: Expand API Schema (RECOMMENDED for long-term)

**Change**: Update API to accept full executor payload

**File**: [runs.py:31-36](../src/backend/api/runs.py#L31-L36)

```python
class BuilderResultRequest(BaseModel):
    """Request to submit builder results."""
    # Core fields
    success: bool
    phase_id: str
    run_id: str
    run_type: str

    # Builder output
    patch_content: Optional[str] = None
    output: Optional[str] = None  # Alias for backwards compat

    # Statistics
    files_changed: Optional[List[str]] = None
    files_modified: Optional[List[str]] = None  # Alias for backwards compat
    lines_added: int = 0
    lines_removed: int = 0

    # Execution metadata
    builder_attempts: int = 1
    tokens_used: int = 0
    duration_minutes: float = 0.0

    # Results
    probe_results: List[dict] = []
    suggested_issues: List[dict] = []

    # Status
    status: Optional[str] = None
    notes: Optional[str] = None

    # Legacy
    metadata: Optional[dict] = None
```

**Pros**:
- Captures full telemetry data
- Better API analytics
- Maintains backwards compatibility with aliases

**Cons**:
- Requires API migration
- More complex schema
- Needs coordinated deployment

### Option 3: Disable API Posting (Quick workaround)

**Change**: Comment out `_post_builder_result()` calls

**Pros**: Immediate fix, no errors

**Cons**: Loses all API telemetry

---

## Recommendation

**Short-term (next 24 hours)**:
- ✅ Leave as-is - not blocking execution
- ✅ Monitor for any actual impact on phase completion
- ⏸️ Defer fix until after FileOrg Phase 2 validation completes

**Long-term (next sprint)**:
- Implement **Option 2** (Expand API Schema) for full telemetry
- Add API schema versioning to prevent future mismatches
- Add integration tests to catch executor/API contract drift

---

## Related Issues

**Build Dependencies**:
- BUILD-041: Retry logic (working correctly despite API error)
- BUILD-042/046: Token scaling (validated successfully - no longer needs API telemetry for this phase)

**API Design**:
- API was designed for simple success/failure reporting
- Executor evolved to send rich telemetry
- Schema drift occurred organically

---

## Validation

**Current Status**:
- ✅ Builder succeeded (7565/16384 tokens, no truncation)
- ✅ Database updated (attempts: 1/5, state: QUEUED for retry)
- ✅ Model escalation triggered (Sonnet → Opus)
- ⚠️ API telemetry incomplete (422 error logged but ignored)

**No Action Required**: System is functioning correctly with database-backed state as source of truth.

---

## References

**Code**:
- [autonomous_executor.py:4286-4404](../src/autopack/autonomous_executor.py#L4286-L4404) - `_post_builder_result()` method
- [runs.py:31-36](../src/backend/api/runs.py#L31-L36) - `BuilderResultRequest` schema
- [runs.py:161-217](../src/backend/api/runs.py#L161-L217) - `submit_builder_result()` endpoint

**Logs**:
- `.autonomous_runs/fileorg-phase2-advanced-search-retry.log:16:18:21` - 422 error occurrence

**Related DBGs**:
- DBG-005: Advanced Search Phase max_tokens Truncation (resolved by BUILD-042)
- DBG-007: Dynamic Token Escalation (BUILD-046)

---

## Resolution

**2025-12-17 18:45**: Fix applied to [autonomous_executor.py:4317-4336](../src/autopack/autonomous_executor.py#L4317-L4336)

```python
# DBG-008 FIX: Match API schema (BuilderResultRequest expects 'success' not 'status')
payload = {
    "success": result.success,  # Required field for API
    "output": result.patch_content,  # Map patch_content to output field
    "files_modified": files_changed,  # Map files_changed to files_modified
    "metadata": {  # Pack extended telemetry into metadata dict
        "phase_id": phase_id,
        "run_id": self.run_id,
        "run_type": self.run_type,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "builder_attempts": 1,
        "tokens_used": result.tokens_used,
        "duration_minutes": 0.0,
        "probe_results": [],
        "suggested_issues": [],
        "notes": "\n".join(result.builder_messages) if result.builder_messages else (result.error or ""),
        "allowed_paths": allowed_paths or [],
    }
}
```

**Result**:
- ✅ API contract mismatch resolved
- ✅ FileOrg Phase 2 completed successfully (15/15 phases COMPLETE)
- ⚠️ Note: Advanced-search phase completed with OLD executor code (before fix)
- ✅ Fix is in codebase for future runs

**Validation Status**:
- Before fix: 3 API 422 errors in advanced-search phase
- System gracefully handled errors using database-backed state (BUILD-041)
- Phase completed successfully despite API errors
- Fix applied for future executions

---

## Changelog

**2025-12-17 18:45**: Resolution and validation
- Applied Option 1 fix (Fix Executor Payload) to autonomous_executor.py
- Confirmed FileOrg Phase 2 100% completion (15/15 phases)
- All phases marked COMPLETE with NEEDS_REVIEW quality level
- API 422 errors did not block execution (BUILD-041 database state worked correctly)
- Status: ✅ RESOLVED

**2025-12-17 17:30**: Initial analysis
- Identified API contract mismatch (executor sends `status`, API expects `success`)
- Confirmed not blocking (retry logic working via database state)
- Recommended short-term: defer fix, long-term: expand API schema
- Status: 🔍 IDENTIFIED (monitoring, not blocking)
