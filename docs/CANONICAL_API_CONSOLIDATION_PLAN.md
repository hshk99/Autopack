# Canonical API Consolidation Plan (Make Autopack 100% “Ready to Run”)

## Goal
Eliminate “dual FastAPI app” drift and make **one canonical Autopack server** that all tooling (executor, parallel/replay scripts, dashboards, A/B, telemetry) targets consistently.

**Canonical server target**: `PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000`

This plan is designed for **clean long‑term** without a risky full reconstruction.

---

## Current state (what’s true in repo)

### Two FastAPI apps exist
- **Supervisor / Autopack**: `autopack.main:app` (`src/autopack/main.py`)
  - Owns run lifecycle endpoints used by the executor (`/runs/start`, `/runs/{run_id}/phases/{phase_id}/update_status`, etc.)
  - Owns many dashboard endpoints (`/dashboard/runs/{run_id}/status`, `/dashboard/usage`, `/dashboard/models`, etc.)
- **Backend**: `src.backend.main:app` (`src/backend/main.py`)
  - Owns some “production hardening” endpoints (enhanced `/health`, consolidated metrics, kill switch behavior, etc.)
  - Has its own auth model (JWT/bearer) and some test suite under `tests/backend/*`

### One known intertwine
- `src/autopack/main.py` imports the backend auth router:
  - `from backend.api import auth as auth_router`
  - So **you cannot delete the backend package immediately** without first migrating auth.

---

## Non‑negotiable invariants (safety + readiness)
- **One canonical server process** for production usage (`autopack.main:app`).
- **One canonical API contract** for:
  - executor
  - parallel/replay tooling
  - dashboard frontend
  - observability endpoints
- **Kill switches default OFF** (explicit opt‑in required).
- **No new LLM calls** as part of API/telemetry.
- **Windows + Postgres** remain first‑class.
- **Backward compatibility strategy**:
  - Keep old endpoints temporarily where feasible, but make canonical endpoints the ones used by all first‑party scripts.

---

## Decision matrix (choose the path that matches “clean long‑term”)

### Decision 1 — What to do with `src/backend/main.py` (server entrypoint)
You want clean long‑term; choose one of these:

#### Option A (recommended): **Hard deprecate backend server**
- `src/backend/main.py` becomes non-runnable (errors with a clear message)
- All docs/scripts point to `autopack.main:app`
- Backend package may still exist as **library** until auth migration is done

Pros: cleanest long‑term, no dual runtime.
Cons: you must ensure all “backend-only” endpoints are moved into autopack first.

#### Option B (transitional): backend server **re-exports** autopack app
- `src/backend/main.py` simply imports `autopack.main:app` and exposes it
- Still only one actual app in memory

Pros: smoothest transition; avoids breaking old docs/scripts immediately.
Cons: less “clean”; still encourages two entrypoints in docs if you’re not strict.

**If you truly want clean long‑term, plan to end at Option A.**

### Decision 2 — What to do with backend auth router

#### Option A (recommended staged): Keep backend auth as library (for now)
- Keep `backend.api.auth` import working
- Move “server-ish” concerns out of backend into autopack first
- Later migrate auth into `autopack/auth/*`

Pros: reduces risk; avoids large security refactor while you stabilize runtime.
Cons: backend package remains present longer.

#### Option B (final): Migrate auth into autopack and delete backend package
- Move JWT/JWKS/login/register/me endpoints into `autopack` namespace
- Update all imports
- Delete `src/backend/` after tests/docs updated

Pros: cleanest end-state.
Cons: riskier; more code movement.

---

## Implementation phases (execute in order)

### Phase 0 — Inventory & lock the canonical contract (1–2 hours)
**Objective**: define the endpoint list that “must work” on `autopack.main:app`.

1. Write down required endpoints:
   - Run lifecycle (executor needs):
     - `POST /runs/start`
     - `GET /runs/{run_id}`
     - `POST /runs/{run_id}/phases/{phase_id}/update_status`
     - `POST /runs/{run_id}/phases/{phase_id}/builder_result`
   - Health:
     - `GET /health` with DB identity + dependency checks + kill switch states
   - Dashboard:
     - existing legacy endpoints already in autopack
     - **plus** consolidated metrics:
       - `GET /dashboard/runs/{run_id}/consolidated-metrics` (kill switch default OFF)
     - Phase 6 stats endpoints
   - Optional but recommended:
     - A/B results endpoints (if you persist them)

2. Ensure first-party scripts reference only endpoints in this canonical list.

**Acceptance**: a single “contract doc” section exists (can be inside README or a new doc).

---

### Phase 1 — Move backend-only endpoints/guards into autopack (core consolidation)
**Objective**: after this phase, running `autopack.main:app` alone is sufficient for all first-party workflows.

1. Port enhanced `/health` behavior into autopack:
   - DB connectivity check
   - optional Qdrant check
   - kill switch state reporting
   - DB identity hash (keep existing semantics)

2. Port consolidated metrics into autopack:
   - `GET /dashboard/runs/{run_id}/consolidated-metrics`
   - kill switch default OFF: require `AUTOPACK_ENABLE_CONSOLIDATED_METRICS=1`
   - pagination/limits:
     - enforce hard cap (e.g., max 10000)
     - reasonable defaults

3. Ensure autopack dashboard schemas include necessary response models.

4. Update docs to mark consolidated endpoint as canonical; keep legacy endpoints as “legacy”.

**Acceptance**:
- `autopack.main:app` serves `/health` with dependency + kill switch fields.
- `autopack.main:app` serves consolidated metrics with kill switch default OFF.
- Existing dashboard endpoints still work.

---

### Phase 2 — Canonicalize auth behavior (consistency for scripts + executor)
**Objective**: no “Bearer vs X-API-Key” drift; one shared dependency.

1. Decide canonical auth header:
   - Prefer `X-API-Key` for executor automation.
   - Support Bearer as compatibility if needed.

2. Create one shared dependency in the canonical server (autopack):
   - `verify_api_key_or_bearer()` (or similar)
   - Make it strict in production when keys are configured; permissive in TESTING/dev if repo expects that.

3. Update scripts (`scripts/run_parallel.py`, replay, ab tooling) to use canonical auth.

**Acceptance**:
- Executor works against canonical server with `X-API-Key`.
- Scripts work against canonical server and do not assume backend-only auth.

---

### Phase 3 — Remove dual server entrypoint (clean long-term)
**Objective**: make it impossible (or strongly discouraged) to run `src.backend.main:app` as a separate control plane.

Choose one (recommended end-state: Option A):

#### Option A: Hard deprecate backend server (cleanest)
- `src/backend/main.py` exits with a clear error message instructing:
  - “Run `uvicorn autopack.main:app`”
- Update docs to remove all references to `backend.main:app` and `src.backend.main:app`
- Update any “next session” prompt docs that mention backend.

#### Option B: Re-export canonical app (transitional)
- `src/backend/main.py` imports and exposes `autopack.main:app`
- Still update docs to prefer autopack.

**Acceptance**:
- There is one documented way to start the server.
- No docs claim “backend can fully replace supervisor” unless backend is re-exporting the same app.

---

### Phase 4 — Contract tests + CI guardrails (prevent future drift)
**Objective**: prevent re-introduction of a second control plane.

1. Add integration tests that boot the canonical app and verify:
   - required run lifecycle endpoints exist
   - health returns DB identity + kill switch fields
   - consolidated metrics kill switch is OFF by default
   - consolidated metrics works when enabled

2. Add a “docs drift” test or simple grep check in CI:
   - fail if docs mention `uvicorn backend.main:app` or `uvicorn src.backend.main:app`
   - (or keep a single explicit “legacy” section if you must)

**Acceptance**:
- CI fails if someone reintroduces backend server as “primary”.
- CI verifies canonical server surface.

---

### Phase 5 — Migrate auth into autopack and delete backend package ✅ COMPLETE

**Status**: ✅ COMPLETE (2025-12-31, commit `4e9d3935`)

1. ✅ Created `src/autopack/auth/*` and ported:
   - JWT key mgmt (RS256, auto-generation for dev/test)
   - login/register/me endpoints (all at `/api/auth/*`)
   - JWKS endpoint (`/api/auth/.well-known/jwks.json`)
   - User model using `autopack.database.Base`
   - Pydantic schemas (UserCreate, Token, UserResponse, etc.)

2. ✅ Updated `autopack.main` to import from `autopack.auth.*` and removed backend auth import.

3. ✅ Removed `src/backend/` package (38 files) and `tests/backend/` (18 files).
   - Migrated auth tests to `tests/test_autopack_auth.py` (14 comprehensive tests)
   - Added JWT settings to `autopack.config.Settings`
   - Enhanced drift checker with 5 auth path validation patterns

**Acceptance** (all met):
- ✅ No imports from `backend` remain in runtime
- ✅ All auth tests moved to autopack (14/14 passing)
- ✅ Contract tests updated and passing (12/12)
- ✅ CI drift detection prevents regression (0 violations)
- ✅ All SOT endpoints preserved at `/api/auth/*`

---

## Risk management & rollback strategy
- Make each phase a separate commit/PR.
- Prefer adding new endpoints to autopack before removing anything.
- Keep environment kill switches OFF by default.
- If a production deployment currently uses backend server, Phase 3 must be delayed until Phase 1–2 validated.

---

## "Definition of done" for "100% ready" ✅ ACHIEVED

All criteria met as of 2025-12-31:

- ✅ One canonical server documented and used by scripts: `autopack.main:app`
- ✅ All first-party scripts and executor aligned to canonical endpoints + auth
- ✅ Consolidated metrics + health hardening live in canonical server
- ✅ Backend server entrypoint removed (package fully deleted)
- ✅ CI has contract tests that enforce the above (12 tests + drift detection)
- ✅ Auth migrated to `autopack.auth` namespace
- ✅ Backend package fully removed (56 files deleted, 7,679 lines)
- ✅ Zero backend imports remain in runtime
- ✅ Full test coverage: 26/26 tests passing (12 contract + 14 auth)


