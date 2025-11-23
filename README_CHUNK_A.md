# Chunk A Implementation: Core Run/Phase/Tier Model

This document describes the Chunk A implementation for Autopack, following the v7 autonomous build playbook.

## What Was Implemented

Per the requirements in [cursor_chunk_prompts_v7.md](cursor_chunk_prompts_v7.md), Chunk A implements:

### 1. Database Models

Implemented in [src/autopack/models.py](src/autopack/models.py):

- **Run**: Autonomous build run with lifecycle states per §3 of v7 playbook
  - States: `PLAN_BOOTSTRAP`, `RUN_CREATED`, `PHASE_QUEUEING`, `PHASE_EXECUTION`, `GATE`, `CI_RUNNING`, `SNAPSHOT_CREATED`, `DONE_SUCCESS`, `DONE_FAILED_*`
  - Budgets per §9.1: token_cap (5M default), max_phases (25 default), max_duration_minutes (120 default)
  - Tracks tokens used, CI runs, issues

- **Tier**: Logical grouping of phases per §4.2
  - States: `PENDING`, `IN_PROGRESS`, `COMPLETE`, `FAILED`, `SKIPPED`
  - Tier-level budgets per §9.2
  - Cleanliness tracking per §10.3

- **Phase**: Individual unit of work per §4.1
  - States: `QUEUED`, `EXECUTING`, `GATE`, `CI_RUNNING`, `COMPLETE`, `FAILED`, `SKIPPED`
  - Classification: task_category, complexity, builder_mode
  - Per-phase budgets per §9.3

### 2. API Endpoints

Implemented in [src/autopack/main.py](src/autopack/main.py):

- **POST /runs/start**: Create run with tiers and phases
  - Accepts RunStartRequest with run metadata, tier list, phase list
  - Creates DB records and initializes file layout
  - Returns full run details with nested tiers and phases

- **GET /runs/{run_id}**: Retrieve run details
  - Returns complete run state including all tiers and phases
  - Used for inspection during and after runs

- **POST /runs/{run_id}/phases/{phase_id}/update_status**: Update phase status
  - Updates phase state and optional metrics (builder_attempts, tokens_used, issues)
  - Updates corresponding phase summary file
  - Basic state machine implementation (full logic in later chunks)

### 3. File Layout

Implemented in [src/autopack/file_layout.py](src/autopack/file_layout.py):

File structure under `.autonomous_runs/{run_id}/`:
```
.autonomous_runs/
└── {run_id}/
    ├── run_summary.md
    ├── tiers/
    │   ├── tier_00_{name}.md
    │   ├── tier_01_{name}.md
    │   └── ...
    ├── phases/
    │   ├── phase_00_{phase_id}.md
    │   ├── phase_01_{phase_id}.md
    │   └── ...
    └── issues/
        (prepared for Chunk B)
```

Per §3 and §5 of v7 playbook, the Supervisor maintains these artefacts for:
- Post-run inspection
- Human review of summaries
- Issue tracking (Chunk B)
- Promotion decisions (Chunk E)

### 4. Testing

Comprehensive unit tests in `tests/`:

- **test_models.py**: Database model tests
  - Run/Tier/Phase creation
  - Relationships and cascades
  - State transitions

- **test_api.py**: API endpoint tests
  - Run creation and retrieval
  - Phase status updates
  - Error handling
  - File layout verification

- **test_file_layout.py**: File system tests
  - Directory creation
  - Summary file generation
  - Path handling

### 5. Probe Script

[scripts/autonomous_probe_run_state.sh](scripts/autonomous_probe_run_state.sh):

Automated probe that:
1. Creates a dummy run with 2 tiers and 3 phases
2. Verifies DB entries exist
3. Verifies file layout was created
4. Updates phase status
5. Advances phase through state machine
6. Validates final state

Per Chunk A requirements, this probe:
- Does not touch git
- Uses only Supervisor APIs
- Validates end-to-end functionality

## Running the Implementation

### Prerequisites

- Python 3.11+
- Docker and docker-compose (for Postgres)

### Setup

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Start Docker services
docker-compose up -d

# Or use make
make install
make docker-up
```

### Run Unit Tests

```bash
# Run all tests
pytest tests/ -v

# Or use make
make test
```

### Run Probe Script

```bash
# Ensure Docker is running
docker-compose up -d

# Run probe
bash scripts/autonomous_probe_run_state.sh

# Or use make
make probe
```

## File Structure

```
autopack/
├── src/autopack/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── models.py            # Database models
│   ├── schemas.py           # Pydantic schemas
│   ├── database.py          # DB setup
│   ├── config.py            # Configuration
│   └── file_layout.py       # File system utilities
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   ├── test_models.py       # Model tests
│   ├── test_api.py          # API tests
│   └── test_file_layout.py  # File layout tests
├── scripts/
│   └── autonomous_probe_run_state.sh
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── Makefile
```

## Next Steps

Chunk A is now complete. Next chunks will implement:

- **Chunk B**: Phase issues, run issue index, and project backlog
- **Chunk C**: StrategyEngine, rules, and high-risk mapping
- **Chunk D**: Builder and Auditor integration
- **Chunk E**: CI profiles, preflight gate, and promotion
- **Chunk F**: Operational calibration and observability

## Compliance with v7 Playbook

This implementation follows:

- §2: Roles and Responsibilities (Supervisor)
- §3: Deterministic Run Lifecycle (states and transitions)
- §4: Phases, Tiers, and Run Scope
- §9: Cost Controls and Budgets
- §10.3: Tier cleanliness (preparation)

All invariants from §12 are enforced:
- No human in the loop (API-only control)
- Deterministic state progression
- Integration-only writes (prepared for Chunk D)
- Structured recording of state
