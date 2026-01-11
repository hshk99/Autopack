# Cursor Implementation Prompt: Implement *all* items from `COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`

**Audience**: Another Cursor agent implementing changes (code + docs + tests) in this repo.  
**Goal**: Implement *everything* required by the canonical PR stack and numbered checklist in `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`, with strong guardrails and CI proof.  
**Non-goal**: Do not “improve things opportunistically” outside the explicitly listed items—avoid scope creep.

---

## Canonical inputs (do not fork truth)

- **Primary plan**: `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
  - Use **`## Canonical PR stack (single plan; use this)`** as the single source of truth for ordering and dependencies.
  - Use the **numbered P0–P3 checklist** for acceptance criteria and file anchors.
- **Navigation hub**: `docs/INDEX.md` (do not invent new “canonical” docs without linking)
- **Governance posture**: `docs/GOVERNANCE.md` (DEC-046 default-deny; NEVER auto-approve critical paths)
- **Docs drift guardrails**:
  - `scripts/check_docs_drift.py`
  - `tests/docs/test_copy_paste_contracts.py`
- **CI**: `.github/workflows/ci.yml` (respect staged mypy posture, docs-sot-integrity job, etc.)

---

## Operating constraints (read carefully)

- **No “two truths”**:
  - If you update behavior, update the canonical docs/contracts and add/adjust contract tests in the same PR.
  - Do not update historical append-only ledgers to rewrite history. Prefer adding clarifying notes or updating living docs.
- **Safe-by-default**:
  - Any feature that can bypass governance, expose secrets, or perform side effects must default OFF / default-deny.
- **Keep PRs small and stackable**:
  - Follow the PR stack order below. Each PR should be independently mergeable and CI-green.
- **Windows reality**:
  - Avoid introducing unicode/encoding pitfalls in scripts (see CI’s Windows unicode guards).

---

## Pre‑PR Drift Zero Gatekeeper protocol (must run before opening a PR)

**Goal**: Before requesting review (or opening a PR), ensure the branch is mechanically consistent and CI-ready. If anything fails, fix it on-branch and re-run until green.

### Hard rules

- Do **not** claim “Implemented” in docs/DECs unless the corresponding code/docs change is actually present in the branch.
- Do **not** change historical ledgers (`docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, etc.) except via the repo’s official SOT refresh scripts.
- Keep changes minimal and scoped to the failure/drift (avoid opportunistic refactors while chasing drift).

### Required local checks (run in this order)

1) **Docs/SOT contract suite** (most drift shows up here):

```bash
python -m pytest -q tests/docs/
```

If any docs/SOT test fails:

- Read the failure message and run the recommended remediation command(s).
- Common fixes:
  - If README SOT summary mismatch:

```bash
python scripts/tidy/sot_summary_refresh.py --execute
```

  - If copy/paste docs contract fails: fix the specific doc(s) in the allowlist; do **not** weaken the test.
  - If decision ledger uniqueness/count mismatch: fix `docs/ARCHITECTURE_DECISIONS.md` to match reality (status labels must be accurate).

Re-run until green:

```bash
python -m pytest -q tests/docs/
```

2) **Unit tests touched by your changes**:

- If you touched executor/LLM wiring:

```bash
python -m pytest -q tests/llm_service/
```

- Also run any directly related test suites referenced by the changed module(s).

3) **Style checks (fast)**:

```bash
ruff check src/ tests/
black --check src/ tests/
```

### Git hygiene before PR

- `git status` must be clean.
- Ensure the PR description matches reality:
  - If something is staged/informational/commented out in CI, label it **STAGED** (not “enforced”).
  - If a DEC is decision-only and not implemented, mark it 🧭 Planned (or equivalent), not ✅.

### PR creation output format (must follow)

When done, paste:

- PR link
- Checks run locally (exact commands)
- What you changed to fix drift (bullet list)
- What remains planned/staged (bullet list)

### Common drift traps to proactively avoid

- After adding/editing DECs: always run `python -m pytest -q tests/docs/` and refresh README SOT summary if needed.
- Don’t update `docs/ARCHITECTURE_DECISIONS.md` statuses to ✅ unless the PR includes the actual implementation.
- Don’t say “dependency drift enforcement enabled” if the workflow step is still commented out / informational.

## PR implementation order (must follow)

Implement PRs in this order. Each PR section below includes scope, pitfalls, and tests.

### PR-00 (P0): Governance docs “one truth” convergence (DEC-046)

**Scope**:
- Update `docs/GOVERNANCE.md` to match actual enforced policy (default-deny; NEVER auto-approve `docs/`, `tests/`, `config/`, `.github/`, `src/autopack/`).

**Pitfalls**:
- Don’t describe auto-approval of docs/tests anywhere.

**CI/tests**:
- Ensure `tests/ci/test_governance_docs_contract.py` passes; extend only if it’s missing coverage for the new wording.

---

### PR-01 (P0): Remove legacy auto-approval footgun (AUTO_APPROVE_BUILD113)

**Scope**:
- `src/autopack/main.py`: `POST /approval/request` default should not auto-approve.
- Add a CI contract test (suggested in the scan): `tests/ci/test_legacy_approval_autoapprove_default_safe.py`.

**Pitfalls**:
- Don’t break legacy workflows accidentally: keep the capability behind explicit opt-in, but default safe.
- Consider hard rule: never allow auto-approve in `AUTOPACK_ENV=production`.

**CI/tests**:
- Add/extend tests verifying default is safe and (optionally) production blocks auto-approve even if env var is set.

---

### PR-02 (P0): Fix production override “one truth” (compose comments + doc-contract)

**Scope**:
- `docker-compose.yml`: comment block must reference `docker-compose.prod.example.yml` (or explicitly instruct copying it).
- Extend `tests/docs/test_copy_paste_contracts.py` to prevent regressions.

**Pitfalls**:
- Keep the guidance consistent with `docs/DEPLOYMENT.md` (it already uses copy-from-example).

**CI/tests**:
- Docs contract tests (`tests/docs/`) must pass; docs-sot-integrity will enforce drift checks too.

---

### PR-03 (P0): Fix nginx routing semantics for `/api/auth/*` without breaking `/api/runs*`

**Scope**:
- `nginx.conf`: ensure `/api/auth/` is explicitly routed so `/api/auth/login` reaches backend `/api/auth/login` while `/api/runs` continues to map correctly.
- Update deployment docs (`docs/DEPLOYMENT.md` and/or `docs/CANONICAL_API_CONTRACT.md`) to describe routing invariants.
- Add `tests/ci/test_nginx_proxy_contracts.py` (contract test).

**Pitfalls**:
- Nginx `proxy_pass` trailing slash semantics are easy to get wrong. Keep `/api/` and `/api/auth/` behavior explicit.
- Health endpoints: preserve `/health` and `/nginx-health` semantics as documented.

**CI/tests**:
- Add config string-based assertions (keep them stable and minimal).

---

### PR-04 (P0): Secrets injection via `*_FILE` (production template parity)

**Scope**:
- `src/autopack/config.py`: support `DATABASE_URL_FILE`, `JWT_PRIVATE_KEY_FILE`, `JWT_PUBLIC_KEY_FILE`, and (optionally) `AUTOPACK_API_KEY_FILE`.
- Add `tests/autopack/test_secret_file_env_support.py`.

**Pitfalls**:
- Don’t log secret file contents. Ensure any logging stays sanitized.
- Precedence must be deterministic: `*_FILE` > env var > defaults.

---

### PR-05 (P0/P1): `.credentials/` posture + containment (no plaintext-by-default)

**Scope**:
- `src/autopack/auth/oauth_lifecycle.py`: production-safe persistence posture; plaintext persistence must not be default.
- `src/autopack/credentials/rotation.py`: treat `.credentials/metadata.json` carefully (metadata can still leak posture).
- Update docs: `docs/DEPLOYMENT.md` / `docs/WORKSPACE_ORGANIZATION_SPEC.md` if needed.

**Pitfalls**:
- `.credentials/` must remain local-only: never indexed, never returned by artifacts endpoints by default.
- Keep dev ergonomics, but require explicit opt-in for risky persistence.

**CI/tests**:
- Add `tests/credentials/test_oauth_persistence_policy.py` or extend existing credential tests to enforce production behavior.

---

### PR-06 (P1/P2): Operator-surface hosted-readiness (per-run auth + artifact redaction)

**Scope**:
- Decide explicit single-tenant vs multi-tenant semantics (see scan P1-05).
- Implement per-run authorization checks *if* multi-tenant.
- Add optional artifact content redaction, and ensure responses indicate truncation/redaction.

**Pitfalls**:
- Never bake secrets into the frontend bundle.
- Avoid breaking local dev usability; keep dev toggles explicit and documented.

**CI/tests**:
- Extend production auth coverage contracts and add route-level contract tests for run/artifact endpoints.

---

### PR-07 (P3): Migration surface clarity (“no fake Alembic”)

**Scope**:
- Decide Alembic dependency posture (`pyproject.toml`) and document it.
- Ensure any Alembic-path heuristics are clearly “generic template only when present”, or remove/adjust them for this repo.

**CI/tests**:
- Add `tests/ci/test_no_fake_alembic_assumptions.py` if needed.

---

### PR-08 (P3): Close or guard `/runs` N+1

**Scope**:
- Verify whether N+1 actually exists. If already resolved, close the item with evidence (no code changes).
- If not resolved, optimize query and optionally add a regression guard.

---

## CI workflow / how to avoid painful loops

- Run the **smallest relevant test scope** per PR locally:
  - Docs-only PRs: `pytest -q tests/docs/`
  - CI contract PRs: `pytest -q tests/ci/`
  - Backend changes: `pytest tests/ -m "not research and not aspirational and not legacy_contract" -q` (match CI core gate)
- Before pushing:
  - `python scripts/check_docs_drift.py` for docs-heavy PRs
  - `python scripts/tidy/sot_summary_refresh.py --check` if SOT summary markers are touched

---

## What to watch out for (common failure modes)

- **“Two truths” regressions**: a code fix without doc-contract updates will fail `docs-sot-integrity` or drift checks later.
- **Auth drift**: if you tighten auth on endpoints, update `docs/CANONICAL_API_CONTRACT.md` and the contract tests that assume unauthenticated access (if any).
- **Nginx path rewriting**: always validate `/api/auth/*` and `/api/runs*` behavior together.
- **Secrets persistence**: no plaintext credential writes in production by default; `.credentials/` must never be exposed.

---

## Output requirements for each PR

Each PR must include:

- The code/doc change(s)
- The contract test(s) that prevents regression
- A short update to `docs/BUILD_HISTORY.md` entry (if that is the repo’s current norm) **or** whatever the current “ledger update” policy requires


