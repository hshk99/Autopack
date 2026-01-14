# Implementation Plan: Dev-Loop Speedups via Seam Refactors (High-ROI + Secondary)

**Date**: 2026-01-12
**Audience**: “implementation Cursor” (code changes expected)
**Goal**: reduce day-to-day iteration friction (merge conflicts, review difficulty, test isolation pain) while preserving Autopack’s README thesis: **safe, deterministic, mechanically enforceable via CI contracts**.

This plan intentionally gives **one clear direction** (no “choose option A/B”) and is written as an execution guide + PR stack.

---

## 0) North-star constraints (do not violate)

- **Behavior stability first**: refactor by extraction, not by redesign.
- **Mechanical enforcement**: every seam extraction must have a contract test (or extend an existing one) that prevents drift.
- **No “two truths”**:
  - Do not introduce duplicate “canonical” docs.
  - Do not weaken doc/SOT contract tests to “make CI green”.
- **Historical ledgers are append-only**: do not rewrite `docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, `docs/CHANGELOG.md` except through official tidy scripts.
- **README SOT block is generator-owned**: never manually edit the `<!-- SOT_SUMMARY_START/END -->` block.

---

## 1) The plan sources of truth

- **Execution seam queue + already-done tracking**: `docs/reports/IMPROVEMENT_GAPS_CURRENT_2026-01-12.md` (Sections 6–7)
- **Ideal-state posture**: `README.md` + `docs/INDEX.md`
- **Drift gates**: `tests/docs/` + `scripts/check_docs_drift.py` + `scripts/tidy/sot_summary_refresh.py`

This file defines **the next refactor targets** (high-ROI + secondary) and the **PR/testing discipline** to keep the repo deterministic.

---

## 2) Highest-ROI refactors (do these next)

### 2.1 Shrink the executor mega-file

**Target**: `src/autopack/autonomous_executor.py`
**Reason**: largest merge-conflict surface + hardest to review + easiest to reintroduce drift.

**Direction**: continue extraction into `src/autopack/executor/*` and `src/autopack/supervisor/*` so the executor becomes a small orchestrator.

**Required seams** (must be done in this order):

1. `SupervisorApiClient` (all HTTP calls live here)
2. `ApprovalFlow` (approval request/poll; testable clock)
3. `CiRunner` (CI execution + parsing + log persistence)
4. `RunCheckpoint` (checkpoint/rollback; subprocess isolated)
5. `ContextPreflight` + `RetrievalInjection` (preflight/injection policy separated from loading mechanics)
6. `ContextLoadingHeuristic` extracted (no giant helper buried inside executor)
7. Remove “obsolete code below” blocks from runtime (move to `archive/` if needed)

**Contract tests**: follow `docs/reports/IMPROVEMENT_GAPS_CURRENT_2026-01-12.md` Section 6.2.

### 2.2 Split provider mega-client (Anthropic)

**Target**: `src/autopack/anthropic_clients.py`
**Reason**: complex parsing/prompt/transport code; regressions are subtle; test isolation is currently expensive.

**Direction**: split into:
- transport (SDK wrapper)
- prompt builders
- parsers (full-file/ndjson/structured edit/legacy diff)
- diff generator helper (deterministic)

**Contract tests**: add parser/transport/prompt-mode contracts before moving logic.

### 2.3 Micro-kernel split for governed apply (safety-critical)

**Target**: `src/autopack/governed_apply.py`
**Reason**: safety boundary; needs clean separation between policy, sanitization, validation, and apply engine.

**Direction**: create `src/autopack/patching/*` modules (sanitize/policy/quality/apply_engine) while preserving `GovernedApplyPath.apply_patch()` API.

### 2.4 Shrink `LlmService` into internal subsystems (stable facade)

**Target**: `src/autopack/llm_service.py`
**Reason**: central orchestration; large file makes it harder to safely evolve model routing/usage/doctor flows.

**Direction**:
- `llm/client_resolution.py`
- `llm/usage.py`
- `llm/doctor.py`

Keep `LlmService` as the stable facade that delegates.

---

## 3) Secondary refactors (do after the high-ROI items)

These improve day-to-day editing when they become hotspots, but they are not as merge-conflict heavy as the top group:

- `src/autopack/memory/memory_service.py` (split retrieval vs formatting vs indexing)
- `src/autopack/deliverables_validator.py` (split schema validation vs rules vs IO)
- `src/autopack/manifest_generator.py` (split plan parsing vs scope derivation vs validation)
- `src/autopack/health_checks.py` (split provider checks vs DB checks vs formatting)

Rule: **only schedule these when you’re touching them frequently**, or when a refactor removes a recurring regression class.

---

## 4) Target skeleton structure (end state)

This is the intended “shape” after the high-ROI refactors land.

### 4.1 API server shape (already in progress)

```
src/autopack/
  main.py                  # thin shim: `from autopack.api.app import app`
  api/
    __init__.py
    deps.py                # verify_api_key, verify_read_access, get_client_ip, limiter
    app.py                 # create_app() and app wiring
    routes/
      __init__.py
      health.py
      files.py
      storage.py
      dashboard.py
      governance.py
      approvals.py
      artifacts.py
      phases.py
      runs.py
```

### 4.2 Executor shape (desired)

```
src/autopack/
  autonomous_executor.py        # orchestrator only; minimal logic
  supervisor/
    api_client.py               # all HTTP calls; no requests.* in executor
  executor/
    approval_flow.py
    ci_runner.py
    run_checkpoint.py
    context_preflight.py
    retrieval_injection.py
    context_loading_heuristic.py
```

### 4.3 Patching safety shape (desired)

```
src/autopack/
  governed_apply.py             # facade; calls patching/*
  patching/
    patch_sanitize.py
    policy.py
    patch_quality.py
    apply_engine.py
    diff_generator.py
```

### 4.4 LLM subsystem shape (desired)

```
src/autopack/
  llm_service.py                # facade
  llm/
    client_resolution.py
    usage.py
    doctor.py
    providers/
      anthropic_transport.py
    prompts/
      anthropic_builder_prompts.py
    parsers/
      anthropic/
        full_file.py
        ndjson.py
        structured_edit.py
        legacy_diff.py
```

---

## 5) Test + CI discipline (required)

### 5.1 Minimum local tests for each PR

- **Docs/SOT contracts** (run first; fastest drift detection):
  - `python -m pytest -q tests/docs/`
- **If you touched API routes/wiring**:
  - `python -m pytest -q tests/api/`
  - `python -m pytest -q tests/api/test_route_contract.py`
- **If you touched executor/LLM wiring**:
  - `python -m pytest -q tests/llm_service/`
  - plus targeted executor tests referenced by your changes
- **Fast style checks**:
  - `ruff check src/ tests/`
  - `black --check src/ tests/`

### 5.2 CI expectations

CI will enforce:
- doc/SOT integrity + drift checks
- route contract test stability
- core tests + lint/format
- staged mypy lane (informational)

Do not label a check as “enforced” if it’s staged/non-blocking.

---

## 6) Pre‑PR Drift Zero Gatekeeper (copy/paste into every implementation runbook)

You are the **Pre‑PR Drift Zero Gatekeeper** for Autopack.

**Goal**: before opening a PR (or before requesting review), ensure the branch is mechanically consistent and CI-ready. If anything fails, fix it on-branch and re-run until green. Then create the PR and paste the link + a concise, accurate summary.

### 6.1 Hard rules

- Do not claim “Implemented” in docs/DEC unless the code/docs change is actually present.
- Do not change historical ledgers (BUILD_HISTORY/DEBUG_LOG/etc.) except via the repo’s official SOT refresh scripts.
- Keep changes minimal and scoped to the failure/drift.
- Never manually edit the README SOT block; always use `sot_summary_refresh.py`.

### 6.2 Required local checks (run in this order)

1) Run doc/SOT contract suite:
- `python -m pytest -q tests/docs/`

2) If any docs/SOT test fails:
- Read the failure message and run the recommended remediation command(s).
- Common fixes:
  - If README SOT summary mismatch:
    - `python scripts/tidy/sot_summary_refresh.py --execute`
  - If copy/paste docs contract fails:
    - fix the specific doc(s) in allowlist; do not weaken the test
  - If decision ledger uniqueness/count mismatch:
    - fix `docs/ARCHITECTURE_DECISIONS.md` to match reality (statuses must be accurate)
- Re-run until green:
  - `python -m pytest -q tests/docs/`

3) Run unit tests touched by changes:
- If you touched executor/LLM wiring:
  - `python -m pytest -q tests/llm_service/`
  - plus any referenced executor tests

4) Style checks (fast):
- `ruff check src/ tests/`
- `black --check src/ tests/`

### 6.3 Git hygiene before PR

- `git status` must be clean.
- Ensure the PR description matches reality:
  - If something is staged/informational/commented out in CI, label it **STAGED** (not “enforced”).
  - If a DEC is decision-only and not implemented, mark it 🧭 Planned (do not mark ✅).

### 6.4 PR creation output format (must follow)

When done, paste:
- PR link
- Checks run locally (exact commands)
- What you changed to fix drift (bullet list)
- What remains planned/staged (bullet list)

### 6.5 Common drift traps to proactively avoid

- After adding/editing DECs: always run `python -m pytest -q tests/docs/` and refresh README SOT summary if needed.
- Don’t update `docs/ARCHITECTURE_DECISIONS.md` statuses to ✅ unless the corresponding implementation PR includes the actual implementation.
- Don’t say “dependency drift enforcement enabled” if the workflow step is still commented out.

---

## 7) “Mark implemented” rule (required)

After each PR is merged (or as part of the PR), update:
- `docs/reports/IMPROVEMENT_GAPS_CURRENT_2026-01-12.md`

For each completed PR item:
- mark it **IMPLEMENTED ✅**
- add completion date
- list tests run locally
- ensure claims match actual diffs
