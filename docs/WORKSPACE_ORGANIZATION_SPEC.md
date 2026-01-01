# Workspace Organization Specification

**Version**: 1.0
**Date**: 2026-01-01
**Status**: Canonical (Single Source of Truth)

## Purpose

This document defines the **authoritative** workspace organization rules for the Autopack repository. It serves as:
- The canonical reference for what belongs where in the repository
- The basis for automated tidy/cleanup validation
- The specification that tidy scripts enforce

## 1. Repository Root (c:\dev\Autopack\)

### Allowed Files at Root

The repository root should remain **minimal** and contain only:

#### Essential Configuration Files
- `.gitignore` - Git ignore rules
- `.dockerignore` - Docker ignore rules
- `.eslintrc.cjs` - ESLint configuration
- `.env` - Environment variables (not committed to git)
- `README.md` - Primary repository documentation
- `LICENSE` - License file
- `pyproject.toml` - Python project configuration
- `package.json` - Node.js project configuration
- `tsconfig.json` - TypeScript configuration
- `docker-compose.yml` - Docker Compose configuration
- `docker-compose.dev.yml` - Docker Compose (development) configuration
- `Dockerfile` - Docker build configuration
- `Dockerfile.*` - Additional Docker build configurations (e.g., `Dockerfile.frontend`)
- `requirements.txt` - Python dependencies
- `requirements-dev.txt` - Python dev/test dependencies
- `poetry.lock`, `package-lock.json`, `yarn.lock` - Dependency lock files
- `pytest.ini` - Pytest configuration (if present)
- `Makefile` - Build/dev task runner (if present)
- `nginx.conf` - Nginx config (if present)
- `index.html` - Frontend entrypoint (if present; e.g., Vite root frontend)
- `vite.config.*` - Frontend build config (if present; e.g., `vite.config.ts`)
- `tsconfig*.json` - TypeScript configs (e.g., `tsconfig.node.json`)

#### Database Files (Development)
- `autopack.db` - **Primary development database** (active, should remain at root)
- **Historical/test databases are NOT allowed at root** - they will be routed to `archive/data/databases/`
  - Telemetry seed databases → `archive/data/databases/telemetry_seeds/`
  - Debug snapshots → `archive/data/databases/debug_snapshots/`
  - Test artifacts → `archive/data/databases/test_artifacts/`
  - Legacy backups → `archive/data/databases/legacy/`
- Note: Production databases should use PostgreSQL, not SQLite files

#### Build Artifacts (Temporary)
- `.coverage`, `.coverage.json` - Code coverage reports (temporary, not committed)
- `.pytest_cache/` - Pytest cache (not committed)
- `__pycache__/` - Python bytecode cache (not committed)
- `node_modules/` - Node.js dependencies (not committed)

### Disallowed at Root (Should Be Routed)

These file types should **never** accumulate at repository root and must be routed by tidy:

- **Markdown Documentation** (`*.md` except `README.md`)
  - Build reports → `archive/reports/`
  - Debug logs → `archive/diagnostics/`
  - Implementation plans → `archive/plans/`
  - Prompts → `archive/prompts/`
  - Research notes → `archive/research/`

- **Python Scripts** (`*.py` except build tools)
  - Backend scripts → `scripts/backend/`
  - Test scripts → `scripts/test/`
  - Utility scripts → `scripts/utility/`
  - Temporary scripts → `scripts/temp/`

- **Log Files** (`*.log`)
  - All logs → `archive/diagnostics/logs/`

- **JSON Files** (non-config)
  - Phase plans → `archive/plans/`
  - Error reports → `archive/diagnostics/`
  - Other JSON → `archive/unsorted/`

- **Shell Scripts** (`*.sh`, `*.bat`, `*.ps1`)
  - Utility scripts → `scripts/utility/`
  - Archived scripts → `scripts/archive/`

## 2. Documentation Directory (docs/)

### The 6-File SOT Structure

The `docs/` directory contains the **Single Source of Truth (SOT)** for project knowledge. The core structure is:

1. **PROJECT_INDEX.json** - Quick reference (setup, API, structure)
2. **BUILD_HISTORY.md** - Implementation history (auto-updated by tidy)
3. **DEBUG_LOG.md** - Troubleshooting log (auto-updated by tidy)
4. **ARCHITECTURE_DECISIONS.md** - Design decisions (auto-updated by tidy)
5. **FUTURE_PLAN.md** - Roadmap and backlog (manually maintained)
6. **LEARNED_RULES.json** - Auto-updated learned rules (auto-updated by system)

### Additional Allowed Files in docs/

Beyond the core 6-file SOT, the following files are explicitly allowed in `docs/`:

#### Core Documentation Files
- **INDEX.md** - Navigation hub for the documentation
- **CHANGELOG.md** - Version history and release notes
- **WORKSPACE_ORGANIZATION_SPEC.md** - This file (canonical organization rules)
- **ARCHITECTURE.md** - System architecture overview
- **QUICKSTART.md** - Quick start guide for new users
- **CONTRIBUTING.md** - Contribution guidelines

#### Canonical Guides (Truth Sources)
These are **current, canonical reference documents** that serve as authoritative truth sources:

- **DEPLOYMENT.md** - Deployment instructions
- **GOVERNANCE.md** - Governance rules and policies
- **TROUBLESHOOTING.md** - Troubleshooting guide
- **TESTING_GUIDE.md** - Testing guidelines and procedures
- **CONFIG_GUIDE.md** - Configuration guide
- **AUTHENTICATION.md** - Authentication setup and usage
- **ERROR_HANDLING.md** - Error handling patterns
- **TELEMETRY_GUIDE.md** - Telemetry system usage
- **TELEMETRY_COLLECTION_GUIDE.md** - Telemetry collection procedures
- **TIDY_SYSTEM_USAGE.md** - Tidy system usage guide
- **PARALLEL_RUNS.md** - Parallel runs documentation
- **PHASE_LIFECYCLE.md** - Phase lifecycle documentation
- **MODEL_INTELLIGENCE_SYSTEM.md** - Model intelligence system docs

#### Pattern-Based Allowlists
Files matching these patterns are allowed as canonical documentation:

- **CURSOR_PROMPT_*.md** - Cursor AI prompt guides
- **IMPLEMENTATION_PLAN_*.md** - Active implementation plans (current work)
- **PRODUCTION_*.md** - Production-related documentation
- **SOT_*.md** - SOT-related documentation
- **IMPROVEMENTS_*.md** - Improvement plans (active)
- **IMPLEMENTATION_SUMMARY_*.md** - Implementation summaries
- **RUNBOOK_*.md** - Operational runbooks
- ***_GUIDE.md** - Any canonical guide (e.g., CONFIG_GUIDE, TESTING_GUIDE)
- **CANONICAL_*.md** - Explicitly canonical documents (e.g., CANONICAL_API_CONTRACT)
- ***_SYSTEM.md** - System documentation (e.g., MODEL_INTELLIGENCE_SYSTEM)

#### Historical Files (Should Be Archived)
These patterns indicate **historical/completed documentation** that should be moved to `archive/`:

- **BUILD-NNN_*.md** - Build reports (older than 30 days) → `archive/reports/`
- **DBG-*.md**, **DEBUG_*.md** - Debug reports → `archive/diagnostics/`
- **ANALYSIS_*.md**, **SUMMARY_*.md** - Analysis reports → `archive/reports/`
- **PROMPT_*.md** - Prompts (except CURSOR_PROMPT_*) → `archive/prompts/`
- **TASK_*.md** - Task reports → `archive/reports/`
- Files in `archive/superseded/` - Already processed, never move back to docs/

### Allowed Subdirectories in docs/

Only these subdirectories are permitted under `docs/`:

1. **docs/guides/** - User guides and tutorials
   - Example: `BUILD-139_T1-T5_HANDOFF.md`

2. **docs/cli/** - CLI documentation and reference
   - Command line interface guides
   - Usage examples

3. **docs/cursor/** - Cursor-specific documentation
   - Handoff reports
   - Cursor AI integration guides

4. **docs/examples/** - Code examples and sample usage
   - Integration examples
   - API usage samples

5. **docs/api/** - API documentation
   - OpenAPI specs
   - API reference guides

6. **docs/autopack/** - Autopack-specific technical docs
   - Deep technical documentation
   - System architecture details

7. **docs/research/** - Active research documentation
   - Ongoing research
   - Experimental features

8. **docs/reports/** - Current/active reports
   - Recent build reports
   - Current analysis reports
   - Note: Historical reports go to `archive/reports/`

### Disallowed in docs/ (Should Be Archived)

These file types should **not** remain in `docs/` and should be moved to `archive/`:

- **Historical build reports** (`BUILD-NNN_*.md` older than 30 days) → `archive/reports/`
- **Debug reports** (`DBG-*.md`, `DEBUG_*.md`) → `archive/diagnostics/`
- **Old analysis reports** (`ANALYSIS_*.md`, `*_SUMMARY.md`) → `archive/reports/`
- **Prompts** (`PROMPT_*.md`, `*_PROMPT.md`) → `archive/prompts/`
- **Diagnostic files** (`*_DIAGNOSTIC*.md`) → `archive/diagnostics/`
- **Superseded documentation** (old versions) → `archive/superseded/`

### Intent: docs/ is NOT an Inbox

**Critical principle**: `docs/` is the **authoritative truth source**, not an inbox for accumulating files.

- Files created by Cursor in the repo root should be **routed to archive** by tidy, not moved to docs/
- Only documents that serve as **current, canonical references** belong in docs/
- Historical/completed documents belong in archive/, not docs/

## 3. Archive Directory (archive/)

### Purpose

The `archive/` directory serves two purposes:
1. **Inbox**: Temporary storage for files created by Cursor before tidy classification
2. **History**: Long-term storage for historical artifacts after tidy consolidates them to SOT

### Required Subdirectories

- **archive/plans/** - Implementation plans, phase definitions
- **archive/reports/** - Build reports, analysis summaries, completion reports
- **archive/research/** - Research notes, market analysis, investigations
- **archive/prompts/** - Prompt templates, delegation prompts
- **archive/diagnostics/** - Debug logs, error reports, diagnostic outputs
  - **archive/diagnostics/logs/** - Log files
  - **archive/diagnostics/errors/** - Error dumps and stack traces
- **archive/scripts/** - Archived scripts (old versions, deprecated utilities)
- **archive/superseded/** - Files that have been consolidated into SOT
  - Mirror structure: `superseded/reports/`, `superseded/prompts/`, etc.
- **archive/unsorted/** - Temporary inbox for unclassified files
- **archive/data/** - Archived data files
  - **archive/data/databases/** - Historical database files
    - **archive/data/databases/telemetry_seeds/** - Telemetry seed databases
      - **archive/data/databases/telemetry_seeds/debug/** - Debug telemetry seeds
      - **archive/data/databases/telemetry_seeds/final/** - Final/green telemetry seeds
    - **archive/data/databases/debug_snapshots/** - Debug database snapshots
    - **archive/data/databases/test_artifacts/** - Test database files
    - **archive/data/databases/legacy/** - Legacy/backup databases
    - **archive/data/databases/backups/** - Database backups
    - **archive/data/databases/misc/** - Other databases
- **archive/experiments/** - Archived experiments and research code
  - **archive/experiments/research_code/** - Experimental research code
  - **archive/experiments/research_tracer/** - Research tracer experiments
  - **archive/experiments/tracer_bullet/** - Tracer bullet proofs of concept
- **archive/misc/** - Miscellaneous archived items
  - **archive/misc/root_directories/** - Directories moved from root for manual review

### Workflow

1. **Creation**: Cursor creates files at repo root
2. **Routing**: Tidy routes them to `archive/{bucket}/` based on type
3. **Consolidation**: Tidy consolidates archive markdown into SOT ledgers
4. **Archival**: Consolidated files move to `archive/superseded/`
5. **Retention**: Superseded files retained for auditability, not reprocessed

## 4. Runtime Directory (.autonomous_runs/)

### Purpose

The `.autonomous_runs/` directory contains **runtime artifacts** and **project-specific workspaces**.

### Structure

- **.autonomous_runs/checkpoints/** - Tidy checkpoints (zip backups)
- **.autonomous_runs/autopack/** - **Runtime workspace** (not a project SOT root)
  - Contains runtime artifacts, telemetry, run logs
  - Does NOT require the 6-file SOT structure (intentionally excluded from SOT validation)
  - Main project SOT lives in repo root `docs/`
- **.autonomous_runs/{project-id}/** - Project-specific runtime artifacts
  - Example: `.autonomous_runs/file-organizer-app-v1/`
  - Each project has its own SOT structure under `{project}/docs/`
  - Each project has its own archive under `{project}/archive/`

### Runtime Workspace vs Project Workspace

**Runtime Workspace** (`.autonomous_runs/autopack/`):
- Stores executor runtime artifacts, telemetry, and operational data
- May have `docs/` and `archive/` subdirectories but NOT with the canonical 6-file SOT structure
- Excluded from SOT validation (verifier skips this directory)
- Purpose: execution infrastructure, not source of truth

**Project Workspace** (`.autonomous_runs/{project-id}/`):
- Full project structure with 6-file SOT under `{project}/docs/`
- Subject to SOT validation
- Purpose: self-contained project with its own truth sources

### Project Structure

For each project under `.autonomous_runs/{project}/`:

```
.autonomous_runs/file-organizer-app-v1/
├── docs/                      # Project SOT (6-file structure)
│   ├── PROJECT_INDEX.json
│   ├── BUILD_HISTORY.md
│   ├── DEBUG_LOG.md
│   ├── ARCHITECTURE_DECISIONS.md
│   ├── FUTURE_PLAN.md
│   └── LEARNED_RULES.json
├── archive/                   # Project history
│   ├── plans/
│   ├── reports/
│   ├── research/
│   └── superseded/
├── phases/                    # Phase execution state
├── runs/                      # Run execution logs
└── logs/                      # Runtime logs
```

### Cleanup Policy

The tidy system automatically cleans up `.autonomous_runs/` to prevent clutter:

**Orphaned Logs**:
- Executor logs not contained in run directories are deleted
- Example: `.autonomous_runs/executor.log` (not in a run directory)

**Duplicate Baseline Archives**:
- Only the most recent baseline archive is kept
- Older `baselines_*.zip` files are deleted

**Old Run Directories**:
- Keeps last **10 runs per project** by default
- Only deletes runs older than **7 days** by default
- Run directories are grouped by prefix (e.g., `build-*`, `telemetry-collection-*`)
- Runtime workspaces (`.autonomous_runs/autopack/`) and project directories are never deleted

**Empty Directories**:
- Empty directories are deleted after run cleanup
- Prevents directory tree bloat from old runs

## 5. Scripts Directory (scripts/)

### Purpose

The `scripts/` directory contains **operational scripts** and **tooling**.

### Allowed Subdirectories

- **scripts/tidy/** - Tidy system scripts
  - `tidy_workspace.py`, `run_tidy_all.py`, `autonomous_tidy.py`, etc.
- **scripts/backend/** - Backend-related scripts
- **scripts/frontend/** - Frontend-related scripts
- **scripts/test/** - Test scripts and utilities
- **scripts/utility/** - General utility scripts
- **scripts/temp/** - Temporary/experimental scripts
- **scripts/archive/** - Archived/deprecated scripts
  - **scripts/archive/root_scripts/** - Scripts moved from repo root

### Disallowed

- Random `.py` files not organized into subdirectories
- Documentation files (`.md`) should go to `docs/` or `archive/`, not `scripts/`

## 6. Source Code Directory (src/)

### Purpose

The `src/` directory contains the **application source code**.

### Structure

- **src/autopack/** - Main Python package
  - Core modules: executor, diagnostics, models, etc.
- **src/{other-packages}/** - Additional packages

### Rules

- Only source code belongs here
- No documentation, logs, or temporary files
- Tests should be in `tests/`, not mixed with `src/`

## 7. Tests Directory (tests/)

### Purpose

The `tests/` directory contains **automated tests**.

### Structure

- **tests/autopack/** - Autopack core tests
- **tests/backend/** - Backend tests (FastAPI, database)
- **tests/integration/** - Integration tests
- **tests/fixtures/** - Test fixtures and sample data

### Rules

- Test files follow `test_*.py` naming convention
- Fixtures organized by test domain
- No production code in `tests/`

## 8. Backend/Frontend Directories

### Purpose

Project-specific application code (if applicable).

### Structure

- **backend/** - Backend application code (FastAPI, database, API)
- **frontend/** - Frontend application code (React, UI components)

### Rules

- These directories are project-specific and may not exist for all projects
- Follow standard web application structure conventions
- Configuration and environment files at project root, not in these directories

## 9. Validation Rules

### Root File Validation

Tidy system must:
- **Detect** root files not in allowed list
- **Route** them to appropriate archive buckets or scripts subdirectories
- **Report** any unroutable files (ask user for classification)

### Docs Directory Validation

Tidy system must:
- **Enforce** 6-file SOT presence (error if missing)
- **Allow** only explicitly permitted files and subdirectories
- **Block** creation of new subdirectories not in allowlist
- **Offer** `--docs-reduce-to-sot` mode to move non-SOT files to archive

### Archive Directory Validation

Tidy system must:
- **Create** required subdirectories if missing
- **Consolidate** archive markdown into SOT ledgers
- **Move** consolidated files to `archive/superseded/`
- **Never reprocess** files already in `archive/superseded/`

## 10. Tidy System Behavior

### Default Mode (Conservative)

- Routes root files to archive/scripts
- Does **not** modify docs/ except to append to SOT ledgers
- Consolidates archive/ into SOT
- Creates checkpoints before changes

### Reduction Mode (`--docs-reduce-to-sot`)

- Routes root files to archive/scripts
- **Moves** non-SOT files from docs/ to archive/
- Consolidates archive/ into SOT
- Enforces strict docs/ allowlist

### Safety Guarantees

- **Dry-run by default** - No changes without `--execute`
- **Checkpoint creation** - Zip backup before any moves
- **Git checkpoint** - Optional pre/post git commits
- **Validation** - Block invalid operations, report clearly
- **Idempotency** - Repeated runs should not cause churn

## 11. Version History

- **v1.0 (2026-01-01)**: Initial canonical specification
  - Extracted from README.md and IMPLEMENTATION_PLAN_TIDY_GAP_CLOSURE.md
  - Formalized as single source of truth for workspace organization
  - Defines rules for tidy validation and enforcement

---

**Note**: This specification is the **authoritative reference** for workspace organization. Any tidy scripts, validation tools, or documentation that conflicts with this spec should be updated to match.
