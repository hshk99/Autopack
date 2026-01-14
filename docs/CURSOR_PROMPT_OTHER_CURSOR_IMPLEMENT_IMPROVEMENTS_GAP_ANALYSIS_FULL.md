## Mission

Implement the remaining work described in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` in a way that honors Autopack’s thesis:

- **safe**
- **deterministic**
- **mechanically enforceable via CI**
- **one canonical truth** (no “two truths” docs/configs)

You are the implementation agent. You must keep changes coherent, small, and PR-friendly.

---

## Ground Rules (Do Not Violate)

- **No secrets**: never paste real tokens, cookies, API keys, client secrets, refresh tokens. Use placeholders only.
- **No “two truths”**: if docs or configs disagree, choose one canonical and enforce it (docs drift checker + contract tests).
- **Do not rewrite historical ledgers** (`BUILD_HISTORY.md`, `DEBUG_LOG.md`, `CHANGELOG.md`, `ARCHITECTURE_DECISIONS.md`) unless explicitly required. Prefer to fix **living docs** and add guardrails.
- **External side effects require approval**: publishing/listing/trading must be human-approved by default.
- **Windows-safe output**: keep console output ASCII-safe where enforced.
- **Never hand-edit the README SOT summary block**: always regenerate via `python scripts/tidy/sot_summary_refresh.py --execute` (and verify with `--check`).

---

## What to Implement (Source of Truth)

Read and follow:

- `docs/IMPROVEMENTS_GAP_ANALYSIS.md` (primary backlog and decisions)
- `docs/WORKSPACE_ORGANIZATION_SPEC.md` (canonical workspace rules)
- `docs/CANONICAL_API_CONTRACT.md` (canonical endpoints; CI drift-checked)
- `scripts/check_docs_drift.py` (existing drift enforcement patterns)

---

## Implementation Order (Strict Priority)

### Phase 0 — Close remaining P0 “two truths” items

1) **Run layout docs drift (missing `<family>/`)**

- Update the operator-facing living docs listed in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` to use:
  - `.autonomous_runs/<project>/runs/<family>/<run_id>/...`
  - Use `<run_id>` (underscore), not `<run-id>`.
- Add mechanical enforcement (choose one):
  - **Preferred**: create `tests/docs/test_run_layout_contract.py` that scans only operator-facing living docs and blocks legacy patterns.
  - Optional: add allowlisted checks to `scripts/check_docs_drift.py` (avoid false positives in historical docs).

2) **De-legacy `docs/DOCKER_DEPLOYMENT_GUIDE.md`**

- Ensure all code blocks match current reality:
  - compose services: `backend`, `frontend`, `db`, `qdrant`
  - frontend build uses `Dockerfile.frontend` and `nginx.conf`
  - no references to nested dashboard frontend as canonical

Acceptance: `python scripts/check_docs_drift.py` passes and updated docs are copy/paste correct.

---

### Phase 1 — Convert remaining OPEN items into enforceable contracts

3) **CI/contract enforcement gaps**

- Ensure any canonical docs that should never drift are either:
  - covered by drift checks, or
  - covered by a dedicated docs contract test in `tests/docs/`.

At minimum:
- run layout contract test (above)
- keep `tests/docs/test_project_index_contract.py` passing

---

### Phase 2 — Real-world automation foundations (your Etsy/Shopify/YouTube/trading direction)

Treat Section 6 items as a roadmap. Implement behind feature flags where appropriate and keep PRs small.

4) **Durable idempotency + external action ledger**

- Implement persistent idempotency for side effects (DB-backed).
- Add an append-only `external_actions` ledger with:
  - idempotency_key, payload_hash, provider, action, approval reference, status, timestamps, retry_count, redacted response summary.
- Ensure retries consult the ledger before executing.

5) **Provider OAuth lifecycle**

- Add provider credential types and refresh handling (bounded retries).
- Add non-secret credential health/status visibility (no leakage).

6) **Publish/list “publish packet” gate**

- Implement deterministic publish packet artifact (media hashes + text + policy snapshot refs).
- Require approval before executing publish/list actions.

7) **Policy monitoring**

- Add policy snapshot/diff mechanism and gate publish/list on “fresh + acknowledged” snapshots.

8) **Trading safety controls**

- Paper trading only by default; explicit promotion gate to live trading.
- Hard kill switch + strict risk limits; strategy changes require approval.

---

### Phase 3 — Claude Code sub-agent workflow support (optional but recommended)

Implement the minimal “glue” in Section 7:

- Canonical run-local `handoff/context.md`
- Standard sub-agent output contract
- Autopack command to generate sub-agent task briefs from run artifacts

Guardrails:
- no secrets in artifacts
- no side effects from sub-agents

---

## CI / Testing Checklist (Run These Before PR)

Run locally (minimum):

- `python scripts/check_docs_drift.py`
- `python scripts/tidy/sot_summary_refresh.py --check`
- `pytest -q tests/docs/`
- `pytest -q tests/ci/` (or at least the new/modified contract tests)

If you touch runtime behavior:

- `pytest tests/ -m "not research and not aspirational and not legacy_contract"`

Do not widen scope unnecessarily. Keep changes incremental.

---

## End-of-build drift closure (REQUIRED before opening a PR)

This repo intentionally uses derived-state generators + contract tests to prevent “two truths”.
Before you open a PR, you must make sure all SOT/doc derived state is clean.

- **Docs drift**:
  - Run: `python scripts/check_docs_drift.py`
- **README SOT summary derived state**:
  - Verify: `python scripts/tidy/sot_summary_refresh.py --check`
  - If drift: run `python scripts/tidy/sot_summary_refresh.py --execute`
  - Re-run `--check` until clean
- **Docs contract tests**:
  - Run: `pytest -q tests/docs/`
- **Doc links**:
  - Run: `python scripts/check_doc_links.py`
- **Workspace structure**:
  - Run: `python scripts/tidy/verify_workspace_structure.py`

If any of these steps fail, fix the drift and include the fix in the same PR. Do not defer drift fixes.

---

## PR Strategy (Recommended)

Create multiple small PRs rather than one mega-PR:

1) **Docs run-layout drift fix + enforcement** (P0)
2) **Docker deployment guide canonicalization** (P0/P1)
3) **External action ledger + idempotency** (P0 for real-world ops)
4) **OAuth lifecycle + credential health** (P0/P1)
5) **Publish packet gate + policy monitor** (P0/P1)
6) **Trading kill switches + risk controls** (P0 for trading)
7) **Sub-agent workflow glue** (optional)

Each PR must keep CI green and include tests/guardrails that prevent regression.

---

## Common Footguns (Watch Out)

- Accidentally reintroducing legacy run paths in living docs (missing `<family>/`).
- Adding new canonical config/doc files that are not wired or enforced (creates “two truths”).
- Logging secrets in artifacts (headers, cookies, OAuth tokens, HAR files).
- Making side-effect actions executable without approval gates.
- Breaking Windows console safety checks with Unicode output in critical scripts.
