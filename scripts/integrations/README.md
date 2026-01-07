# Autopack Integration Modules

This directory contains integration modules for connecting AI agents (Cursor and Codex) with the Autopack orchestrator.

## Overview

Per the v7 autonomous build playbook, Autopack orchestrates three types of agents:

1. **Supervisor** - Orchestrates the entire build process
2. **Builder (Cursor)** - Implements code changes for each phase
3. **Auditor (Codex)** - Reviews Builder output for quality and security

## Modules

### `cursor_integration.py` - Builder Integration

Provides `CursorBuilder` class for integrating Cursor AI as the Builder agent.

**Usage:**
```python
from cursor_integration import CursorBuilder

builder = CursorBuilder(api_url="http://localhost:8000")
result = builder.execute_phase(
    run_id="my-run",
    phase_id="P1",
    task_description="Implement user authentication"
)
```

**Key Methods:**
- `execute_phase()` - Execute a phase using Cursor
- `submit_builder_result()` - Submit results to Autopack API

### `codex_integration.py` - Auditor Integration

Provides `CodexAuditor` class for integrating Codex AI as the Auditor agent.

**Usage:**
```python
from codex_integration import CodexAuditor

auditor = CodexAuditor(api_url="http://localhost:8000")
result = auditor.review_phase(
    run_id="my-run",
    phase_id="P1"
)
```

**Key Methods:**
- `request_audit()` - Request audit from Autopack
- `review_phase()` - Perform code review using Codex
- `submit_auditor_result()` - Submit review results to Autopack

### `supervisor.py` - Orchestration Loop

Provides `Supervisor` class that coordinates Builder and Auditor to execute autonomous builds.

**Usage:**
```python
from supervisor import Supervisor

supervisor = Supervisor(api_url="http://localhost:8000")

tiers = [{"tier_id": "T1", "tier_index": 0, "name": "Tier 1", "description": "..."}]
phases = [{"phase_id": "P1", "phase_index": 0, "tier_id": "T1", ...}]

result = supervisor.run_autonomous_build(
    run_id="my-build",
    tiers=tiers,
    phases=phases
)
```

**Key Methods:**
- `create_run()` - Create a new run via Autopack API
- `execute_phase()` - Execute a phase (Builder + Auditor workflow)
- `run_autonomous_build()` - Run a complete autonomous build
- `monitor_run()` - Monitor a running build
- `get_run_summary()` - Get comprehensive run summary

## Workflow

The typical autonomous build workflow:

```
1. Supervisor creates run via Autopack API
   ↓
2. For each phase:
   ├─ Supervisor dispatches to Builder (Cursor)
   ├─ Builder implements changes and submits result
   ├─ Supervisor dispatches to Auditor (Codex)
   ├─ Auditor reviews and submits recommendation
   └─ Supervisor decides: approve, retry, or escalate
   ↓
3. Supervisor gets final summary
```

## Integration Status

⚠️ **Current Status: Stub Implementation**

The modules in this directory are **integration stubs** that demonstrate the API patterns and workflow. They include:

- ✅ Correct API endpoint usage
- ✅ Proper data schemas per v7 playbook
- ✅ Orchestration workflow logic
- ⚠️ Simulated AI agent responses (not real Cursor/Codex)

## Next Steps for Production

To make these integrations production-ready:

### 1. Cursor Integration
- [ ] Implement actual Cursor API/CLI invocation
- [ ] Capture real diffs and file changes
- [ ] Track actual token usage
- [ ] Handle Cursor errors and retries

### 2. Codex Integration
- [ ] Implement actual Codex API invocation
- [ ] Perform real code analysis
- [ ] Generate meaningful review notes
- [ ] Detect security issues and code smells

### 3. Supervisor
- [ ] Add retry logic for failed phases
- [ ] Implement state machine transitions
- [ ] Add budget monitoring and limits
- [ ] Handle concurrent phase execution
- [ ] Add comprehensive error handling

## Testing Integration

To test the integration stubs:

```bash
# Ensure Autopack API is running
docker-compose up -d

# Test Cursor integration
python scripts/integrations/cursor_integration.py

# Test Codex integration
python scripts/integrations/codex_integration.py

# Test Supervisor
python scripts/integrations/supervisor.py
```

## API Endpoints Used

These integrations use the following Autopack API endpoints:

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `POST /runs/start` | Create run | Supervisor |
| `POST /runs/{run_id}/phases/{phase_id}/builder_result` | Submit Builder result | Builder |
| `POST /runs/{run_id}/phases/{phase_id}/auditor_request` | Request audit | Auditor |
| `POST /runs/{run_id}/phases/{phase_id}/auditor_result` | Submit review | Auditor |
| `GET /reports/run_summary/{run_id}` | Get run summary | Supervisor |
| `GET /metrics/runs` | Get run metrics | Supervisor |

## Architecture Diagram

```
┌─────────────┐
│ Supervisor  │
│   (Python)  │
└──────┬──────┘
       │
       ├───────────┐
       │           │
       ▼           ▼
┌─────────┐  ┌──────────┐
│ Builder │  │ Auditor  │
│(Cursor) │  │ (Codex)  │
└────┬────┘  └────┬─────┘
     │            │
     └────┬───────┘
          │
          ▼
    ┌──────────┐
    │ Autopack │
    │   API    │
    └──────────┘
```

## Dependencies

```bash
pip install requests
```

## Configuration

All modules accept an `api_url` parameter:

```python
# Development (default)
api_url = "http://localhost:8000"

# Production
api_url = "https://autopack.example.com"
```

## Error Handling

All API calls use `response.raise_for_status()` to raise exceptions on HTTP errors. In production, add proper error handling:

```python
try:
    result = builder.execute_phase(...)
except requests.HTTPError as e:
    # Handle API errors
    print(f"API error: {e}")
except Exception as e:
    # Handle other errors
    print(f"Unexpected error: {e}")
```

## Logging

Consider adding structured logging in production:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Executing phase {phase_id}")
```

---

**Status:** Integration stubs ready for production implementation
**Last Updated:** 2025-11-23
