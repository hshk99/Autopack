## Goal
Finish the remaining “tidy gap closure” correctness work so the system is **safe** (no silent SOT data loss) and **actually closes the reuse loop** (tidy → SOT → indexing → runtime retrieval).

You must follow the canonical spec in `docs/WORKSPACE_ORGANIZATION_SPEC.md` and the intent section in `README.md` (“tidy backlog → SOT ledgers → semantic indexing → Autopack uses it when it needs it”).

## Current state (important)
- `scripts/tidy/tidy_up.py` exists and now **blocks** auto-moving root SOT duplicates when they differ from `docs/` copies.
- Executor SOT indexing exists (`AutonomousExecutor._maybe_index_sot_docs()`), and we added logic to **honor a dirty marker**:
  - Autopack: `.autonomous_runs/sot_index_dirty_autopack.json`
  - Sub-project: `.autonomous_runs/<project>/.autonomous_runs/sot_index_dirty.json`
- Verifier `scripts/tidy/verify_workspace_structure.py` was fixed for Windows console encoding and reduced `.autonomous_runs` false positives.

## Your tasks

### Task A — Add tests for the new safety + dirty-marker behavior
- **A1 (tidy safety)**: create a test that sets up a temp repo root with:
  - `docs/BUILD_HISTORY.md` and a different `BUILD_HISTORY.md` at root
  - run `tidy_up.py --execute` (or call the internal function if easier)
  - assert it **does not move** the root SOT file and emits a clear “manual merge required” message (and/or returns non-zero).
- **A2 (tidy identical duplicate)**: same but make the root and docs copies identical; assert it routes the root duplicate into:
  - `archive/superseded/root_sot_duplicates/BUILD_HISTORY.md`
- **A3 (dirty marker)**:
  - run a tidy action that would mark dirty (e.g., `--skip-archive-consolidation` off in execute mode, or a simulated SOT move)
  - assert marker file is created.
- **A4 (executor clears marker)**:
  - create marker file before executor initialization
  - enable `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true`
  - run `_maybe_index_sot_docs()` using a stubbed MemoryService/store
  - assert marker is deleted after successful indexing.

### Task B — Make tidy_up fail fast on unsafe root SOT duplicates (execute mode)
Right now it prints “[BLOCK] … manual merge required” but still continues.
Update `tidy_up.py` so that:
- In `--execute` mode, if any root SOT duplicate differs from docs, **exit non-zero** with a short summary of blocked files.
- In dry-run, it can remain “report-only”.

### Task C — Tighten “dirty marker” semantics
Currently `tidy_up.py` marks dirty if Phase 3 ran, even if it no-ops.
Improve to reduce unnecessary reindex:
- After Phase 3 consolidation completes, mark dirty **only if** SOT files changed.
  - Simplest: compare git status/diff for the 6 SOT files (if in git), or compare file mtimes/hashes before/after Phase 3.
Keep it bounded and Windows-safe.

### Task D — Update documentation
- Update `docs/TIDY_SYSTEM_USAGE.md` with:
  - “Do not run tidy until you manually resolve root SOT duplicates if present”
  - A short section explaining dirty markers and how they get cleared by executor.
- Optionally add a short note in `docs/CURSOR_PROMPT_TIDY.md` pointing to `scripts/tidy/tidy_up.py` as the preferred entrypoint.

## Acceptance criteria
- Running `python scripts/tidy/verify_workspace_structure.py` works on Windows and prints a report without crashing.
- `tidy_up.py --execute` **never** silently moves or overwrites divergent SOT files.
- Dirty marker causes exactly one re-index at next startup (when enabled), then is cleared.
- Tests cover both safety and marker semantics.


