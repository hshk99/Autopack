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

## Getting Started

See the [Cursor Chunk Prompts](cursor_chunk_prompts_v7.md) for the staged implementation plan:

- **Chunk A:** Core run/phase/tier persistence
- **Chunk B:** Issue tracking and backlog
- **Chunk C:** StrategyEngine and rulesets
- **Chunk D:** Builder/Auditor integration
- **Chunk E:** CI profiles and promotion
- **Chunk F:** Metrics and observability

## Tech Stack

- **Language:** Python 3.11+
- **Backend:** FastAPI for Supervisor APIs
- **Database:** Postgres for run/tier/phase metadata
- **Containers:** Docker/docker-compose
- **CI:** GitHub Actions
- **Vector DB (optional):** Qdrant for retrieval-augmented memory

## License

See LICENSE file for details.
