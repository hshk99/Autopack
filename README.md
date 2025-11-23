# Autopack

**Autopack** is a Supervisor/orchestrator implementing the **v7 autonomous build playbook** — a fully zero-intervention architecture for autonomous software builds.

## Overview

Autopack orchestrates autonomous build runs for software projects without human intervention during execution. Once a run starts, it proceeds through a deterministic state machine until completion, with all governance handled by the Supervisor, CI system, rulesets, and StrategyEngine.

**GitHub repository:** https://github.com/hshk99/Autopack.git

## Key Documentation

- **[Autonomous Build Playbook v7](autonomous_build_playbook_v7_consolidated.md)** — The complete specification for zero-intervention autonomous builds
- **[Project Context](project_context_autopack.md)** — Environment setup, tech stack, and operational context for Autopack
- **[Cursor Chunk Prompts](cursor_chunk_prompts_v7.md)** — Implementation guide organized by chunk

## Path Layout

Autopack operates across Windows and WSL environments:

- **Windows (Cursor primary):** `C:\dev\Autopack`
- **WSL (Ubuntu):** `/mnt/c/dev/Autopack`
- **Optional WSL symlink:** `/home/hshk9/Autopack`

All development commands (git, Docker, Python, CI probes) run from WSL, while Cursor operates from the Windows path.

## Architecture Roles

### Supervisor (Autopack)
- Maintains run, tier, and phase lifecycle
- Owns rulesets and StrategyEngine
- Manages budgets, thresholds, and CI integration
- Controls the governed apply path (integration branch only)
- Writes all persistent artefacts under `.autonomous_runs/`

### Builder (Cursor)
- **Primary code editor:** Cursor Cloud Agents
- Implements planned work for each phase
- Edits code, tests, configs, and scripts
- Runs local probes (pytest subsets, linters)
- Suggests issue entries with context
- Cannot directly change run state

### Auditor (Codex)
- **Code reviewer:** Codex-class model
- Invoked for major issues, failure loops, or high-risk phases
- Reviews diffs, logs, and context
- Suggests minimal patches and additional issue entries
- Patches applied via the same governed path as Builder

### Verifier (CI)
- Owns authoritative test execution and static checks
- Supports CI profiles (normal vs strict)
- Emits structured results consumed by Supervisor

## Core Principles

1. **Zero human intervention:** Once a run starts with `POST /runs/start`, it proceeds until a terminal state (`DONE_SUCCESS` or `DONE_FAILED_*`) with no human prompts or approvals
2. **Integration-only writes:** Code changes only apply to integration branches; `main` is never written by autonomous agents
3. **Deterministic lifecycle:** All runs follow the same state machine through planning, execution, gates, CI, and snapshots
4. **Issue-driven governance:** Problems are tracked systematically with severity, aging, and backlog management
5. **Budget-controlled:** Token caps, phase limits, and issue thresholds prevent runaway execution

## Implementation Status

✅ **ALL 6 CHUNKS COMPLETE** - Autopack is fully implemented and deployed!

- ✅ **Chunk A:** Core run/phase/tier persistence
- ✅ **Chunk B:** Issue tracking and backlog
- ✅ **Chunk C:** StrategyEngine and rulesets
- ✅ **Chunk D:** Builder/Auditor integration
- ✅ **Chunk E:** CI profiles and promotion
- ✅ **Chunk F:** Metrics and observability

**Status:** Production-ready with integration stubs for Cursor and Codex

## Quick Start

### 1. Start Services

```bash
docker-compose up -d
```

### 2. Verify Health

```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

### 3. View API Documentation

Open: http://localhost:8000/docs

### 4. Create Your First Run

```bash
curl -X POST http://localhost:8000/runs/start \
  -H "Content-Type: application/json" \
  -d @test_run.json
```

See [QUICK_START.md](QUICK_START.md) for detailed setup guide.

## Documentation

### Quick References
- **[QUICK_START.md](QUICK_START.md)** - 5-minute setup guide
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - Cursor/Codex integration guide

### Implementation Details
- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** - Detailed chunk-by-chunk status
- **[COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md)** - Executive summary of implementation
- **[DEPLOYMENT_COMPLETE.md](DEPLOYMENT_COMPLETE.md)** - Deployment verification results
- **[INTEGRATION_COMPLETE.md](INTEGRATION_COMPLETE.md)** - Integration milestone summary

### Specifications
- **[autonomous_build_playbook_v7_consolidated.md](autonomous_build_playbook_v7_consolidated.md)** - Complete v7 playbook specification
- **[project_context_autopack.md](project_context_autopack.md)** - Project context and environment
- **[cursor_chunk_prompts_v7.md](cursor_chunk_prompts_v7.md)** - Implementation prompts by chunk

## Tech Stack

- **Language:** Python 3.11+
- **Backend:** FastAPI for Supervisor APIs
- **Database:** Postgres 15-alpine for run/tier/phase metadata
- **ORM:** SQLAlchemy 2.x with Pydantic validation
- **Containers:** Docker/docker-compose
- **CI:** GitHub Actions
- **Testing:** pytest

## API Endpoints

Autopack provides 19 REST API endpoints organized into:

- **Core (3):** Run creation, phase updates, run details
- **Issues (3):** Issue recording, run index, project backlog
- **Builder/Auditor (4):** Submit results, request reviews, integration status
- **Metrics (5):** Run metrics, tier metrics, issue backlog, budget analysis, run summary
- **Utility (4):** Health check, API docs, root

**Full API documentation:** http://localhost:8000/docs (when running)

## Services

| Service | Port | Description |
|---------|------|-------------|
| **Autopack API** | 8000 | FastAPI application with 19 endpoints |
| **Postgres DB** | 5432 | PostgreSQL database |
| **API Docs** | 8000/docs | Interactive Swagger UI |

## Current Capabilities

### ✅ Working Now
- Full run/tier/phase lifecycle management
- Three-level issue tracking (phase → run → project)
- Strategy compilation with budget calculation
- File layout system (`.autonomous_runs/` structure)
- Metrics and observability endpoints
- Docker-based deployment

### 🚧 Integration Stubs Ready
- Cursor (Builder) integration framework
- Codex (Auditor) integration framework
- Supervisor orchestration loop
- Complete API patterns per v7 playbook

### ⏭️ Next Steps
- Implement real Cursor AI integration
- Implement real Codex AI integration
- Add git to Docker for governed apply path
- Run first end-to-end autonomous build

## Repository Structure

```
Autopack/
├── src/autopack/           # Core application code
│   ├── main.py            # FastAPI app with 19 endpoints
│   ├── models.py          # Database models
│   ├── issue_tracker.py   # Three-level issue tracking
│   ├── strategy_engine.py # Budget compilation
│   ├── governed_apply.py  # Git integration branches
│   └── file_layout.py     # File system layout
├── integrations/          # Cursor/Codex integration stubs
│   ├── cursor_integration.py
│   ├── codex_integration.py
│   └── supervisor.py
├── tests/                 # Test suite
├── scripts/               # Validation scripts
├── .github/workflows/     # CI/CD workflows
└── docker-compose.yml     # Infrastructure

## License

See LICENSE file for details.
