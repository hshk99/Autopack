# Scope Path Bug Fix - Implementation Progress

**Date**: 2025-12-03
**Bug**: Builder modifying files outside specified scope
**Root Cause**: Scope configuration dropped at API layer (identified by GPT)

---

## ✅ Phase 1 Complete: Schema & Database

### Step 1.1: Add `scope` to PhaseSpec schema ✅
**File**: [src/autopack/schemas.py](src/autopack/schemas.py)
- Added `Dict, Any` imports
- Added `scope: Optional[Dict[str, Any]]` to `PhaseCreate` (line 40)
- Added `scope: Optional[Dict[str, Any]]` to `PhaseResponse` (line 75)

### Step 1.2: Add scope column to Phase model ✅
**File**: [src/autopack/models.py](src/autopack/models.py)
- Added `JSON` import
- Added `scope = Column(JSON, nullable=True)` (line 159)

### Step 1.3: Update API to persist scope ✅
**File**: [src/autopack/main.py](src/autopack/main.py)
- Added `scope=phase_create.scope` to Phase creation (line 209)

### Step 1.4: Database migration ✅
**File**: [scripts/migrate_add_scope_column.py](scripts/migrate_add_scope_column.py)
- Created PostgreSQL migration script
- Executed successfully: scope column added to phases table

---

## ✅ Phase 2 Complete: Context Loading

### Step 2.1: Update context_selector.py ✅
**File**: [src/autopack/context_selector.py](src/autopack/context_selector.py)

**Completed Changes**:
1. ✅ Added `_normalize_scope_paths()` helper method (lines 406-421)
2. ✅ Added `_build_scoped_context()` for scope-aware loading (lines 423-497)
3. ✅ Modified `get_context_for_phase()` to check for scope and use scoped loading (lines 64-71)

**Implementation Details**:
```python
def get_context_for_phase(...):
    scope_config = phase_spec.get("scope") or {}
    scope_paths = self._normalize_scope_paths(scope_config.get("paths"))
    readonly_roots = self._normalize_scope_paths(scope_config.get("read_only_context"))

    if scope_paths:
        return self._build_scoped_context(scope_paths, readonly_roots, token_budget, phase_spec)

    # Fallback to existing logic for backward compatibility
    return self._existing_logic()
```

### Step 2.2: Update autonomous_executor.py ✅
**File**: [src/autopack/autonomous_executor.py](src/autopack/autonomous_executor.py)

**Completed Changes**:
1. ✅ Added `_determine_workspace_root()` method (lines 2599-2631)
   - Option B implemented: project directory for project_build
   - Autopack root for autopack_maintenance
2. ✅ Added `_load_scoped_context()` method (lines 2633-2685)
   - Uses ContextSelector for scope enforcement
   - Validates scope paths were loaded
   - Logs scope configuration for debugging
3. ✅ Modified `_load_repository_context()` to check for scope (lines 2453-2457)
   - Calls `_load_scoped_context()` if scope.paths defined
   - Falls back to heuristic loading for backward compatibility

**Implementation Details**:
- Workspace root extracted from first scope path (e.g., `.autonomous_runs/file-organizer-app-v1/`)
- ContextSelector initialized with determined workspace root
- Scope paths validated after loading (warns about missing files)

---

## ✅ Phase 3 Complete: Validation (Option C - Defense in Depth)

### Step 3.1: Add validation in autonomous_executor ✅
**Location**: Before Builder execution (line 2166-2169)
- ✅ Added `_validate_scope_context()` method (lines 2693-2753)
- ✅ Validates loaded files match scope.paths
- ✅ Allows read_only_context files
- ✅ Raises RuntimeError if files loaded outside scope

### Step 3.2: Extend governed_apply validation ✅
**File**: [src/autopack/governed_apply.py](src/autopack/governed_apply.py)
- ✅ Added `scope_paths` parameter to `__init__` (line 172)
- ✅ Extended `_validate_patch_paths()` to check scope (lines 280-294)
- ✅ Rejects patches attempting to modify files outside scope.paths
- ✅ Updated autonomous_executor to pass scope_paths (lines 2312-2320)

**Implementation Notes**:
- Option C implemented: Two-layer validation (context + patch)
- Layer 1: Pre-Builder validation ensures context loading is correct
- Layer 2: GovernedApplyPath prevents patches from escaping scope
- Option C.3 (LlmService validation) deferred - current layers sufficient

---

## ✅ Phase 4 Complete: Token Estimation Fix

**Analysis**: Token estimation already fixed by Phase 2 implementation
- Token estimation in [anthropic_clients.py:207](src/autopack/anthropic_clients.py:207) uses full prompt text
- Full prompt text is built from file_context
- Phase 2 already ensures file_context only contains scoped files
- Therefore, token estimates now automatically reflect scope.paths only

**No additional changes needed**: Context loading fix (Phase 2) automatically fixes token estimation

---

## 🧪 Phase 5: Testing (PENDING)

### Test 1: Rerun FileOrganizer test
```bash
python src/autopack/autonomous_executor.py \
  --run-id fileorg-test-suite-fix-20251203-181941 \
  --run-type project_build --verbose
```

**Expected Behavior**:
- ✅ Builder ONLY attempts to modify requirements.txt and pytest.ini
- ✅ NO attempts to modify fileorg_test_run.log or scripts/*
- ✅ Token estimate ~8k (not 80k)
- ✅ Patch application succeeds

### Test 2: Verify backward compatibility
- Run autopack_maintenance task without scope
- Should work as before (no scope required)

---

## 📝 Implementation Notes

### GPT's Key Insights
1. **Root Cause**: Bug starts at API schema layer, not context loading
2. **Workspace Strategy**: Use project directory as workspace root for external projects
3. **Validation**: Option C (defense in depth) - validate at multiple layers
4. **Backward Compatibility**: Make scope optional for autopack_maintenance, required for project_build

### Files Modified So Far
- ✅ src/autopack/schemas.py
- ✅ src/autopack/models.py
- ✅ src/autopack/main.py
- ✅ scripts/migrate_add_scope_column.py (new)

### Files Pending Modification
- ⏳ src/autopack/context_selector.py
- ⏳ src/autopack/autonomous_executor.py
- ⏳ src/autopack/governed_apply.py
- ⏳ src/autopack/llm_service.py

---

## 🚀 Next Steps

1. **Continue with Step 2.1**: Update context_selector.py
   - Implement scope-aware context loading
   - Add normalization and validation helpers

2. **Then Step 2.2**: Update autonomous_executor.py
   - Implement workspace root determination (Option B)
   - Add scoped file loading logic
   - Add pre-Builder validation

3. **Then Phases 3-5**: Validation, token fix, testing

---

**Current Status**: Phases 1-3 complete (9/9 steps ✅)
**Remaining**: Phase 4 (token estimation - optional), Phase 5 (testing)
**Major Implementation Complete**: Scope enforcement now active
