# BUILD-180: Mechanical Enforcement Convergence

**Status**: COMPLETE ✅
**Priority**: High (closes gaps between README ideal state and actual implementation)
**Related**: BUILD-179 (CLI/Supervisor consolidation), BUILD-178 (Pivot Intentions v2), `docs/SECURITY_BURNDOWN.md` (TODO: check_production_config.py)
**Aligned to README ideal state**: safe, deterministic, mechanically enforceable; SOT-led memory; execution writes run-local only; explicit gates; default-deny autonomy.

---

## Why (gap vs ideal state)

BUILD-178/179 delivered the autonomy skeleton (gap scanning, plan proposing, autopilot sessions, parallelism gates), but several components remain **placeholder or heuristic**:

| Gap | Current State | Ideal State |
|-----|---------------|-------------|
| Autopilot execution | `_execute_bounded_batch()` is a placeholder ("would execute" log only) | Real executor for safe action types; run-local artifact persistence |
| Doc drift detection | Heuristic string-contains check; returns empty list | Mechanical: run existing `scripts/check_docs_drift.py`, `pytest tests/docs/`, `scripts/tidy/sot_summary_refresh.py --check` |
| Workspace digest | Falls back to timestamp if git fails (non-deterministic) | Deterministic sentinel on git failure |
| Phase proof metrics | Hardcoded `files_created/modified/deleted=0`, `tests_passed/failed=0` | Deterministic minimal metrics via `git diff --name-only` |
| Security CI guard | `docs/SECURITY_BURNDOWN.md` calls out missing `scripts/ci/check_production_config.py` | Implemented + wired into CI |
| Model routing catalog | Hardcoded `SEED_CATALOG` in `model_routing_refresh.py` | Read from `config/models.yaml` + `config/pricing.yaml` |
| Parallelism default | Both policy-checked and non-checked APIs are public | Policy-checked API is the default/recommended path |

This BUILD closes these gaps with **mechanical, deterministic, test-backed** implementations.

---

## Direction (no ambiguity)

1. **Autopilot may auto-execute only read-only or run-local-artifact-write actions** (gap reports, plan proposals, session logs). Anything that changes repo working tree (docs/, config/, src/, tests/, .github/) requires explicit approval and is classified `requires_approval`.

2. **Doc drift detection uses existing mechanical checks** rather than heuristics:
   - `python scripts/check_docs_drift.py` (exit code)
   - `pytest -q tests/docs/` (if exists)
   - `python scripts/tidy/sot_summary_refresh.py --check` (exit code)

3. **Workspace digest is deterministic even on git failure**: use sentinel `unknown|git_unavailable` (hashed), never timestamps.

4. **Phase proofs include deterministic minimal metrics**: changed-file count via `git diff --name-only`, with explicit `metrics_placeholder=False` when real metrics are available.

5. **Security CI guard closes the documented TODO**: `scripts/ci/check_production_config.py` blocks DEBUG-like production configs.

6. **Model routing reads from repo config files**: `config/models.yaml` + `config/pricing.yaml` replace hardcoded `SEED_CATALOG`.

7. **Parallelism APIs default to policy-checked**: external entrypoints use `execute_parallel_with_policy_check()`; non-checked method is internal-only.

---

## Scope

### In scope

- Implement bounded action executor for autopilot (safe actions only)
- Replace gap scanner heuristics with mechanical checks
- Fix workspace digest determinism
- Add minimal deterministic metrics to phase proofs
- Implement `scripts/ci/check_production_config.py`
- Consolidate model catalog source to config files
- Make policy-checked parallelism the default entrypoint

### Not in scope

- Tidy system changes (tidy remains the only SOT writer)
- New gap types beyond the 10 currently defined
- Parallel phases within a single run (deferred)
- Full executor instrumentation (bounded/minimal metrics only)

---

## Implementation Plan

### Phase 0 - Contract-first test hardening

**Goal**: Ensure new behavior is enforceable and non-regressing before implementation.

**Work**:
- Add tests: autopilot never executes write actions without approval
- Add tests: gap scanner doc drift calls mechanical checks
- Add tests: workspace digest deterministic on git failure
- Add tests: phase proof metrics are real when git available

**Files**:
- `tests/autonomy/test_autopilot_safe_actions_only.py` (new)
- `tests/autonomy/test_gap_scanner_mechanical_drift.py` (new)
- `tests/autonomy/test_workspace_digest_deterministic.py` (new)
- `tests/autopack/test_phase_proof_git_metrics.py` (new)

**Acceptance criteria**:
- [ ] Tests run offline and deterministically
- [ ] Tests fail with current placeholder implementations (red-green cycle)

---

### Phase 1 - Bounded autopilot execution

**Goal**: Replace placeholder `_execute_bounded_batch()` with real executor for safe action types.

**Work**:
- Introduce `ActionExecutor` interface with `SafeActionExecutor` implementation
- Define action allowlist (read-only commands, run-local artifact writes)
- Autopilot persists run-local artifacts: `gap_report_v1.json`, `plan_proposal_v1.json`, `autopilot_session_v1.json`
- Actions targeting repo writes classified `requires_approval`

**Files**:
- `src/autopack/autonomy/action_executor.py` (new)
- `src/autopack/autonomy/action_allowlist.py` (new)
- `src/autopack/autonomy/autopilot.py` (modify `_execute_bounded_batch()`)

**Acceptance criteria**:
- [ ] Autopilot completes session end-to-end with run-local artifacts persisted
- [ ] Any action targeting repo writes (docs/, config/, src/, tests/, .github/) is classified `requires_approval` and not executed
- [ ] Read-only checks (doc drift, lint) can be executed without approval

---

### Phase 2 - Mechanical gap detectors

**Goal**: Replace heuristic gap detectors with existing repo contracts.

**Work**:
- `_detect_doc_drift()`: Run `scripts/check_docs_drift.py` + `scripts/tidy/sot_summary_refresh.py --check`
- Evidence includes command run, exit code, stderr excerpt hash
- Workspace digest: return deterministic sentinel `unknown|git_unavailable` (hashed) on git failure, never timestamp
- Baseline policy drift: validate YAML structure, not just existence

**Files**:
- `src/autopack/gaps/scanner.py` (modify)
- `src/autopack/gaps/doc_drift.py` (new - thin wrapper)

**Acceptance criteria**:
- [ ] Gap report doc_drift evidence includes command + exit code
- [ ] Workspace digest stable across runs when git unavailable
- [ ] No timestamp fallback anywhere in scanner

---

### Phase 3 - Deterministic phase proof metrics

**Goal**: Proofs include real metrics without heavy instrumentation.

**Work**:
- Add `src/autopack/proof_metrics.py` with pure functions:
  - `count_changed_files(workspace_root: Path) -> int` via `git diff --name-only`
  - `list_changed_files(workspace_root: Path, limit: int = 10) -> List[str]`
- Update `phase_proof_writer.py` to call these and set `metrics_placeholder=False` when git available
- If git unavailable, keep placeholder with explicit flag

**Files**:
- `src/autopack/proof_metrics.py` (new)
- `src/autopack/phase_proof_writer.py` (modify)

**Acceptance criteria**:
- [ ] Proof `files_modified` count matches `git diff --name-only | wc -l`
- [ ] `metrics_placeholder=False` when real metrics captured
- [ ] `metrics_placeholder=True` with zeros when git unavailable

---

### Phase 4 - Security CI guard

**Goal**: Close `SECURITY_BURNDOWN.md` TODO for production config validation.

**Work**:
- Implement `scripts/ci/check_production_config.py`:
  - Reject `DEBUG=1`, `DEBUG=true`, `DEBUG="1"` in production config files
  - Check `.env.production`, `config/production.yaml`, deployment manifests
  - Clear exit code + remediation message
- Wire into CI (`.github/workflows/ci.yml` or security workflow)

**Files**:
- `scripts/ci/check_production_config.py` (new)
- `tests/ci/test_check_production_config.py` (new)
- `.github/workflows/ci.yml` or `.github/workflows/security-scan.yml` (modify)

**Acceptance criteria**:
- [ ] CI fails if production config contains DEBUG enablement
- [ ] Clear error message with remediation steps
- [ ] Conservative: low false positives (only explicit DEBUG patterns)

---

### Phase 5 - Model catalog consolidation

**Goal**: Single authoritative model catalog source for routing refresh.

**Work**:
- Create `src/autopack/model_catalog.py`:
  - `load_model_catalog_from_config(models_path, pricing_path) -> List[ModelCatalogEntry]`
  - Parse `config/models.yaml` aliases + `config/pricing.yaml` costs
  - Validate required tiers (haiku, sonnet, opus) present
- Update `model_routing_refresh.py`:
  - Replace `SEED_CATALOG` with call to `load_model_catalog_from_config()`
  - Keep `SEED_CATALOG` as fallback if config files unreadable
- Preserve deterministic selection contract (stable sort keys)

**Files**:
- `src/autopack/model_catalog.py` (new)
- `src/autopack/model_routing_refresh.py` (modify)
- `tests/autopack/test_model_catalog_from_config.py` (new)

**Acceptance criteria**:
- [ ] Routing uses models from `config/models.yaml`
- [ ] Pricing from `config/pricing.yaml`
- [ ] Fallback to seed catalog if config unreadable (logged)
- [ ] Snapshot refresh reproducible across machines

---

### Phase 6 - Parallelism default gating

**Goal**: Reduce footguns by making policy-checked API the default.

**Work**:
- Rename/restructure in `parallel_orchestrator.py`:
  - `execute_parallel()` becomes `_execute_parallel_internal()` (private)
  - `execute_parallel_with_policy_check()` becomes `execute_parallel()` (public default)
  - Add deprecation warning if internal method called directly
- Ensure CLI commands use the public (policy-checked) method
- Update convenience function `execute_parallel_runs()` to require anchor parameter

**Files**:
- `src/autopack/parallel_orchestrator.py` (modify)
- `src/autopack/supervisor/parallel_run_supervisor.py` (modify if entrypoint)
- `tests/parallelism/test_parallel_default_policy_check.py` (new)

**Acceptance criteria**:
- [ ] Parallel execution (workers > 1) without anchor fails with clear message
- [ ] CLI and external entrypoints enforce policy by default
- [ ] Single-run execution still works without anchor (no parallelism gate needed)

---

## Testing / Verification Plan

### Must-pass (CI-blocking)

| Test | Validates |
|------|-----------|
| `test_autopilot_safe_actions_only.py` | Autopilot classifies write actions as requires_approval |
| `test_gap_scanner_mechanical_drift.py` | Doc drift runs real scripts, captures exit codes |
| `test_workspace_digest_deterministic.py` | No timestamp fallback, sentinel on git failure |
| `test_phase_proof_git_metrics.py` | Real file counts when git available |
| `test_check_production_config.py` | CI guard blocks DEBUG in production |
| `test_model_catalog_from_config.py` | Catalog loads from config files |
| `test_parallel_default_policy_check.py` | Parallelism requires anchor by default |

### Informational

- Autopilot end-to-end smoke test (run in temp workspace)
- Model routing snapshot reproducibility check

---

## Failure Modes (how it must fail)

| Scenario | Expected Behavior |
|----------|-------------------|
| Autopilot attempts write action | Classified `requires_approval`, not executed, session continues |
| Doc drift script not found | Gap flagged with evidence "script not found", not silent pass |
| Git unavailable for workspace digest | Deterministic sentinel hash, not timestamp |
| Git unavailable for proof metrics | `metrics_placeholder=True`, zeros, no crash |
| Production config has DEBUG=1 | CI fails with remediation instructions |
| Model config unreadable | Fallback to seed catalog with warning log |
| Parallel run without anchor | Immediate failure with actionable error message |

---

## Rollback Strategy

- Each phase is independently deployable
- Phase 1 (autopilot): Revert to placeholder if issues; autopilot already default-off
- Phase 2 (gap scanner): Revert to heuristics if mechanical checks flaky
- Phase 4 (CI guard): Disable in workflow if false positives
- Phase 5 (model catalog): Fallback to seed catalog already built-in
- Phase 6 (parallelism): Keep both APIs during transition; deprecation warning first

---

## File Skeleton Summary

### New Files

```
src/autopack/autonomy/action_executor.py      # ActionExecutor interface + SafeActionExecutor
src/autopack/autonomy/action_allowlist.py     # Canonical allowlisted action types
src/autopack/gaps/doc_drift.py                # Thin wrapper for mechanical drift checks
src/autopack/proof_metrics.py                 # Pure functions for git-based metrics
src/autopack/model_catalog.py                 # Config file loader for model catalog
scripts/ci/check_production_config.py         # CI guard for DEBUG in production

tests/autonomy/test_autopilot_safe_actions_only.py
tests/autonomy/test_gap_scanner_mechanical_drift.py
tests/autonomy/test_workspace_digest_deterministic.py
tests/autopack/test_phase_proof_git_metrics.py
tests/ci/test_check_production_config.py
tests/autopack/test_model_catalog_from_config.py
tests/parallelism/test_parallel_default_policy_check.py
```

### Modified Files

```
src/autopack/autonomy/autopilot.py            # Replace placeholder with real executor
src/autopack/gaps/scanner.py                  # Mechanical drift + deterministic digest
src/autopack/phase_proof_writer.py            # Real metrics when available
src/autopack/model_routing_refresh.py         # Load from config instead of seed
src/autopack/parallel_orchestrator.py         # Policy-checked as default
.github/workflows/ci.yml                      # Wire production config check
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Autopilot can complete full session with run-local artifacts | Yes |
| Gap scanner doc_drift evidence includes command + exit code | Yes |
| Workspace digest deterministic (same git state = same hash) | Yes |
| Phase proofs have real file counts when git available | Yes |
| CI blocks DEBUG=1 in production configs | Yes |
| Model routing uses config files (not hardcoded catalog) | Yes |
| Parallel execution requires anchor by default | Yes |

---

## References

- [README.md](../README.md) - Ideal state definition
- [BUILD-179](BUILD-179_AUTONOMY_CLI_AND_SUPERVISOR_CONSOLIDATION.md) - CLI/Supervisor consolidation
- [BUILD-178](BUILD-178_PIVOT_INTENTIONS_V2_GAP_TAXONOMY_AUTONOMY_LOOP.md) - Pivot Intentions v2
- [SECURITY_BURNDOWN.md](SECURITY_BURNDOWN.md) - Security TODO (check_production_config.py)
- [GOVERNANCE.md](GOVERNANCE.md) - Default-deny posture
- [scripts/check_docs_drift.py](../scripts/check_docs_drift.py) - Existing mechanical drift check
