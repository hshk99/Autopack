# Autopack

Autopack is an **autonomous project factory** — a system that transforms rough project ideas into production-ready, monetizable applications with minimal human intervention.

**Core capability**: Idea → Research → Planning → Build → Document → Deploy → Monetize

## Vision: Fully Autonomous Project Creation

Autopack's ultimate goal is to take a rough project description (e.g., "Automated Etsy image upload with AI generation") and autonomously:

1. **Research** — Market analysis, competitive landscape, technical feasibility, API availability, legal/policy constraints
2. **Clarify** — Ask targeted questions to fill gaps in the specification, propose optimal tech stacks with pros/cons
3. **Plan** — Generate comprehensive intention anchors, architecture decisions, and phased build plans
4. **Build** — Execute the plan with governance gates, quality controls, and safety boundaries
5. **Iterate** — Learn from build history, improve processes, accumulate reusable patterns

**The end product must be**: Not just "working" but intricate, sophisticated, comprehensive — production-grade applications suitable for monetization.

### Current State vs. Ideal State

| Capability | Current | Target |
|------------|---------|--------|
| **Research Infrastructure** | ✅ Exists (agents, frameworks, discovery) | Wire to project bootstrap |
| **Intent Clarification** | ✅ `validate_pivot_completeness()` exists | Interactive Q&A loop |
| **Research → Anchor Pipeline** | ❌ Missing | Auto-generate anchors from research |
| **Tech Stack Proposal** | ❌ Missing | Propose APIs, MCPs, frameworks with pros/cons |
| **Gap Scanner** | ✅ Complete | Continue improving |
| **Plan Proposer** | ✅ Complete | Integrate research insights |
| **Autonomous Execution** | ✅ Core loop works | Expand to full project lifecycle |

**Roadmap**: See `docs/IMPLEMENTATION_PLAN_RESEARCH_TO_ANCHOR_PIPELINE.md`

## How this repo is meant to be used (especially by LLMs)

This repo is structured so that **LLMs (Cursor / Claude / etc.) should rely on SOT ledgers** as the canonical, machine-consumable "memory":

- `docs/BUILD_HISTORY.md`: what changed and what was verified
- `docs/DEBUG_LOG.md`: failures → root cause → fix → verification
- `docs/ARCHITECTURE_DECISIONS.md`: durable rationale ("why")

`README.md` intentionally stays short to avoid stale build journals and "two truths". The navigation hub is `docs/INDEX.md`.

### "One stream" intention flow (idea → research → plan → build → tidy → memory → reuse)

Autopack is designed so that high-signal information **survives** and becomes reusable:

- **Idea intake** — Raw project descriptions are parsed and queued for research
- **Research phase** — Market analysis, competitive intelligence, technical feasibility gathered
- **Anchor generation** — Research findings map to 8 pivot intention types (NorthStar, Safety, Evidence, Scope, Budget, Memory, Governance, Parallelism)
- **Planning / execution artifacts** (run/tier/phase outcomes, summaries, telemetry) are produced during runs
- **Documentation phase** — Generates comprehensive API docs, architecture guides, user manuals, and examples
- **Tidy consolidates** durable learnings into the SOT ledgers above (append-only)
- **Optional runtime retrieval**: the executor can index/retrieve SOT chunks via `MemoryService` (vector memory: Qdrant/FAISS) when enabled:
  - `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true`
  - `AUTOPACK_SOT_RETRIEVAL_ENABLED=true`

Note: SOT→DB sync (`scripts/tidy/sot_db_sync.py`) exists as a derived index (`sot_entries`) for DB/Qdrant sync workflows; **runtime decisioning currently uses vector memory retrieval**, not DB reads from `sot_entries`.

### Hybrid Mode: Claude Code Agents + Autopack

While the research→anchor pipeline is being built, Autopack supports a **hybrid workflow**:

1. **Claude Code agents** handle research and anchor generation (30%)
2. **Autopack** handles build execution with governance (70%)
3. **File-based handoff** via `READY_FOR_AUTOPACK` marker files

See `docs/IMPLEMENTATION_PLAN_CLAUDE_AGENTS_RESEARCH_BRIDGE.md` for the agent setup.

### Project Isolation Architecture

**Bootstrapped projects are created in a separate directory** (`AUTOPACK_PROJECTS_ROOT`) to prevent:
- Lint conflicts between tool and project code
- CI contamination during parallel development
- Git noise from mixed commits

```
C:\dev\Autopack\           # The tool (this repo)
C:\dev\AutopackProjects\   # Bootstrapped projects (separate)
    └── {project-name}\
        ├── .autopack\     # Project-specific Autopack data
        ├── src\           # Project source code
        └── intention_anchor.yaml
```

**Configuration**: Set `AUTOPACK_PROJECTS_ROOT` environment variable (default: `C:\dev\AutopackProjects`)

See [docs/PROJECT_ISOLATION_ARCHITECTURE.md](docs/PROJECT_ISOLATION_ARCHITECTURE.md) for rationale and [docs/MIGRATION_PLAN_PROJECT_ISOLATION.md](docs/MIGRATION_PLAN_PROJECT_ISOLATION.md) for migration steps.

**Full historical changelog**: `docs/CHANGELOG.md` (version history and feature announcements)

## Quickstart

**New developers**: Get Autopack running in <15 minutes:
- **[Developer Quickstart Guide](docs/QUICKSTART.md)** - Step-by-step setup for local development

**Already familiar?** Quick commands:
- **Run the API (dev)**:
  - `PYTHONPATH=src python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000`
- **Run an executor**:
  - `python src/autopack/autonomous_executor.py --run-id my-run`

## Docs (start here)

- **Docs index (navigation hub)**: `docs/INDEX.md`
- **Build ledger (authoritative)**: `docs/BUILD_HISTORY.md`
- **Debug ledger (authoritative)**: `docs/DEBUG_LOG.md`
- **Architecture decisions (authoritative)**: `docs/ARCHITECTURE_DECISIONS.md`
- **Changelog (historical ledger)**: `docs/CHANGELOG.md`
- **Reliability track (P0 + P1)**: `docs/P0_RELIABILITY_DECISIONS.md`
- **Next major roadmap (universal autonomy + safe parallelism)**: `docs/IMPLEMENTATION_PLAN_PIVOT_INTENTIONS_AUTONOMY_PARALLELISM.md`

## Operator Guides

- **Memory Service Production Guide**: [docs/MEMORY_SERVICE_OPERATOR_GUIDE.md](docs/MEMORY_SERVICE_OPERATOR_GUIDE.md) - Comprehensive guide for operating the vector memory service (Qdrant/FAISS, setup, troubleshooting, performance tuning)

## Project Status

**Version**: 0.5.1

**Distribution intent**: Autopack is **for personal/internal use only** (not distributed). No external contributions are accepted. Projects built using Autopack **may be published and monetized**; downstream projects must implement their own security posture (threat modeling, secure hosting, release pipeline, monitoring) appropriate to their distribution model.

<!-- SOT_SUMMARY_START -->
**Last Updated**: 2026-01-30 15:08

- **Builds Completed**: 214 (includes multi-phase builds, 187 unique)
- **Latest Build**: BUILD-178: Pivot Intentions v2 + Gap Taxonomy + Autonomy Loop - Phases 0-5 [OK]
- **Architecture Decisions**: 49
- **Debugging Sessions**: 86

*Auto-generated by Autopack Tidy System*
<!-- SOT_SUMMARY_END -->

## CI-Efficient Development

Autopack uses a **3-gate CI test strategy** with 4,901 core tests that must pass. To enable fast, efficient development:

- **Path Filtering**: CI automatically skips irrelevant jobs based on changed files
- **Test Markers**: `aspirational`, `research`, and `legacy_contract` tests are non-blocking
- **Parallel Execution**: pytest-xdist reduces test time by 50% (PR-INFRA-1)
- **Smart Pre-flight**: Local targeted testing with `scripts/preflight_smart.py` (PR-INFRA-2)
- **Comprehensive Scans**: CI-categorized improvement workflow (PR-INFRA-3)

**Quick Reference**: [docs/CI_EFFICIENT_DEVELOPMENT.md](docs/CI_EFFICIENT_DEVELOPMENT.md) - Choose the right workflow for your task (docs/frontend/backend/refactoring/comprehensive scan)

**For comprehensive improvement scans**: Use [docs/COMPREHENSIVE_SCAN_UNIVERSAL_PROMPT.md](docs/COMPREHENSIVE_SCAN_UNIVERSAL_PROMPT.md) to categorize improvements by CI impact (A/B/C/D/E) and execute in parallel waves. Reduces CI time from 450+ min to ~125 min (72% reduction).

**Full Strategy**: [docs/COMPREHENSIVE_SCAN_WORKFLOW.md](docs/COMPREHENSIVE_SCAN_WORKFLOW.md)
#   C I   t r i g g e r 
 
 
