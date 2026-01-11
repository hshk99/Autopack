# Cursor Implementation Prompt — Close `IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11` (Full Execution)

**Audience**: Another Cursor agent implementing changes (code + docs + tests) in this repo.  
**Objective**: Implement **everything** listed in `docs/reports/IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11.md` (including its appendices) in a safe, deterministic, mechanically-enforced way.  
**Non-goal**: Do not “improve things opportunistically” outside the report. Avoid scope creep.

---

## Canonical inputs (do not fork truth)

- **Primary plan**: `docs/reports/IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11.md`
  - Treat **Appendix E (PR-ready execution checklist)** as the canonical ordering scaffold.
  - Use **Appendix B–D** to find exact hotspots and policy constraints.
- **Navigation hub / canonical surfaces**: `docs/INDEX.md`, SOT ledgers, and canonical operator docs allowlist:
  - Canonical operator docs allowlist is implemented in: `scripts/ci/check_canonical_doc_refs.py` (`CANONICAL_OPERATOR_DOCS`).
- **Governance posture**: `docs/GOVERNANCE.md` (default-deny; avoid changes that create “two truths”).

---

## Hard constraints (read carefully)

### Do not rewrite history / do not create two truths

- **Avoid broad edits** to append-only ledgers: `docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, `docs/CHANGELOG.md`, `docs/ARCHITECTURE_DECISIONS.md`.
  - If you must touch them, do it as “recent-window-only” or add explicit `HISTORICAL` labels; do not mass-normalize.
- **If you change behavior**, update the canonical docs/contracts/tests in the **same PR**.
- **Never manually edit the README SOT summary block** (`<!-- SOT_SUMMARY_START --> ... <!-- SOT_SUMMARY_END -->`). Only update via:
  - `python scripts/tidy/sot_summary_refresh.py --execute`

### Safety posture

- Anything that can expose secrets, weaken auth, or enable side effects must be **safe-by-default** (default OFF / default-deny) and must have **contract tests**.
- Never commit secrets (`.env`, tokens, credentials) or generated artifacts (`__pycache__`, `*.pyc`).

---

## CI flow (what must pass)

Autopack’s CI jobs (from `.github/workflows/ci.yml`):

- `lint`
- `docs-sot-integrity`
- `test-core`
- `frontend-ci`
- `governance-approval-tests`
- `preflight-normal`, `preflight-strict`
- `test-aspirational` (informational)
- `test-research` (informational)

Security workflows (from `.github/workflows/security.yml`):

- `secret-scan`
- `dependency-scan`
- `container-scan`
- `codeql-analysis`
- `sbom-generation`

**Rule**: every PR in the stack must be independently mergeable and CI-green (unless the repo explicitly uses non-blocking jobs; do not downgrade enforcement).

---

## Required local pre-flight (run before EVERY PR)

Run the smallest relevant subset, but always include docs integrity when you touch docs or CI scripts:

### Docs + SOT integrity

```bash
python scripts/check_docs_drift.py
python scripts/tidy/sot_summary_refresh.py --check
python scripts/check_doc_links.py
python scripts/tidy/verify_workspace_structure.py
python -m pytest -q tests/docs/
python scripts/ci/check_canonical_doc_refs.py
```

If the README SOT summary is out of sync:

```bash
python scripts/tidy/sot_summary_refresh.py --execute
python scripts/tidy/sot_summary_refresh.py --check
```

### Non-optional “close the loop on drift” rule (end of every PR)

This repo’s thesis requires drift closure to be **mechanical** and **repeatable**.

- Before opening a PR (and again before requesting final review), run:

```bash
python scripts/check_docs_drift.py
python scripts/tidy/sot_summary_refresh.py --check
python scripts/check_doc_links.py
python scripts/tidy/verify_workspace_structure.py
pytest -q tests/docs/
```

- If any drift is detected:
  - regenerate derived state **only via the generator**:

```bash
python scripts/tidy/sot_summary_refresh.py --execute
```

  - re-run the checks above until clean.
  - ensure the PR includes the drift-fix commit(s) so CI stays green.

**Critical rule**: never manually edit the `README.md` SOT summary block (`<!-- SOT_SUMMARY_START --> ... <!-- SOT_SUMMARY_END -->`). Always use `scripts/tidy/sot_summary_refresh.py`.

### Backend style checks (when touching Python)

```bash
ruff check src/ tests/
black --check src/ tests/
```

### Frontend checks (when touching frontend)

```bash
npm run lint
npm run type-check
npm run build
```

---

## Implementation order (PR stack; follow strictly)

Implement in the order below. Each PR should contain:
- minimal diffs
- explicit acceptance criteria
- contract tests (where applicable)
- a short PR description with test commands run locally

### PR-01 (E1): Fix `docs/FUTURE_PLAN.md` copy/paste traps (6-file SOT)

**Scope** (minimum):
- Replace `cd c:/dev/Autopack` → `cd $REPO_ROOT` (or “run from repo root”) in both fenced bash blocks.
- Fix unscoped legacy `src/backend` “Allowed Paths” bullets (see Appendix B/D):
  - Either label as “FileOrganizer repo paths (NOT Autopack)” **or** move those items into FileOrganizer’s own project doc and link.

**Watch out**:
- `docs/FUTURE_PLAN.md` is SOT; keep edits surgical.
- Don’t “clean up the whole file”; only fix the explicit traps.

**Validation**:
- `python -m pytest -q tests/docs/`
- `python scripts/check_docs_drift.py`

### PR-02 (E2): Add a “6-file SOT portability contract” (mechanical enforcement)

**Goal**: prevent workstation absolute paths from being reintroduced into SOT (at minimum `docs/FUTURE_PLAN.md`).

**Recommended implementation**:
- Add a new test like `tests/docs/test_sot_portability_contract.py` that scans exactly:
  - `docs/PROJECT_INDEX.json`
  - `docs/LEARNED_RULES.json`
  - `docs/FUTURE_PLAN.md` (**strict**)
  - For append-only ledgers (`BUILD_HISTORY.md`, `DEBUG_LOG.md`, `ARCHITECTURE_DECISIONS.md`): prefer **recent-window-only** enforcement to avoid rewriting history.

**Patterns to forbid** (unless explicitly labeled `HISTORICAL`/`LEGACY` on the same line):
- `c:/dev/Autopack` (case-insensitive)
- `C:\\dev\\Autopack` and variants like `D:\\dev\\Autopack`

**Watch out**:
- Do not break historical ledgers by enforcing on the entire file unless you are willing to do a “history rewrite” project (avoid).

**Validation**:
- `python -m pytest -q tests/docs/`

### PR-03: Feature flags registry enforcement (make env-var interface truly mechanical)

This repo already has `config/feature_flags.yaml`, but “complete and mechanically verified” is the goal.

**Implementation steps**:
1) **Decide the boundary**:
   - Preferred: registry is **all `AUTOPACK_*`**, and non-AUTOPACK aliases are explicitly documented as legacy/back-compat.
2) Ensure the test that enforces the registry:
   - extracts env vars from `os.getenv` / `os.environ.get` / `os.environ[...]`
   - extracts Pydantic settings aliases and field-derived env var names (where many real knobs exist)

**Watch out**:
- Don’t turn the registry into “everything in the universe” (CI vars, OS vars). Be explicit about what’s excluded and enforce that rule.

**Validation**:
- `python -m pytest -q tests/ci/test_feature_flags_registry.py`
- full `lint` suite locally if feasible

### PR-04: Deployment parity (CI vs compose) + optional compose topology smoke

**Goal**: reduce “works in compose, fails in CI” drift.

**Scope**:
- Align Postgres image tag between CI and compose (or write an ADR-style note if intentional mismatch).
- Optional but high ROI: add a **manual/scheduled** compose smoke workflow that boots compose and probes:
  - `/nginx-health`
  - `/health` (backend readiness proxied)

**Watch out**:
- Keep this non-blocking initially if runtime cost is high; do not silently weaken existing CI gates.

**Validation**:
- For workflow changes: ensure YAML is SHA-pinned and passes existing CI policy checks.

### PR-05: Health checks correctness (DB backend + provider keys)

**Goal**: health should reflect configured DB backend and “at least one provider key present.”

**Scope**:
- Update `src/autopack/health_checks.py` (or whichever module owns health logic) so:
  - DB health checks Postgres connectivity when Postgres is configured, and SQLite file checks only when SQLite is configured.
  - API key checks require at least one supported provider key (not all keys).

**Watch out**:
- Avoid requiring GLM if it’s tooling-only; keep provider posture consistent with docs/feature flags.
- Add tests covering key combinations and DB URL modes.

**Validation**:
- targeted pytest runs for the health check tests + `test-core` locally if feasible.

### PR-06: Rate limiting correctness behind nginx (keying strategy)

**Goal**: rate limiting must be correct in the canonical topology.

**Scope**:
- Decide and implement keying strategy:
  - preferred: per-principal (`X-API-Key` / JWT subject), not per-IP behind proxies
- Document the decision in `docs/DEPLOYMENT.md`.
- Add a minimal unit test around the limiter key function.

### PR-07: Frontend maturity (tests + sourcemap posture + auth story)

**Scope**:
- Decide whether production builds should ship sourcemaps (internal) or not (hosted/public).
- If UI is production-relevant: add a minimal test harness (keep dependencies minimal; prefer modern defaults).
- Ensure no secret is ever embedded in the frontend bundle.

### PR-08+: Maintainability program (seam refactors) — large scope, do last

These are multi-PR refactors; keep each PR behavior-preserving and contract-tested.

**Order**:
1) Split `src/autopack/main.py` into routers without changing route shapes.
2) Add seam tests (route shape / auth coverage contracts).
3) Introduce executor phase handler registry and extract pure helpers.
4) Remove/limit broad lint ignores as seams are isolated.

**Watch out**:
- Do not change APIs while extracting routers.
- Always add contract tests to prevent drift.

---

## PR hygiene (must follow)

- Keep PRs small and stackable (one theme per PR).
- Always include in PR description:
  - **Summary**
  - **Why** (tie back to README ideal state: safe/deterministic/mechanical)
  - **Test plan** (exact commands run)
- Do not add or commit generated artifacts:
  - `__pycache__/`, `*.pyc`, `.pytest_cache/`, build outputs

---

## “Stop conditions” (pause and re-evaluate)

- If docs integrity tests start failing broadly, you likely expanded enforcement scope too far (especially on append-only ledgers).
- If feature-flags registry scope explodes, you need a stricter boundary decision before continuing.
- If refactors start changing route behavior, stop and add contract tests before proceeding.

