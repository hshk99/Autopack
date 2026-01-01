```text
You are implementing “Phase E — Ideal State” improvements for Autopack tidy.

Follow the plan exactly:
docs/IMPLEMENTATION_PLAN_TIDY_IDEAL_STATE_PHASE_E.md

High-level goals from README:
- SOT stays machine-usable and low-drift
- tidy enables linear reuse + semantic reuse (include_sot retrieval)
- root/docs do not re-accumulate clutter

Your tasks:
1) Update WORKSPACE_ORGANIZATION_SPEC + verifier allowlists so docs warnings reflect real “truth sources” (not hundreds of false positives).
2) Decide and encode `.autonomous_runs/autopack` semantics:
   - either exclude it from “project SOT validation” (runtime workspace), OR
   - make it a real project workspace with the 6 SOT files.
3) Add centralized logging defaults so scripts stop writing logs to repo root.
4) Make consolidation idempotent at content level (merge markers + dedupe).
5) Add CI enforcement (start non-blocking, then blocking) and optional pre-commit hook.

Constraints:
- Windows-safe output (no emoji crashes)
- No silent SOT data loss
- Keep behavior opt-in where it could surprise users
- Add tests for new behavior (unit tests for allowlist, project detection, merge-marker dedupe; minimal integration test for log routing).

Done means:
- verify script gives actionable warnings (not huge noise)
- root clutter recurrence is prevented (logs go to archive by default)
- SOT retrieval is consistently useful (bounded, structured entries)
```


