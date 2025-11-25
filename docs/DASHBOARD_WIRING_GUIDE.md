# Dashboard Integration & Wire-Up Guide

**Version**: 1.0
**Last Updated**: 2025-11-25
**Status**: Ready for integration

---

## Overview

This guide explains how to integrate the completed dashboard components into your Autopack execution flow.

### What's Been Built

✅ **Backend Services**:
- `usage_recorder.py` - Database model for LLM usage tracking
- `usage_service.py` - Usage aggregation and reporting
- `run_progress.py` - Run completion calculations
- `model_router.py` - Quota-aware model selection
- `llm_service.py` - **NEW**: Integrated LLM service with automatic routing + usage tracking
- `dashboard_schemas.py` - API schemas
- 5 dashboard API endpoints in `main.py`

✅ **Frontend**:
- React + Vite dashboard UI
- 4 real-time panels (RunProgress, Usage, ModelMapping, InterventionHelpers)
- Auto-polling every 5 seconds
- Accessible at `http://localhost:8000/dashboard`

---

## Integration Steps

### Step 1: Replace Direct OpenAI Calls with LlmService

The new `LlmService` wraps your existing `OpenAIBuilderClient` and `OpenAIAuditorClient` with automatic:
- Model selection via `ModelRouter`
- Usage tracking via `LlmUsageEvent`
- Quota-aware fallback logic

#### Before (Direct OpenAI Client Usage):

```python
from .openai_clients import OpenAIBuilderClient, OpenAIAuditorClient

builder = OpenAIBuilderClient()
result = builder.execute_phase(
    phase_spec=phase_spec,
    file_context=context,
    model="gpt-4o",  # ❌ Hard-coded model
)
# ❌ No usage tracking
# ❌ No quota awareness
```

#### After (Using LlmService):

```python
from .llm_service import LlmService
from .database import get_db

# In your phase executor or supervisor
db = next(get_db())
llm_service = LlmService(db, config_path="config/models.yaml")

result = llm_service.execute_builder_phase(
    phase_spec=phase_spec,
    file_context=context,
    run_id=run.id,  # ✅ For usage tracking
    phase_id=phase.phase_id,  # ✅ For usage tracking
    run_context={"model_overrides": {}},  # ✅ For per-run model selection
)
# ✅ Model automatically selected based on task_category + complexity
# ✅ Usage automatically recorded in database
# ✅ Quota-aware fallback if provider near limit
```

### Step 2: Update Your Main Execution Loop

Find where you currently execute builder and auditor phases. This is likely in your supervisor or orchestrator code.

#### Example Integration Location:

Look for code similar to this pattern:

```python
# In your run executor (likely in a file like supervisor.py or orchestrator.py)
def execute_phase(run, tier, phase):
    # Build phase spec
    phase_spec = {
        "phase_id": phase.phase_id,
        "task_category": phase.task_category,
        "complexity": phase.complexity,
        "description": phase.description,
        "acceptance_criteria": [...],
    }

    # Get file context
    file_context = {...}

    # ❌ OLD: Direct client usage
    builder = OpenAIBuilderClient()
    result = builder.execute_phase(phase_spec, file_context, model="gpt-4o")

    # ✅ NEW: Use LlmService
    from .llm_service import LlmService
    from .database import get_db

    db = next(get_db())
    llm_service = LlmService(db)

    result = llm_service.execute_builder_phase(
        phase_spec=phase_spec,
        file_context=file_context,
        run_id=run.id,
        phase_id=phase.phase_id,
        project_rules=load_project_rules(),  # Optional
        run_hints=load_run_hints(run.id),    # Optional
    )

    # Use result as before
    if result.success:
        apply_patch(result.patch_content)
```

### Step 3: Create Models Config File

The `ModelRouter` needs a config file to map tasks to models.

Create `config/models.yaml`:

```yaml
# Model selection configuration

# Complexity-based defaults
complexity_models:
  low:
    builder: "gpt-4o-mini"
    auditor: "gpt-4o-mini"
  medium:
    builder: "gpt-4o"
    auditor: "gpt-4o"
  high:
    builder: "gpt-4-turbo-2024-04-09"
    auditor: "gpt-4-turbo-2024-04-09"

# Category-specific overrides
category_models:
  external_feature_reuse:
    description: "Using external libraries/APIs"
    builder_model_override: "gpt-4-turbo-2024-04-09"  # Always use best model
    auditor_model_override: "gpt-4-turbo-2024-04-09"

  security_auth_change:
    description: "Security or auth code changes"
    builder_model_override: "gpt-4-turbo-2024-04-09"
    auditor_model_override: "gpt-4-turbo-2024-04-09"

  schema_contract_change:
    description: "Database or API schema changes"
    builder_model_override: "gpt-4-turbo-2024-04-09"
    auditor_model_override: "gpt-4-turbo-2024-04-09"

  docs:
    description: "Documentation generation"
    builder_model_override: "gpt-4o-mini"  # Cheaper model for docs
    auditor_model_override: "gpt-4o-mini"

  tests:
    description: "Test code generation"
    builder_model_override: "gpt-4o"
    auditor_model_override: "gpt-4o"

# Provider quota configuration
provider_quotas:
  openai:
    weekly_token_cap: 50000000  # 50M tokens/week
    soft_limit_ratio: 0.8  # Warn at 80%, fallback at this threshold

  anthropic:
    weekly_token_cap: 10000000  # 10M tokens/week
    soft_limit_ratio: 0.8

# Quota-aware routing
quota_routing:
  enabled: true

  # Categories that should NEVER fallback to cheaper models
  never_fallback_categories:
    - "external_feature_reuse"
    - "security_auth_change"
    - "schema_contract_change"

# Fallback strategy when quota is exceeded
fallback_strategy:
  by_category:
    general:
      fallbacks:
        - "gpt-4o-mini"
        - "claude-3-haiku-20240307"

    tests:
      fallbacks:
        - "gpt-4o-mini"

    docs:
      fallbacks:
        - "gpt-4o-mini"

  default_fallbacks:
    - "gpt-4o-mini"
    - "claude-3-haiku-20240307"

# Global defaults
defaults:
  high_risk_builder: "gpt-4o"
  high_risk_auditor: "gpt-4o"
```

### Step 4: Verify Dashboard Access

1. **Start the API**:
   ```bash
   docker-compose up -d
   ```

2. **Open in Cursor** (recommended):
   - Press `Ctrl+Shift+P` / `Cmd+Shift+P`
   - Type "Simple Browser: Show"
   - Enter: `http://localhost:8000/dashboard`

3. **Or open in browser**: Navigate to `http://localhost:8000/dashboard`

---

## API Endpoints Reference

### Dashboard Endpoints

#### 1. Get Run Status
```http
GET /dashboard/runs/{run_id}/status
```

**Response**:
```json
{
  "run_id": "run_test_123",
  "state": "TIER_IN_PROGRESS",
  "current_tier_name": "Tier 1",
  "current_phase_name": "Phase 2",
  "total_tiers": 3,
  "total_phases": 12,
  "completed_tiers": 0,
  "completed_phases": 1,
  "percent_complete": 8.33,
  "tokens_used": 125000,
  "token_cap": 5000000,
  "minor_issues_count": 3,
  "major_issues_count": 0
}
```

#### 2. Get Usage Summary
```http
GET /dashboard/usage?period=week
```

**Response**:
```json
{
  "providers": [
    {
      "provider": "openai",
      "total_tokens": 2500000,
      "cap_tokens": 50000000,
      "percent_of_cap": 5.0
    }
  ],
  "models": [
    {
      "model": "gpt-4o",
      "total_tokens": 1800000
    },
    {
      "model": "gpt-4o-mini",
      "total_tokens": 700000
    }
  ]
}
```

#### 3. Submit Human Note
```http
POST /dashboard/human-notes
Content-Type: application/json

{
  "run_id": "run_test_123",
  "note": "Skip UI tests for this run due to missing test data"
}
```

**Response**:
```json
{
  "message": "Note added successfully",
  "timestamp": "2025-11-25T10:30:00.123456",
  "notes_file": ".autopack/human_notes.md"
}
```

#### 4. Get Model Mappings
```http
GET /dashboard/models
```

**Response**: Array of model mappings
```json
[
  {
    "role": "builder",
    "category": "security_auth_change",
    "complexity": "high",
    "model": "gpt-4-turbo-2024-04-09",
    "scope": "global"
  },
  ...
]
```

#### 5. Override Model (Global)
```http
POST /dashboard/models/override
Content-Type: application/json

{
  "scope": "global",
  "role": "builder",
  "category": "tests",
  "complexity": "medium",
  "model": "gpt-4o-mini"
}
```

**Note**: Global overrides require manual config file updates. Per-run overrides require database schema update (see TODO below).

---

## Usage Patterns

### Pattern 1: Standard Phase Execution

```python
from .llm_service import LlmService
from .database import get_db

def execute_build_phase(run, phase):
    db = next(get_db())
    llm = LlmService(db)

    phase_spec = {
        "phase_id": phase.phase_id,
        "task_category": phase.task_category,  # e.g., "security_auth_change"
        "complexity": phase.complexity,         # e.g., "high"
        "description": phase.description,
        "acceptance_criteria": phase.acceptance_criteria,
    }

    result = llm.execute_builder_phase(
        phase_spec=phase_spec,
        file_context=get_file_context(),
        run_id=run.id,
        phase_id=phase.phase_id,
    )

    return result
```

### Pattern 2: Auditor Review

```python
def execute_audit_phase(run, phase, patch_content):
    db = next(get_db())
    llm = LlmService(db)

    result = llm.execute_auditor_review(
        patch_content=patch_content,
        phase_spec=phase.to_dict(),
        run_id=run.id,
        phase_id=phase.phase_id,
    )

    if result.approved:
        return "APPROVED", result.issues_found
    else:
        return "NEEDS_REVISION", result.issues_found
```

### Pattern 3: With Per-Run Model Overrides (Future)

```python
# When run_context JSON field is added to Run model
run_context = {
    "model_overrides": {
        "builder": {
            "security_auth_change:high": "o1-preview",  # Override for this run only
        }
    }
}

result = llm.execute_builder_phase(
    phase_spec=phase_spec,
    run_id=run.id,
    run_context=run_context,  # Passed to ModelRouter
)
```

---

## TODO: Future Enhancements

### 1. Per-Run Model Overrides (Database Schema)

Currently, per-run overrides are not persisted. To enable this:

**Add to Run model** (`models.py`):
```python
class Run(Base):
    # ... existing fields ...
    run_context = Column(JSONB, nullable=True)  # Store model_overrides here
```

**Migration**:
```bash
alembic revision --autogenerate -m "Add run_context to runs table"
alembic upgrade head
```

**Update endpoint** (`main.py:1058`):
```python
@app.post("/dashboard/models/override")
def override_model(request: ModelOverrideRequest, db: Session = Depends(get_db)):
    if request.scope == "run":
        run = db.query(models.Run).filter(models.Run.id == request.run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {request.run_id} not found")

        # Update run_context with override
        run_context = run.run_context or {}
        if "model_overrides" not in run_context:
            run_context["model_overrides"] = {}

        override_key = f"{request.category}:{request.complexity}"
        run_context["model_overrides"][request.role] = run_context["model_overrides"].get(request.role, {})
        run_context["model_overrides"][request.role][override_key] = request.model

        run.run_context = run_context
        db.commit()

        return {"message": "Per-run model override saved", ...}
```

### 2. Accurate Prompt/Completion Token Tracking

Currently using rough estimates (40/60 split for builder, 60/40 for auditor).

**Update OpenAI clients** to return separate counts:

In `openai_clients.py`, modify `BuilderResult` and `AuditorResult`:

```python
# Extract from response.usage
prompt_tokens = response.usage.prompt_tokens
completion_tokens = response.usage.completion_tokens

return BuilderResult(
    success=True,
    patch_content=result_json.get("patch", ""),
    prompt_tokens=prompt_tokens,        # NEW
    completion_tokens=completion_tokens, # NEW
    tokens_used=response.usage.total_tokens,
    model_used=model,
)
```

Then update `LlmService` to use actual counts instead of estimates.

### 3. Real-Time WebSocket Updates

For live dashboard updates without polling:

```python
# Add to main.py
from fastapi import WebSocket

@app.websocket("/ws/runs/{run_id}")
async def websocket_run_status(websocket: WebSocket, run_id: str):
    await websocket.accept()
    while True:
        # Send run status every 2 seconds
        status = get_run_status(run_id)
        await websocket.send_json(status)
        await asyncio.sleep(2)
```

Update frontend to use WebSocket instead of polling.

### 4. Quota Warning Alerts

Add proactive warnings when approaching quota limits:

```python
# In LlmService, before executing call
usage_pct = self.model_router._get_provider_usage_percent(model)
if usage_pct > 90:
    # Send alert to dashboard or human_notes.md
    log_quota_warning(f"Provider at {usage_pct}% capacity!")
```

---

## Testing

### Manual Testing

1. **Create a test run**:
   ```bash
   curl -X POST http://localhost:8000/runs/start \
     -H "Content-Type: application/json" \
     -d '{"run": {"run_id": "test_001", ...}, "tiers": [...], "phases": [...]}'
   ```

2. **Check dashboard**: Navigate to `/dashboard` and verify all panels load

3. **Test usage recording**: Execute an LLM call, then check `/dashboard/usage`

4. **Test human notes**: Submit a note via dashboard UI, verify file created in `.autopack/human_notes.md`

### Integration Tests

Run the dashboard integration tests:

```bash
pytest tests/test_dashboard_integration.py -v
```

**Note**: Some tests require `config/models.yaml` to exist. Create it first or skip those tests.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Dashboard UI (React)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────┐ │
│  │ Run Progress │  │ Usage Panel  │  │ Model Mapping│  │ Help│ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP polling (5s)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Endpoints                           │
│  /dashboard/runs/{id}/status  │  /dashboard/usage  │  /models   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        LlmService                                │
│  ┌──────────────────┐         ┌──────────────────────────────┐ │
│  │   ModelRouter    │ ──────> │  OpenAI Builder/Auditor      │ │
│  │ (quota-aware)    │         │  Clients                     │ │
│  └──────────────────┘         └──────────────────────────────┘ │
│         │                                    │                  │
│         │                                    │                  │
│         ▼                                    ▼                  │
│  ┌──────────────────┐         ┌──────────────────────────────┐ │
│  │ UsageService     │ <────── │  UsageRecorder               │ │
│  │ (aggregation)    │         │  (tracks every call)         │ │
│  └──────────────────┘         └──────────────────────────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PostgreSQL Database                         │
│  • runs                 • llm_usage_events                       │
│  • tiers                • (other tables...)                      │
│  • phases                                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Support & Next Steps

1. **Review this guide** and understand the integration points
2. **Create `config/models.yaml`** with your desired model mappings
3. **Update your phase executor** to use `LlmService` instead of direct OpenAI clients
4. **Test with a sample run** and verify dashboard updates
5. **Monitor usage** via dashboard and adjust quotas as needed

For questions or issues, refer to:
- [DASHBOARD_IMPLEMENTATION_PLAN.md](./DASHBOARD_IMPLEMENTATION_PLAN.md) - Full implementation details
- [Dashboard Integration Tests](../tests/test_dashboard_integration.py) - Code examples
- FastAPI auto-generated docs: `http://localhost:8000/docs`
