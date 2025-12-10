## Goal
Make run/output creation and tidy-up storage predictable and project-scoped, avoiding the nested/duplicated paths that accumulated in `.autonomous_runs` and `archive`. Define where new files/folders should be created up front; add regrouping and normalization rules only as a safety net.

## Target layout
- Autopack project (tidy tooling, shared docs): `C:\dev\Autopack\archive\tidy_up\` (or `archive\unsorted` as last-resort inbox).
- File Organizer project:
  - Active runs output: `C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1\runs\<family>\<run-id>\`
  - Superseded/archived runs: `C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1\archive\superseded\runs\<family>\<run-id>\`
  - Truth/refs: `...file-organizer-app-v1\refs\` (or under `archive\superseded\refs\` when archived).
  - Buckets remain: `reports/`, `research/`, `delegations/`, `diagnostics/`, `prompts/`, `refs/`, `runs/`.

## Classification / grouping
- Run families (examples): `fileorg-country-uk`, `fileorg-docker`, `fileorg-frontend-build`, `fileorg-p2`, `fileorg-phase2-beta`, `phase3-delegated`, etc. Use prefix before the timestamp as family; fallback to full folder name if no timestamp pattern.
- Logs stay inside their run folder; no stripping or re-rooting logs outside `runs/<family>/<run-id>/`.

## Creation rules (preferred)
- Autopack (tidy itself, File Organizer outputs): write directly into the project scope:
  - File Organizer runs → `.autonomous_runs\file-organizer-app-v1\runs\<family>\<run-id>\` (active) and `...archive\superseded\runs\<family>\<run-id>\` (archived).
  - File Organizer docs/refs → `.autonomous_runs\file-organizer-app-v1\refs\` or the proper bucket (reports/research/diagnostics/prompts/refs).
- Cursor/manual for Autopack tidy: if the destination is known, write to the right project/bucket. If not, use `archive\tidy_up\` (or `archive\unsorted\` inbox) as a last resort; tidy_up will later sort by project/run_id/traits.
- Cursor/manual for File Organizer: same principle—prefer exact destination; otherwise at least place under `.autonomous_runs\file-organizer-app-v1\` (e.g., `refs/`), and only fall back to `archive\tidy_up\` when no classification is possible.

## Safety net (tidy regroup)
- When tidying `.autonomous_runs`: move all non-ignored top-level run folders into `...file-organizer-app-v1\archive\superseded\runs\<family>\<run-id>\` (preserve family/run nesting; do NOT strip `runs/<family>`). Subsequent manual tidy runs should regroup same-family runs into the same family folder under `runs/`.
- Normalize destinations without removing `runs/<*>` for regroup; only strip leading `archive/superseded` when flattening legacy paths.
- Keep `.autonomous_runs/file-organizer-app-v1` untouched; only ingest siblings.

## Needed code changes (summary)
- Adjust `.autonomous_runs` branch in `scripts/tidy_workspace.py`:
  - Use a dedicated normalizer that preserves `runs/<family>/<run-id>`; do not drop `runs` segments.
  - Destination for regroup: `project_root/archive/superseded/runs/<family>/<run-id>`.
  - Exclude only known infra dirs (archive, checkpoints, patches, exports, docs, openai_delegations, runs, file-organizer-app-v1); leave others to regroup.
- Optional (recommended): update run-creation scripts to emit directly to `.autonomous_runs\file-organizer-app-v1\runs\<family>\<run-id>\` and place logs inside the run folder.
- Inbox fallback: keep `archive\tidy_up\` (or `archive\unsorted\`) only for unclassified Cursor/manual drops; tidy_up will later bucket them.
- Autopack project outputs: route plans/analysis/logs/prompts for Autopack itself into `C:\dev\Autopack\archive\plans|analysis|logs|prompts` and move all Autopack source-of-truth files (README.md, consolidated_*.md, debug/log/db logs) to `C:\dev\Autopack\docs`; revise any auto-updaters to use that directory.
- Project-specific truth sources (e.g., File Organizer): place source-of-truth files in `C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1\docs`; ensure project updaters read/write there (not elsewhere). Project-specific run logs belong under that project’s `archive\superseded\runs/<family>/<run-id>` (not in `C:\dev\Autopack\archive`).
- Provide helpers: `route_new_doc(...)` and `route_run_output(...)` to classify docs and runs at creation time, auto-detecting projects from `.autonomous_runs` (new projects are picked up automatically). Use these in creators to avoid post-facto tidy moves.
- Add inbox directory `C:\dev\Autopack\archive\unsorted` as the last-resort drop zone when classification is impossible at creation time; tidy_up can later bucket these.
- Add CLI helper `scripts/run_output_paths.py` to surface the routing helpers for manual use (`--run-id/--family/--project/--doc-name/--doc-purpose`).
- Add wrapper `scripts/create_run_with_routing.py` to wrap run creation and print the routed local output directory (uses `route_run_output`).

## Risks / checks
- Verify we do not move truth-source files (`WHATS_LEFT_TO_BUILD*.md`, DBs, rules) during regroup.
- Ensure logger writes project_id `file-organizer-app-v1` for regroup actions.
- Dry-run before execute on `.autonomous_runs` after code changes; confirm path examples match target layout.

## Next steps
- Implement the tidy changes above in `tidy_workspace.py` (no run yet).
- If desired, patch run creators to write directly into `runs/<family>/<run-id>`.
- Optionally add a `archive\unsorted` inbox and document it in README.
- Add doc-creation routing for Cursor/manual:
  1) Implement a helper to classify new docs at creation time into buckets (plans → `archive\plans\`, analysis/reports → `archive\analysis\` or existing `reports/research`, prompts/delegations → `archive\prompts`/`delegations`, diagnostics → `archive\diagnostics`, scripts → `archive\scripts` or live `scripts/` if runnable). Fallback: `archive\tidy_up` (or `archive\unsorted`) for unclassified.
  2) Update tidy regroup logic to recognize these buckets so they aren’t reshuffled.
  3) Add README guidance: where Cursor-generated plans/analyses/prompts should be saved by default for File Organizer and for Autopack tidy (with inbox fallback).
  4) Ensure tidy regroup on `.autonomous_runs` preserves `runs/<family>/<run-id>` for manual runs, so reruns keep same-family grouping under `archive\superseded\runs`.
  5) Define Autopack project buckets (plans/analysis/logs/docs/prompts) under `archive\...` and point any Autopack truth-source updates (README, consolidated_*.md) to `archive\docs`.***

