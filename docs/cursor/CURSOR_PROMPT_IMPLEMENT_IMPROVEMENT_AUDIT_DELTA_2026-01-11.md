## Cursor Prompt: Implement `IMPROVEMENT_AUDIT_DELTA_2026-01-11` (Full Closure)

> **HISTORICAL SNAPSHOT** — This prompt was fully executed via PRs #103–#110. Kept as a record of the agent-driven closure; not a canonical planning surface.

**Objective**: Implement everything listed in `docs/reports/IMPROVEMENT_AUDIT_DELTA_2026-01-11.md` with the smallest safe diffs, preserving Autopack's core thesis: **safe, deterministic, mechanically enforceable via CI contracts**.

This prompt is written for a *separate Cursor agent* to execute end-to-end: code, docs, tests, and PRs.

---

### Ground rules (do not violate)

- **Do not create “two truths.”** If you update docs, ensure any CI guardrails/contract tests that assert the canonical truth also get updated (or vice versa).
- **Don’t rewrite history.** Avoid broad edits to append-only ledgers (BUILD_HISTORY/DEBUG_LOG/CHANGELOG/ARCHITECTURE_DECISIONS). Prefer targeted fixes to canonical operator docs and CI guards.
- **Keep diffs minimal.** Prefer small PRs with focused scope and clear CI validation.
- **No secrets committed.** Never add `.env`, tokens, credentials, or real secret values.
- **Don’t touch archive unless required.** The goal is “canonical truth surfaces” + enforcement, not archival churn.
- **Never manually edit the README SOT block.** The `<!-- SOT_SUMMARY_START --> ... <!-- SOT_SUMMARY_END -->` block in `README.md` must ONLY be updated via `python scripts/tidy/sot_summary_refresh.py --execute`.

---

### Recommended PR order (minimize cascade failures)

Implement in this order to avoid CI drift and rework:

1. **PR-01: Canonical docs truth drift closure** (PR‑T1)
2. **PR-02: Canonical doc portability enforcement + fix incorrect checker mapping** (PR‑T2)
3. **PR-03: CI enforcement ladder documentation** (PR‑T3)
4. **PR-04: Feature flags registry completeness + mechanical contract upgrade** (Delta 1.1 / 1.9 / 1.10)
5. **PR-05: Rollback env var wiring** (Delta 1.1.3)
6. **PR-06: Telegram env var truth convergence** (Delta 1.10.1 mismatch)
7. **PR-07: Pre-commit vs CI tool drift** (Delta 1.2)
8. **PR-08: Requirements header / canonical generation alignment** (Delta 1.3)
9. **PR-09: CI Postgres tag alignment (optional)** (Delta 1.6)
10. **PR-10: Makefile portability stance (doc-only or add PS runner)** (Delta 1.8)
11. **PR-11: Safety posture decision (doc-only or add enforcement)** (Delta 1.5)

If you want fewer PRs, you can merge PR‑T1/2/3 into one “docs+CI-hardening” PR, but **keep feature-flags changes separate** (those often cascade into many tests).

---

### Pre-flight: verify what is already done (avoid churn)

This repo may already have merged some or all of the delta items (e.g., via recent PRs).

Before making changes:

- Confirm whether each delta item is **already implemented** in the current branch by checking the relevant file(s) and tests.
- If a delta item is already implemented, do **not** re-implement it. Instead:
  - confirm the corresponding CI guard/test exists and passes,
  - and proceed to the next item.

This prevents “busywork” commits and preserves determinism (no accidental re-diffs).

---

### CI flow (what proves closure)

The repo’s CI is in `.github/workflows/ci.yml` and `.github/workflows/security.yml`.

**For each PR, ensure these pass (minimum):**

- **Docs / SOT Integrity** (`docs-sot-integrity` job):
  - `pytest -q tests/docs/`
  - `python scripts/tidy/verify_workspace_structure.py`
  - `python scripts/check_docs_drift.py`
  - `python scripts/ci/check_canonical_doc_refs.py`
  - `python scripts/tidy/sot_summary_refresh.py --check`
  - `python scripts/check_doc_links.py`
  - security burndown count check + SECBASE enforcement
- **Core tests** (`test-core` job)
- **Frontend CI** (`frontend-ci` job)
- **Security diff gates** (`security.yml` jobs) — especially if you touch security-related docs or config

---

### Non-optional pre-PR drift loop (must do every time)

Before opening **any** PR (docs or code), run the repo’s drift checks locally:

```bash
python scripts/check_docs_drift.py
python scripts/tidy/sot_summary_refresh.py --check
python scripts/check_doc_links.py
python scripts/tidy/verify_workspace_structure.py
pytest -q tests/docs/
```

If **any** drift is detected:

1) Regenerate derived state (only via the generator):

```bash
python scripts/tidy/sot_summary_refresh.py --execute
```

2) Re-run the drift checks above until clean.

3) Ensure the PR includes the drift-fix commit(s), so CI stays green.

**Critical rule**: never manually edit the `README.md` SOT summary block (`<!-- SOT_SUMMARY_START --> ... <!-- SOT_SUMMARY_END -->`). Always use `python scripts/tidy/sot_summary_refresh.py --execute`.

---

## SOT updates (required “close the loop” step per PR)

For each PR you open as part of this delta closure, ensure the relevant SOT surfaces are updated:

- **`docs/BUILD_HISTORY.md`**: add a concise entry describing what was changed and how it was verified (link to the PR number once created).
- **`docs/ARCHITECTURE_DECISIONS.md`**: only if a real decision is made (e.g., “Safety scan posture is informational-only”); add a DEC entry with rationale and constraints. Do not add DEC entries for pure mechanical fixes.
- **`docs/FUTURE_PLAN.md`**: if an item is deferred rather than implemented, record it as a tracked backlog item (with acceptance criteria) instead of leaving it implicit.

After updating any SOT docs, re-run the drift loop (above) and refresh derived state via:

- `python scripts/tidy/sot_summary_refresh.py --check`
- if needed: `python scripts/tidy/sot_summary_refresh.py --execute`

---

## PR‑T1 — FUTURE_PLAN + ARCHITECTURE (remove “two truths”)

### Goal
Remove stale “IN PROGRESS” claims and drift-prone examples from canonical docs without rewriting history.

### Files
- `docs/FUTURE_PLAN.md`
- `docs/ARCHITECTURE.md`

### Exact changes (shortest diff)

#### FUTURE_PLAN
- **Search**: `**BUILD-041** (2025-12-17T02:00) - 🔄 IN PROGRESS: Executor State Persistence Fix`
  - Replace `🔄 IN PROGRESS` with `✅ COMPLETE` **and add 1–2 evidence links** (prefer a BUILD_HISTORY anchor or the relevant section in `docs/IMPROVEMENTS_GAP_ANALYSIS.md`).
- **Search**: `- 🔄 Phase 3: Refactor execute_phase() to use database state (IN PROGRESS)`
  - Replace with an “implemented” statement + evidence pointers.
- Keep the rest of that BUILD-041 block mostly intact to avoid “rewrite history”; if needed prefix remaining sub-bullets with `Historical plan:` so they don’t read as current state.

#### ARCHITECTURE
- **Find/replace**:
  - `src/autopack/` → `src/autopack/`
- **Search**: ``- `alembic/versions/*.py` → database``
  - Replace with ``- `scripts/migrations/*.py` → database (scripts-first canonical; see DEC-048)``
- Optional: bump “Last Updated” date or add “refreshed for path correctness”.

### Validation
- Local: `pytest -q tests/docs/` (fast)
- CI: `docs-sot-integrity` must be green.

---

## PR‑T2 — Canonical doc portability enforcement + fix checker mapping

### Goal
Make workstation-path usage impossible in canonical operator docs, and ensure the existing canonical-doc checker doesn’t enforce a false legacy mapping.

### Files
- `scripts/ci/check_canonical_doc_refs.py`
- (only if CI flags them) canonical docs in the checker allowlist

### Exact changes (shortest diff)

1) **Fix incorrect legacy mapping in `check_canonical_doc_refs.py`**

- Remove the `src/frontend/` “legacy” entry (this repo’s canonical frontend is `src/frontend/`).
- Remove the corresponding remediation line `- src/frontend/ -> ...`.

2) **Fix canonical security README path**

- In `CANONICAL_OPERATOR_DOCS`, replace `README.md` with `security/README.md`.

3) **Add workstation-path enforcement (copy/paste snippet)**

Add these to `LEGACY_PATH_PATTERNS`:

```python
    # Workstation-specific absolute paths (do not allow in canonical docs)
    (r"[A-Za-z]:\\\\dev\\\\Autopack", "C:\\\\dev\\\\Autopack (workstation path - use $REPO_ROOT/)"),
    (r"(?i)c:/dev/Autopack", "c:/dev/Autopack (workstation path - use $REPO_ROOT/)"),
```

**Watch out**:
- Keep this scoped to `CANONICAL_OPERATOR_DOCS` only (do not scan all docs).
- After enabling, fix only the canonical docs that fail (likely `docs/ARCHITECTURE.md` and/or `docs/GOVERNANCE.md`).

### Validation
- Local: `python scripts/ci/check_canonical_doc_refs.py`
- CI: `docs-sot-integrity` must be green.

---

## PR‑T3 — CI enforcement ladder doc (blocking vs informational)

### Goal
Document what is PR-blocking vs informational, and when informational checks become blocking.

### Files
- Prefer: `docs/CONTRIBUTING.md` (append a short section after the existing Mypy ladder)

### Content checklist (keep ≤ ~60 lines)
- Blocking: `lint`, `docs-sot-integrity`, `test-core`, `frontend-ci`, `security.yml` diff gates
- Informational: mypy step (`continue-on-error`), aspirational/research tests, Safety artifacts
- Promotion criteria: short bullets for mypy/Safety/xfail graduation

### Validation
- CI: `docs-sot-integrity` must be green.

---

## PR‑04 — Feature flags registry: make it real and mechanically enforced

### Goal
Close the registry “contract gap” by making `config/feature_flags.yaml` reflect reality, and upgrade the contract test so it can’t miss Pydantic settings.

### Files
- `config/feature_flags.yaml`
- `tests/ci/test_feature_flags_registry.py`

### Implementation checklist

1) **Add missing `AUTOPACK_*` names** listed in the delta audit sections 1.9 + 1.10.1.
2) Decide policy for non-`AUTOPACK_*` env vars:
   - either document them too, or explicitly exclude them in the contract (and test that rule).
3) Replace/extend the existing regex-only scan with AST-based extraction:
   - detect `os.getenv/os.environ.get/os.environ[...]`
   - parse `src/autopack/config.py` for:
     - Settings field name → env var default mapping
     - `AliasChoices(...)` string literals

**Watch out**:
- Don’t turn this into a “list everything in the universe” registry. If you exclude platform/CI env vars, document that explicitly and enforce the boundary in tests.

### Validation
- Local: `pytest -q tests/ci/test_feature_flags_registry.py`
- CI: `lint` + `test-core` + `docs-sot-integrity`

---

## PR‑05 — Rollback env var wiring

### Goal
Make the documented rollback flag actually work, and add a real test.

### Checklist
- In `src/autopack/config.py`, add:
  - `validation_alias=AliasChoices("AUTOPACK_ROLLBACK_ENABLED", "EXECUTOR_ROLLBACK_ENABLED")` to `executor_rollback_enabled`
- Update the smoke test to assert behavior (currently placeholder).

### Validation
- Add/adjust tests under `tests/autopack/` and run `pytest -q tests/autopack/test_build145_rollback_smoke.py`.

---

## PR‑06 — Telegram env var truth convergence

### Goal
Make docs + registry + code agree on Telegram configuration variable names.

### Options (pick one, keep minimal)
- **Option A (recommended)**: Treat `AUTOPACK_TELEGRAM_*` as canonical; keep `TELEGRAM_*` as legacy aliases only (document + registry + tests).
- **Option B**: Swap code to use `TELEGRAM_*` (bigger blast radius; avoid unless necessary).

### Validation
- Ensure registry and any doc references align. Run `docs-sot-integrity` locally if possible.

---

## PR‑07 — Pre-commit vs CI drift

### Goal
Align pre-commit tool pins with CI reality to keep local == CI behavior.

### Checklist
- Bump `.pre-commit-config.yaml` hook versions (ruff hook rev, etc.).
- Ensure local pre-commit run matches CI’s ruff/format behavior.

---

## PR‑08 — Requirements header / canonical generation alignment

### Goal
Regenerate requirements using the declared canonical environment so headers match policy (and consider adding a guard).

### Checklist
- Regenerate `requirements.txt` + `requirements-dev.txt` in Linux/CI + Python 3.11.
- Ensure you don’t break platform markers (win32 vs non-win32 packages).

---

## PR hygiene and finalization

- Prefer **one feature per PR**, with a short test plan in the PR description.
- For each PR, include:
  - **Summary** (what changed)
  - **Why** (which “two truths” risk it closes)
  - **Test plan** (local commands run + CI jobs expected)

---

## What to do with the audit artifacts (this prompt + delta report)

These audit docs are planning artifacts. Once their actionable items are fully implemented and reflected in SOT:

- Prefer consolidating the durable “what/why/status” into SOT (`BUILD_HISTORY`, `ARCHITECTURE_DECISIONS`, `FUTURE_PLAN`).
- After consolidation, these audit docs can be:
  - **kept as historical snapshot** under `docs/reports/` (if you want a record of the audit pass), or
  - **routed to `archive/`** (if you want to keep `docs/` lean), consistent with `docs/WORKSPACE_ORGANIZATION_SPEC.md`.

Do not let planning reports become a competing truth surface.

---

### Out of scope (but required for downstream published/monetized projects)

Autopack is an internal framework. For downstream target projects that will be published/monetized, apply release/provenance and supply-chain policies **in the target repo**, not here:

- SBOM generation + signing/provenance (SLSA-style)
- container hardening (non-root, minimal base, digest pinning, runtime seccomp/AppArmor if applicable)
- security posture + CI gating (vuln scanning, regression-only diff gates, secret scanning)
- release process + versioning policy

Keep Autopack focused on being a deterministic, mechanically enforceable builder/auditor framework; let target repos own their production release policy.

### Branch naming + PR title conventions (match current repo style)

Recent merges use lightweight Conventional-Commit-like prefixes and descriptive scopes, and branches often follow `docs/`, `feat/`, `fix/`, `chore/` patterns.

- **Branch names** (recommended):
  - `docs/improvement-audit-delta-t1-future-plan-architecture`
  - `fix/canonical-doc-refs-workstation-paths`
  - `chore/precommit-ruff-sync`
  - `fix/feature-flags-registry-contract`
  - `docs/ci-enforcement-ladder`

- **PR titles** (recommended patterns):
  - `docs(future-plan): reconcile BUILD-041 status with current implementation`
  - `docs(architecture): fix canonical paths and migration surface examples`
  - `fix(ci-docs): enforce canonical docs portability + correct legacy path mapping`
  - `docs(ci): document CI enforcement ladder (blocking vs informational)`
  - `chore(precommit): align ruff hook rev with CI`
  - `test(ci): harden feature flags registry contract (Settings + AST scan)`

Keep titles short, start with the change type (`docs`, `fix`, `chore`, `test`, `feat`), and include a scope in parentheses when it helps.

---

### “Stop conditions” (when to pause and re-evaluate)

- If doc-contract tests start failing broadly: you probably touched a “canonical truth surface” unintentionally.
- If `docs-sot-integrity` fails due to drift checks: update only the minimal doc lines that violated the mechanical rule.
- If feature-flags expansion becomes huge: you need a policy boundary (what belongs in registry vs not).
