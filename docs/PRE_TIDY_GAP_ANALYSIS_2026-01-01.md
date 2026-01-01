# Pre-Tidy Gap Analysis - 2026-01-01

**Date**: 2026-01-01T23:45:00Z
**Context**: BUILD-150 Archive Nesting Bug + Gap Closure Phases Complete
**Purpose**: Identify remaining gaps before running tidy system against ideal state

---

## Executive Summary

**Current State**: BUILD-150 completed archive nesting fixes and gap-closure phases (A1-A2, B1-B2, C1-C5, D) are implemented and tested. However, the repository root and `.autonomous_runs/` directory contain significant clutter that violates the ideal state described in [docs/IMPLEMENTATION_PLAN_TIDY_IDEAL_STATE_PHASE_E.md](IMPLEMENTATION_PLAN_TIDY_IDEAL_STATE_PHASE_E.md).

**Key Problems**:
1. **25 `.db` files at root** - test/development databases polluting repo root
2. **10+ directories at root that don't belong** - `backend/`, `code/`, `config/`, `fileorganizer/`, `logs/`, `migrations/`, `reports/`, `research_tracer/`, `tracer_bullet/`, `examples/`
3. **`.autonomous_runs/` is messy** - mixed runtime files, old build logs, scattered baselines
4. **`fileorganizer/` project misplaced** - should be under `.autonomous_runs/file-organizer-app-v1/` not root

---

## Gap Analysis by Category

### 1. Root Directory Clutter ⚠️ CRITICAL

#### Database Files (25 files, ~13.5 MB total)

**Problem**: Test and telemetry seed databases scattered at root instead of organized location.

```
autopack.db (2.8 MB) - KEEP (primary dev database)
autopack_legacy.db (2.1 MB) - ARCHIVE
autopack_telemetry_seed*.db (12 files) - ARCHIVE (historical telemetry seeds)
mismatch_*.db (2 files) - ARCHIVE (debug snapshots)
telemetry_seed_*.db (8 files) - ARCHIVE (various telemetry experiments)
test*.db (5 files) - ARCHIVE or DELETE (test artifacts)
```

**Action Required**:
- Keep `autopack.db` at root (active development database)
- Move historical/seed databases to `archive/data/databases/telemetry_seeds/`
- Move test databases to `archive/data/databases/test_artifacts/`
- Update `.gitignore` to prevent future `*.db` proliferation

**Implementation Note**: Root `*.db` pattern is currently **allowed** in `ROOT_ALLOWED_PATTERNS` (line 74 of tidy_up.py). This is too permissive and allows unlimited database clutter.

**Fix**: Change allowlist to explicit files only:
```python
ROOT_ALLOWED_FILES = {
    "autopack.db",  # Primary dev database
    # ... other files
}
# Remove "*.db" from ROOT_ALLOWED_PATTERNS
```

#### Misplaced Directories (10 directories)

| Directory | Current Contents | Should Move To | Reason |
|-----------|------------------|----------------|--------|
| `backend/` | `test_api.py` (13KB) | `scripts/backend/` or `tests/backend/` | Backend test, not a top-level module |
| `code/` | `research_orchestrator.py`, `__init__.py` | `scripts/research/` or archive | Research experiment, not production code |
| `config/` | 11 YAML config files | `src/autopack/config/` or keep at root | Config files belong with framework |
| `fileorganizer/` | Project directories (backend/, frontend/, fileorganizer/) | `.autonomous_runs/file-organizer-app-v1/` | This is the first Autopack project, not framework code |
| `logs/` | Runtime logs | `archive/diagnostics/logs/` | Historical logs belong in archive |
| `migrations/` | Database migrations | `scripts/migrations/` or `src/autopack/migrations/` | Migration scripts |
| `reports/` | Build/analysis reports | `archive/reports/` | Historical reports belong in archive |
| `research_tracer/` | Research experiment | `archive/experiments/research_tracer/` | Superseded research code |
| `tracer_bullet/` | Proof of concept | `archive/experiments/tracer_bullet/` | Historical PoC |
| `examples/` | Example projects | `docs/examples/` or `.autonomous_runs/examples/` | Documentation or project workspace |

**Critical Issue: `fileorganizer/`**
This appears to be the "file-organizer-app-v1" project built with Autopack (mentioned in README.md line 87-88). It should live under `.autonomous_runs/file-organizer-app-v1/` with proper SOT structure, not as a root-level directory.

**Action Required**:
- Move `fileorganizer/` → `.autonomous_runs/file-organizer-app-v1/src/` (or appropriate structure)
- Create `.autonomous_runs/file-organizer-app-v1/docs/` with 6-file SOT
- Update README.md references

### 2. `.autonomous_runs/` Clutter ⚠️ HIGH

#### Problem: Mixed Runtime and Historical Artifacts

**Current State** (50+ items):
```
_shared/                        - OK (shared runtime resources)
autopack/                       - OK (runtime workspace)
api_server.log                  - MOVE to archive/diagnostics/logs/
baseline.json                   - MOVE to baselines/ or delete (orphaned)
baselines/                      - OK (test baseline cache)
batch_drain_sessions/           - OK (runtime workspace)
build*.log (15+ files)          - ARCHIVE (historical build logs)
checkpoints/                    - OK (git checkpoint storage)
diagnostics*/                   - MIXED (some runtime, some historical)
autopack-*/                     - MIXED (old run directories)
build*/                         - MIXED (old run directories)
```

**Action Required**:
1. Move orphaned `.log` files → `archive/diagnostics/logs/autopack/`
2. Identify completed run directories and move to archive
3. Keep only:
   - `_shared/` (shared resources)
   - `autopack/` (runtime workspace)
   - `baselines/` (test baseline cache)
   - `checkpoints/` (checkpoint storage)
   - Active project directories (e.g., `file-organizer-app-v1/`)
   - Active run directories (currently executing or recent)

#### Problem: `.autonomous_runs/autopack` Semantics Unclear

**Current Verifier Behavior**: Treats `.autonomous_runs/autopack` as a project and expects 6-file SOT structure.

**Reality**: It's a runtime workspace for Autopack maintenance runs, not a project SOT root.

**Fix Already Implemented**: Lines 216-218 of tidy_up.py skip SOT validation for "autopack":
```python
if project_id == "autopack":
    print("[REPAIR][SKIP] .autonomous_runs/autopack is a runtime workspace (not a project SOT root)")
    return False
```

**Action Required**: Update verifier (`verify_workspace_structure.py`) to match tidy's semantics (skip SOT validation for `autopack`).

### 3. `config/` Directory Decision Point 🤔

**Current State**: 11 YAML configuration files at `c:/dev/Autopack/config/`:
- `diagnostics.yaml`
- `feature_catalog.yaml`
- `memory.yaml`
- `models.yaml` (model intelligence catalog)
- `pricing.yaml`
- `project_types.yaml`
- `stack_profiles.yaml`
- `storage_policy.yaml`
- `tidy_scope.yaml`
- `tools.yaml`
- `templates/` subdirectory

**Question**: Should these live at repo root `config/` or be moved?

**Options**:
1. **Keep at root** - Treat as "configuration files" (like `pyproject.toml`, `pytest.ini`)
   - Pro: Easy to find, conventional location
   - Con: Clutters root namespace

2. **Move to `src/autopack/config/`** - Treat as framework config data
   - Pro: Cleaner root, config lives with code
   - Con: Requires import path updates

3. **Keep at root but document in spec** - Explicitly allow `config/` in `ROOT_ALLOWED_DIRS`
   - Pro: No code changes
   - Con: Perpetuates root clutter

**Recommendation**: **Keep at root** and add to `ROOT_ALLOWED_DIRS` (it's already there). These are framework configuration files used by multiple components, and having them at root makes them easy to find and edit. Document in `WORKSPACE_ORGANIZATION_SPEC.md` that `config/` is an allowed top-level directory for YAML configuration files.

### 4. Tidy System Gaps vs. Phase E Ideal State

Based on [docs/IMPLEMENTATION_PLAN_TIDY_IDEAL_STATE_PHASE_E.md](IMPLEMENTATION_PLAN_TIDY_IDEAL_STATE_PHASE_E.md):

#### Phase E.1: Align spec + verifier with intended "truth sources" ✅ MOSTLY DONE
- Spec already defines canonical guides allowlist
- Verifier needs minor updates to reduce false warnings
- **Gap**: Some legitimate docs flagged as "Non-SOT" (needs verifier alignment)

#### Phase E.2: `.autonomous_runs/autopack` semantics ✅ DONE
- Tidy already skips SOT validation for `autopack` (lines 216-218)
- **Gap**: Verifier still expects SOT structure (needs matching skip logic)

#### Phase E.3: Centralized logging to prevent root clutter ⚠️ NOT DONE
- **Problem**: No centralized logging configuration
- Scripts still write logs to CWD (root)
- **Gap**: Need `src/autopack/logging_config.py` with default log directory
- **Gap**: Need to update scripts to use centralized config

#### Phase E.4: Idempotent consolidation ⚠️ NOT DONE
- **Problem**: Consolidation can duplicate content across runs
- **Gap**: No merge markers or content hashing in ledgers
- **Gap**: No deduplication logic

#### Phase E.5: CI/hooks for prevention ⚠️ NOT DONE
- **Gap**: No CI check for workspace structure violations
- **Gap**: No pre-commit hook to prevent root clutter

---

## Recommended Action Plan (Before Running Tidy)

### Immediate Fixes (Do Before Tidy Run)

1. **Fix Database Allowlist** (HIGH PRIORITY)
   - Update `scripts/tidy/tidy_up.py` lines 73-82
   - Remove `"*.db"` from `ROOT_ALLOWED_PATTERNS`
   - Add `"autopack.db"` to `ROOT_ALLOWED_FILES`
   - This prevents tidy from ignoring 24 databases that should be archived

2. **Update Verifier for `autopack` Workspace** (MEDIUM PRIORITY)
   - Update `scripts/tidy/verify_workspace_structure.py`
   - Skip SOT validation for `.autonomous_runs/autopack` (match tidy behavior)

3. **Document `config/` Directory** (LOW PRIORITY)
   - Update `docs/WORKSPACE_ORGANIZATION_SPEC.md`
   - Explicitly document `config/` as allowed root directory for YAML configs
   - Add to spec that it contains framework configuration (models, pricing, diagnostics, etc.)

### Tidy Run Strategy

After fixes above, run tidy with these steps:

```bash
# Step 1: Dry run to preview changes
python scripts/tidy/tidy_up.py --verbose

# Step 2: Review proposed changes carefully
# - Check database routing (should archive 24 .db files)
# - Check fileorganizer/ routing
# - Check .autonomous_runs/ cleanup

# Step 3: Execute with checkpoint
git checkout -b tidy-cleanup-2026-01-01
python scripts/tidy/tidy_up.py --execute

# Step 4: Verify results
python scripts/tidy/verify_workspace_structure.py

# Step 5: Commit if clean
git add .
git commit -m "chore: Tidy workspace - archive databases, reorganize projects"
```

### Post-Tidy Enhancements (Phase E.3-E.5)

These are NOT blockers for the tidy run, but should be implemented afterward:

1. **Centralized Logging** (Phase E.3)
   - Create `src/autopack/logging_config.py`
   - Default log directory: `archive/diagnostics/logs/autopack/`
   - Update scripts to use centralized config

2. **Idempotent Consolidation** (Phase E.4)
   - Add merge markers to ledger entries (source_path, source_sha, tidy_run_id)
   - Implement deduplication logic in consolidation

3. **CI Prevention** (Phase E.5)
   - Add workspace structure check to `.github/workflows/ci.yml`
   - Create pre-commit hook template for root clutter prevention

---

## Specific File Routing Recommendations

### Database Files
```
autopack.db                          → KEEP at root (active dev DB)
autopack_legacy.db                   → archive/data/databases/legacy/
autopack_telemetry_seed.db           → archive/data/databases/telemetry_seeds/
autopack_telemetry_seed_v2.db        → archive/data/databases/telemetry_seeds/
autopack_telemetry_seed_v3.db        → archive/data/databases/telemetry_seeds/
mismatch_api.db                      → archive/data/databases/debug_snapshots/
mismatch_executor.db                 → archive/data/databases/debug_snapshots/
telemetry_seed_debug*.db (3 files)   → archive/data/databases/telemetry_seeds/debug/
telemetry_seed_final_green*.db (7)   → archive/data/databases/telemetry_seeds/final/
telemetry_seed_fullrun.db            → archive/data/databases/telemetry_seeds/
telemetry_seed_v5.db                 → archive/data/databases/telemetry_seeds/
telemetry_seed_v6_pilot.db           → archive/data/databases/telemetry_seeds/
test.db                              → DELETE (orphaned test artifact)
test_auth.db                         → archive/data/databases/test_artifacts/
test_canonical.db                    → archive/data/databases/test_artifacts/
test_dashboard.db                    → archive/data/databases/test_artifacts/
test_slash.db                        → archive/data/databases/test_artifacts/
```

### Directories
```
backend/                → scripts/backend/  (or tests/backend/ if all tests)
code/                   → archive/experiments/research_code/
config/                 → KEEP at root (document in spec)
fileorganizer/          → .autonomous_runs/file-organizer-app-v1/src/
logs/                   → archive/diagnostics/logs/autopack/
migrations/             → scripts/migrations/
reports/                → archive/reports/
research_tracer/        → archive/experiments/research_tracer/
tracer_bullet/          → archive/experiments/tracer_bullet/
examples/               → docs/examples/ (if documentation) or .autonomous_runs/examples/
```

---

## Risk Assessment

### Low Risk
- Database archival (just moving files, can be undone)
- Directory moves to archive (can be undone via git)
- Config documentation (non-code change)

### Medium Risk
- `fileorganizer/` move (requires careful structure setup)
  - **Mitigation**: Create proper SOT structure first, verify paths
- `.autonomous_runs/` cleanup (risk of deleting active run data)
  - **Mitigation**: Only move clearly historical items (old build logs)

### High Risk
- Changing database allowlist (could route wrong files)
  - **Mitigation**: Dry run first, manual review of routing

---

## Success Criteria

After tidy run, workspace should have:

✅ Root directory:
- Only `autopack.db` database (active dev)
- No orphaned `.log` files
- `config/` directory (documented as allowed)
- No `backend/`, `code/`, `fileorganizer/`, `logs/`, `migrations/`, `reports/`, `research_tracer/`, `tracer_bullet/` at root

✅ `.autonomous_runs/`:
- `_shared/`, `autopack/`, `baselines/`, `checkpoints/` (runtime resources)
- `file-organizer-app-v1/` with proper 6-file SOT structure
- No orphaned `.log` files
- Only active run directories (no historical build* directories)

✅ `archive/`:
- 24 historical databases in `archive/data/databases/`
- Historical build logs in `archive/diagnostics/logs/`
- Superseded experiments in `archive/experiments/`
- Historical reports in `archive/reports/`

✅ Verifier clean:
- No false warnings about canonical docs
- No complaints about `.autonomous_runs/autopack` SOT structure
- All actual violations caught and reported

---

## Conclusion

**Before running tidy again**, we need to:

1. ✅ **Fix database allowlist** - Critical to enable proper database archival
2. ✅ **Update verifier for autopack workspace** - Prevent false SOT violations
3. ✅ **Document config/ as allowed** - Clarify spec

**After these fixes**, tidy should successfully:
- Archive 24 historical databases
- Move 10 misplaced directories to proper locations
- Clean up `.autonomous_runs/` historical artifacts
- Verify clean workspace structure

**Phase E.3-E.5 enhancements** can be implemented afterward to prevent future clutter accumulation.
