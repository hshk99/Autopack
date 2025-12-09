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

### Memory & Context System (IMPLEMENTED 2025-12-09)
Vector memory for context retrieval and goal-drift detection:

- **Vector Memory** (`src/autopack/memory/`):
  - `embeddings.py` - OpenAI + local fallback embeddings
  - `faiss_store.py` - FAISS backend (Qdrant-ready adapter)
  - `memory_service.py` - Collections: code_docs, run_summaries, errors_ci, doctor_hints
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
  top_k_retrieval: 5
  goal_drift:
    enabled: true
    mode: advisory  # or 'blocking'
    threshold: 0.7
  ```

See `docs/IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md` for full details.

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
