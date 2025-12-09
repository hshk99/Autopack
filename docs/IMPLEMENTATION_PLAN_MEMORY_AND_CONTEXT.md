# Autopack Memory, Context, and Goal-Alignment Plan

## Goals
- Cut token waste by replacing bulk scope preloads with on-demand context and retrieval.
- Add persistent, searchable memory (vector index) alongside SQLite for unstructured recall (code/docs, run summaries, errors, doctor hints).
- Improve goal alignment and pre-apply gating (especially for YAML/compose).
- Preserve existing executor/run lifecycle; changes are additive and incremental.

## Architecture Overview
- **SQLite (keep):** authoritative for run/phase state, attempts, configs, audits.
- **Vector memory (add):** FAISS (no infra) with an adapter to swap to Qdrant later. Collections:
  - `code_docs`: embeddings of workspace files (under `.autonomous_runs/file-organizer-app-v1` + top-level docs).
  - `run_summaries`: short per-phase summaries (changes, CI result, errors).
  - `errors_ci`: failing test/error snippets.
  - `doctor_hints`: doctor hints/actions/outcomes.
- **Prompt inputs:** (a) lazily loaded target files; (b) top-k retrieved snippets from vector memory; (c) goal anchor (short text).

## Scope (MVP)
1) Introduce vector memory service (FAISS) and embedding helpers.
2) Switch executor to on-demand file loading (no bulk scope preload).
3) Add post-phase hooks to persist summaries/errors/hints into vector memory.
4) Add lightweight goal-drift check before apply (optional gating).
5) Harden YAML/compose validation pre-apply.

## Components & File Touches
- New module (e.g., `src/autopack/memory/`):
  - Reuse from `C:\dev\chatbot_project\backend` where possible:
    - `embedding_utils.py` → adapt as `embeddings.py` (keep OpenAI + local fallback, truncate input; adjust logging/config paths).
    - `qdrant_utils.py` → adapt interface; if using FAISS first, keep a thin adapter that can switch to Qdrant; retain schema/collection helpers.
    - `memory_lookup.py` → adapt to search by project_id/run_id/task_type; expose sync/async helpers.
    - `memory_maintenance.py` → adapt TTL prune + optional compression hook.
    - `short_term_memory.py` → optional per-run/per-phase bounded cache.
  - `faiss_store.py`: minimal FAISS backend (no infra); keep adapter shape so Qdrant swap is easy.
  - `memory_service.py`: high-level insert/search for collections above.
- Executor integration:
  - `src/autopack/autonomous_executor.py`: replace bulk `_load_repository_context` usage with lazy file loads (per target file list) and retrieval for supplemental context; call post-phase hooks to write summaries/errors/hints.
  - `src/autopack/llm_service.py` & `src/autopack/anthropic_clients.py`: accept a “files to edit” payload (small) plus retrieved snippets; avoid passing entire scope.
- Validation:
  - Add a YAML/compose validator utility (e.g., `src/autopack/validators/yaml_validator.py`) used pre-apply.
- Goal alignment:
  - Store a short goal anchor per run (in SQLite); before apply, run a small LLM check comparing current change intent vs anchor; block or replan on drift.

## Data & Payload Schemas
- Vector payload keys: `run_id`, `phase_id`, `project_id`, `task_type`, `timestamp`, `path` (for code/docs), `type` (summary/error/hint/code).
- Embedding limits: truncate inputs (e.g., 30k chars) before embedding; cap retrieved chunk sizes.

## Execution Flow Changes (MVP)
1) **Before builder call:**
   - Determine target files (from phase scope + planned edits); load only those file contents.
   - Retrieve supplemental context (top-k) from vector memory for: code_docs, run_summaries, errors_ci, doctor_hints (filtered by project_id/run_id/task_type).
   - Build prompt from target files + retrieved snippets + goal anchor (short).
2) **Apply/gate:**
   - Run YAML/compose validator pre-apply; fail fast on incomplete/truncated output.
   - Optional goal-drift check before apply.
3) **After phase:**
   - If succeeded: write a compact phase summary to `run_summaries`.
   - If CI/error: write failing test/error snippets to `errors_ci`.
   - If doctor invoked: write hint/outcome to `doctor_hints`.
4) **Maintenance (background/periodic):**
   - TTL prune old vector entries; optional compression for long contents.

## Config & Env
- New config (e.g., `config/memory.yaml`):
  - enable_memory: true|false
  - backend: faiss | qdrant
  - faiss_index_path: `.autonomous_runs/file-organizer-app-v1/.faiss/index.faiss`
  - top_k_retrieval: 3–5
  - max_embed_chars: 30000
  - ttl_days: e.g., 30
- Env (for OpenAI embeddings if desired): `OPENAI_API_KEY`, `USE_OPENAI_EMBEDDINGS=1`.

## Testing Strategy
- Unit: embeddings (truncate), FAISS insert/search, YAML/compose validator.
- Integration: executor lazy-load path—ensure only target files are in prompt; retrieval returns bounded snippets; post-phase summaries are written.
- Regression: run a phase with large scopes and confirm prompt size shrinks and no bulk scope load occurs.

## Risks & Mitigations
- Prompt bloat from retrieval: cap top-k and chunk size; filter by task_type/phase_id.
- Embedding latency: use local deterministic embeddings if OpenAI is unavailable; cache embeddings per file hash.
- Schema drift (future Qdrant): keep an adapter interface; validate dimensions on startup.
- Goal-drift false positives: start as advisory logging; make gating configurable.

## Milestones (incremental)
1) Add memory service (FAISS), embeddings helper, config; no executor change yet.
2) Executor lazy file loading + retrieval in prompts; disable bulk preload.
3) Post-phase hooks writing summaries/errors/hints to vector memory.
4) YAML/compose pre-apply validator; optional goal-drift check (advisory).
5) Optional chat/CLI to query memory (read-only) for navigation.

## Minimal Code Touch List (expected)
- Add: `src/autopack/memory/{embeddings.py,faiss_store.py,memory_service.py,maintenance.py}`
- Update: `src/autopack/autonomous_executor.py` (lazy loads, retrieval integration, post-phase writes)
- Update: `src/autopack/llm_service.py`, `src/autopack/anthropic_clients.py` (prompt inputs accept small file set + retrieved snippets)
- Add: `src/autopack/validators/yaml_validator.py`
- Add config: `config/memory.yaml`
- Docs: this plan file


