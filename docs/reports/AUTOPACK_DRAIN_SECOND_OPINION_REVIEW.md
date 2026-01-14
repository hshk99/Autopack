# Autopack drain second-opinion review (based on provided pack)

Date: 2025-12-27 (report generated in ChatGPT)

## Evidence reviewed (from your pack)
- `README.md`
- `docs/SOT_BUNDLE.md`
- `CONSOLIDATED_CI_LOGS.txt`
- `CONSOLIDATED_CI_REPORTS.ndjson`
- `research-system-v1_DIAGNOSTICS.jsonl`
- `CODE_AND_GIT_CONTEXT.txt`

This report focuses on whether the observed drain/CI behavior matches the documented claims, and on extracting cross-run patterns that affect drain reliability.

---

## A) README mismatches (if any) + evidence pointers

### A1) README claims “all core tests passing”, but CI artifacts show many failures
- README includes a milestone claim: **“All core tests passing (89 passed, 30 skipped, 0 failed)”**.
  - Evidence: `README.md` (Configuration section) shows that milestone statement alongside “Last Updated: 2025-12-11”.
    - Pointer: README snippet lines **L67–L72** in the pack extract.
- Your consolidated CI output shows a **large failing set** during real runs (≈60 failed tests alongside >1200 passes).
  - Evidence: `CONSOLIDATED_CI_LOGS.txt` summary section shows `== 60 failed, 1256 passed, 132 skipped ... ==`
    - Pointer: CI log lines **L1–L22** around that summary.

**Assessment**: Either (a) “core tests” refers to a smaller subset than what CI is running during drains, or (b) README is stale/out-of-scope for drain CI. As written, the README statement is misleading for drain operators.

**Recommendation**: Clarify in README whether “core tests passing” means *a scoped subset* (and name the command), or update it to reflect the reality that *regression gating is delta-based even when CI overall is red*.

### A2) README “Last Updated” header conflicts with auto-generated SOT summary timestamps
- README shows “Last Updated: 2025-12-11” near the version block.
  - Pointer: README snippet lines **L67–L70**.
- The embedded SOT summary inside README shows “Last Updated: 2025-12-27 14:07”.
  - Pointer: README snippet lines **L77–L86**.

**Assessment**: Not functionally harmful, but signals the README has both “static” and “generated” freshness fields that disagree.

**Recommendation**: Either remove the static “Last Updated” line or make it auto-generated alongside the SOT summary.

### A3) README implies “no more /runs/{id} 500s” (during validation), but a later systemic 500 cause was still discovered and fixed
- The SOT/README narrative includes “No more `/runs/<built-in function id>` 500s during validation” after fixing API identity & DB matching.
  - Pointer: `docs/SOT_BUNDLE.md` P10-validation section, lines **L13–L21**.
- A later systemic blocker was recorded and fixed: `/runs/research-system-v1` could return **500** due to **legacy string `Phase.scope`** breaking response schema validation.
  - Evidence: build log entry and schema fix note in `docs/SOT_BUNDLE.md` (2025-12-28 entry).
    - Pointer: `docs/SOT_BUNDLE.md` build log snippet lines **L8–L13**.
  - Evidence: commit `5a29b35c` describes the fix explicitly.
    - Pointer: `CODE_AND_GIT_CONTEXT.txt` diff header and summary for `5a29b35c`.

**Assessment**: The earlier claim is directionally correct for the *wrong-service / wrong-DB* cause, but is too broad as a blanket statement. It should be narrowed (e.g., “eliminated 500s caused by wrong service / wrong DB”), and mention that other legacy-data causes can still exist.

---

## B) Pattern analysis + hypothesized root causes + confidence

### Overview: CI report corpus (from `CONSOLIDATED_CI_REPORTS.ndjson`)
The pack contains 6 pytest JSON reports. Summary:

| run_id                     | phase (pytest report name)             |   exitcode |   tests_total |   tests_failed |   failed_collectors | report_path                                                                                |   ndjson_line |
|:---------------------------|:---------------------------------------|-----------:|--------------:|---------------:|--------------------:|:-------------------------------------------------------------------------------------------|--------------:|
| build112-completion        | build112-phase5-dashboard-pause-resume |          1 |          1441 |             59 |                   0 | .autonomous_runs\build112-completion\ci\pytest_build112-phase5-dashboard-pause-resume.json |             4 |
| research-system-v1         | research-tracer-bullet                 |          1 |          1443 |             60 |                   0 | .autonomous_runs\research-system-v1\ci\pytest_research-tracer-bullet.json                  |             6 |
| research-system-v20        | research-foundation-intent-discovery   |          1 |          1450 |             60 |                   0 | .autonomous_runs\research-system-v20\ci\pytest_research-foundation-intent-discovery.json   |             1 |
| research-system-v26        | research-testing-polish                |          1 |          1448 |             60 |                   0 | .autonomous_runs\research-system-v26\ci\pytest_research-testing-polish.json                |             2 |
| research-system-v29        | research-testing-polish                |          2 |             0 |              0 |                  10 | .autonomous_runs\research-system-v29\ci\pytest_research-testing-polish.json                |             3 |
| scope-smoke-20251206184302 | P1                                     |          1 |          1441 |             61 |                   0 | .autonomous_runs\scope-smoke-20251206184302\ci\pytest_P1.json                              |             5 |

Key takeaways:
- Most runs show **exitcode=1** with ~59–61 failed tests (but >1200 passing).
- One run (`research-system-v29`) shows **exitcode=2**, **0 tests**, and **10 failed collectors** — a strong signature of **collection/import failure**.

---

### Pattern 1: CI collection/import failures
**Evidence**
- `research-system-v29` CI run: “collected 1389 items / 10 errors”, with repeated `ModuleNotFoundError` and `ImportError while importing test module …`.
  - Pointer: `CONSOLIDATED_CI_LOGS.txt` includes `pytest_research-testing-polish.log` with this signature and details.
- Example missing modules: `src.research.manager`, `src.api`.
  - Pointer: `CONSOLIDATED_CI_LOGS.txt` error block shows `ModuleNotFoundError: No module named 'src.research.manager'` and `No module named 'src.api'` lines.

**Hypothesized root cause**
- High likelihood this is a **“real gate” outcome of partial/truncated patch application**: tests are importing modules that were expected to exist in the workspace but were not created (or were created in the wrong location), so pytest fails before executing tests.

Alternative hypotheses (lower probability without more artifacts):
- `PYTHONPATH`/packaging mismatch for `src/` layout (but the errors are “module missing”, not “package not found due to sys.path”, and the tests clearly expect `src.research.*`).

**Classification**
- Usually **real gate** for the affected phase/run (the codebase is not in a test-importable state).
- Becomes a **systemic drain blocker** only if this same missing-module signature repeats across many runs due to a recurring Autopack mechanism (e.g., scope mis-rooting, apply dropping new files, or consistent truncation leaving incomplete deliverables).

**Proposed fix/tests if it becomes systemic**
- If repeated for the same module surface:
  - Add a **compat shim/skeleton** phase early in the research-system runs (create `src/research/__init__.py`, `src/research/manager.py`, etc.), or enforce deliverables more strictly.
  - Add an integration test that validates the **minimum import surface** exists after the earliest research-system phases.
- If repeated with “files exist on disk but imports still fail”:
  - Add/verify test runner config to ensure repo-root is on `sys.path` and `src/` behaves as intended.

**Confidence**: High for diagnosis (collection failure), medium for exact root cause (missing deliverables vs packaging) without workspace snapshot.

---

### Pattern 2: Phases marked COMPLETE despite CI failures
**Evidence**
- The pack’s SOT summary explicitly records phases completing even when CI is failing:
  - `research-system-v26`: “Phase finalized COMPLETE … CI failed but phase finalized via existing policy (no systemic blocker).”
  - `scope-smoke P1`: “CI failed but phase finalized via existing policy.”
  - Pointer: `docs/SOT_BUNDLE.md` drain-status summary section lines **L9–L13**.
- CI reports for these runs show exitcode=1 and ~60 failed tests.
  - Pointer: `CONSOLIDATED_CI_REPORTS.ndjson` summary table (above).

**Hypothesized root cause**
- This is consistent with **delta-based regression gating**: CI can be “red” in absolute terms, yet a phase can still complete if it introduces **no new regressions** relative to a stored baseline (or only a severity class that is configured as “warn-only”).
  - Supporting evidence: the CI logs include PhaseFinalizer test coverage such as `test_assess_completion_medium_regression_warns_only` and `test_finalizer_high_regression_blocks`.
    - Pointer: `CONSOLIDATED_CI_LOGS.txt` unit test names list near the end of the run.

**Classification**
- Not necessarily a drain blocker; likely **intended policy**.
- However, it is a **documentation/operational hazard**: operators (and future Cursor chats) will read “CI failed” and assume it must block completion unless the policy is spelled out.

**Proposed fix/tests (systemic quality improvement)**
- Add an explicit README section: “Phase completion policy is based on regression delta, not absolute CI pass/fail; collection errors always block.”
- Ensure PhaseFinalizer’s completion message always includes:
  - absolute CI status (exitcode)
  - baseline delta summary (new failures, resolved failures, severity)
  - why it allowed completion (e.g., “no regressions” / “medium regression warn-only with human approval”)

**Confidence**: Medium-high (fits evidence and observed stable failure counts across runs).

---

### Pattern 3: No-op apply / “no operations”
**Evidence**
- `build112-completion Phase 5`: “Builder produced JSON outputs; structured edit fallback resulted in ‘No operations (structured edit)’. This did not block …”
  - Pointer: `docs/SOT_BUNDLE.md` drain-status summary section lines **L14–L16**.

**Hypothesized root cause**
- Likely one of:
  1) Builder emitted a structured edit plan with 0 operations, or
  2) structured edit extraction failed and yielded 0 operations, or
  3) deliverables were already satisfied so the phase was effectively idempotent.

Without the phase’s apply logs and the phase spec’s deliverables, this cannot be disambiguated.

**Classification**
- Potential **systemic risk** if it occurs frequently (false “work completed”).
- Could also be benign (idempotent phase).

**Proposed fix/tests if systemic**
- Record `apply_stats` (operations_parsed, operations_applied, touched_paths_count) into the phase result and CI report metadata.
- Add a PhaseFinalizer “no-op guard”:
  - If expected deliverables are missing AND `operations_applied == 0`, **block**.
  - Allow explicit opt-out via `phase_spec.allow_noop=true` for doc-only or idempotent phases.
- Add unit tests for structured-edit phases ensuring operations count is non-zero when a diff/plan claims changes.

**Confidence**: Medium (real occurrence confirmed; cause ambiguous).

---

### Pattern 4: Truncation / 100% utilization behavior
**Evidence**
- Triage and mitigation summary: documentation tasks were a primary driver; P7+P9+P10 introduced adaptive buffers and an “escalate-once” retry strategy.
  - Pointer: `docs/SOT_BUNDLE.md` truncation mitigation entry (2025-12-25), lines **L24–L28**.
- P10 design was motivated by repeated **exactly 100% utilization** events despite buffers.
  - Pointer: `docs/SOT_BUNDLE.md` P10 section includes “phases hitting EXACTLY 100% utilization …” lines **L57–L62** in the truncation mitigation details.
- P10 stability evidence: retried budgets are actually applied across drain batches (persists in DB).
  - Pointer: `docs/SOT_BUNDLE.md` “P10 Stability” section lines **L3–L8**.

**Hypothesized root cause**
- Underestimation + hard max-token overrides leading to responses that hit the cap, compounded by doc_synthesis tasks requiring larger context reconstruction.
- Truncation then cascades into downstream “real gate” failures (missing deliverables, import errors), which matches the observed collector failures in v29.

**Classification**
- **Systemic** (it is a general property of the generator + token budgeting strategy, not a single run).
- Many downstream failures are *run-specific manifestations* of this systemic constraint.

**Proposed fix/tests**
- Run the documented “validation batch” (10–15 phases) and measure:
  - truncation rate
  - P10 escalation frequency
  - success-after-escalation rate
  - downstream CI collection error frequency
- Ensure the validation scripts check the DB-backed escalation events (so validation isn’t log-scrape dependent).
- Add a test that forces doc_synthesis category + high deliverable count and asserts P10 triggers at ≥95% utilization, writes an event, and uses retry_max_tokens on the next attempt.

**Confidence**: High for being systemic; medium for quantifying improvements until the validation batch is run.

---

### Review of the two systemic changes (commit diffs)

#### Commit `cf80358c` — P10-first run selection helper
- Adds `scripts/pick_next_run.py` which prints `run_id` and an inferred `run_type` (prefers P10-first scoring, falls back to highest queued).
  - Pointer: `CODE_AND_GIT_CONTEXT.txt` shows README update adding this helper and describes output formats.
**Assessment**
- High ROI operational improvement: eliminates interactive “which run_id?” loops by computing the next drain target deterministically.

**Potential follow-ups**
- Make `infer_run_type()` overridable via CLI flag for ambiguous run_ids.
- Print (optional) “why” score breakdown for transparency.

#### Commit `5a29b35c` — API `/runs` serialization normalization for legacy string scopes
- Adds schema normalization to coerce legacy string scopes into dicts (e.g., `{"_legacy_text": ...}`) and includes regression tests.
  - Pointer: `CODE_AND_GIT_CONTEXT.txt` shows the `field_validator("scope", mode="before")` and new tests.
**Assessment**
- Correct systemic fix: it turns a hard 500 (executor-blocking) into a tolerable legacy-data condition that can be auto-fixed downstream.

**Potential follow-ups**
- Consider adding a warning log/metric when `_legacy_text` is used so the “legacy scope rate” is visible.

---

## C) What’s systemic vs what’s run-specific

| Pattern | Systemic drain blocker? | “Real gate” for a run? | Notes |
|---|---:|---:|---|
| CI collector/import failures (exitcode=2, collectors failed, tests=0) | Sometimes | Yes | Treat as systemic only if repeated due to Autopack behavior; otherwise it’s the run not producing importable code. |
| CI red but phase marked COMPLETE | No (policy) | No (unless regression is critical) | Likely delta-based gating; should be documented to reduce operator confusion. |
| No-op apply / “no operations” | Potentially | Sometimes | Needs instrumentation to distinguish benign idempotence vs false completion. |
| Truncation / 100% utilization / P10 triggers | Yes | Indirectly | Systemic constraint; manifests as many downstream run-specific failures. |
| `/runs/<built-in function id>` 500 from legacy scope string | Yes (fixed) | No | Resolved via schema normalization + tests. |

---

## D) Recommended next steps (highest ROI first) + extra evidence needed

### 1) Fix the operational/documentation mismatch in README (highest confusion reducer)
- Replace or qualify the “tests-passing-v1.0 (0 failed)” claim.
- Add a short, explicit section: **“CI gating is regression-delta based; CI can be red and phases may still complete if no regressions; collection errors always block.”**
- Narrow the “no more /runs 500s” claim to the cause fixed (wrong service/wrong DB), and reference the separate legacy-scope fix.

**Extra evidence helpful**
- A single screenshot/snippet of the PhaseFinalizer decision output for a “CI failed but COMPLETE” case, showing the delta logic.

### 2) Turn the “no-op apply” from ambiguous to explainable
- Add and persist `apply_stats` (ops parsed/applied, touched paths, mode) into the phase record (and surface it in logs).
- Add a PhaseFinalizer guard for “no changes when changes required”, with `phase_spec.allow_noop` escape hatch.

**Extra evidence needed**
- The phase spec (deliverables + allowed no-op?) and the apply-step logs for `build112-phase5-dashboard-pause-resume`.

### 3) Systematically separate “collection errors due to missing deliverables” from “packaging/path config”
- When collection errors occur:
  - check whether expected modules exist on disk (`src/research/*`)
  - if they exist, check import path setup (`PYTHONPATH`, package init files)
- If repeated missing-module errors occur across research-system runs, seed a minimal skeleton in an early phase or harden deliverables enforcement.

**Extra evidence needed**
- Workspace tree snapshot (`dir /s src\research`) at the moment of v29 failure.

### 4) Run the P10 validation batch and publish results
- You already have the instrumentation and ranking plan; execute the validation batch and record:
  - truncation rate
  - P10 event frequency
  - success-after-escalation ratio
  - count of collector/import failures post-P10
- Use `scripts/pick_next_run.py --format json` to avoid run selection back-and-forth.

**Extra evidence needed**
- Export of the `token_budget_escalation_events` table after the batch (even as a simple CSV or sqlite query output).

---

## Appendix: Quick “evidence pointers” (where to look)
- CI collector/import failure signature: `CONSOLIDATED_CI_LOGS.txt` around `pytest_research-testing-polish.log` (v29).
- Phase completion despite CI red: `docs/SOT_BUNDLE.md` drain-status summary section.
- Run selection helper: `CODE_AND_GIT_CONTEXT.txt` diff for `cf80358c`, and README update line mentioning `scripts/pick_next_run.py`.
- Legacy scope 500 fix: `CODE_AND_GIT_CONTEXT.txt` diff for `5a29b35c`.
