# Prompt for Cursor Agent: Implement GAP-8.10.x (UI Operator Surface) Correctly

## Objective

Implement **GAP-8.10.1–8.10.4** from `docs/IMPROVEMENTS_GAP_ANALYSIS.md` Section **8.10**.

**Non-negotiable**: implement in the **canonical root Vite UI** (`src/frontend/`). Do **not** implement these features in the legacy dashboard UI under `src/autopack/dashboard/frontend/`.

## “What success looks like”

- Users can navigate to:
  - `/runs` (Runs Inbox)
  - `/runs/:run_id/artifacts` (Artifacts viewer)
  - `/runs/:run_id/browser` (Browser artifacts viewer)
  - `/runs/:run_id/progress` (Progress view)
- These pages render real data from the API and do not require new LLM calls.
- Backend provides any missing endpoints (notably **`GET /runs`** and artifact indexing).
- CI is green (frontend CI + docs/SOT + core tests).

## Guardrails / Watch-outs

- **No “claim drift”**: do not mark GAP items ✅ in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` unless code is actually merged and reachable.
- **No filesystem escapes**: artifact file endpoints must prevent path traversal and must not leak secrets.
- **No stack traces / str(e) in responses**: follow the security posture established in PR #93 (server-side logs + correlation IDs).
- **Avoid two-truth UIs**: don’t add parallel implementations in the legacy dashboard frontend.

## Implementation plan (recommended order)

### Step 1 — Backend: list runs (required for inbox)

Add `GET /runs` to `src/autopack/main.py`:
- Supports `limit` and `offset`.
- Returns a lightweight summary per run (id, created_at, updated_at, state, tokens_used, token_cap, current phase summary if available).

Add tests:
- `tests/api/test_runs_list.py` (or similar) verifying:
  - returns 200 + list
  - respects limit/offset

### Step 2 — Backend: artifacts index + file streaming

Add:
- `GET /runs/{run_id}/artifacts/index`
- `GET /runs/{run_id}/artifacts/file?path=<relative>`

Requirements:
- `path` must be constrained to the run directory (block `..`, absolute paths, and drive letters on Windows).
- If you render text inline, run content through existing redaction before returning (or render-only in UI by fetching server-redacted content).

Add tests:
- happy path lists files for a synthetic run dir fixture
- denial path: `path=../secrets.txt` returns 400/403

### Step 3 — Frontend: implement the 4 pages in `src/frontend/pages/`

Create pages:
- `RunsInbox.tsx`
- `RunArtifacts.tsx`
- `RunBrowserArtifacts.tsx`
- `RunProgress.tsx`

Add routes in `src/frontend/App.tsx`:
- `/runs`
- `/runs/:run_id/artifacts`
- `/runs/:run_id/browser`
- `/runs/:run_id/progress`

Add navigation links from `src/frontend/pages/Dashboard.tsx`.

### Step 4 — Frontend: API layer

Implement a small API client for these pages (fetch/axios), using the same base URL strategy already used by the root frontend.

### Step 5 — Verification

Run locally:

```bash
python -m pytest -q tests/docs/
python -m pytest -q tests/   # at least the new API tests
npm run lint
npm run type-check
npm run build
```

### Step 6 — Update the tracker

After merge is ready and pages are reachable, update `docs/IMPROVEMENTS_GAP_ANALYSIS.md`:
- Flip GAP-8.10.1–8.10.4 from ⏳ to ✅
- Add PR number + date


