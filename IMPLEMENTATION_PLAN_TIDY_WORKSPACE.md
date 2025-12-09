# Workspace Tidying & Safeguards – Implementation Plan

## Goals
- Provide a single entrypoint to tidy documentation and run artifacts without touching active/important files.
- Consolidate and archive outdated artifacts while preserving truth sources.
- Capture a reversible checkpoint before any destructive/move operations.
- Keep token/API usage at zero (local file ops only).
  - NEW: allow optional embeddings via HF sentence-transformers (EMBEDDING_MODEL env); fallback hash embeddings; persist vectors to Postgres/Qdrant.

## Scope (initial targets)
- Roots: `.autonomous_runs/file-organizer-app-v1`, `.autonomous_runs/` (other runs), `archive/`, `archive/correspondence/`, `docs/` research, and project archives.
- File types: Markdown, logs (`.log`, `.txt`), diagnostics/errors (`diagnostics/`, `errors/`), patches, exports (`.csv`, `.xlsx`, `.pdf`), JSON plans.

## Explicit Exclusions (never move/delete)
- `project_learned_rules.json`, `project_learned_rules` derivatives.
- Databases: `autopack.db`, `fileorganizer.db`, `test.db`, any `*.db` or migration folders.
- Current planning/truth sources: `WHATS_LEFT_TO_BUILD.md`, `WHATS_LEFT_TO_BUILD_MAINTENANCE.md`, `plan_*.json`, `autopack_phase_plan.json`, `plan_generated*.json`, `rules_updated.json`, `project_*rules*.json`.
- Source code, configs, and `scripts/` in repo root or project subroots.

## Safety & Checkpointing
- Always support `--dry-run` (default: dry-run true) with a manifest of proposed actions.
- Before executing moves/deletes, create a checkpoint archive (zip/tar) of affected files to `.autonomous_runs/checkpoints/<timestamp>_tidy.zip`.
- No API/LLM calls; pure filesystem operations.

## Tooling Plan
- New entrypoint: `scripts/tidy_workspace.py`
  - Args: `--root <path>` (repeatable), defaults to repo root; `--dry-run` (default true), `--verbose`, `--age-days <N>` for pruning logs/diagnostics, `--checkpoint-dir <path>`.
  - Steps:
    1) Discover files under target roots with allow/deny patterns.
    2) Classify:
       - Markdown → delegate to existing `tidy_docs` categorization where applicable.
       - Consolidation: optionally invoke `consolidate_docs` for archives (opt-in flag `--consolidate-md`).
       - Logs/diagnostics/errors → move to `archive/logs/` or `archive/runs/<run_id>/` (preserve structure).
       - Exports → `exports/` (per project), keep latest by timestamp if duplicates (no deletion without `--prune`).
       - Patches → `patches/` under the project.
    3) Prune (optional): if `--prune` and older than `--age-days`, move to `archive/superseded/`; delete only when `--purge` is explicitly set.
    4) Execute actions after creating checkpoint; print manifest of moves/deletes.
- Reuse components:
  - Import `DocumentationOrganizer` from `scripts/tidy_docs.py` for MD moves.
  - Optionally call `scripts/consolidate_docs.py` as a subprocess when `--consolidate-md` is set.
  - Persistent stores: JSON cache; Postgres (tidy_semantic_cache table); Qdrant (payload + vector embeddings). Embeddings via HF model if EMBEDDING_MODEL is set, else hash fallback.

## Directory Conventions
- `archive/superseded/` for outdated files (any type) that should be retained but hidden.
- `archive/logs/` for log/diagnostic/error artifacts not tied to a specific run.
- `archive/runs/<run_id>/` to hold migrated diagnostics/errors/patches per historical run.
- `exports/` under each project for CSV/XLSX/PDF; keep originals in-place if already there.

## Non-Goals (v1)
- No content-diff freshness detection between overlapping notes.
- No automated DB migration/cleanup.
- No modification of code/tests/configs.
  - Truth merges are append-only blocks with provenance markers; no auto-diff/section replace yet.

## Acceptance Criteria
- Dry-run shows a manifest; no files changed in dry-run mode.
- Running with `--checkpoint` creates an archive of all to-be-changed files before any move/delete.
- Truth-source files and DBs remain untouched (validated by an exclusion filter).
- Logs/diagnostics/patches are relocated to archive folders; Markdown is organized per existing rules; superseded content is moved, not deleted, unless `--purge` is set.
- No external API/LLM calls; exits non-zero on errors.
  - Persistent semantic cache stored in Postgres or Qdrant when available; embeddings captured when EMBEDDING_MODEL is provided.

