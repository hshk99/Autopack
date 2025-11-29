# Debug Journal - FileOrganizer Phase 2

**Purpose**: This journal tracks all errors, fixes, and testing results for the FileOrganizer Phase 2 autonomous run. It prevents repetitive debugging by maintaining a single source of truth for what has been tried and what worked.

## HOW TO USE THIS JOURNAL

**For Cursor/Autopack agents starting a new debugging session:**

1. **READ THIS FILE FIRST** before attempting any fixes
2. Check the "Current Open Issues" section to see what's unresolved
3. Check the "Resolved Issues" section to avoid re-trying failed approaches
4. Pick the highest-priority open issue to work on
5. **UPDATE THIS JOURNAL** with new findings before ending the session
6. When testing a fix, **ALWAYS CREATE A NEW RUN** - never reuse old runs with stale state

---

## Current Open Issues

### Issue #4: Patch Corruption on Large Files
**Status**: OPEN
**Priority**: HIGH
**First Observed**: 2025-11-29
**Run ID**: fileorg-test-verification-2025-11-29

**Symptom**:
```
ERROR: Patch check failed: error: corrupt patch at line 32
ERROR: Patch check failed: error: corrupt patch at line 181
ERROR: Patch check failed: error: corrupt patch at line 808
```

**Pattern**:
- Small patches (UK Pack, Canada Pack) succeed
- Large patches (>500 lines) fail with "corrupt patch" errors
- Corruption happens at varying line numbers

**Suspected Root Cause**:
- Patch truncation during LLM generation or transmission
- Possible JSON formatting conflicts in Builder prompts
- May be related to earlier "literal `...`" issue that was supposedly fixed

**Actions Taken**:
- None yet - just discovered during verification run

**Next Steps**:
1. Investigate Builder prompt in anthropic_clients.py for JSON/diff conflicts
2. Check if there's a response size limit being hit
3. Test with a single large-file phase to isolate the issue

---

### Issue #5: API 500 Errors on Builder Result POST
**Status**: OPEN
**Priority**: MEDIUM
**First Observed**: 2025-11-29
**Run ID**: fileorg-test-verification-2025-11-29

**Symptom**:
```
WARNING: Failed to post builder result: 500 Server Error: Internal Server Error
```

**Pattern**:
- Intermittent - not all builder result POSTs fail
- Appears to correlate with large patches (but not definitively)

**Suspected Root Cause**:
- Server-side error in the API endpoint
- Possible schema mismatch in BuilderResult payload
- Database constraint violation

**Actions Taken**:
- None yet

**Next Steps**:
1. Check API server logs for the 500 error details
2. Verify BuilderResult schema matches API expectations
3. Test with smaller payload to isolate issue

---


### Test Error - Debug Journal Integration
**Status**: OPEN
**Priority**: LOW
**First Observed**: 2025-11-29
**Run ID**: test-journal-2025-11-29
**Phase ID**: N/A

**Symptom**:
```
Testing the debug journal system integration
```

**Suspected Root Cause**:
This is a test to verify the journal module works

**Actions Taken**:
- None yet - just discovered

**Next Steps**:
1. Investigate root cause
2. Implement fix
3. Test on a FRESH run (not reusing old run)

---

## Resolved Issues


**Fix Applied** (2025-11-29 22:06:46):
Applied test fix to verify journal integration

**Files Changed**:
- src/autopack/debug_journal.py

**Test Run**: test-journal-2025-11-29
**Result**: success


**Resolution** (2025-11-29):
Test completed successfully - journal system is working

**Verified On Run**: test-journal-2025-11-29
**Status**: ✅ RESOLVED

### Issue #1: Slice Error in Anthropic Builder
**Status**: RESOLVED
**Date Resolved**: 2025-11-29
**Commit**: [See AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md]

**Symptom**:
```python
TypeError: 'dict' object is not subscriptable
# in list(files.items())[:5]
```

**Root Cause**:
- `file_context` was wrapped in `{"existing_files": {...}}`
- Code expected direct dict but got wrapped version
- `.items()` failed because dict subscripting `[slice]` isn't valid

**Fix Applied**:
```python
# anthropic_clients.py line 240
files = file_context.get("existing_files", file_context)
for file_path, content in list(files.items())[:5]:
```

**Verification**:
- Run `fileorg-test-verification-2025-11-29` executed 8 iterations without slice errors
- 2 phases completed successfully (UK Pack, Canada Pack)

---

### Issue #2: OpenAI API Key Dependency in Anthropic-Only Mode
**Status**: RESOLVED
**Date Resolved**: 2025-11-29
**Commit**: [See AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md]

**Symptom**:
```
OpenAIError: The api_key client option must be set either by passing api_key to the client or by setting the OPENAI_API_KEY environment variable
```

**Root Cause**:
- Unconditional import of OpenAI clients at module load time
- OpenAI package tries to read env var during initialization
- System should support Anthropic-only, OpenAI-only, or both

**Fix Applied**:
```python
# llm_service.py lines 22-30
try:
    from .openai_clients import OpenAIAuditorClient, OpenAIBuilderClient
    OPENAI_AVAILABLE = True
except (ImportError, Exception) as e:
    OPENAI_AVAILABLE = False
    OpenAIAuditorClient = None
    OpenAIBuilderClient = None
```

**Verification**:
- Import tests passed for all three configurations (Anthropic-only, OpenAI-only, both)
- Run `fileorg-test-verification-2025-11-29` initialized successfully with both APIs

---

### Issue #3: Unicode Encoding Error (Emoji in Logs)
**Status**: RESOLVED
**Date**: Earlier (before current session)

**Symptom**:
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2705'
```

**Root Cause**:
- Windows console uses cp1252 encoding by default
- Logging code used emoji characters

**Fix Applied**:
- Pre-emptive `PYTHONUTF8=1` environment variable
- Error recovery module auto-applies this fix

**Verification**:
- Run `fileorg-test-verification-2025-11-29` started successfully with encoding fix

---

## Critical Lesson: Never Reuse Old Runs for Testing New Fixes

**Why This Matters**:

When you fix a bug in the code and then test it on an **old run** (one created before the fix), you're often testing against:
- Old phase definitions that may not exercise the new code path
- Stale phase states (EXECUTING phases that block new work)
- Cached or pre-computed results
- Old configuration that doesn't match current code

**Result**: The fix appears not to work, leading to wasted debugging cycles.

**Protocol Going Forward**:

1. **After implementing a fix**: Create a NEW run with a new run_id
2. **Fresh workspace**: Use a clean checkout or ensure workspace reflects latest code
3. **Clear state**: No phases in EXECUTING, all start from QUEUED
4. **Document the test**: Record in this journal which run_id was used to verify which fix

**Example**:
- ❌ BAD: Fix slice error, test on `fileorg-phase2-beta` (created days ago)
- ✅ GOOD: Fix slice error, create `fileorg-test-slice-fix-2025-11-29`, test on fresh run

---

## Run History

### fileorg-test-verification-2025-11-29
**Date**: 2025-11-29
**Purpose**: Verify Issues #1 (slice) and #2 (API key) fixes
**Result**: PARTIAL SUCCESS
**Details**:
- ✅ Both fixes confirmed working (no slice or API key errors)
- ✅ 2/9 phases completed (UK Pack, Canada Pack)
- ❌ 6/9 phases failed with NEW issues (patch corruption)
- ⏸️ 1/9 phase not attempted (timeout)

**Key Finding**:
The system no longer fails at infrastructure initialization. It now fails during patch application, proving Issues #1 and #2 are truly resolved. This revealed NEW issues (#4 and #5) which are expected in "onion debugging."

---

## Next Session Checklist

When starting a new debugging session:

- [ ] Read this DEBUG_JOURNAL.md file completely
- [ ] Check "Current Open Issues" for highest priority
- [ ] Review "Resolved Issues" to avoid repeating fixes
- [ ] If testing a fix: CREATE A NEW RUN (don't reuse old ones)
- [ ] Update this journal with findings before ending session
- [ ] Mark issues as RESOLVED only after verification on a FRESH run

---

## References

- **Legacy History**: `AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md` (comprehensive but no longer updated)
- **Run Analysis**: `AUTOPACK_RUN_ANALYSIS_FOR_GPT_REVIEW.md`
- **System Design**: `AUTOPACK_RUN_REVIEW_AND_DEBUG_JOURNAL_SYSTEM.md` (ref5.md)
