# Implementation Plan: Memory/Context Phase 2 (Post-Merge Integration Checklist)

This plan assumes the Phase 1 memory/context changes have been applied (new memory module, YAML validator, goal drift check, retrieved_context in prompts, goal_anchor in Run). The goal is to harden, connect, and operationalize the new pieces with minimal disruption.

## Objectives
- Finish wiring the new memory components into the executor/LLM flow safely.
- Add ingestion, versioning, and retrieval for planning artifacts and plan changes.
- Add decision logging and cleanup/maintenance paths with auditability.
- Provide an optional chat/CLI front-end that routes natural-language intents to safe commands.

## Prerequisites (already merged in Phase 1)
- New files:
  - `src/autopack/memory/embeddings.py`
  - `src/autopack/memory/faiss_store.py`
  - `src/autopack/memory/memory_service.py`
  - `src/autopack/memory/maintenance.py`
  - `src/autopack/memory/goal_drift.py`
  - `src/autopack/validators/yaml_validator.py`
  - `config/memory.yaml`
- Modified:
  - `src/autopack/autonomous_executor.py` (MemoryService init, retrieval before builder, post-phase hooks, YAML validation, goal drift check, goal anchor init)
  - `src/autopack/llm_service.py` (retrieved_context passed to builder)
  - `src/autopack/anthropic_clients.py` (retrieved_context in prompt)
  - `src/autopack/models.py` (Run.goal_anchor)

## Phase 2 Work Items

### A. Ingestion & Versioning of Planning Artifacts
1) Add an ingestion script (e.g., `scripts/ingest_planning_artifacts.py`) that:
   - Reads `templates/hardening_phases.json`, `templates/phase_defaults.json`, `planning/kickoff_prompt.md`, `prompts/claude/planner_prompt.md`, and any compiled outputs from the analysis agent.
   - Stores a structured version row in SQLite (table: `planning_artifacts`): id, path, version, timestamp, hash, author/agent (if available), reason.
   - Embeds both raw text and a short summary into vector memory (collection: `code_docs` or a dedicated `planning` collection) with payload: {project_id, path, version, timestamp, type: "planning_artifact"}.
2) Add a small helper in `memory_service.py` to write/read planning artifacts by path+version and a convenience “latest” fetch.

### B. Plan Change Logging (Diff/Summary)
1) Add a plan_changes table in SQLite: id, run_id (optional), phase_id (optional), timestamp, author/agent, summary, rationale, replaces_version (nullable).
2) After a plan/template change, write a short summary to SQLite and embed it into vector memory (collection: `run_summaries` or `planning`) with type: "plan_change".
3) Retrieval bias: when fetching context for planning/build, prefer latest plan_change by timestamp but include the rationale field.

### C. Decision Log
1) Add decision_log table in SQLite: id, run_id, phase_id, timestamp, trigger (issue/failure), alternatives_considered, choice, rationale.
2) Post a compact summary into vector memory (collection: `run_summaries`, type: "decision_log") for replan recall.
3) Update executor: when doctor/replan triggers, write a decision_log entry and embed the summary.

### D. Outdated Data Handling / Maintenance
1) In vector memory: add “tombstone” support: when an entry is superseded, write a small payload noting `replaced_by` and `reason`; optionally compress/delete the old payload content.
2) In SQLite: mark artifacts/plan_changes as superseded/archived; keep links to replacements.
3) Maintenance job:
   - TTL prune unless `pinned`.
   - Keep latest N versions of planning artifacts; compress older ones and keep a note: “Replaced by vX due to Y.”
   - Expose a script entry point (e.g., `python -m autopack.memory.maintenance run`).

### E. Executor/LLM Wiring Validation
1) Confirm `autonomous_executor.py` uses:
   - Lazy file loading (no bulk `existing_files`).
   - Retrieval before builder call: top-k from memory_service filtered by project_id/run_id/task_type.
   - Post-phase hooks writing summaries/errors/doctor hints.
   - YAML validation pre-apply; goal drift check optional/advisory.
2) Confirm `llm_service.py` and `anthropic_clients.py` include `retrieved_context` in prompts and keep prompt size bounded (cap top-k and chunk size).

### F. Optional Chat/CLI Front-End
1) Add a thin CLI/chat router (e.g., `scripts/chat_cli.py`) that:
   - Maps natural-language intents to safe commands (create/run, status, replan, query memory, show plan changes, trigger ingestion).
   - Uses vector retrieval to answer context queries; never bypasses executor safety gates.
2) Keep it read-only for dangerous ops; actual mutations go through existing executor pathways.

### G. Testing & Safety
1) Unit tests: embeddings truncation, FAISS insert/search, planning artifact ingestion, decision_log writes, YAML validator.
2) Integration: run a phase with large scopes; verify prompt excludes bulk scope and includes retrieved snippets; verify post-phase writes to memory.
3) Regression: ensure goal drift check is advisory/configurable; ensure no breaking changes to existing executor runs without memory enabled.

## Minimal Schema Changes (SQLite)
- Table `planning_artifacts`: id, path, version, timestamp, hash, author, reason, status (active/superseded), replaced_by (nullable).
- Table `plan_changes`: id, run_id (nullable), phase_id (nullable), timestamp, author, summary, rationale, replaces_version (nullable).
- Table `decision_log`: id, run_id, phase_id, timestamp, trigger, alternatives, choice, rationale.
- Column `goal_anchor` on `runs` (already added).

## Config Additions
- `config/memory.yaml`: already present; extend if needed with `planning_collection` name and maintenance settings (`ttl_days`, `keep_versions`).

## Rollout Steps
1) Apply schema migrations for new tables.
2) Add ingestion script and run initial ingest of planning artifacts.
3) Enable memory (faiss) in config; keep Qdrant adapter ready but disabled unless configured.
4) Validate executor/LLM wiring with a dry run; ensure prompts are small and retrieved_context is present.
5) Add decision_log and plan_changes writes on replan/doctor/plan edits.
6) (Optional) Add chat/CLI router for safe NL-driven queries/actions.


