# BUILD-145 P1.1/P1.2/P1.3 Hardening - Handoff Document

## Current Status (2025-12-31)

**Overall**: 95% complete (20/21 tests passing)
- Phase A (P1.1): 92% - Database + functions complete, wiring incomplete
- Phase B (P1.2): 100% - Cache working but in-memory only (spec wants persistence)
- Phase C (P1.3): 100% - All methods implemented

**What's Done**:
- ✅ TokenEfficiencyMetrics database schema
- ✅ record_token_efficiency_metrics() and get_token_efficiency_stats()
- ✅ In-memory embedding cache with content-hash invalidation
- ✅ Per-phase embedding cap with lexical fallback
- ✅ History pack, SOT doc substitution, extended context loading
- ✅ Documentation updated (README, BUILD_HISTORY, DEBUG_LOG)
- ✅ Committed and pushed to branch `phase-a-p11-observability`

**What's Missing** (Critical Gaps vs Specs):

### P0 Issues (Blocking Production Use)

1. **Phase A NOT wired into executor** ❌
   - `select_files_for_context()` exists but `_load_scoped_context()` never calls it
   - Budget telemetry won't record in real runs (only in unit tests)
   - **Impact**: Context budgeting completely bypassed in production

2. **Artifact path layout incompatibility** ❌
   - Test failing: `test_with_substitutions` writes to legacy `.autonomous_runs/<run_id>/phases`
   - `ArtifactLoader` uses `RunFileLayout.base_dir` (new layout)
   - **Impact**: Breaks backward compatibility with existing runs

3. **run_id usage bug in executor** ❌
   - `_load_scoped_context` uses `phase.get("run_id", "")` to init ArtifactLoader
   - Most phase dicts don't have run_id field
   - **Impact**: Artifact loading will fail silently or use wrong path

### P1 Issues (Spec Drift)

4. **Phase A metrics payload incomplete** ⚠️
   - Spec requires: `artifact_tokens_used_est`, `fullfile_tokens_avoided_est`, `context_budget_cap_tokens`, `context_budget_selected_tokens_est`, `substituted_paths` (capped list <=10)
   - Current: Only `artifact_substitutions`, `tokens_saved_artifacts`, basic budget fields
   - **Impact**: Metrics don't match acceptance criteria

5. **Phase B persistence gap** ⚠️
   - Spec requires: "Embedding cache persists locally (file or sqlite)"
   - Current: In-memory only (lost between runs)
   - **Impact**: Cache effectiveness limited to single run

6. **Embedding cap semantics inconsistent** ⚠️
   - config.py comment: "0 = unlimited"
   - context_budgeter code: 0 = disabled
   - **Impact**: Operator confusion, future bugs

### P2 Issues (Nice to Have)

7. **No embedding cache observability**
   - Cache hits/misses not tracked in Phase A metrics
   - Can't measure cache effectiveness

8. **No integration-level test**
   - All tests are unit-level with mocking
   - No end-to-end test of `_load_scoped_context()` flow

---

## Prioritized Task List

### P0: Fix Production Blockers (Must Do)

#### Task 1: Fix artifact path compatibility
**File**: `tests/autopack/test_token_efficiency_observability.py`

**Problem**: Test writes artifacts to legacy path but ArtifactLoader uses new RunFileLayout
```python
# Current (BROKEN):
artifacts_dir = temp_workspace / ".autonomous_runs" / "test-run-123" / "phases"

# Should be:
from autopack.file_layout import RunFileLayout
layout = RunFileLayout(temp_workspace, "test-run-123")
artifacts_dir = layout.base_dir / "phases"
```

**Additional**: Add legacy fallback in `ArtifactLoader.__init__`:
```python
# If new layout dir doesn't exist, check legacy path
if not self.layout.base_dir.exists():
    legacy_path = self.workspace / ".autonomous_runs" / self.run_id
    if legacy_path.exists():
        # Use legacy path for backward compatibility
        self.layout = LegacyLayout(legacy_path)
```

**Acceptance**: `test_with_substitutions` passes, backward compatibility preserved

---

#### Task 2: Wire Phase A context budgeting into executor
**File**: `src/autopack/autonomous_executor.py`

**Location**: In `_load_scoped_context()` after artifact-first loading (around line 7227)

**Current flow**:
1. Load read_only_context files with artifact substitution
2. Return `existing_files` dict directly ❌

**Required flow**:
1. Load read_only_context files with artifact substitution
2. **Call `select_files_for_context()` to apply budget** ✅
3. Return `selection.kept` dict + track BudgetSelection

**Implementation**:
```python
# After artifact loading completes (line ~7227)
from autopack.context_budgeter import select_files_for_context
from autopack.config import settings

# Apply context budgeting
budget_selection = select_files_for_context(
    files=existing_files,  # All loaded files
    scope_metadata=scope_metadata,
    deliverables=phase.get("deliverables", []),
    query=phase.get("description", ""),
    budget_tokens=settings.context_budget_tokens
)

# Replace existing_files with budgeted selection
existing_files = budget_selection.kept

# Store BudgetSelection for telemetry (add to return or instance var)
self._last_budget_selection = budget_selection  # Or return it
```

**Telemetry wiring**: After phase execution, record metrics:
```python
# In execute_phase() after Builder completes
if hasattr(self, '_last_budget_selection') and self._last_budget_selection:
    record_token_efficiency_metrics(
        db=self.db,
        run_id=self.run_id,
        phase_id=phase.get("id", "unknown"),
        artifact_substitutions=artifact_stats.get("substitutions", 0),
        tokens_saved_artifacts=artifact_stats.get("tokens_saved", 0),
        budget_mode=self._last_budget_selection.mode,
        budget_used=self._last_budget_selection.used_tokens_est,
        budget_cap=self._last_budget_selection.budget_tokens,
        files_kept=self._last_budget_selection.files_kept_count,
        files_omitted=self._last_budget_selection.files_omitted_count
    )
```

**Acceptance**: Budget selection active in real runs, metrics recorded

---

#### Task 3: Fix run_id usage bug
**File**: `src/autopack/autonomous_executor.py`
**Location**: `_load_scoped_context()` where ArtifactLoader is initialized

**Problem**:
```python
# BROKEN - phase dict doesn't have run_id
artifact_loader = ArtifactLoader(workspace, phase.get("run_id", ""))
```

**Fix**:
```python
# Use executor's run_id (always available)
artifact_loader = ArtifactLoader(
    workspace=workspace,
    run_id=self.run_id,
    project_id=getattr(self, 'project_id', None)  # If available
)
```

**Acceptance**: Artifact loading uses correct run_id in all cases

---

### P1: Close Spec Drift (Should Do)

#### Task 4: Extend Phase A metrics payload
**File**: `src/autopack/usage_recorder.py`

**Current schema**:
```python
class TokenEfficiencyMetrics(Base):
    artifact_substitutions = Column(Integer)
    tokens_saved_artifacts = Column(Integer)
    budget_mode = Column(String)
    budget_used = Column(Integer)
    budget_cap = Column(Integer)
    files_kept = Column(Integer)
    files_omitted = Column(Integer)
```

**Spec requires** (from phase_a_p11_observability.json line 48):
- `artifact_tokens_used_est` - tokens used from artifacts
- `fullfile_tokens_avoided_est` - tokens saved by not loading full files
- `context_budget_cap_tokens` - budget cap (already have as budget_cap)
- `context_budget_selected_tokens_est` - actual tokens selected (already have as budget_used)
- `substituted_paths` - capped list of paths <=10

**Option A** (extend schema):
```python
class TokenEfficiencyMetrics(Base):
    # ... existing fields ...
    artifact_tokens_used = Column(Integer, nullable=False, default=0)
    fullfile_tokens_avoided = Column(Integer, nullable=False, default=0)
    substituted_paths = Column(JSON, nullable=True)  # List[str], max 10
```

**Option B** (compact JSON blob):
```python
class TokenEfficiencyMetrics(Base):
    # ... existing fields ...
    metrics_detail = Column(JSON, nullable=True)  # Full spec-compliant payload
```

**Migration**: Create `scripts/migrations/add_phase_a_extended_metrics.py`

**Acceptance**: Metrics match spec acceptance criteria (line 48-51)

---

#### Task 5: Resolve Phase B persistence + semantics
**Files**: `src/autopack/context_budgeter.py`, `src/autopack/config.py`

**Issue 1 - Persistence gap**:
Spec (line 45): "Embedding cache persists locally (file or sqlite)"
Current: In-memory dict only

**Decision needed**:
- **Option A**: Implement persistent cache (sqlite or shelve)
  - Pro: Matches spec, cache survives restarts
  - Con: Adds complexity, disk I/O, cache invalidation
- **Option B**: Update spec/docs to "in-memory by design"
  - Pro: Simpler, current implementation is correct
  - Con: Spec drift remains

**Recommendation**: Option B (in-memory is sufficient for per-phase cache)
- Update phase_b_p12_embedding_cache.json line 45
- Update README to clarify "in-memory per-run cache"

**Issue 2 - Cap semantics**:
config.py line 61: `# Maximum number of embedding API calls per phase (0 = unlimited)`
context_budgeter.py line 146: `if call_cap == 0: use_semantic = False`

**Fix**:
```python
# config.py - Update comment
embedding_cache_max_calls_per_phase: int = 100  # 0=disabled, -1=unlimited, >0=capped

# context_budgeter.py - Already correct, just verify comment matches
def _get_embedding_call_cap() -> int:
    """Get per-phase embedding call cap from config/env.

    Returns:
        - 0 = embeddings disabled (fall back to lexical)
        - -1 = unlimited embeddings
        - > 0 = cap at that number
    """
```

**Acceptance**: Semantics consistent across code + docs

---

### P2: Improve Observability (Nice to Have)

#### Task 6: Add embedding cache metrics
**File**: `src/autopack/usage_recorder.py`

Add to TokenEfficiencyMetrics:
```python
# Embedding cache observability
embedding_cache_hits = Column(Integer, nullable=False, default=0)
embedding_cache_misses = Column(Integer, nullable=False, default=0)
embedding_calls_made = Column(Integer, nullable=False, default=0)
embedding_cap_value = Column(Integer, nullable=False, default=0)
embedding_fallback_reason = Column(String, nullable=True)  # "cap_exceeded", "disabled", None
```

Wire into context_budgeter to track cache stats.

---

#### Task 7: Add integration test
**File**: `tests/autopack/test_context_budgeting_integration.py` (NEW)

End-to-end test covering:
1. Create phase with read_only_context + deliverables
2. Call `_load_scoped_context()` (not mocked)
3. Verify artifact substitution happened
4. Verify budget selection happened
5. Verify metrics recorded in database
6. Verify logs emitted correctly

---

## Quick Reference

### Files Modified This Session
- `src/autopack/config.py` - Added context_budget_tokens setting
- `src/autopack/context_budgeter.py` - Fixed embedding cap semantics
- `tests/autopack/test_token_efficiency_observability.py` - Fixed syntax error
- `README.md` - Added P1.1/P1.2/P1.3 section
- `docs/BUILD_HISTORY.md` - Added BUILD-145 entry
- `docs/DEBUG_LOG.md` - Added DBG-071 entry

### Key Code Locations
- **Context budgeting**: `src/autopack/context_budgeter.py:select_files_for_context()`
- **Artifact loading**: `src/autopack/artifact_loader.py:load_with_artifacts()`
- **Executor integration point**: `src/autopack/autonomous_executor.py:_load_scoped_context()` (line ~7019-7227)
- **Telemetry recording**: `src/autopack/usage_recorder.py:record_token_efficiency_metrics()`

### Test Commands
```bash
# Phase A tests (11/12 passing, 1 skipped)
pytest -xvs tests/autopack/test_token_efficiency_observability.py

# Phase B tests (9/9 passing)
pytest -xvs tests/autopack/test_embedding_cache.py

# All token efficiency tests
pytest -xvs tests/autopack/test_token_efficiency_observability.py tests/autopack/test_embedding_cache.py tests/autopack/test_context_budgeter.py
```

### Database Check
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import engine
from sqlalchemy import inspect
inspector = inspect(engine)
print('token_efficiency_metrics exists:', 'token_efficiency_metrics' in inspector.get_table_names())
"
```

---

## Success Criteria (Updated)

After completing P0 tasks:
- ✅ All 21 tests passing (100%)
- ✅ Context budgeting active in real executor runs
- ✅ Metrics recorded for every phase execution
- ✅ Backward compatibility with legacy artifact paths
- ✅ No run_id lookup bugs

After completing P1 tasks:
- ✅ Metrics payload matches Phase A spec acceptance criteria
- ✅ Embedding cache semantics documented and consistent
- ✅ Spec drift resolved or documented as intentional

---

## Watch Outs

1. **Keep logs token-light**: Never log file contents, only counts and small summaries
2. **Cap lists**: Max 10 paths in substituted_paths
3. **Preserve opt-in design**: All features disabled by default
4. **Backward compatibility**: Legacy artifact paths must work
5. **Test determinism**: No network calls, stub embedding providers
6. **Database migrations**: Create idempotent migration scripts

---

## Recommended Approach

**Session 1** (P0 blockers):
1. Fix Task 3 first (run_id bug) - 5 min
2. Fix Task 1 (artifact paths) - 15 min
3. Wire Task 2 (context budgeting) - 30 min
4. Run tests, verify 21/21 passing

**Session 2** (P1 spec drift):
5. Extend metrics schema (Task 4) - 30 min
6. Resolve cache persistence decision (Task 5) - 15 min
7. Update docs to match decisions

**Session 3** (P2 polish):
8. Add embedding cache metrics (Task 6) - 20 min
9. Add integration test (Task 7) - 30 min

**Total estimate**: ~2.5 hours for full completion

---

## Questions for User

Before starting, confirm:
1. **Phase B persistence**: In-memory OK, or implement sqlite cache?
2. **Phase A metrics**: Extend schema with new columns, or use JSON blob?
3. **Priority**: Focus on P0 only, or complete P1 spec alignment too?

---

## Git Status

Branch: `phase-a-p11-observability`
Commit: `f2e8c0f4` - "feat: BUILD-145 P1.1/P1.2/P1.3 Token Efficiency Infrastructure (95% Complete)"
Pushed: ✅ https://github.com/hshk99/Autopack/tree/phase-a-p11-observability

Uncommitted changes:
- `.claude/settings.local.json`, `docs/LEARNED_RULES.json` (ignore)
- Other workspace files not part of Phase A/B/C scope

---

## Pasteable Prompt for Next Session

```
You're finishing BUILD-145 P1.1–P1.3 hardening. Read .autopack/PHASE_ABC_HANDOFF.md for full context.

Priority: Focus on P0 blockers (Tasks 1-3) to get to 100% functional:

1) Fix run_id bug (Task 3): In autonomous_executor.py::_load_scoped_context, change:
   artifact_loader = ArtifactLoader(workspace, phase.get("run_id", ""))
   to: artifact_loader = ArtifactLoader(workspace, self.run_id)

2) Fix artifact path test (Task 1): Update test_with_substitutions to use RunFileLayout.base_dir instead of legacy path. Add legacy fallback in ArtifactLoader.__init__ if new layout missing.

3) Wire context budgeting (Task 2): In _load_scoped_context after artifact loading, call select_files_for_context() with budget_tokens=settings.context_budget_tokens. Store BudgetSelection for telemetry. Wire telemetry recording in execute_phase().

Verify: All 21 tests passing, context budgeting active in real runs, metrics recorded.

After P0: Review P1 tasks (extend metrics schema, resolve cache persistence) and decide priority with user.
```
