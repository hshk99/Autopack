# BUILD-188: Security Baseline Refresh Workflow Hardening (Determinism + Safety)

**Status**: COMPLETE
**Priority**: Medium (operational safety + determinism)
**Related**: BUILD-174 (baseline automation), BUILD-174.1, BUILD-186 (Windows UTF-8), DEC-045, README.md

---

## Why (gap vs README ideal state)

The baseline refresh workflow performs privileged operations (branch creation + push + PR creation). To preserve the README ideal state (safe, deterministic, mechanically enforceable), we must:
- avoid unsafe force-push footguns
- prevent overlapping workflow runs
- allow deterministic testing against a specific artifact set

---

## Direction (no ambiguity)

1. Replace `git push -f` with `git push --force-with-lease`
2. Add `workflow_dispatch` input `artifacts_run_id`
3. Add `concurrency` block to prevent overlapping runs
4. Add CI contract test enforcing these invariants

---

## Implementation

### 1) Workflow dispatch input
- Add `on.workflow_dispatch.inputs.artifacts_run_id`
- If provided: download artifacts by `run_id`
- Else: download latest artifacts from `main`

### 2) Concurrency
- `concurrency.group = security-baseline-refresh-${{ github.ref }}`
- `cancel-in-progress: true`

### 3) Force-with-lease
- Replace `git push -f origin "${BRANCH}"` with `git push --force-with-lease origin "${BRANCH}"`

### 4) Mechanical enforcement (tests)
- Add `tests/ci/test_security_baseline_refresh_workflow_contract.py`
- Must fail PR if invariants regress

---

## Acceptance criteria

- [x] Workflow supports deterministic artifact sourcing via `artifacts_run_id`
- [x] Workflow cannot run concurrently for the same ref (concurrency enabled)
- [x] No usage of `git push -f` in the workflow
- [x] CI contract test enforces all above
- [x] All tests pass: `pytest -q tests/ci/test_security_baseline_refresh_workflow_contract.py`
- [x] Workflow file is ASCII-clean (BUILD-186 compliance)

---

## Verification commands

```bash
pytest -q tests/ci/test_security_baseline_refresh_workflow_contract.py
```

Optional manual verification:
- Trigger workflow_dispatch without input -> downloads latest
- Trigger with `artifacts_run_id=<known_run_id>` -> downloads from that run id

---

## Files changed

- `.github/workflows/security-baseline-refresh.yml`
- `tests/ci/test_security_baseline_refresh_workflow_contract.py`
- `docs/BUILD-188_SECURITY_BASELINE_REFRESH_WORKFLOW_HARDENING.md`
