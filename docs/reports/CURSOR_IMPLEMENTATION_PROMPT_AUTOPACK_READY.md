You are an AI coding agent working in the Autopack repo.

Your job is to IMPLEMENT everything in:
- `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
including the “Balanced Readiness Program” / “External-side-effect posture” / PR plan sections.

## Hard constraints (do not violate)
- Default-deny: production posture must be mechanically enforced via CI contract tests.
- No “two truths”: if you change runtime behavior, update the canonical docs + contract tests in the same PR.
- Prefer small PRs but each PR must be end-to-end coherent: code + docs + tests + CI passing.
- Never bake secrets into frontend bundles. Never introduce plaintext secret persistence in production.
- Do not weaken existing security scanning/diff-gates.
- Keep Windows compatibility (paths, encoding, file locking).

## How to apply the propose-only patchset (docs additions)
- Apply the patch content in `docs/reports/PROPOSE_ONLY_PATCHSET_READINESS_PROGRAM.md` to update the report.
- After applying, treat the new “Readiness gates / rubric / side-effect posture” sections as implementation requirements.

## Your operating approach
- Work PR-by-PR. For each PR:
  - Implement changes
  - Update docs (especially `docs/CANONICAL_API_CONTRACT.md`, `docs/DEPLOYMENT.md`, `docs/GOVERNANCE.md` as relevant)
  - Add/adjust contract tests to prevent regressions
  - Run targeted tests locally, then run full `pytest` before finishing the PR
  - Update the report: mark items as implemented, add links to tests/files
  - **Update the Readiness score rubric (0–16)**: after each PR, set the relevant gate(s) to **0/1/2** with a link to the specific tests/docs proving it.

## Implementation order (balanced readiness sequence)
Implement in this order (each is a PR unless you can prove it’s safer combined):

### PR-01 / R-01 (G1 + G8): Auth & exposure + contract convergence
- Ensure all non-allowlisted endpoints are protected in `AUTOPACK_ENV=production`.
- Ensure CI auth coverage detects both protection mechanisms (e.g. `verify_api_key` and `verify_read_access`).
- Update `docs/CANONICAL_API_CONTRACT.md` to match actual behavior (auth + response shapes).
- Add/extend tests:
  - `tests/ci/test_production_auth_coverage.py`: must fail if any endpoint outside allowlist is unauthenticated in production.
  - Add a canonical API contract test for any “required endpoint” that exists in docs but is missing in code.
- Watch-outs:
  - Many unit/integration tests assume auth is bypassed under test; do NOT make tests flaky.
  - If you add auth deps, ensure tests either set `TESTING=1` or supply headers explicitly.
  - Keep allowlist minimal and justified.

### PR-02 / R-02 (G6): nginx routing + health semantics
- Fix nginx so `/api/auth/*` works alongside `/api/runs*` without breaking existing UI calls.
- Decide health semantics:
  - Either proxy `/health` to backend or introduce `/nginx-health` + `/health` backend readiness.
- Update `docs/DEPLOYMENT.md` and/or `docs/CANONICAL_API_CONTRACT.md` with “Reverse proxy routing invariants”.
- Add/adjust tests to ensure canonical deployment mapping is documented and not drifting.
- Watch-outs:
  - nginx `proxy_pass` trailing slash behavior strips prefixes—test it explicitly.

### PR-03 / R-03 (G4): `*_FILE` secrets support
- Implement `*_FILE` support in config:
  - `DATABASE_URL_FILE`
  - `JWT_PRIVATE_KEY_FILE` / `JWT_PUBLIC_KEY_FILE`
  - optionally `AUTOPACK_API_KEY_FILE`
- Precedence: `*_FILE` > direct env > defaults. Fail fast in production when required secrets missing.
- Add unit tests for each file secret path: missing, empty, unreadable, whitespace.
- Watch-outs:
  - Do not log secrets; ensure logs show only masked/sanitized values.

### PR-04 (also R-03 / G4): OAuth credential persistence hardening
- In production, forbid plaintext OAuth token persistence by default.
- Provide one supported secure path:
  - secret files (`*_FILE`) OR OS keychain OR encrypted store; pick one and document.
- Update docs to explain operator steps and how exceptions are recorded.
- Add tests to ensure production mode fails fast unless explicitly enabled.

### PR-05 / R-04+R-05 (G2 + G3): Governance/approval enforcement for external side effects
- Implement deterministic classification of actions into Tier A/B/C.
- For Tier C:
  - require explicit approval
  - bind approval to payload hash
  - block execution in `PENDING`
- Ensure the external action ledger enforces this.
- Add audit log minimum fields for every Tier C proposal/execution.
- Add kill switches:
  - global external actions enable
  - per-domain switches: Etsy/Shopify/YouTube/Trading
  - dry-run mode default ON
  - spend caps
- Update docs:
  - ensure the “Recommended posture for external-side-effect automation” section is accurate and referenced
  - ensure `docs/GOVERNANCE.md` matches enforced rules (no contradictions about docs/tests being auto-approved).
- Watch-outs:
  - Payload hash must be computed deterministically (stable JSON serialization).
  - Ensure idempotency keys remain stable and are logged.

### PR-06 / R-06 (G5): Artifact boundary hardening
- Add size caps + deterministic truncation for artifact reads.
- Optional redaction on read using existing redaction utilities; return metadata flags.
- Add tests covering:
  - traversal attempts
  - huge file handling
  - redaction correctness
  - deterministic output
- Watch-outs:
  - Avoid loading huge files fully into memory; stream or truncate safely.

### PR-07 / R-07 (G7): Observability correctness + auth unification decision
- Decide and document:
  - `X-API-Key` is primary; JWT optional for multi-user UI
- Ensure frontend production story does not embed secrets:
  - either JWT login flow OR reverse proxy injection (document as unsafe for multi-user)
- Fix token cap source-of-truth (remove “cap=0” placeholders).
- Ensure kill switches default OFF and are tested.

## CI / testing flow you must follow
- Before coding: run targeted tests for the area you touch.
- After coding each PR:
  - run `pytest -q <relevant tests>`
  - run `pytest -q` full suite
  - ensure docs contract tests and security diff gate tests pass
- Never leave the repo with “implemented in code but not documented” or “documented but not implemented”.

## Deliverables per PR
- Code changes
- Updated docs
- Updated/added tests
- Report update: in `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`, mark items as implemented with evidence links.
- **Rubric update**: update the readiness score rubric table (0–16) for the gates affected by the PR, with evidence links.

## Common pitfalls to avoid
- Breaking `/api/auth/*` behind nginx due to prefix stripping.
- Making auth enforcement depend on fragile test environment assumptions; prefer explicit `TESTING=1` or explicit test headers.
- Letting “proposal-only” actions still execute from `PENDING`.
- Storing OAuth tokens in plaintext in production.
- Returning unbounded artifact content.
- Creating multiple competing “canonical lists” of endpoints/SOT—always converge to the canonical docs.
