# CURSOR_PROMPT: Implement `docs/IMPROVEMENTS_GAP_ANALYSIS.md` End-to-End

**Audience**: Another Cursor AI agent implementing the full gap list.  
**Repo**: `hshk99/Autopack`  
**Canonical task list**: `docs/IMPROVEMENTS_GAP_ANALYSIS.md` (treat as the source of truth; verify each item before changing code).

---

## 0) Prime directive (do not violate these)

- **SOT / “one truth”**:
  - Don’t create parallel sources of truth. Prefer updating existing docs and code contracts over adding new competing docs.
  - If you add a *new canonical SOT ledger* (rare), register it in `config/sot_registry.json`. (Most new docs should be `CURSOR_PROMPT_*`, `GUIDE`, or `IMPLEMENTATION_PLAN_*` and do **not** require SOT registry entries.)
- **Mechanical enforcement**:
  - Every change should end with a **mechanical check**: test/contract/lint/build command that proves the change works.
  - Avoid “hand-wavy” fixes. If a rule exists in docs, encode it in code/tests where feasible.
- **Safety**:
  - Prefer small PRs; avoid sweeping refactors while closing hygiene/CI/security gaps.
  - Never add secrets to git. All example env files must use placeholders only.

---

## 1) Recommended execution order (minimize coupling)

Implement in this order; stop after each “chunk” and ensure green CI:

1. **P0 hygiene + portability + secret safety** (fast ROI, blocks other work)
2. **P1 CI completeness + determinism** (prevents regressions during later changes)
3. **P2 repo meta + docs clarity** (CODEOWNERS, dependabot, templates, etc.)
4. **P5 hardening backlog** (bigger design choices; do after CI is solid)
5. **P6 beyond-repo** (run self-audit; document results; adjust GitHub settings)

---

## 2) CI flow (what must stay green)

Primary workflow: `.github/workflows/ci.yml` (jobs commonly required for merge):

- **lint**: ruff + black + policy checks
- **docs-sot-integrity**: doc-contract tests + SOT drift checks + doc link checks + SECBASE enforcement
- **test-core**: core pytest gate (postgres service)
- **test-aspirational**: informational (allowed to fail)
- **test-research**: informational (allowed to fail)
- **governance-approval-tests**: PR-only governance contracts

Always run locally (minimum):

```bash
python -m pip install -e ".[dev]"
ruff check src/ tests/
black --check src/ tests/
pytest -q tests/docs/
pytest tests/ -m "not research and not aspirational and not legacy_contract" -v
```

If you touch Docker/frontend:

```bash
docker build --target backend --tag autopack-backend:scan .
docker build -f Dockerfile.frontend .
```

If you touch any frontend package:

```bash
npm ci
npm run lint
npm run type-check
npm run build
```

---

## 3) PR strategy (how to ship safely)

Create multiple PRs, one per theme, each with its own “proof” (tests + acceptance criteria):

- **PR-1 (P0)**: workspace hygiene + DB routing + stray artifacts checks
- **PR-2 (P0)**: portability + secret safety + API version alignment
- **PR-3 (P1)**: CI completeness (frontend + mypy staged) + python version policy
- **PR-4 (P2)**: repo meta files (LICENSE/SECURITY.md/CODEOWNERS/Dependabot/.editorconfig/.gitattributes/templates)
- **PR-5 (P5)**: hardening backlog items (auth/env modes, sanitizer consolidation, etc.)

Rules:
- Each PR must include **exact verification commands** in the PR description.
- Avoid mixing independent concerns.
- Ensure workflow actions remain SHA-pinned per existing policy.

---

## 4) Detailed implementation checklist (by section in gap analysis)

### 4.1 P0 items (Section 1)

#### 1.1 `node_modules/` / `dist/` hygiene
- **Goal**: ensure artifacts are never tracked and are blocked when present under tracked paths.
- **Actions**:
  - Confirm `git ls-files` contains no `node_modules` or `dist`.
  - Strengthen workspace structure verification so it fails if these dirs exist under tracked paths (even if ignored).
- **Proof**:
  - Add/extend a CI test or script check; verify `ci.yml` runs it.

#### 1.2 + 1.10 Root DB clutter (`telemetry_seed_*.db`, other `*.db`)
- **Goal**: align with `docs/WORKSPACE_ORGANIZATION_SPEC.md` root DB rules.
- **Actions**:
  - Decide: are these DBs test fixtures or historical artifacts?
    - Fixtures → `tests/fixtures/`
    - Historical → `archive/data/databases/...`
  - Update tidy routing + `verify_workspace_structure.py` to enforce this mechanically.
- **Proof**:
  - Add a test under `tests/tidy/` or `tests/ci/` that fails if root contains forbidden `*.db` patterns.

#### 1.3 Portability: workstation paths in SQL seeds
- **Important**: The file currently claims BUILD-188 removed hardcoded paths; verify current contents before changing.
- **Goal**: no workstation-specific absolute paths in schema migrations or required runtime config.
- **Actions**:
  - Ensure SQL migration(s) are schema-only; move any seed examples to `docs/examples/`.
  - Add a CI grep-based guard for `C:\dev\`, `/Users/`, `/home/` in `src/autopack/migrations/**/*.sql`.

#### 1.4 Startup logging secret safety
- **Important**: The file currently claims BUILD-188 redacted logs; verify current `src/autopack/main.py` before changing.
- **Goal**: never log raw credentials; ensure `sanitize_url()` is used.
- **Actions**:
  - Add a unit/contract test that fails if raw DB creds leak in logs (at least validate sanitize function behavior).

#### 1.5 Error reporting secret/PII persistence
- **Goal**: sanitize headers/query params before persisting error reports.
- **Actions**:
  - Implement a single sanitizer for error context (headers/query/local vars).
  - Add tests asserting redaction for common secret keys.

#### 1.6 Governance contradictions (docs vs implementation)
- **Goal**: one canonical policy source.
- **Actions**:
  - Decide: tests/docs always auto-approvable, or never? Update code + docs to match.
  - Encode policy in one place (config/module) and import it in proposer/scorers.
- **Proof**:
  - Add/extend contract tests covering governance policy behavior.

#### 1.7 API version mismatch
- **Goal**: FastAPI version matches `pyproject.toml` / `autopack.__version__`.
- **Actions**:
  - Wire version from package metadata; add OpenAPI metadata test.

#### 1.8 Docker/frontend path mismatch
- **Goal**: `Dockerfile.frontend` builds from the real frontend source.
- **Actions**:
  - Decide canonical frontend path(s).
  - Update Dockerfile(s) to match.
- **Proof**:
  - `docker build -f Dockerfile.frontend .` from clean clone.

#### 1.9 Stray backup-like files under `src/`
- **Important**: The doc cites `src/autopack/governed_apply.py.bak2`; verify whether it exists before claiming current state.
- **Goal**: CI blocks backup patterns in source tree.
- **Actions**:
  - Ensure checks cover `*.bak*`, `*.backup*`, `*.broken*`.

---

### 4.2 P1 items (Section 2)

#### 2.1 Frontend in CI
- **Goal**: lint/typecheck/build runs for supported frontend(s).
- **Actions**:
  - Decide which frontend is canonical (root Vite vs dashboard frontend vs autopack frontend).
  - Add CI job(s) with `npm ci` and relevant scripts.

#### 2.2 Python version policy across workflows
- **Goal**: unify on 3.11 (matches `pyproject.toml`) or explicitly run a matrix.
- **Actions**:
  - Update `.github/workflows/intention-autonomy-ci.yml` (currently uses 3.12) and any others.
  - Document policy briefly in `docs/TESTING_GUIDE.md` or `docs/CONTRIBUTING.md`.

#### 2.3 mypy in CI (staged adoption)
- **Goal**: start with a small allowlist or baseline config so CI stays actionable.
- **Actions**:
  - Add `mypy` step with config allowing incremental rollout (exclude quarantined dirs).

#### 2.4 Security diff gates rollout → enforce
- **Goal**: decide enforcement posture for PRs vs scheduled workflows.
- **Actions**:
  - Flip `continue-on-error` to blocking when stable (at least for PRs).
  - Ensure baseline refresh workflow remains safe and reviewable.

#### 2.5 Gap scanner baseline policy drift
- **Goal**: `GapScanner` should not guarantee a “missing baseline policy” gap.
- **Actions**:
  - Either create the expected `config/baseline_policy.yaml` or update the scanner to reference the real policy files under `config/`.
- **Proof**:
  - Add a test that a clean repo produces no baseline-policy gap.

#### 2.6 Autonomy artifact path consistency
- **Goal**: one canonical layout between docs, examples, and `RunFileLayout`.
- **Actions**:
  - Update docs/examples; add a contract test if feasible.

#### 2.7 Executor ↔ API operational hardening
- **Goal**: safe-by-default errors + prod auth posture.
- **Actions**:
  - Introduce `AUTOPACK_ENV=dev|test|prod` (or similar) and enforce:
    - prod: API key required; JWT keys must be configured; no auto-generation.
    - dev/test: convenience allowed.

#### 2.8 Supply-chain determinism (Docker digests + deps)
- **Goal**: deterministic container builds over time.
- **Actions**:
  - Decide digest pinning policy for base images.
  - Decide dependency pin strategy for container installs (hashes/constraints/wheelhouse).

#### 2.9 Security scan redundancy
- **Goal**: coherent posture (what blocks PRs, what’s scheduled, what’s baseline-driven).
- **Actions**:
  - Consolidate schedules; keep one canonical enforcement path.

#### 2.10 Docs portability (C:\ paths)
- **Goal**: non-Windows-only docs avoid workstation-specific paths.
- **Actions**:
  - Replace with `$REPO_ROOT`/`<repo_root>` conventions.
  - Add a low-noise check (warn or non-blocking at first).

#### 2.11 SOT registry mismatch
- **Goal**: align `docs/INDEX.md` “authoritative docs” list with `config/sot_registry.json` (or explicitly explain exceptions).
- **Actions**:
  - Decide whether to protect additional docs (SECURITY_* docs, CHANGELOG) or downgrade them from “SOT” language.
  - Update tests/ci consistency checks accordingly.

#### 2.12 Dependabot
- **Goal**: keep pins/deps fresh with reviewable PRs.
- **Actions**:
  - Add `.github/dependabot.yml` for:
    - github-actions
    - pip
    - npm (as appropriate)

#### 2.13 CODEOWNERS
- **Goal**: auto-route review for sensitive surfaces.
- **Actions**:
  - Add CODEOWNERS entries for `.github/`, `config/`, `security/`, SOT ledgers, core runtime.

---

### 4.3 P2 items (Section 3 + Section 4 paper cuts)

#### 3.1 Frontend consolidation
- **Goal**: “one true way” to run/build UI.
- **Actions**:
  - Pick canonical frontend, delete/wire the rest, align docs + Docker + CI.

#### 3.2 Migration discipline
- **Goal**: one migration approach (Alembic OR SQL-only).
- **Actions**:
  - Document and enforce; add drift checks if possible.

#### 3.3 Workspace structure checks expansion
- **Goal**: prevent caches/backup patterns across src/tests/root.
- **Actions**:
  - Expand existing checker(s) rather than creating many new overlapping scripts.

#### 3.4 Dev install consistency
- **Goal**: CI and docs use the same dependency install strategy (`pyproject.toml` SOT).
- **Actions**:
  - Align Makefile + docs to `pip install -e ".[dev]"` (or document both paths and keep them in sync).

#### 3.5 Missing community files (LICENSE / SECURITY.md / CODE_OF_CONDUCT)
- **Goal**: satisfy workspace spec + GitHub discovery conventions.
- **Actions**:
  - Add root `SECURITY.md` pointing to `security/README.md` (or migrate content).
  - Add LICENSE consistent with intent (personal/internal tool is fine; pick a license explicitly or mark “All rights reserved” if desired).

#### 3.6 API versioning/OpenAPI stability enhancements
- **Goal**: stable API metadata and discoverable version.
- **Actions**:
  - Add `/version` or `X-Autopack-Version` header; add test.

#### 3.7 Observability polish
- **Goal**: consistent caps/usage semantics.
- **Actions**:
  - Close TODOs in dashboard, ensure metrics endpoints respect kill switches.

#### 3.9 `.editorconfig` + `.gitattributes`
- **Goal**: minimize cross-OS diff churn.
- **Actions**:
  - Add `.editorconfig`
  - Add `.gitattributes` (LF enforcement where appropriate)

#### Paper cuts
- Fix docs referencing `postgres` service name if compose uses `db`.
- Decide `docs/api/` strategy; align tidy/docs references and actual layout.
- Add `.github` issue template / PR template if you want standardization.

---

### 4.4 P5 hardening backlog (Section 5)

These are higher risk and may require careful scoping:
- Centralize sanitization for anything persisted
- Tighten auth behavior so dev conveniences never leak into “prod mode”
- Add request limits / CORS / safer error responses
- Nginx hardening (CSP, permissions policy, request IDs, body size)
- Close executor determinism TODOs only with strong contract coverage

Strategy: implement one sub-item per PR with tests.

---

### 4.5 Beyond-repo (Section 6)

#### Branch protections + self-audit
- Use the existing self-audit:
  - Guide: `docs/GITHUB_SETTINGS_SELF_AUDIT_GUIDE.md`
  - Script: `scripts/ci/github_settings_self_audit.py`
- Run:
  - `python scripts/ci/github_settings_self_audit.py --repo hshk99/Autopack --branch main --check`
- If it fails due to 401: set `GITHUB_TOKEN` with repo read.

Document outcomes as:
- a short note in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` (or a dedicated checklist doc) stating which protections are enabled and which remain TODO.

---

## 5) What to watch out for (common footguns)

- **Doc drift**: update any references you break; CI has doc-contract tests and link checks.
- **Protected paths / SOT**: SOT docs and some configs are protected; ensure changes are intentional and mechanically validated.
- **Action pinning policy**: any new GitHub actions must follow SHA pin rules.
- **Windows vs Linux**: CI is linux; local is often Windows. Guard against path and encoding issues.
- **Secrets**: never log `DATABASE_URL` raw; never persist raw headers/query/local vars in error reports.
- **Multiple frontends**: avoid partial fixes; pick a canonical frontend path and make Docker/CI/docs agree.

---

## 6) Deliverable definition

Work is “done” only when:
- the corresponding acceptance criteria in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` are met,
- CI is green on PR,
- and any new policy is encoded in tests/scripts (or explicitly documented as “beyond-repo setting”).


