# Backlog Maintenance Plan (Focused)

Purpose: avoid ambiguity by separating maintenance/backlog fixes from the main Phase 2 build plan. This file is the source for maintenance runs (diagnostics-first, apply gated).

Runbook (summary)
- Convert this markdown to a phase JSON: `scripts/plan_from_markdown.py --in .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD_MAINTENANCE.md --out .autonomous_runs/file-organizer-app-v1/plan_maintenance.json`
- (Optional) merge with an existing plan using `--merge-base ... --allow-update` only if you intend to update matching phase ids.
- Run maintenance (checkpoint on by default): `python src/autopack/autonomous_executor.py --run-id fileorg-maint --maintenance-plan .autonomous_runs/file-organizer-app-v1/plan_maintenance.json --maintenance-patch-dir patches --maintenance-apply --maintenance-auto-apply-low-risk --maintenance-checkpoint --test-cmd "pytest -q tests/smoke"`
- Auditor + apply gates: apply only if auditor approves; low-risk auto-apply additionally enforces small diff/tests passing. Checkpoints required for apply.
- Logging/token efficiency: default to compact JSON summaries; include short excerpts only for high-priority events (apply failure, auditor reject, test failure, protected-path violation); keep full logs/patches as artifacts and reference paths.
- Allowed paths: default to backend/frontend/Dockerfile/docker-compose/README/docs/scripts/src unless overridden in tasks; protected: .git/, .autonomous_runs/, config/.

Maintenance Tasks (OI issues from CONSOLIDATED_DEBUG)
- Phase IDs prefixed with `fileorg-maint-`.

### Task: Fix UK YAML truncation
**Phase ID**: `fileorg-maint-uk-yaml-truncation`
**Category**: maintenance
**Complexity**: medium
**Description**: Resolve OI-FO-UK-YAML-TRUNCATION (truncated YAML in UK packs). Validate/repair YAML headers and required mappings.
**Acceptance Criteria**:
- [ ] YAML loads without truncation errors
- [ ] Tests pass for UK packs (targeted YAML validation or pack load)
- [ ] Compact diagnostics summary + artifact paths; excerpts only on failure
**Allowed Paths**: `prompts/`, `docs/`, `templates/`, `src/`
**Tests**: (add when known) e.g., `pytest -q tests/test_pack_routes.py -k uk`
**Patches**: If available, place as `patches/fileorg-maint-uk-yaml-truncation.patch`
**Apply**: low-risk auto-apply permitted if auditor approves; otherwise propose-first.

### Task: Fix frontend no-op
**Phase ID**: `fileorg-maint-frontend-noop`
**Category**: maintenance
**Complexity**: medium
**Description**: Resolve OI-FO-FRONTEND-NOOP (frontend action not taking effect). Identify and fix the no-op behavior; run targeted frontend/backend tests if available.
**Acceptance Criteria**:
- [ ] Repro fixed (no-op resolved)
- [ ] Targeted tests pass (add when known)
- [ ] Compact diagnostics summary + artifact paths; excerpts only on failure
**Allowed Paths**: `src/frontend/`, `prompts/`, `docs/`, `scripts/`
**Tests**: (add when known) e.g., `npm test` or `pytest -q tests/test_frontend_*`
**Patches**: If available, place as `patches/fileorg-maint-frontend-noop.patch`
**Apply**: low-risk auto-apply permitted if auditor approves; otherwise propose-first.

### Task: General backlog maintenance slot
**Phase ID**: `fileorg-maint-open-issue-slot`
**Category**: maintenance
**Complexity**: medium
**Description**: Reserved slot for another OI-FO-* issue from CONSOLIDATED_DEBUG (fill in description/paths/tests before run).
**Acceptance Criteria**:
- [ ] Issue-specific repro fixed
- [ ] Targeted tests pass
- [ ] Compact diagnostics summary + artifact paths; excerpts only on failure
**Allowed Paths**: `src/backend/`, `src/frontend/`, `docs/`, `prompts/`, `scripts/`
**Tests**: (fill in)
**Patches**: (optional) place as `patches/fileorg-maint-open-issue-slot.patch`
**Apply**: low-risk auto-apply permitted if auditor approves; otherwise propose-first.

# Notes
- Do not overwrite `WHATS_LEFT_TO_BUILD.md` with maintenance tasks; this file is the maintenance source.
- Only use `--allow-update` on merge when you intend to replace an existing phase id.
- Keep checkpoints enabled for any apply path; revert to checkpoint on apply failure.
# Backlog Maintenance Plan (FileOrganizer)

Purpose: Focused maintenance plan for addressing open issues (OI-FO-*) using the Autopack maintenance flow. This is separate from the Phase 2 feature tasks in `WHATS_LEFT_TO_BUILD.md`.

## Modes
- Option A: Maintain/build the maintenance system (meta) — run acceptance criteria for `fileorg-backlog-maintenance`.
- Option B: Use maintenance to fix specific open issues (OI-FO-*) from `CONSOLIDATED_DEBUG.md`.

## Runbook
1) Convert markdown → plan JSON  
   - `python scripts/plan_from_markdown.py --in .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD_MAINTENANCE.md --out .autonomous_runs/file-organizer-app-v1/plan_generated.json`
   - If merging into an existing plan: add `--merge-base autopack_phase_plan.json --allow-update` (only when you intend to overwrite ids).

2) Run maintenance (checkpoints on by default)  
   - Diagnostics first; apply only if auditor approves + checkpoint exists; low-risk auto-apply optional.  
   - Example:  
     ```
     python src/autopack/autonomous_executor.py --run-id backlog-maint \
       --maintenance-plan .autonomous_runs/file-organizer-app-v1/plan_generated.json \
       --maintenance-patch-dir patches \
       --maintenance-apply \
       --maintenance-auto-apply-low-risk \
       --maintenance-checkpoint \
       --test-cmd "pytest -q tests/smoke"
     ```

3) Logging/token efficiency  
   - Default: compact JSON summaries; include short excerpts only for high-priority events (apply failure, auditor reject, test failure, protected-path violation); keep full logs/patches as artifacts and reference paths.

4) Safety  
   - Allowed paths: constrain per item; protected: `.git/`, `.autonomous_runs/`, `config/`.  
   - Apply is gated by auditor and checkpoints; auto-apply low-risk enforces size/test guards.

## Maintenance Items (OI-FO-*)
- OI-FO-UK-YAML-TRUNCATION  
  - phase_id: oi-fo-uk-yaml-truncation  
  - desc: Fix truncated UK YAML packs (missing `---`/mappings).  
  - allowed_paths: `packs/`, `src/backend/packs/`, `tests/`  
  - test_cmd: `pytest -q tests/test_pack_routes.py -k uk`  
  - apply: allowed (auditor+checkpoint)

- OI-FO-FRONTEND-NOOP  
  - phase_id: oi-fo-frontend-noop  
  - desc: Frontend no-op fix for planned UI hook.  
  - allowed_paths: `src/frontend/`, `frontend/`, `README`  
  - test_cmd: `npm test` (if available) or `npm run build`  
  - apply: allowed (auditor+checkpoint)

- OI-FO-YAML-SCHEMA-WARNINGS  
  - phase_id: oi-fo-yaml-schema  
  - desc: Resolve YAML schema warnings across packs.  
  - allowed_paths: `packs/`, `src/backend/packs/`, `tests/`  
  - test_cmd: `pytest -q tests/test_pack_routes.py`  
  - apply: allowed (auditor+checkpoint)

- OI-FO-PATCH-APPLY-MISMATCH  
  - phase_id: oi-fo-patch-mismatch  
  - desc: Address patch apply mismatches on structured edits.  
  - allowed_paths: `src/backend/`, `src/frontend/`, `tests/`  
  - test_cmd: `pytest -q tests/test_autonomous_executor.py`  
  - apply: allowed (auditor+checkpoint)

- OI-FO-CI-FAILURE-REVIEW  
  - phase_id: oi-fo-ci-failure  
  - desc: Investigate failing CI items; collect diagnostics and propose fixes.  
  - allowed_paths: `src/`, `tests/`, `README`, `docs/`  
  - test_cmd: `pytest -q` (or targeted failing suites)  
  - apply: propose-first unless auditor approves + checkpoint

Add more OI-FO-* items here as discovered. Keep entries concise and scoped.

## Meta Task (Maintenance System) — optional
- phase_id: fileorg-backlog-maintenance  
  - Build/verify backlog maintenance system (diagnostics, auditor, apply gating, checkpoints, compact summaries).  
  - allowed_paths: `scripts/`, `src/autopack/`, `README`, `docs/`  
  - apply: propose-first; apply only for guarded changes.

