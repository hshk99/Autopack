# Prompt for Cursor Agent: Implement Remaining Gaps from `docs/IMPROVEMENTS_GAP_ANALYSIS.md`

## Objective

Implement **ONLY** the items marked **UNIMPLEMENTED** in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` (Section **8.0.1**). Do **not** refactor unrelated code. Keep PRs small and mechanically verified by CI.

**Important**: Section **8.10 (UI operator-surface upgrades)** is included in the UNIMPLEMENTED list but should be treated as **optional / P2** work and shipped in separate PRs from any P0/P1 items.

## Ground Rules / Watch-outs

- **Do not rewrite historical ledgers**: do not do broad search/replace across `docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/CHANGELOG.md`, or `docs/BUILD-*.md`. Only adjust operator-facing living docs and contract tests.
- **Preserve “one truth”**: if you change a canonical command/path/port, update the relevant contract tests and drift checks so CI blocks regressions.
- **Prefer allowlists over global scans**: contract tests should scan small allowlists of canonical docs, not the entire docs tree.
- **Keep side effects bounded**: no auto-merging. No network calls. No secrets in artifacts.
- **Frontend scope**: do UI work only in the **canonical root Vite frontend** (`src/frontend/`). Do not revive or expand the legacy dashboard frontend under `src/autopack/dashboard/frontend/`.
- **No new LLM calls for UI features**: Section 8.10 should consume **existing** run data/artifacts (DB + filesystem) only.

## CI Map (what will run in PRs)

Key CI jobs (see `.github/workflows/ci.yml` and `.github/workflows/security.yml`):

- **lint**: ruff + black, plus drift checks
- **docs-sot-integrity**: `pytest -q tests/docs/` + workspace verification + docs drift + SOT derived drift
- **test-core**: full core tests against Postgres
- **security**: trivy/codeql diff gates (regression-only blocking)

Your changes must keep these green.

## Implementation Order (do in this order)

### Phase 0 — Establish the “remaining work” list (no code changes yet)

1. Open `docs/IMPROVEMENTS_GAP_ANALYSIS.md`.
2. Use Section **8.0.1 UNIMPLEMENTED backlog** as the authoritative list.
3. Create a short execution checklist in your scratchpad with the IDs (GAP-8.x.y) and planned PR slicing.

### Phase 1 — Decisions (must happen before code changes)

These items are marked 🧭 (decision required). Pick one and record the decision (prefer an ADR entry, or update `docs/ARCHITECTURE_DECISIONS.md` with a new DEC).

- **GAP-8.5.1**: Canonical migration surface
  - Option A: **Alembic-first** (then you must add a real Alembic env and canonical commands)
  - Option B: **scripts-first** (treat `scripts/migrations/` as canonical; add a disciplined “migration runner” pattern; deprecate Alembic dependency or document why it stays)
- **GAP-8.9.1**: guides/cursor docs
  - Option A: mark as **legacy/historical** (label clearly; avoid surfacing them as canonical)
  - Option B: normalize them too (`$REPO_ROOT`, remove workstation paths, align bootstrap guidance)
- **GAP-8.9.2**: `docs/AUTHENTICATION.md` ✅ IMPLEMENTED (DEC-048)
  - Chosen: Option A - rewrite to match `src/autopack/auth/*` and `/api/auth/*`
  - All `src/backend/` paths updated to canonical `src/autopack/auth/` paths
- **GAP-8.9.4**: Python versions
  - Option A: add CI matrix 3.11+3.12
  - Option B: keep CI 3.11 only, but document “3.11 canonical” and add local tooling guidance

### Phase 2 — Mechanical enforcement upgrades (safe, test-driven)

#### GAP-8.4.1: Security baseline system contract tests ✅ IMPLEMENTED

The contract tests referenced in `security/README.md` are now implemented:

- `tests/security/test_update_baseline_determinism.py`: validates baseline format and determinism
- `tests/security/test_normalize_sarif_determinism.py`: normalization determinism (same input SARIF → identical normalized output)
- `tests/security/test_normalize_sarif_schema.py`: SARIF schema validation
- `tests/security/test_diff_gate_semantics.py`: diff gate behavior (new findings cause nonzero exit; no new findings passes)
- `tests/security/test_exemption_classifier.py`: exemption classification for auto-merge decisions

All tests are hermetic (no network access required) and use static fixtures.

#### GAP-8.3.1: Mypy adoption ladder ✅ IMPLEMENTED

**Status**: IMPLEMENTED (2026-01-09)

Implementation:
- Created `config/mypy_allowlist.txt` - list of files that must pass mypy
- Created `scripts/ci/check_mypy_allowlist.py` - CI script to verify allowlist
- Added `[tool.mypy]` section to `pyproject.toml` with staged adoption config
- Updated `.github/workflows/ci.yml` to use allowlist-based mypy (PR-blocking)
- Fixed `src/autopack/exceptions.py` type issues (Optional types)

Allowlist approach:
- Start with small, well-typed files (version.py, __version__.py, exceptions.py)
- Expand progressively by adding files to `config/mypy_allowlist.txt`
- Files on allowlist must pass mypy - no regressions allowed

#### GAP-8.3.2: Re-enable dependency drift enforcement ✅ ALREADY ENFORCED

**Status**: ALREADY IMPLEMENTED (alternative approach)

The original `check_dependency_sync.py` is intentionally disabled because pip-compile output differs between Windows/Linux (hash differences). Instead, the repo uses:

- `scripts/check_requirements_portability.py` - enforces platform markers (pywin32, python-magic)
- Policy: requirements must be generated on Linux/WSL (CI canonical)
- CI job `check_requirements_portability.py` is PR-blocking

This is the correct approach per `security/README.md` "Requirements Regeneration Policy".

### Phase 3 — Runtime TODO closure (behavioral work)

#### GAP-8.2.1: Scope reduction proposal generation wiring

Target: `src/autopack/autonomous/executor_wiring.py`

- Wire `generate_scope_reduction_proposal()` to the canonical LLM abstraction (`LlmService` or the executor’s current call path).
- Requirements:
  - Deterministic prompt construction
  - Strict JSON validation (use existing schema validation patterns)
  - Proposal-only (no destructive apply)
- Tests:
  - Add a unit test suite under `tests/autopack/autonomous/` (or the closest existing location) that:
    - validates prompt shape
    - validates parsing/validation of a representative JSON output
    - ensures safe failure modes (invalid JSON → None + reason, or raises a controlled exception)

### Phase 4 — Quality + doc convergence (optional / polish)

#### GAP-8.7.x: ROADMAP closures (P2)

- **GAP-8.7.2**: Learned rules relevance filters (scope intersection + scope_pattern)
- **GAP-8.7.3**: Continuation recovery robust JSON parsing with error recovery
- **GAP-8.7.1**: Model catalog source-of-truth decision and deterministic refresh tests

These are valuable but can be split into separate PRs; do not mix with P0/P1 changes.

#### GAP-8.9.5: Canonical operator docs list ✅ IMPLEMENTED

Added Section 10 to `docs/GOVERNANCE.md` with:
- Table of canonical operator docs with drift test status
- Clear distinction between canonical vs non-canonical (historical) docs
- Lists 9 canonical docs with drift testing references

#### GAP-8.10.x: UI operator-surface upgrades ✅ IMPLEMENTED

**Status**: IMPLEMENTED (2026-01-09)

All four UI components have been implemented:

- **GAP-8.10.1**: Artifacts panel ✅
  - `src/frontend/pages/Artifacts.tsx` - Plan preview, phase summaries, logs, errors
  - Tabbed interface with overview, phases, logs, and errors views
  - Uses demo data with API fallback (backend endpoints needed)

- **GAP-8.10.2**: Multi-run "Inbox" view ✅
  - `src/frontend/pages/RunsInbox.tsx` - Lists active/completed/failed runs
  - Filter controls by status
  - Quick links to artifacts and progress views

- **GAP-8.10.3**: Browser/Playwright artifacts viewer ✅
  - `src/frontend/pages/BrowserArtifacts.tsx` - Screenshots/HAR/video/trace display
  - Grid display with type filtering and detail modal
  - Download and preview actions
  - Does NOT implement "visual self-healing" per spec

- **GAP-8.10.4**: Enhanced progress visualization ✅
  - `src/frontend/pages/ProgressView.tsx` - Real-time phase timeline
  - Pending approval display with file change preview
  - Redaction support for sensitive files (shows "[REDACTED]")
  - Approve/reject/request changes action buttons

Supporting infrastructure:
- `src/frontend/types/index.ts` - TypeScript types matching backend schemas
- `src/frontend/services/api.ts` - Centralized API client
- `src/frontend/components/StatusBadge.tsx` - Status display component
- `src/frontend/components/ProgressBar.tsx` - Progress visualization
- `src/frontend/components/RunCard.tsx` - Run summary card

Routes added to `src/frontend/App.tsx`:
- `/runs` → RunsInbox
- `/builds/:buildId/artifacts` → Artifacts
- `/builds/:buildId/browser-artifacts` → BrowserArtifacts
- `/builds/:buildId/progress` → ProgressView

## PR Slicing Recommendation (keep cheap + low risk)

1. **PR-A (decisions + docs)**: DEC entries + updates to canonical docs pointing to the chosen migration/auth/docs policy.
2. **PR-B (security contract tests)**: implement tests for baseline format/normalize/diff gate.
3. **PR-C (CI tightening)**: mypy ladder + dependency drift enforcement.
4. **PR-D (runtime TODO)**: scope reduction LLM wiring + tests.
5. **PR-E (optional P2)**: learned rules filters / continuation parsing / model catalog improvements.
6. **PR-F (optional P2 UI)**: GAP-8.10.x UI operator-surface upgrades (Artifacts + Inbox + Viewer + Progress UX)

## Local Verification Commands (run before PR)

Run at minimum:

```bash
python -m pytest -q tests/docs/
python -m pytest -q tests/security/   # if you added these
python -m pytest -q tests/ -m "not research and not aspirational and not legacy_contract"
ruff check src/ tests/
black --check src/ tests/
```

(If you changed frontend-related docs or APIs, ensure `npm run lint` / `npm run type-check` / `npm run build` still works, but do not start servers unless needed.)

## Completion Definition

You are done when **every item** in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` Section **8.0.1** is either:

- implemented and updated to ✅, or
- explicitly marked “won’t do” with a decision and rationale (and removed from the UNIMPLEMENTED backlog).


