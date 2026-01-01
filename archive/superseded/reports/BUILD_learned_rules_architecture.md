# BUILD: LEARNED_RULES.json Architecture Restructure

**Date**: 2025-12-13
**Status**: ✅ Implemented
**Category**: build_history

## Context
Standardized the LEARNED_RULES.json file architecture across Autopack and sub-projects. Previously, there was confusion between configuration files and actual learned rules, with files in both `docs/` and `.autonomous_runs/` locations.

## Problem Statement

**Before**:
1. Autopack's `docs/LEARNED_RULES.json` contained **configuration** (category_defaults, safety_profiles) - NOT learned rules
2. File-organizer had TWO files:
   - `docs/LEARNED_RULES.json` (2830 lines of actual learned rules)
   - `.autonomous_runs/file-organizer-app-v1/project_learned_rules.json` (empty, redundant)
3. Code expected rules in `.autonomous_runs/{project}/project_learned_rules.json`
4. Actual rules were in `docs/LEARNED_RULES.json`
5. Architecture mismatch causing confusion

## Changes Made

### 1. Separated Runtime Config from Learned Rules

**Autopack Configuration**:
- Moved config content from `docs/LEARNED_RULES.json` → `.autonomous_runs/autopack/RUN_CONFIG.json`
- Config includes: category_defaults, safety_profiles, high_risk_categories, run_token_cap
- Replaced `docs/LEARNED_RULES.json` with empty rules structure: `{"rules": []}`

**File Content** (`.autonomous_runs/autopack/RUN_CONFIG.json`):
```json
{
  "category_defaults": {
    "prompt": "prompts/",
    "plan": "archive/plans/",
    ...
  },
  "safety_profiles": {
    "low_risk": {...},
    "medium_risk": {...},
    "high_risk": {...}
  },
  "high_risk_categories": [...],
  "run_token_cap": 200000
}
```

### 2. Standardized LEARNED_RULES.json Location

**New Architecture**:
- **Main Autopack**: `docs/LEARNED_RULES.json` (SOT location)
- **Sub-projects**: `.autonomous_runs/{project}/docs/LEARNED_RULES.json` (SOT location)

**Code Changes** (`src/autopack/learned_rules.py:665-675`):
```python
def _get_project_rules_file(project_id: str) -> Path:
    """Get path to project rules file

    Returns the SOT location for learned rules in docs/ directory.
    For main Autopack project: docs/LEARNED_RULES.json
    For sub-projects: .autonomous_runs/{project}/docs/LEARNED_RULES.json
    """
    if project_id == "autopack":
        return Path("docs") / "LEARNED_RULES.json"
    else:
        return Path(".autonomous_runs") / project_id / "docs" / "LEARNED_RULES.json"
```

### 3. Cleaned Up Redundant Files

**Deleted**:
- `.autonomous_runs/autopack/project_learned_rules.json` (newly created empty file)
- `.autonomous_runs/file-organizer-app-v1/project_learned_rules.json` (newly created empty file)

**Preserved**:
- `.autonomous_runs/file-organizer-app-v1/docs/LEARNED_RULES.json` (2830 lines intact)

### 4. Verified Data Integrity

**File-Organizer Rules** (preserved):
```bash
# Before and after verification
wc -l .autonomous_runs/file-organizer-app-v1/docs/LEARNED_RULES.json
# 2830 lines (unchanged)
```

**No Data Loss**:
- All 2830 lines of file-organizer learned rules preserved
- Autopack config safely moved to RUN_CONFIG.json
- Only deleted newly-created empty files

## Impact

**Before**:
- ❌ Confusion between config and learned rules
- ❌ Two files per project (redundant)
- ❌ Code expected one location, files in another
- ❌ LEARNED_RULES.json not part of documented SOT structure

**After**:
- ✅ Clear separation: RUN_CONFIG.json (runtime) vs LEARNED_RULES.json (SOT)
- ✅ Single file per project for learned rules
- ✅ Consistent path resolution in code
- ✅ LEARNED_RULES.json properly integrated into 6-file SOT structure
- ✅ Auto-updates by executor (not tidy)

## SOT File Structure (Updated)

The **6-file SOT structure** in `docs/` is now:

1. **BUILD_HISTORY.md** - Chronological build log
2. **ARCHITECTURE_DECISIONS.md** - Design decisions
3. **DEBUG_LOG.md** - Debugging sessions
4. **FUTURE_PLAN.md** - Unimplemented features
5. **UNSORTED_REVIEW.md** - Manual review queue
6. **LEARNED_RULES.json** - Runtime learned rules (auto-updated by executor)

**Note**: LEARNED_RULES.json is auto-updated by `autonomous_executor.py` at the end of runs via `promote_hints_to_rules()`, NOT by tidy runs.

## Auto-Update Matrix

| File | Updated By | Trigger |
|------|-----------|---------|
| BUILD_HISTORY.md | Tidy (consolidation) | Step 2 of autonomous_tidy.py |
| ARCHITECTURE_DECISIONS.md | Tidy (consolidation) | Step 2 of autonomous_tidy.py |
| DEBUG_LOG.md | Tidy (consolidation) | Step 2 of autonomous_tidy.py |
| FUTURE_PLAN.md | Manual/Tidy | User edits or Step 2 consolidation |
| UNSORTED_REVIEW.md | Classification Auditor | When low-confidence files detected |
| **LEARNED_RULES.json** | **Executor** | **End of autonomous runs** |

## Files Modified

1. `src/autopack/learned_rules.py` (lines 665-675) - Path resolution update
2. `docs/LEARNED_RULES.json` - Replaced config with empty rules `{"rules": []}`
3. `.autonomous_runs/autopack/RUN_CONFIG.json` - Created with moved config
4. `.autonomous_runs/file-organizer-app-v1/docs/LEARNED_RULES.json` - Preserved (2830 lines)

## Verification

```bash
# Check Autopack learned rules (should be empty initially)
cat docs/LEARNED_RULES.json
# {"rules": []}

# Check Autopack runtime config
cat .autonomous_runs/autopack/RUN_CONFIG.json
# {category_defaults, safety_profiles, ...}

# Check file-organizer learned rules (should be intact)
wc -l .autonomous_runs/file-organizer-app-v1/docs/LEARNED_RULES.json
# 2830 lines
```

## Next Steps
- ✅ Architecture clarified and implemented
- ✅ All data preserved, no loss
- ✅ Code updated to use correct paths
- 🎯 Document in ref2.md (technical reference)
