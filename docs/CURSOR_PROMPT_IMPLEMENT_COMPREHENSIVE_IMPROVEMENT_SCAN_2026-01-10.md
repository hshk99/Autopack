# Cursor Prompt: Implement `COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10` Backlog

**Purpose**: This prompt is for a separate Cursor agent to implement the concrete backlog items enumerated in:

- `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`

**Primary success criteria**: converge “one truth” for canonical/operator docs, and ensure changes are mechanically enforced in CI (contract tests / drift checks), without rewriting historical ledgers unnecessarily.

---

## Ground Rules / Watch-outs (read first)

- **Do not rewrite history by default**:
  - Append-only ledgers (e.g., `docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/CHANGELOG.md`) should not be mass-edited just to remove old strings.
  - Prefer **targeted allowlists** (canonical operator docs) + **explicit “legacy/historical” labeling** for docs that preserve history.

- **Avoid “two truths”**:
  - If a document is canonical/operator-safe, it must be copy/paste correct and match runtime.
  - If a document is historical, label it as such and ensure it is excluded from canonical allowlists and drift checks.

- **Windows shell**:
  - Use PowerShell-friendly commands (no `head`; use `Select-Object -First N`).

- **Keep CI stable**:
  - Narrowly-scoped doc contract tests (allowlist-based) are preferred over broad grep rules across all docs.

---

## Implementation Order (minimize risk)

### PR-A (P0): Fix auth documentation truth

**Goal**: Resolve the “AUTHENTICATION.md is legacy but treated as canonical” contradiction.

1. Decide the strategy:
   - **Preferred**: rewrite `docs/AUTHENTICATION.md` to match current auth code under `src/autopack/auth/*` and `docs/CANONICAL_API_CONTRACT.md` (`/api/auth/*`).
   - Alternative: move it to `archive/` and remove it from canonical operator docs lists (only if you truly do not want an auth guide).

2. Update `docs/AUTHENTICATION.md` to:
   - Remove all `src/backend/*` references
   - Document canonical endpoints:
     - `POST /api/auth/register`
     - `POST /api/auth/login`
     - `GET /api/auth/me`
     - `GET /api/auth/.well-known/jwks.json`
     - `GET /api/auth/key-status`
   - Reflect current production key behavior (ephemeral key generation blocked in production).

3. Mechanical enforcement:
   - Update / add a doc contract test under `tests/docs/` to ensure canonical operator docs do **not** contain `src/backend/`.
   - Keep scope to the canonical operator allowlist (see `docs/GOVERNANCE.md` Section 10).

### PR-B (P0): Fix governance doc contradictions

**Goal**: Make `docs/GOVERNANCE.md` internally consistent and aligned to the real policy.

1. Reconcile contradictions:
   - If docs/tests are not auto-approved in practice, remove Tier-1 examples implying they are.
   - Ensure “Tier definitions”, “Category Safety”, and “Auto-approval examples” all agree.

2. Mechanical enforcement:
   - Add a small contract test (or extend existing doc tests) asserting `docs/GOVERNANCE.md` does not simultaneously state conflicting rules.
   - If code already has governance contract tests, reference them and ensure docs match.

### PR-C (P0): Remove GLM drift from canonical onboarding

**Goal**: Stop docs from advertising GLM support if it’s disabled.

1. Update canonical onboarding surfaces:
   - `docs/PROJECT_INDEX.json`: remove GLM as a “required”/“normal” API key option (or label as legacy/disabled).
   - `docs/CONFIG_GUIDE.md` and any canonical guides that mention GLM: align to supported providers.

2. Optional enforcement:
   - Add a doc-contract check that canonical docs do not advertise GLM unless explicitly marked “disabled/legacy”.

### PR-D (P1): Production compose override template

**Goal**: Provide a safe “production override” example and align docs to it.

1. Add `docker-compose.prod.example.yml` (non-secret):
   - Don’t expose `db`/`qdrant` ports to host
   - Use `*_FILE` placeholders for secrets (document “provide via Docker secrets”)
   - Keep deterministic image pinning strategy consistent with repo policy

2. Update `docs/DEPLOYMENT.md` to reference this example.

### PR-E (P2/P3): Cleanup polish + migration ambiguity decision

1. Fix “stale actions/checkout@v3” snippets in canonical docs (if they are canonical).
2. Address migration ambiguity:
   - Either create an ADR clarifying Alembic is future-only, or remove Alembic from `pyproject.toml` (if truly unused).

---

## “Legacy-doc containment” strategy (do this carefully)

1. **Define canonical operator docs allowlist** (use `docs/GOVERNANCE.md` Section 10).
2. Forbid `src/backend/` in that allowlist via tests (do not grep every file in `docs/`).
3. For docs that must keep historical references:
   - Add a top banner:
     - `> LEGACY/HISTORICAL — do not copy/paste. Preserved for audit/history.`
   - Ensure those docs are excluded from the operator allowlist and drift tests.

---

## CI / Testing Flow (must follow)

Before pushing:

```powershell
# From repo root
python -m pytest -q tests/docs/
python -m pytest -q tests/ci/
python -m pytest -q tests/ -m "not research and not aspirational and not legacy_contract" -v
```

If you changed only docs/tests, keep the run minimal (docs + CI tests).

---

## PR Hygiene Checklist

- Ensure the report itself is tracked:
  - `git status` should not show `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md` as untracked.
- Keep changes tightly scoped per PR (A/B/C/D/E split above).
- Update `docs/INDEX.md` if you want the report discoverable.
- For doc-only PRs: include a short “why” + “how verified” in the PR body, referencing the contract tests you ran.

---

## Deliverables

1. A sequence of PRs implementing items from `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`.
2. New/updated doc contract tests ensuring canonical docs stay copy/paste correct and do not reintroduce legacy path references.
3. Optional: `docker-compose.prod.example.yml` + aligned deployment docs.


