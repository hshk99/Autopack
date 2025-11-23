# Autopack Integration Guide

This guide explains how to integrate Cursor (Builder) and Codex (Auditor) with Autopack for autonomous builds.

---

## Overview

Autopack provides a REST API that orchestrates autonomous builds by coordinating:

1. **Supervisor** - Orchestration loop (your code)
2. **Builder (Cursor)** - AI agent that implements code changes
3. **Auditor (Codex)** - AI agent that reviews Builder output

The `integrations/` directory contains Python integration stubs that demonstrate the API patterns.

---

## Quick Start

### 1. Ensure Autopack is Running

```bash
# Start services
docker-compose up -d

# Verify API is healthy
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

### 2. Install Integration Dependencies

```bash
cd integrations
pip install -r requirements.txt
```

### 3. Review Integration Stubs

The integration modules are **stubs** that demonstrate the API patterns but don't invoke real AI agents:

- `cursor_integration.py` - Builder integration stub
- `codex_integration.py` - Auditor integration stub
- `supervisor.py` - Orchestration loop stub

---

## Integration Architecture

```
┌──────────────┐
│  Supervisor  │  ← Your orchestration code
│   (Python)   │     Creates runs, dispatches work
└──────┬───────┘
       │
       ├─────────────┬──────────────┐
       │             │              │
       ▼             ▼              ▼
┌──────────┐  ┌───────────┐  ┌──────────┐
│ Builder  │  │  Auditor  │  │ Autopack │
│ (Cursor) │  │  (Codex)  │  │   API    │
└────┬─────┘  └─────┬─────┘  └────┬─────┘
     │              │              │
     └──────────────┴──────────────┘
              API Calls
```

---

## API Workflow

### Creating a Run

```bash
curl -X POST http://localhost:8000/runs/start \
  -H "Content-Type: application/json" \
  -d '{
    "run": {
      "run_id": "my-run",
      "safety_profile": "normal",
      "run_scope": "incremental"
    },
    "tiers": [{
      "tier_id": "T1",
      "tier_index": 0,
      "name": "Tier 1",
      "description": "First tier"
    }],
    "phases": [{
      "phase_id": "P1",
      "phase_index": 0,
      "tier_id": "T1",
      "name": "Phase 1",
      "description": "First phase",
      "task_category": "feature_scaffolding",
      "complexity": "low",
      "builder_mode": "compose"
    }]
  }'
```

### Builder Workflow (Cursor Integration)

**Step 1:** Cursor implements the phase

```python
from integrations import CursorBuilder

builder = CursorBuilder(api_url="http://localhost:8000")

# In production, this would invoke real Cursor AI
# For now, it's a stub that simulates Cursor's output
result = builder.execute_phase(
    run_id="my-run",
    phase_id="P1",
    task_description="Add health check endpoint"
)
```

**Step 2:** Builder submits result to Autopack

```bash
curl -X POST http://localhost:8000/runs/my-run/phases/P1/builder_result \
  -H "Content-Type: application/json" \
  -d '{
    "phase_id": "P1",
    "run_id": "my-run",
    "patch_content": "diff --git...",
    "files_changed": ["src/api.py"],
    "lines_added": 10,
    "lines_removed": 2,
    "builder_attempts": 1,
    "tokens_used": 5000,
    "duration_minutes": 1.5,
    "status": "success",
    "notes": "Added /health endpoint"
  }'
```

### Auditor Workflow (Codex Integration)

**Step 1:** Request audit from Autopack

```bash
curl -X POST http://localhost:8000/runs/my-run/phases/P1/auditor_request
```

**Step 2:** Codex reviews the code

```python
from integrations import CodexAuditor

auditor = CodexAuditor(api_url="http://localhost:8000")

# In production, this would invoke real Codex AI
# For now, it's a stub that simulates Codex's review
result = auditor.review_phase(
    run_id="my-run",
    phase_id="P1"
)
```

**Step 3:** Auditor submits review

```bash
curl -X POST http://localhost:8000/runs/my-run/phases/P1/auditor_result \
  -H "Content-Type: application/json" \
  -d '{
    "phase_id": "P1",
    "run_id": "my-run",
    "review_notes": "Code looks good, no issues found",
    "issues_found": [],
    "suggested_patches": [],
    "auditor_attempts": 1,
    "tokens_used": 3000,
    "recommendation": "approve",
    "confidence": "high"
  }'
```

### Monitoring Progress

```bash
# Get run summary
curl http://localhost:8000/reports/run_summary/my-run | jq

# Get run metrics
curl http://localhost:8000/metrics/runs | jq

# Get tier metrics
curl http://localhost:8000/metrics/tiers/my-run | jq
```

---

## Production Integration

To make this production-ready, you need to:

### 1. Implement Real Cursor Integration

Replace the stub in `integrations/cursor_integration.py` with real Cursor invocation:

```python
def execute_phase(self, run_id, phase_id, task_description):
    # TODO: Replace this with real Cursor API/CLI invocation
    # Example (pseudo-code):
    # cursor_response = cursor_api.execute(
    #     prompt=task_description,
    #     workspace=workspace_path
    # )
    # patch_content = cursor_response.get_diff()
    # tokens_used = cursor_response.token_count

    # Then submit to Autopack
    return self.submit_builder_result(...)
```

### 2. Implement Real Codex Integration

Replace the stub in `integrations/codex_integration.py` with real Codex invocation:

```python
def review_phase(self, run_id, phase_id):
    # TODO: Replace this with real Codex API invocation
    # Example (pseudo-code):
    # codex_response = codex_api.review(
    #     code=diff_content,
    #     checks=["security", "quality", "style"]
    # )
    # issues = codex_response.get_issues()
    # recommendation = codex_response.get_recommendation()

    # Then submit to Autopack
    return self.submit_auditor_result(...)
```

### 3. Implement Supervisor Logic

The `integrations/supervisor.py` provides the orchestration pattern, but you'll need to add:

- Retry logic for failed phases
- Budget monitoring
- State machine transitions
- Error handling
- Logging and observability

---

## Known Limitations

### Docker Environment

The current Docker setup does NOT support the Builder/Auditor endpoints that involve git operations (`governed_apply.py`). This is because:

1. Git is not installed in the Docker container
2. The container doesn't have access to the host's git repository
3. The governed apply path requires git commands

**Workaround for Testing:**
- Use the metrics and reporting endpoints (these work)
- Test Builder/Auditor endpoints outside Docker (direct Python API)
- Or add git to the Docker container and mount the repository

### Git Integration Branches

The `governed_apply.py` module creates integration branches like `autonomous/{run_id}` for applying patches. This requires:

- Git installed and configured
- Write access to the repository
- Proper git credentials

For production, ensure your deployment environment has git access.

---

## Testing Integration Stubs

You can test the integration stubs (they simulate AI responses):

```bash
# Note: Builder/Auditor endpoints won't work in Docker due to git dependency
# Use these tests outside Docker or configure git in container

cd integrations

# Test Cursor integration (will fail with git error in Docker)
python cursor_integration.py

# Test Codex integration (will fail with git error in Docker)
python codex_integration.py

# Test Supervisor (will fail with git error in Docker)
python supervisor.py
```

**Alternative:** Test endpoints that don't require git:

```bash
# These work in Docker:
curl http://localhost:8000/health
curl http://localhost:8000/metrics/runs
curl http://localhost:8000/reports/run_summary/demo-run-002
```

---

## API Endpoints Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/runs/start` | POST | Create new run |
| `/runs/{run_id}` | GET | Get run details |
| `/runs/{run_id}/phases/{phase_id}/builder_result` | POST | Submit Builder result |
| `/runs/{run_id}/phases/{phase_id}/auditor_request` | POST | Request Auditor review |
| `/runs/{run_id}/phases/{phase_id}/auditor_result` | POST | Submit Auditor review |
| `/runs/{run_id}/integration_status` | GET | Get integration branch status |
| `/metrics/runs` | GET | Get run metrics |
| `/metrics/tiers/{run_id}` | GET | Get tier metrics |
| `/reports/issue_backlog_summary` | GET | Get issue backlog |
| `/reports/budget_analysis` | GET | Get budget failures |
| `/reports/run_summary/{run_id}` | GET | Get comprehensive summary |

Full API documentation: http://localhost:8000/docs

---

## Environment Variables

Configure integration via environment variables:

```bash
# Autopack API URL
export AUTOPACK_API_URL="http://localhost:8000"

# Cursor configuration (when implementing real integration)
export CURSOR_API_KEY="your-cursor-api-key"
export CURSOR_WORKSPACE="/path/to/workspace"

# Codex configuration (when implementing real integration)
export CODEX_API_KEY="your-codex-api-key"
export CODEX_MODEL="gpt-4"
```

---

## Example: Complete Autonomous Build

```python
from integrations import Supervisor

# Create supervisor
supervisor = Supervisor(api_url="http://localhost:8000")

# Define build structure
tiers = [
    {"tier_id": "T1", "tier_index": 0, "name": "Foundation", "description": "Core features"}
]

phases = [
    {
        "phase_id": "P1",
        "phase_index": 0,
        "tier_id": "T1",
        "name": "Add Authentication",
        "description": "Implement JWT authentication",
        "task_category": "feature_scaffolding",
        "complexity": "medium",
        "builder_mode": "compose"
    }
]

# Run autonomous build
result = supervisor.run_autonomous_build(
    run_id="auth-feature-001",
    tiers=tiers,
    phases=phases,
    safety_profile="normal"
)

print(f"Build completed: {result}")
```

---

## Troubleshooting

### Error: "500 Internal Server Error" on builder_result

This happens because git is not available in the Docker container. To fix:

**Option 1:** Test outside Docker
```bash
# Run API directly (not in Docker)
cd src
uvicorn autopack.main:app --reload
```

**Option 2:** Add git to Docker container

Edit `Dockerfile`:
```dockerfile
RUN apk add --no-cache git
```

Then rebuild:
```bash
docker-compose down
docker-compose up -d --build
```

### Error: "Run {run_id} not found"

Make sure you created the run first:
```bash
curl -X POST http://localhost:8000/runs/start -d '...'
```

### Error: "Connection refused"

Ensure Autopack API is running:
```bash
docker-compose ps
curl http://localhost:8000/health
```

---

## Next Steps

1. ✅ Integration stubs created
2. ⏭️ Implement real Cursor integration
3. ⏭️ Implement real Codex integration
4. ⏭️ Add production error handling
5. ⏭️ Add monitoring and logging
6. ⏭️ Configure git in deployment environment
7. ⏭️ Run first end-to-end autonomous build

---

**Status:** Integration stubs ready, production implementation needed
**Last Updated:** 2025-11-23
