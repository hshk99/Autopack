# Autopack Framework

**Autonomous AI Code Generation Framework**

Autopack is a framework for orchestrating autonomous AI agents (Builder and Auditor) to plan, build, and verify software projects. It uses a structured approach with phased execution, quality gates, and self-healing capabilities.

---

## Recent Updates (v0.4.1 - Patch Apply Hardening)

### Adaptive structured edits for large scopes (2025-12-09)
- Builder now auto-falls back to structured_edit when full-file outputs truncate or fail JSON parsing on large, multi-path phases (e.g., search, batch-upload).
- Phases can opt into structured_edit via `builder_mode` in the phase spec; large scopes (many files) default to structured_edit to avoid token-cap truncation.
- CI logs can be captured on success per phase (`ci.log_on_success: true`) to aid “needs_review” follow-up.
- Workspace prep: ensure scoped directories exist in the run workspace (e.g., `models/`, `migrations/`) to avoid missing-path scope warnings.
- Reusable hardening templates: see `templates/hardening_phases.json` and `templates/phase_defaults.json` plus `scripts/plan_hardening.py` to assemble project plans; kickoff multi-agent planning with `planning/kickoff_prompt.md`.

### Memory & Context System (IMPLEMENTED & VERIFIED 2025-12-09)
Vector memory for context retrieval and goal-drift detection:

- **Database Architecture**:
  - **Transactional DB**: **PostgreSQL** (default) - Stores phases, runs, decision logs, plan changes, etc.
  - **Vector DB**: **Qdrant** (default) - Production vector search with HNSW indexing, UUID-based point IDs
  - **Fallbacks**: SQLite for transactional (dev/offline via explicit `DATABASE_URL` override); FAISS for vectors (dev/offline)
  - Run PostgreSQL locally: `docker-compose up -d db` (listens on port 5432)
  - Run Qdrant locally: `docker run -p 6333:6333 qdrant/qdrant`
  - Migration: Use `scripts/migrate_sqlite_to_postgres.py` to transfer data from SQLite to PostgreSQL
  - **Status**: ✅ PostgreSQL and Qdrant integration verified with decision logs, phase summaries, and smoke tests passing

- **Vector Memory** (`src/autopack/memory/`):
  - `embeddings.py` - OpenAI + local fallback embeddings
  - `qdrant_store.py` - **Qdrant backend (default)** - Production vector store with deterministic UUID conversion (MD5-based)
  - `faiss_store.py` - FAISS backend (dev/offline fallback)
  - `memory_service.py` - Collections: code_docs, run_summaries, decision_logs, task_outcomes, error_patterns
  - `maintenance.py` - TTL pruning (30 days default)
  - `goal_drift.py` - Detects semantic drift from run goals

- **YAML Validation** (`src/autopack/validators/yaml_validator.py`):
  - Pre-apply syntax validation for YAML/docker-compose files
  - Truncation marker detection
  - Docker Compose schema validation

- **Executor Integration**:
  - Retrieved context injected into builder prompts
  - Post-phase hooks write summaries/errors to vector memory
  - Goal drift check before apply (advisory mode by default)

- **Configuration** (`config/memory.yaml`):
  ```yaml
  enable_memory: true
  use_qdrant: true  # Default to Qdrant (set false for FAISS fallback)
  qdrant:
    host: localhost
    port: 6333
    api_key: ""  # Optional for Qdrant Cloud
  top_k_retrieval: 5
  goal_drift:
    enabled: true
    mode: advisory  # or 'blocking'
    threshold: 0.7
  ```

See `docs/IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md` for full details.

### Intent Router (2025-12-09)
Natural-language entrypoint that maps user intents to safe Autopack actions (no raw commands):
- Script: `scripts/intent_router.py`
- Supports: refresh planning artifacts (ingest + embeddings), memory maintenance (TTL + tombstones), show plan changes/decision log, query planning context.
- Usage examples:
  ```bash
  python scripts/intent_router.py --query "refresh planning artifacts" --project-id file-organizer-app-v1
  python scripts/intent_router.py --query "run memory maintenance" --project-id file-organizer-app-v1 --ttl-days 30
  python scripts/intent_router.py --query "show plan changes" --project-id file-organizer-app-v1
  python scripts/intent_router.py --query "planning context for kickoff" --project-id file-organizer-app-v1
  ```

### Diagnostics (governed troubleshooting)
- Governed diagnostics agent runs allowlisted probes with budgets/timeouts and saves artifacts to `.autonomous_runs/<run_id>/diagnostics`.
- Evidence-first: collects git status/diff, executor logs, env/dependency info, and probe outputs before any mutations; summaries land in DecisionLog + vector memory.
- Intent router supports `diagnose patch failure` and `diagnose ci failure` for manual, read-only runs (uses the same governed palette).
- Executor triggers diagnostics automatically on patch/CI/infra failures to capture signals and hypotheses for Doctor/maintainers.
- Config: `config/diagnostics.yaml` controls budgets, allowed hosts, baseline logs, and sandbox copy paths for risky probes (sandboxed commands run inside `.autonomous_runs/<run_id>/diagnostics/sandbox`).
- Dashboard: `/api/diagnostics/latest` and the dashboard “Latest Diagnostics” card show the most recent diagnostic summary (failure, ledger, probes) read-only.

### Backlog Maintenance (OPTIMIZED 2025-12-10)
Autonomous maintenance system for processing backlog items with propose-first diagnostics and optional patching:

**Core Features**:
- Mode: opt-in "maintenance/backlog" run that ingests a curated backlog file (e.g., `consolidated_debug.md`) and turns items into scoped phases with `allowed_paths`, budgets, and targeted probes/tests.
- Safety: propose-first by default (generate patch + diagnostics + tests); apply only after validation/approval. Use governed_apply, diagnostics runner, and allowlisted commands only.
- Checkpoints: branch per maintenance run; checkpoint commit (or stash) before apply; auto-revert on failed apply/tests; prefer PR generation for higher risk.
- Budgets: one item at a time; caps on probes/commands/time per item; execute_fix remains opt-in/disabled by default.

**Efficiency Optimizations (2025-12-10)** ⚡:
- **Test Execution**: Workspace tests run once before processing items (not per-item) - saves ~63s per 10 items
- **Test Output Storage**: Reference-based deduplication using SHA256 hashes - reduces storage by 80% (~90KB → ~18KB)
- **Artifact Paths**: Relative paths for cross-platform portability (no more absolute Windows paths)
- **File Operations**: Smart existence checks before tail operations - eliminates 30-40 failed commands per run
- **Overall Impact**: 33% faster execution (240s → 160s), 80% smaller artifacts, 100% fewer error logs

**Tooling**:
- `scripts/backlog_maintenance.py --backlog consolidated_debug.md --allowed-path src/` - emits maintenance plan JSON (propose-first)
- `scripts/run_backlog_plan.py --plan .autonomous_runs/backlog_plan.json` - runs diagnostics over plan (propose-first, no apply)
- `scripts/run_backlog_maintenance.py --backlog consolidated_debug.md --allowed-path src/ --checkpoint --test-cmd "pytest -q tests/smoke/"` - end-to-end: parse → plan → diagnostics with test deduplication
- Optional apply: `--apply --patch-dir patches/` applies per-item patches (named `<item_id>.patch`) only if auditor approves

**Observability**:
- Artifacts: `.autonomous_runs/<run_id>/diagnostics/` with command logs, summaries, and test cache
- Test Cache: `test_output_cache.json` stores unique test outputs by hash reference
- Summaries: `backlog_diagnostics_summary.json` with `test_hashes` field for efficient lookups
- DecisionLog + dashboard diagnostics card surface latest run

**Maintenance Auditor** (FIXED 2025-12-10):
- Proposals must satisfy scope/diff/test safety to be auto-approved
- Properly handles `None` diffs (no patch provided) without AttributeError
- Rejects if protected paths touched; requires human review for out-of-scope or oversized changes
- Targeted tests: auditor sees results and will require_human if tests missing/failing

**Low-risk Auto-apply** (recommended safeguards):
- Keep checkpoints on by default
- Only auto-apply auditor-approved patches that are in-scope, small (files/lines), with passing targeted tests
- Anything else remains propose-first for human review

**Executor CLI Flags**:
- `--maintenance-plan`, `--maintenance-patch-dir`, `--maintenance-apply`, `--maintenance-checkpoint`, `--maintenance-auto-apply-low-risk` control maintenance mode
- Low-risk auto-apply enforces extra size/test guards and requires checkpoint

## Repository Structure (Autopack + Projects)
- Autopack core lives at the repo root and includes executor, diagnostics, dashboard, and tooling.
- Project artifacts live under `.autonomous_runs/<project>/` (plans, diagnostics, consolidated logs); e.g., `file-organizer-app-v1` is the first project built with Autopack.
- Additional projects stay under `.autonomous_runs/<project>/` within this repo (not separate repos).
- Use branches per project/maintenance effort when applying automated fixes to keep histories clean; checkpoints are recommended for maintenance/apply flows.

## Plan Conversion (Markdown -> phase_spec)
- Use `scripts/plan_from_markdown.py --in docs/PLAN.md --out .autonomous_runs/<project>/plan_generated.json` to convert markdown tasks into phase specs matching `docs/phase_spec_schema.md`.
- Inline tags in bullets override defaults: `[complexity:low]`, `[category:tests]`, `[paths:src/,tests/]`, `[read_only:docs/]`.
- Defaults: complexity=medium, task_category=feature; acceptance criteria come from indented bullets under each task.
- Fully automated run: `scripts/auto_run_markdown_plan.py --plan-md docs/PLAN.md --run-id my-run --patch-dir patches --apply --auto-apply-low-risk --test-cmd "pytest -q tests/smoke"` converts → plan JSON → runs maintenance mode (diagnostics first, gated apply). Checkpoints are on by default for maintenance runs.

## Owner Intent (Troubleshooting Autonomy)
- Autopack should approach Cursor “tier 4” troubleshooting depth: when failures happen, it should autonomously run governed probes/commands (from a vetted allowlist), gather evidence (logs, test output, patch traces), iterate hypotheses, and log decisions—without requiring the user to type raw commands.
- Natural-language control is preferred: the intent router (and future dashboard hooks) should trigger safe actions like planning ingest, memory maintenance, diagnostics, and context queries.
- Safety is mandatory: all actions must respect allowlists/denylists, timeouts, budgets, and avoid destructive ops; writes happen only in approved worktrees/contexts.
- See `docs/TROUBLESHOOTING_AUTONOMY_PLAN.md` for the implementation plan to reach this capability.

### Patch Apply Hardening (2025-12-06)
- `GovernedApplyPath` now refuses the direct-write fallback whenever a patch touches existing files; fallback is limited to clean new-file-only patches and must write all expected files.
- Patch validation still runs first (dry-run git apply, lenient/3-way) and preserves backups; scope + protected-path enforcement remains unchanged.
- SQLite dev DB (`autopack.db`) now includes the `phases.scope` column to match the production schema (run_id already present).

### Comprehensive Error Reporting System (NEW)
Detailed error context capture and reporting for easier debugging:
- **Automatic Error Capture**: All exceptions automatically captured with full context
- **Rich Context**: Stack traces, phase/run info, request data, environment details
- **Error Reports**: Saved to `.autonomous_runs/{run_id}/errors/` as JSON + human-readable text
- **API Endpoints**:
  - `GET /runs/{run_id}/errors` - Get all error reports for a run
  - `GET /runs/{run_id}/errors/summary` - Get error summary
- **Stack Frame Analysis**: Captures local variables and function context at each stack level
- **Component Tracking**: Identifies where errors occurred (api, executor, builder, etc.)

**Error Report Location**:
```
.autonomous_runs/
  {run_id}/
    errors/
      20251203_013555_api_AttributeError.json  # Detailed JSON
      20251203_013555_api_AttributeError.txt   # Human-readable summary
```

**Usage**:
```bash
# View error summary for a run
curl http://localhost:8000/runs/my-run-id/errors/summary

# Get all error reports
curl http://localhost:8000/runs/my-run-id/errors
```

### Autopack Doctor
LLM-based diagnostic system for intelligent failure recovery:
- **Failure Diagnosis**: Analyzes phase failures and recommends recovery actions
- **Model Routing**: Uses Claude Sonnet 4.5 for routine failures and Claude Opus 4.5 for complex ones
- **Actions**: `retry_with_fix` (with hint), `replan`, `skip_phase`, `mark_fatal`, `rollback_run`
- **Budgets**: Per-phase limit (2 calls) and run-level limit (10 calls) to prevent loops
- **Confidence Escalation**: Upgrades to strong model if confidence < 0.7
- **Rule Refresh**: Project learned rules auto-reload mid-run when updated, so replans use the latest hints/rules without restarting.

**Configuration** (`config/models.yaml`):
```yaml
doctor_models:
  cheap: claude-sonnet-4-5
  strong: claude-opus-4-5
  min_confidence_for_cheap: 0.7
  health_budget_near_limit_ratio: 0.8
  high_risk_categories: [import, logic]
```

### Model Escalation System
Automatically escalates to more powerful models when phases fail repeatedly:
- **Intra-tier escalation**: Within complexity level (e.g., glm-4.6 -> claude-sonnet-4-5)
- **Cross-tier escalation**: Bump complexity level after N failures (low -> medium -> high)
- **Configurable thresholds**: `config/models.yaml` defines `complexity_escalation` settings

### Mid-Run Re-Planning with Message Similarity
Detects "approach flaws" vs transient failures using error message similarity:
- `_normalize_error_message()` - Strips variable content (paths, UUIDs, timestamps, line numbers)
- `_calculate_message_similarity()` - Uses `difflib.SequenceMatcher` with 0.8 threshold
- `_detect_approach_flaw()` - Triggers re-planning after consecutive same-type failures with similar messages

**Configuration** (`config/models.yaml`):
```yaml
replan:
  trigger_threshold: 2
  message_similarity_enabled: true
  similarity_threshold: 0.8
  fatal_error_types: [wrong_tech_stack, schema_mismatch, api_contract_wrong]
```

### Run-Level Health Budget
Prevents infinite retry loops by tracking failures across the run:
- `MAX_HTTP_500_PER_RUN`: 10 (stop after too many server errors)
- `MAX_PATCH_FAILURES_PER_RUN`: 15 (stop after too many patch failures)
- `MAX_TOTAL_FAILURES_PER_RUN`: 25 (hard cap on total failures)

### LLM Multi-Provider Routing
- Routes primarily to Anthropic (Claude Sonnet/Opus). GLM is disabled; OpenAI is fallback.
- **Provider tier strategy**:
  - Low/Medium/High: Claude Sonnet 4.5 (primary), escalate to Claude Opus 4.5 when needed
- Automatic fallback chain: Anthropic -> OpenAI
- Per-category routing policies (BEST_FIRST, PROGRESSIVE, CHEAP_FIRST)

**Environment Variables**:
```bash
# Required for each provider you want to use
ANTHROPIC_API_KEY=your-anthropic-key   # Anthropic - primary
OPENAI_API_KEY=your-openai-key         # OpenAI - optional fallback

# Backend auth (JWT, RS256)
JWT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----...dev or prod key...-----END PRIVATE KEY-----"
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----...dev or prod key...-----END PUBLIC KEY-----"
# Optional overrides
JWT_ISSUER=autopack-backend
JWT_AUDIENCE=autopack-clients
```

### Auth tokens & JWKS
- Tokens are RS256 JWTs with `iss`/`aud` enforced.
- JWKS endpoint: `/api/auth/.well-known/jwks.json` (share with verifiers).
- Key load status: `/api/auth/key-status` (reports env vs generated keys).

### Dashboard (status & usage)
- Provides run status, usage, and models list. Refer to `tests/test_dashboard_integration.py` for expected payloads/fields.
- Key routes (FastAPI):
  - `GET /dashboard/status` — overall health/version.
  - `GET /dashboard/usage` — recent token/phase usage aggregates.
  - `GET /dashboard/models` — current model routing table (source: `config/models.yaml`).
- Start the dashboard/API: `python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8100` (set `PYTHONPATH=src`, `DATABASE_URL=sqlite:///autopack.db`).
- Architecture: `LlmService` is the central routing layer; ensure diagrams include `LlmService` in the control plane feeding dashboard/model metadata.

### Hardening: Syntax + Unicode + Incident Fatigue
- Pre-emptive encoding fix at startup
- `PYTHONUTF8=1` environment variable for all subprocesses
- UTF-8 encoding on all file reads
- SyntaxError detection in CI checks

### Stage 2: Structured Edits for Large Files (NEW)
Enables safe modification of files of any size using targeted edit operations:
- **Automatic Mode Selection**: Files >1000 lines automatically use structured edit mode
- **Operation Types**: INSERT, REPLACE, DELETE, APPEND, PREPEND
- **Safety Features**: Validation, context matching, rollback on failure
- **No Truncation Risk**: Only generates changed lines, not entire file content
- **Format Contract**: Builder outputs must be JSON with a `files` array; legacy git-diff fallback is disabled for malformed outputs.

**3-Bucket Policy**:
- **Bucket A (≤500 lines)**: Full-file mode - LLM outputs complete file content
- **Bucket B (501-1000 lines)**: Diff mode - LLM generates git diff patches  
- **Bucket C (>1000 lines)**: Structured edit mode - LLM outputs targeted operations

For details, see [Stage 2 Documentation](docs/stage2_structured_edits.md) and [Phase Spec Schema](docs/phase_spec_schema.md).

---

## Phase 3 Preview: Direct Fix Execution

### Doctor `execute_fix` Action (Coming Soon)
Enables Doctor to execute infrastructure-level fixes directly without going through Builder:
- **Problem Solved**: Merge conflicts, missing files, Docker issues currently require manual intervention
- **Solution**: Doctor emits shell commands (`git checkout`, `docker restart`, etc.) executed directly
- **Safety**: Strict whitelist, workspace-only paths, opt-in via config, no sudo/admin

**Configuration** (`config/models.yaml`):
```yaml
doctor:
  allow_execute_fix_global: true    # Enabled (whitelisted commands only)
  max_execute_fix_per_phase: 1      # One attempt per phase
  allowed_fix_types: ["git", "file"] # Typed categories
```

**Supported Fix Types** (v1):
- `git`: `checkout`, `reset`, `stash`, `clean`, `merge --abort`
- `file`: `rm`, `mkdir`, `cp`, `mv` (workspace only)
- `python`: `pip install`, `pytest` (planned)

See [IMPLEMENTATION_PLAN.md](archive/IMPLEMENTATION_PLAN.md) for full design details.

---

## Documentation

### Core Documentation
- **[Phase Spec Schema](docs/phase_spec_schema.md)**: Phase specification format, safety flags, and file size limits
- **[Stage 2: Structured Edits](docs/stage2_structured_edits.md)**: Guide to structured edit mode for large files
- **[IMPLEMENTATION_PLAN2.md](IMPLEMENTATION_PLAN2.md)**: File truncation bug fix and safety improvements
- **[IMPLEMENTATION_PLAN3.md](IMPLEMENTATION_PLAN3.md)**: Structured edits implementation plan
- **Planner Prompt (Autopack-ready)**: `prompts/claude/planner_prompt.md` now enforces non-empty descriptions, explicit scope (modifiable paths + read-only context), acceptance criteria, and token/attempt caps for every phase.

### Archive Documentation
Detailed historical documentation is available in the `archive/` directory:

- **[Archive Index](archive/ARCHIVE_INDEX.md)**: Master index of all archived documentation
- **[Claude-GPT Consultation](archive/CONSOLIDATED_CORRESPONDENCE.md)**: Index of all Claude-GPT consultation exchanges
- **[Consultation Summary](archive/GPT_CLAUDE_CONSULTATION_SUMMARY.md)**: Executive summary of all Phase 1 implementation decisions
- **[Autonomous Executor](archive/CONSOLIDATED_REFERENCE.md#autonomous-executor-readme)**: Guide to the orchestration system
- **[Learned Rules](LEARNED_RULES_README.md)**: System for preventing recurring errors
- **[Implementation Plan](archive/IMPLEMENTATION_PLAN.md)**: Historical roadmap and Phase 3+ planning

For detailed decision history, see the `archive/correspondence/` directory (52 individual exchanges).

## Project Structure

```
C:/dev/Autopack/
├── .autonomous_runs/         # Runtime data and project-specific archives
│   ├── file-organizer-app-v1/# Example Project: File Organizer
│   └── ...
├── archive/                  # Framework documentation archive
├── config/
│   └── models.yaml           # Model configuration, escalation, routing policies
├── logs/
│   └── archived_runs/        # Archived log files from previous runs
├── src/
│   └── autopack/             # Core framework code
│       ├── autonomous_executor.py  # Main orchestration loop
│       ├── llm_service.py          # Multi-provider LLM abstraction
│       ├── model_router.py         # Model selection with quota awareness
│       ├── model_selection.py      # Escalation chains and routing policies
│       ├── error_recovery.py       # Error categorization and recovery
│       ├── archive_consolidator.py # Documentation management
│       ├── debug_journal.py        # Self-healing system wrapper
│       ├── memory/                 # Vector memory for context retrieval
│       │   ├── embeddings.py       # Text embeddings (OpenAI + local)
│       │   ├── faiss_store.py      # FAISS backend
│       │   ├── memory_service.py   # High-level insert/search
│       │   ├── maintenance.py      # TTL pruning
│       │   └── goal_drift.py       # Goal drift detection
│       ├── validators/             # Pre-apply validation
│       │   └── yaml_validator.py   # YAML/compose validation
│       └── ...
├── scripts/                  # Utility scripts
│   └── consolidate_docs.py   # Documentation consolidation
└── tests/                    # Framework tests
```

## Key Features

- **Autonomous Orchestration**: Wires Builder and Auditor agents to execute phases automatically.
- **Model Escalation**: Automatically escalates to more powerful models after failures.
- **Mid-Run Re-Planning**: Detects approach flaws and revises phase strategy.
- **Self-Healing**: Automatically logs errors, fixes, and extracts prevention rules.
- **Quality Gates**: Enforces risk-based checks before code application.
- **Multi-Provider LLM**: Routes to Gemini, GLM, Anthropic, or OpenAI with automatic fallback.
- **Project Separation**: Strictly separates runtime data and docs for different projects.

## Usage

### Running an Autonomous Build

```bash
python src/autopack/autonomous_executor.py --run-id my-new-run
```

### Tidy & Archive Maintenance (intent + usage)
- Manual-only tool: `run_tidy_all.py` / `tidy_workspace.py` are deliberate runs, not automatic maintenance.
- One-shot tidy (semantic classify/apply, prune, checkpoints, git commits):
  ```bash
  python scripts/run_tidy_all.py
  ```
- Scopes/config: `tidy_scope.yaml` sets roots (defaults: `.autonomous_runs/file-organizer-app-v1`, `.autonomous_runs`, `archive`), optional `purge: true`, optional `db_overrides` per root (Postgres DSN). Wrapper runs per root with the matching DSN.
- Superseded handling: if a root path contains `superseded`, markdown organizer is skipped so superseded files stay put.
- Semantic store: Postgres (`DATABASE_URL`), then Qdrant (`QDRANT_URL`/`QDRANT_HOST` + `QDRANT_API_KEY`), else JSON cache. Embeddings: set `EMBEDDING_MODEL` (default `BAAI/bge-m3`; hash fallback). Requires `sentence-transformers` for HF models.
- Truth-merge: allocator suggestions can be generated; optional apply is section-aware (inserts under matching headings) with provenance markers. Semantic deletes downgrade to archive moves unless `--semantic-delete` is set.
- Logging: moves/deletes/merges recorded with project_id and SHAs into Postgres (`tidy_activity`) if available; fallback JSONL at `.autonomous_runs/tidy_activity.log`.
- Purge: opt-in only (via `tidy_scope.yaml` or `--purge`); default is prune/move, not delete.

### Consolidating Documentation

To tidy up and consolidate documentation across projects:

```bash
python scripts/consolidate_docs.py
```

This will:
1. Scan all documentation files.
2. Sort them into project-specific archives (`archive/` vs `.autonomous_runs/<project>/archive/`).
3. Create consolidated reference files (`CONSOLIDATED_DEBUG.md`, etc.).
4. Move processed files to `superseded/`.

---

## Configuration

### Model Escalation (`config/models.yaml`)

```yaml
complexity_escalation:
  enabled: true
  thresholds:
    low_to_medium: 2    # Escalate after 2 failures at low complexity
    medium_to_high: 2   # Escalate after 2 failures at medium complexity
  max_attempts_per_phase: 5
  failure_types:
    - auditor_reject
    - ci_fail
    - patch_apply_error

escalation_chains:
  builder:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro, claude-sonnet-4-5]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5, gpt-5]
    high:
      models: [claude-sonnet-4-5, gpt-5]
  auditor:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5]
    high:
      models: [claude-sonnet-4-5, claude-opus-4-5]
```

### Re-Planning (`config/models.yaml`)

```yaml
replan:
  trigger_threshold: 2          # Consecutive same-type failures before re-plan
  message_similarity_enabled: true
  similarity_threshold: 0.8     # How similar messages must be (0.0-1.0)
  min_message_length: 30        # Skip similarity check for short messages
  max_replans_per_phase: 1      # Prevent infinite re-planning loops
  fatal_error_types:            # Immediate re-plan triggers
    - wrong_tech_stack
    - schema_mismatch
    - api_contract_wrong
```

---

**Version**: 0.5.0 (Memory & Context System)
**License**: MIT
**Last Updated**: 2025-12-09

**Milestone**: `tests-passing-v1.0` - All core tests passing (89 passed, 30 skipped, 0 failed)
