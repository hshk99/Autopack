## Autopack Improvement Audit (Delta) — 2026-01-11

> **HISTORICAL SNAPSHOT** — This audit was fully implemented via PRs #103–#110. Kept as a record of the audit pass; not a canonical planning surface. See `docs/BUILD_HISTORY.md` for durable status.

**Scope**: "What's still worth improving" in the current repo state **in addition to** (and sometimes *because of*) the existing comprehensive scan artifacts and recent PR trajectory.

This file intentionally avoids duplicating existing “single-pane” backlogs. Where possible, it points to canonical sources and only records **new deltas, stale-claim fixes, and cross-cutting gaps** that are easy to miss.

---

### 0) Existing “comprehensive scan” artifacts (already present)

If you want the *already-written* repo-wide scans/backlogs, start here:

- **Primary repo-wide backlog (P0–P3)**: `docs/IMPROVEMENTS_GAP_ANALYSIS.md`
- **Single-pane scan report**: `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
- **North-star navigation**: `docs/INDEX.md` + SOT ledgers (`docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, `docs/ARCHITECTURE_DECISIONS.md`)
- **Workspace “ideal state” spec**: `docs/WORKSPACE_ORGANIZATION_SPEC.md`

This delta audit focuses on gaps that remain *after* those scans (or places where those docs are now likely stale due to recent PRs).

---

### 1) Delta findings (new or still-open improvements)

#### 1.1 Feature flags registry contract is incomplete (important “one truth” gap)

- **What**: `config/feature_flags.yaml` declares “**CONTRACT: All AUTOPACK_* environment variables must be documented here**”, but at least two README-described flags are not present:
  - `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING`
  - `AUTOPACK_SOT_RETRIEVAL_ENABLED`
- **Why this matters**: Env vars are part of the repo’s “mechanically enforceable interface”. Missing flags in the registry becomes a “two truths” source (docs/code vs registry).
- **Root cause**: The current registry test (`tests/ci/test_feature_flags_registry.py`) only detects env vars referenced via `os.getenv(...)` / `os.environ(...)`. Many settings are configured via Pydantic settings aliases and won’t be caught.
- **Action**:
  - Add the missing SOT flags to `config/feature_flags.yaml`.
  - Strengthen the registry contract test to also detect env var names embedded in Settings aliases (or in `AliasChoices(...)`).
  - Add a targeted contract test that ensures README-listed “operator knobs” (SOT/memory toggles) are present in the registry.

##### 1.1.1 Concrete evidence (why the current test won’t catch this)

- The settings fields exist in `src/autopack/config.py` as Pydantic `BaseSettings` fields:
  - `autopack_enable_sot_memory_indexing` → env var `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING`
  - `autopack_sot_retrieval_enabled` → env var `AUTOPACK_SOT_RETRIEVAL_ENABLED`
- Those env vars are *not* referenced via `os.getenv(...)` anywhere in production code, so the current regex-based test will never see them.

##### 1.1.2 Broader issue: registry claims “all runtime env vars”, but many are not represented

Even restricting attention to `src/autopack/config.py`, there are multiple runtime env vars that influence behavior but are not present in the registry today (examples):

- `AUTOPACK_ARTIFACT_READ_SIZE_CAP` / `ARTIFACT_READ_SIZE_CAP_BYTES`
- `AUTOPACK_ARTIFACT_REDACTION` / `ARTIFACT_REDACTION_ENABLED`
- `DATABASE_URL_FILE`, `AUTOPACK_API_KEY_FILE`, `JWT_PRIVATE_KEY_FILE`, `JWT_PUBLIC_KEY_FILE`

If the intention is “feature_flags.yaml is the *full* env var registry”, it should include these. If the intention is “only AUTOPACK_*”, the file header + docstrings should be narrowed to avoid “two truths”.

#### 1.1.3 Rollback flag is documented but not actually wired (high-signal drift)

- **What**:
  - `src/autopack/config.py` comments and tests reference `AUTOPACK_ROLLBACK_ENABLED=true`,
  - but the actual settings field is `executor_rollback_enabled` with **no** `validation_alias`, so the env var that would actually be read is `EXECUTOR_ROLLBACK_ENABLED` (Pydantic default field-name mapping).
- **Evidence**:
  - `tests/autopack/test_build145_rollback_smoke.py` sets `AUTOPACK_ROLLBACK_ENABLED` but does not assert behavior (placeholder), masking drift.
  - `src/autopack/governed_apply.py` gates rollback on `settings.executor_rollback_enabled`.
- **Action**:
  - Choose one canonical env var name and make it true:
    - add `validation_alias=AliasChoices("AUTOPACK_ROLLBACK_ENABLED", "EXECUTOR_ROLLBACK_ENABLED")` **or**
    - update docs/tests to use `EXECUTOR_ROLLBACK_ENABLED`.
  - Add a real contract test that proves the env var toggles the behavior (not just “setting exists”).

#### 1.2 Pre-commit vs CI lint drift (local/CI “two truths” risk)

- **What**: `.pre-commit-config.yaml` pins `ruff-pre-commit` at `v0.1.9`, while the repo’s actual ruff version in dev deps is far newer (e.g., `requirements-dev.txt` currently pins `ruff==0.14.10`).
- **Why**: This breaks “local == CI” for lint/format. Developers can get different rule behavior locally than CI (and vice versa).
- **Action**:
  - Update pre-commit hook versions to align with the versions CI effectively uses (or make CI use pre-commit as the single enforcement surface).
  - Ensure the “mirror CI checks” comment in `.pre-commit-config.yaml` is actually true.

#### 1.9 Mechanical diff: env vars implied by `Settings` vs feature-flags registry (actionable list)

This is the mechanically-derived “missing flags” set from `src/autopack/config.py` (Pydantic `BaseSettings` fields + `AliasChoices(...)`), compared against the documented names in `config/feature_flags.yaml` (`flags` + `external_env_vars` sections).

**Key insight**: the existing contract test (`tests/ci/test_feature_flags_registry.py`) cannot detect these because it only looks for `os.getenv(...)` usage, while most of these are settings fields.

##### Missing `AUTOPACK_*` env vars in `config/feature_flags.yaml`

These `AUTOPACK_*` env vars are implied by Settings field names and/or aliases, but are not currently present in the registry:

- `AUTOPACK_ARTIFACT_EXTENDED_CONTEXTS`
- `AUTOPACK_ARTIFACT_HISTORY_PACK`
- `AUTOPACK_ARTIFACT_READ_SIZE_CAP`
- `AUTOPACK_ARTIFACT_REDACTION`
- `AUTOPACK_ARTIFACT_SUBSTITUTE_SOT_DOCS`
- `AUTOPACK_DB_BOOTSTRAP`
- `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING`
- `AUTOPACK_SOT_CHUNK_MAX_CHARS`
- `AUTOPACK_SOT_CHUNK_OVERLAP_CHARS`
- `AUTOPACK_SOT_RETRIEVAL_ENABLED`
- `AUTOPACK_SOT_RETRIEVAL_MAX_CHARS`
- `AUTOPACK_SOT_RETRIEVAL_TOP_K`

##### Missing non-`AUTOPACK_*` alias env vars in `config/feature_flags.yaml` (decision: document or explicitly exclude)

These are non-AUTOPACK alias env vars that are accepted via `AliasChoices(...)` (so they are part of the runtime interface), but are not currently represented in the registry:

- `ARTIFACT_EXTENDED_CONTEXTS_ENABLED`
- `ARTIFACT_HISTORY_PACK_ENABLED`
- `ARTIFACT_READ_SIZE_CAP_BYTES`
- `ARTIFACT_REDACTION_ENABLED`
- `ARTIFACT_SUBSTITUTE_SOT_DOCS`
- `DB_BOOTSTRAP_ENABLED`
- `ENVIRONMENT`

##### Recommendation (to keep “one truth”)

- If `config/feature_flags.yaml` is meant to be the full runtime env-var registry:
  - Add **all** of the above, and update the test to parse `AliasChoices(...)` plus Settings field names.
- If it is meant to be “AUTOPACK_* only”:
  - Keep the **AUTOPACK_*** list complete (add the 12 missing), and explicitly document that non-AUTOPACK aliases are legacy/back-compat and intentionally excluded (and then add a separate test that enforces that rule).

#### 1.10 Mechanical scan: env vars used directly in `src/autopack/*` vs feature-flags registry

This scan looks for env vars referenced via:

- `os.getenv("NAME")`
- `os.environ.get("NAME")`
- `os.environ["NAME"]`

across **all** `src/autopack/**/*.py`, and compares the discovered names to what is documented in `config/feature_flags.yaml`.

**Result (current repo)**:

- scanned files: 347
- env vars found: 66
- missing from registry: 26
  - missing `AUTOPACK_*`: 6
  - missing non-`AUTOPACK_*`: 20

##### 1.10.1 Missing `AUTOPACK_*` env vars (used in code, not in registry)

- `AUTOPACK_AUTOFIX_TS` (used as an optional operator stamp)
- `AUTOPACK_LOG_DIR`
- `AUTOPACK_LOG_LEVEL`
- `AUTOPACK_TELEGRAM_ENABLED`
- `AUTOPACK_TELEGRAM_BOT_TOKEN`
- `AUTOPACK_TELEGRAM_CHAT_ID`

**High-signal mismatch**: Docs and registry currently emphasize `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`, but the modern approvals path in `src/autopack/approvals/service.py` checks for `AUTOPACK_TELEGRAM_*`.

##### 1.10.2 Missing non-`AUTOPACK_*` env vars (used in code, not in registry)

- **Security / governance**:
  - `AUTO_APPROVE_BUILD113` (legacy approval endpoint)
  - `APPROVAL_TIMEOUT_MINUTES`
  - `APPROVAL_DEFAULT_ON_TIMEOUT`
  - `CORS_ALLOWED_ORIGINS`
  - `LIVE_TRADING_ENABLED`
- **Observability / debugging**:
  - `DEBUG_DB_IDENTITY`
- **Tuning / feature toggles**:
  - `EMBEDDING_CACHE_MAX_CALLS_PER_PHASE` (overrides `settings.embedding_cache_max_calls_per_phase`)
  - `USE_OPENAI_EMBEDDINGS`
- **Service config / legacy aliases**:
  - `QDRANT_HOST` (there is also `AUTOPACK_QDRANT_HOST`)
  - `GLM_API_BASE`
- **Integration secrets (potentially future/experimental)**:
  - `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`
  - `TWITTER_BEARER_TOKEN`
- **Environment / CI / platform** (likely intentionally not “feature flags”, but currently part of the runtime surface):
  - `PYTHONPATH`, `PYTHONUTF8`, `PYTEST_CURRENT_TEST`, `LOCALAPPDATA`, `GITHUB_TOKEN`, `WIZTREE_PATH`

##### 1.10.3 Recommendation (mechanical enforcement fix)

The existing “feature flags registry” test should be upgraded from regex-based scanning to **AST-based extraction**, and it should also include:

- Settings field name → env var mapping (Pydantic default behavior)
- `AliasChoices(...)` string literals (back-compat aliases)
- direct env var access via `os.environ["X"]`

This turns `config/feature_flags.yaml` into a truly mechanically enforceable “one truth” surface instead of an aspirational doc.

#### 1.3 Requirements generation metadata drift (minor, but confusing and avoidable)

- **What**: `requirements*.txt` headers indicate they were generated with Python 3.10, while `pyproject.toml` requires `>=3.11` and CI is pinned to 3.11.
- **Why**: It makes “canonical lock generation environment” ambiguous and undermines determinism claims (even if the content is currently correct).
- **Action**:
  - Regenerate `requirements.txt` / `requirements-dev.txt` in the declared canonical environment (Linux/CI, Python 3.11) so the header matches policy.
  - Consider adding a CI contract that verifies the pip-compile header matches the repo’s declared canonical Python version.

#### 1.4 ESLint config discoverability (DX clarity)

- **What**: The repo uses a root `.eslintrc.cjs` (works; `npm run lint` succeeds), but `docs/WORKSPACE_ORGANIZATION_SPEC.md` lists `.eslintrc.cjs` as allowed at root while the repo snapshot tooling can miss dotfiles, leading to “false missing” during audits.
- **Why**: This is mostly a tooling/audit pitfall, but it’s a recurring “scan confusion” vector.
- **Action**:
  - Ensure docs index (`docs/PROJECT_INDEX.json` or `docs/WORKSPACE_ORGANIZATION_SPEC.md`) explicitly mentions the root ESLint config is `.eslintrc.cjs`.
  - Optional: add a tiny doc-contract test that asserts `.eslintrc.cjs` exists when `package.json` has an eslint script.

#### 1.5 Security workflow: Safety is artifact-only (explicitly decide posture)

- **What**: `.github/workflows/security.yml` runs Safety but intentionally does not gate (artifacts only, `|| true`).
- **Why**: That’s fine if it’s intentionally informational, but it should be explicit whether Safety is:
  - **A)** informational-only, or
  - **B)** part of the “regression-only blocking” posture (then it needs stable normalization + diff gate, like Trivy/CodeQL).
- **Action**:
  - Decide and document the Safety posture (and keep it consistent with `SECURITY.md` and security docs).
  - If enforcement is desired, implement deterministic normalization + baseline/diff-gate (or replace with a more deterministic scanner for Python deps).

#### 1.6 CI determinism mismatch: Postgres service tag not patch-pinned (optional)

- **What**: CI uses `postgres:15-alpine` for tests, while `docker-compose.yml` uses `postgres:15.10-alpine`.
- **Why**: This can cause “works in compose, fails in CI” drift via behavior differences (rare, but it’s a determinism footgun).
- **Action**:
  - Align CI’s Postgres image tag with the compose tag (or document why CI intentionally uses a moving patch line).
  - Optional: pin digest for CI services if you want maximum determinism.

#### 1.7 Migration surface “two truths” still leaks into governance docs/examples

- **What**: You have DEC-048 (scripts-first migrations), but governance examples still reference `alembic/versions/*` in places (e.g., `docs/GOVERNANCE.md`).
- **Why**: Even as an example, it can reintroduce ambiguity for operators (“is Alembic canonical here?”).
- **Action**:
  - Normalize examples to the repo’s canonical migration surface (`scripts/migrations/`) unless the file is explicitly “generic downstream template”.
  - Ensure the chosen posture is consistent across: docs, risk scoring patterns, and dependencies (`pyproject.toml`).

#### 1.8 Makefile portability (Windows shell mismatch)

- **What**: `Makefile` includes Unix tools (`rm`, `find`, `sleep`, `bash`) that are not portable to Windows without MSYS/WSL/Git Bash.
- **Why**: This is a DX footgun for Windows contributors (and this repo is actively used on Windows).
- **Action**:
  - Either: document “Makefile requires Bash/WSL” explicitly, or
  - Provide Windows-friendly equivalents (PowerShell scripts) or a Python-based task runner.

#### 1.11 Stale “IN PROGRESS” / “TODO implement” claims in canonical planning docs (two-truth risk)

- **What**: There are still “IN PROGRESS” / “TODO implement” style claims in `docs/` that likely contradict the current codebase state.
- **Evidence** (examples):
  - `docs/FUTURE_PLAN.md` contains `BUILD-041` marked “🔄 IN PROGRESS: Executor State Persistence Fix”, but executor state persistence is described as implemented elsewhere (e.g., in the improvement backlog / execution history).
- **Why**: This is exactly the “two truths” failure mode the repo is built to avoid: a planning doc says something is unfinished while the code/tests/SOT say it’s done.
- **Action**:
  - Reconcile “IN PROGRESS” markers in *canonical* docs (especially `FUTURE_PLAN.md`) to either:
    - **✅ implemented** with evidence pointers (PR/build/test), or
    - explicitly “historical snapshot” (and then exclude from “current status” surfaces).

#### 1.12 `docs/ARCHITECTURE.md` appears stale relative to current repo structure (update or label)

- **What**: `docs/ARCHITECTURE.md` is `Last Updated: 2025-12-29` and still contains drift-prone statements such as:
  - File paths like `src/autopack/...` (this repo is `src/autopack/...`)
  - Category inference examples referencing `alembic/versions/*.py` as canonical “database” deliverables.
- **Why**: `docs/ARCHITECTURE.md` is an onboarding/truth surface. If it’s stale, it becomes a high-cost source of incorrect “repo mental model.”
- **Action**:
  - Either refresh it to match current architecture decisions (scripts-first migrations, canonical frontend, operator auth posture), or label it as legacy/historical and point readers to `docs/INDEX.md` + SOT ledgers instead.

#### 1.13 Workstation-specific absolute paths still exist across docs (containment policy)

- **What**: There are many `C:\\dev\\Autopack` / `c:/dev/Autopack` occurrences across `docs/` (mostly in guides/cursor/historical).
- **Why**: Even if these aren’t “canonical”, they’re copy/paste bait. You already have the right principle (`$REPO_ROOT/` in `WORKSPACE_ORGANIZATION_SPEC.md`), but the repo still contains many violations.
- **Action**:
  - Ensure these docs are either:
    - labeled **LEGACY/HISTORICAL — do not copy/paste**, or
    - normalized to `$REPO_ROOT` notation if they remain canonical.
  - Keep the existing CI “canonical doc refs” checker strict, and ensure the allowlist of canonical docs is explicit (so enforcement is unambiguous).

#### 1.14 CI “mechanical enforcement” posture: remaining non-blocking surfaces (explicit stance recommended)

- **What**: Some CI checks are intentionally informational/non-blocking (e.g., staged mypy adoption, aspirational tests, Safety scan artifacts).
- **Why**: This is fine, but the README’s “mechanically enforceable via CI contracts” ideal state benefits from a clearly documented stance: what is blocking vs informational and why.
- **Action**:
  - Add a short “CI enforcement ladder” section (or ensure it exists and is current) that names:
    - blocking jobs (core safety contract),
    - informational jobs (roadmap tracking),
    - promotion criteria (when informational becomes blocking).

---

### 2) Suggested “next PR” stack (delta-only, minimal churn)

This list intentionally excludes items that are already fully tracked in the existing comprehensive docs, unless they’re **stale-claim cleanup** or **cross-cutting enforcement gaps**.

- **P0**: Update `config/feature_flags.yaml` to include SOT memory flags + expand registry test to detect Settings alias env vars.
- **P1**: Align `.pre-commit-config.yaml` tool versions with CI (ruff hook rev bump, consider adding a formatter hook strategy).
- **P1**: Regenerate requirements on canonical Python (3.11) so headers match policy, and optionally enforce header consistency.
- **P2**: Decide Safety posture (informational vs diff-gated) and document it.
- **P2**: Align CI Postgres tag with compose (or add an ADR explaining why it’s intentionally different).
- **P2**: Replace “Alembic” examples in operator-facing docs with scripts-first migration examples (or clearly label as generic).
- **P2**: Make Makefile Windows-safe (or explicitly declare it “requires bash/WSL” and add PS equivalents).

---

### 3) Notes on recent PR trajectory (what this delta is reacting to)

Recent PRs show strong progress toward the README’s “ideal state”: governance hardening, artifact boundary safety, security diff gates, and docs drift enforcement. The remaining work is now mostly about:

- **eliminating “second truth” surfaces** (feature flags registry, examples that contradict ADRs),
- **closing local/CI drift** (pre-commit tool versions, dependency lock metadata),
- **tightening the operator interface** (docs and commands are mechanically correct across Windows/Linux).

---

### 4) Tight PR plan (smallest “two truths” closure set)

This is the smallest PR stack that specifically closes the remaining **“two truths”** risks you called out:

- `docs/FUTURE_PLAN.md` truth drift
- `docs/ARCHITECTURE.md` staleness/drift
- portable path normalization policy (no workstation paths in canonical docs)
- CI enforcement ladder documentation (blocking vs informational)

#### PR-T1 — Reconcile canonical “current status” docs (FUTURE_PLAN + ARCHITECTURE)

- **Goal**: remove contradictory “IN PROGRESS” / stale claims from canonical onboarding/planning docs.
- **Scope (files)**:
  - `docs/FUTURE_PLAN.md`
  - `docs/ARCHITECTURE.md`
- **Edits (minimal)**:
  - In `FUTURE_PLAN.md`, reconcile any “IN PROGRESS” items that are now implemented (example: `BUILD-041` state persistence) by either:
    - marking ✅ complete + linking to the authoritative evidence (BUILD/PR/tests), or
    - explicitly labeling as “historical snapshot” if you intentionally keep the old narrative.
  - In `ARCHITECTURE.md`, update the most drift-prone facts only:
    - canonical backend path (`src/autopack/...`)
    - canonical migrations posture (scripts-first per DEC-048; avoid implying Alembic is canonical)
    - (optional) brief note that deeper truth lives in SOT ledgers (INDEX already points there)
- **Acceptance criteria**:
  - No “IN PROGRESS” claims remain in canonical status docs unless they truly match current repo state.
  - `docs-sot-integrity` CI job still passes (no doc-contract regressions).

##### PR-T1 ready-to-execute checklist (smallest diff footprint)

- **Files to edit**:
  - `docs/FUTURE_PLAN.md`
  - `docs/ARCHITECTURE.md`

- **`docs/FUTURE_PLAN.md` — exact targets**:
  - **Search**: `**BUILD-041** (2025-12-17T02:00) - 🔄 IN PROGRESS: Executor State Persistence Fix`
    - **Replace (minimal, safe)**: change only the status phrase to reflect current truth, without rewriting the historical sub-bullets:
      - `- 🔄 IN PROGRESS:` → `- ✅ COMPLETE (see evidence links below):`
  - **Search**: `- 🔄 Phase 3: Refactor execute_phase() to use database state (IN PROGRESS)`
    - **Replace**: `- ✅ Implemented (see: docs/IMPROVEMENTS_GAP_ANALYSIS.md section “6.11 Executor state persistence” + corresponding BUILD_HISTORY entry)`
  - **Optional (lowest churn)**: keep the remaining Phase 4–6 bullets but prefix them with `Historical plan:` so they’re not interpreted as current state.

- **`docs/ARCHITECTURE.md` — exact targets**:
  - **Global find/replace (safe, mechanical)**:
    - **Find**: `src/autopack/`
    - **Replace**: `src/autopack/`
  - **Search**: ``- `alembic/versions/*.py` → database``
    - **Replace**: ``- `scripts/migrations/*.py` → database (scripts-first canonical; see DEC-048)``
  - **Optional**: update the “Last Updated” line at the top to today (or add a “refreshed for path correctness” note).

- **CI checks that prove closure**:
  - **Must pass**: `.github/workflows/ci.yml` → `docs-sot-integrity` (doc-contract tests + drift checks).
  - **Specifically relevant**: `python scripts/ci/check_canonical_doc_refs.py` (runs in docs-sot-integrity).

- **Shortest diff approach**:
  - Don’t rewrite the entire FUTURE_PLAN item; just replace the “IN PROGRESS” claims and add 1–2 evidence links.
  - In ARCHITECTURE, do only the two mechanical corrections (path prefix + migration surface example).

#### PR-T2 — Canonical doc portability policy + mechanical enforcement (workstation paths + legacy path mapping)

- **Goal**: make “portable path notation” real for canonical operator docs, and enforce it mechanically.
- **Scope (files)**:
  - `docs/WORKSPACE_ORGANIZATION_SPEC.md` (policy is already present; tighten if needed)
  - `docs/GOVERNANCE.md` (canonical operator docs list is the allowlist)
  - `scripts/ci/check_canonical_doc_refs.py` (extend enforcement)
- **Edits (minimal)**:
  - Extend `scripts/ci/check_canonical_doc_refs.py` to additionally flag workstation-specific paths in canonical operator docs:
    - `C:\\dev\\Autopack`, `c:/dev/Autopack` (and optionally other absolute-root patterns)
    - require `$REPO_ROOT/...` or relative paths instead
  - Fix any incorrect legacy mapping in that script that contradicts current repo reality:
    - today it treats `src/frontend/` as legacy; but in this repo the canonical frontend is `src/frontend/` (root Vite app). The checker should not nudge toward a non-canonical dashboard path.
- **Acceptance criteria**:
  - CI fails if any *canonical operator doc* contains workstation-specific paths.
  - CI fails if canonical docs contain truly legacy/non-existent paths (existing behavior), but the mapping text is consistent with the repo’s actual canonical structure.

##### PR-T2 ready-to-execute checklist (smallest diff footprint)

- **Files to edit**:
  - `scripts/ci/check_canonical_doc_refs.py`
  - (only if CI fails afterward) the specific canonical docs flagged by the checker

- **`scripts/ci/check_canonical_doc_refs.py` — exact targets**:
  - **Fix incorrect legacy mapping**:
    - **Search** inside `LEGACY_PATH_PATTERNS` for the tuple:
      - `(r"src/frontend/", "src/frontend/ (legacy path - frontend in src/autopack/dashboard/)"),`
    - **Change** (minimal): remove this entry entirely. `src/frontend/` is canonical in this repo.
    - **Also update** the remediation text block accordingly:
      - **Search**: `- src/frontend/ -> src/autopack/dashboard/`
      - **Delete** that line.
  - **Fix canonical security README path** (low-risk correctness fix):
    - **Search** in `CANONICAL_OPERATOR_DOCS`: `docs/security/README.md`
    - **Replace**: `security/README.md`
  - **Add workstation-path enforcement**:
    - Add a new pattern set (or extend existing) that flags workstation-specific absolute paths in canonical docs:
      - `C:\\dev\\Autopack`
      - `c:/dev/Autopack`
    - Keep behavior consistent with the existing “legacy path violation” output.
    - **Note**: scope this check to `CANONICAL_OPERATOR_DOCS` only (do not scan all docs to avoid historical ledger noise).

    **Copy/paste snippet (minimal, reuses existing mechanism)**:

```python
# Add these entries to LEGACY_PATH_PATTERNS (workstation path drift).
# Canonical operator docs must use $REPO_ROOT/... or relative paths, never a workstation absolute.
LEGACY_PATH_PATTERNS = [
    # ... existing patterns ...

    # Workstation-specific absolute paths (do not allow in canonical docs)
    (r"[A-Za-z]:\\\\dev\\\\Autopack", "C:\\\\dev\\\\Autopack (workstation path - use $REPO_ROOT/)"),
    (r"(?i)c:/dev/Autopack", "c:/dev/Autopack (workstation path - use $REPO_ROOT/)"),
]
```

- **Expected CI checks that prove closure**:
  - `.github/workflows/ci.yml` → `docs-sot-integrity` must pass (it runs `check_canonical_doc_refs.py`).

- **Shortest diff approach**:
  - Only touch the checker + update any canonical doc(s) that it newly flags.
  - Do not normalize `docs/guides/` / `docs/cursor/` content unless they are in the canonical allowlist.

#### PR-T3 — CI enforcement ladder doc (blocking vs informational, promotion criteria)

- **Goal**: make CI’s “mechanical enforcement” posture explicit so there’s no ambiguity about what’s a hard contract vs a progress tracker.
- **Scope (files)**:
  - Prefer adding a small section to `docs/CONTRIBUTING.md` (keeps docs surface small), or add `docs/CI_ENFORCEMENT_LADDER.md` and link it from `docs/INDEX.md`.
- **Content (minimal)**:
  - **Blocking**: core tests, docs-sot-integrity, security diff gates, workspace structure verification.
  - **Informational**: mypy staged adoption (`continue-on-error`), aspirational tests, Safety artifacts.
  - **Promotion rules**: when an informational check becomes blocking (e.g., mypy allowlist reaches N modules; Safety becomes diff-gated; aspirational tests graduate to core).
- **Acceptance criteria**:
  - One doc explains “what blocks PRs and why” in ≤ ~60 lines.
  - Linked from `docs/INDEX.md` or `docs/CONTRIBUTING.md` so it’s discoverable.

##### PR-T3 ready-to-execute checklist (smallest diff footprint)

- **Preferred file**: `docs/CONTRIBUTING.md` (keeps the doc surface small; already contains mypy ladder).

- **Insertion point (exact)**:
  - Add a new section right after: `### Type Checking (Mypy Adoption Ladder)`
  - Suggested header: `### CI enforcement ladder (blocking vs informational)`

- **Content (copy/paste minimal template)**:
  - **Blocking (PR must be red)**:
    - `lint` job (ruff/black + policy drift checks)
    - `docs-sot-integrity` job (doc contracts, workspace structure, docs drift, canonical doc refs, SOT drift)
    - `test-core` job (core tests)
    - `frontend-ci` job (npm lint/typecheck/build)
    - `security.yml` diff gates (Trivy fs/image + CodeQL)
  - **Informational / tracking only**:
    - mypy step in `lint` (`continue-on-error: true`)
    - `test-aspirational` and `test-research` jobs (`continue-on-error: true`)
    - Safety scan artifacts in `security.yml` (`|| true`, artifact upload only)
  - **Promotion criteria** (keep it short):
    - Mypy: when Tier 1 expands to X modules and stays clean for N PRs → remove `continue-on-error`.
    - Safety: only becomes blocking once normalized + diff-gated (or replaced with deterministic scanner).
    - Aspirational: graduate tests by removing xfail markers and moving them into core selection.

- **Expected CI checks that prove closure**:
  - `docs-sot-integrity` should pass (doc tests will cover basic doc formatting and drift patterns).
  - No new CI jobs required; this is a documentation-only PR.



