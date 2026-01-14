# BUILD-182: Workspace Structure Compliance + Enforcement

**Status**: Complete
**Created**: 2026-01-06
**Branch**: `build/182-workspace-structure-compliance`

## Context

The `verify-workspace-structure` workflow reports "Overall Valid: NO" with 3 pre-existing errors, but the workflow run still concludes with Success status. This defeats the purpose of mechanical enforcement.

### Current Violations

1. **Disallowed file at root: `SOT_BUNDLE.md`**
   - Redirect stub pointing to `docs/BUILD-163_SOT_DB_SYNC.md`
   - Created by doc link triage (BUILD-166)

2. **Disallowed file at root: `archive/docs/CONSOLIDATED_DEBUG.md`**
   - Redirect stub pointing to `docs/DEBUG_LOG.md`
   - Created by doc link triage (BUILD-166)

3. **Disallowed subdirectory in docs/: `schemas/`**
   - Contains 6 JSON schema files used programmatically by `src/autopack/schema_validation/json_schema.py`

## Resolution Strategy

### Root File Violations

Both `SOT_BUNDLE.md` and `archive/docs/CONSOLIDATED_DEBUG.md` are redirect stubs with no unique content (the actual content was moved to their canonical locations). These stubs can be safely deleted.

### docs/schemas Violation

The JSON schema files are **code assets**, not documentation:
- They are loaded and used programmatically by `src/autopack/schema_validation/json_schema.py`
- They validate runtime artifacts (IntentionAnchorV2, GapReportV1, PlanProposalV1, AutopilotSessionV1)

**Decision**: Move schemas from `docs/schemas/` to `src/autopack/schemas/` (code-owned location).

This aligns with:
- WORKSPACE_ORGANIZATION_SPEC.md §6: "Only source code belongs here [in src/]"
- JSON schemas being validation code artifacts, not human-readable documentation

### Enforcement Gap

The workflow uses `continue-on-error: true` and the violation check has `exit 1` commented out.

**Fix**: Remove `continue-on-error` and enable the `exit 1` on violations.

## Changes

### Files Deleted
- `SOT_BUNDLE.md` (redirect stub)
- `archive/docs/CONSOLIDATED_DEBUG.md` (redirect stub)

### Files Moved
- `docs/schemas/*.schema.json` → `src/autopack/schemas/`

### Files Modified
- `src/autopack/schema_validation/json_schema.py` - Update schema path resolution
- `.github/workflows/verify-workspace-structure.yml` - Enable enforcement

### Files Created (SOT stubs)
- `.autonomous_runs/file-organizer-app-v1/docs/DEBUG_LOG.md` - Missing SOT stub
- `.autonomous_runs/file-organizer-app-v1/docs/ARCHITECTURE_DECISIONS.md` - Missing SOT stub
- `.autonomous_runs/file-organizer-app-v1/docs/BUILD_HISTORY.md` - Missing SOT stub
- `.autonomous_runs/file-organizer-app-v1/docs/FUTURE_PLAN.md` - Missing SOT stub

Note: The file-organizer-app-v1 project was missing required SOT files in its docs/ directory.
This was a separate pre-existing issue that surfaced during validation.

## Acceptance Criteria

- [x] Workspace verification report shows "Overall Valid: YES"
- [x] Workspace verification report shows 0 errors
- [x] `verify-workspace-structure` workflow fails (non-zero exit) when violations exist
- [x] All existing tests pass
- [x] Schema validation tests pass with new paths

## Testing

```bash
# Verify workspace structure
python scripts/tidy/verify_workspace_structure.py

# Run schema validation tests
pytest tests/ -k schema -v

# Run full test suite
pytest tests/ -v
```

## References

- WORKSPACE_ORGANIZATION_SPEC.md - Canonical workspace rules
- BUILD-181 - Previous build (wiring merge)
- verify_workspace_structure.py - Verification script
