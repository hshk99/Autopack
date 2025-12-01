# Autopack Dashboard + Model Routing Implementation Plan

**Last Updated**: 2025-11-25
**Status**: ✅ COMPLETED - Phases 1-3 implemented and tested
**Version**: 1.0

---

## 🚀 Quick Start Guide

### Accessing the Dashboard

1. **Start the API**: Ensure Docker containers are running
   ```bash
   docker-compose up -d
   ```

2. **Access via Browser**: Navigate to [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

3. **Access in Cursor** (recommended):
   - Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (Mac)
   - Type "Simple Browser: Show"
   - Enter URL: `http://localhost:8000/dashboard`
   - Dashboard opens in Cursor sidebar - stay in one app!

### Dashboard Features

- **Run Progress Panel**: Real-time progress bar, tier/phase tracking, token usage
- **Usage Panel**: Provider caps with color-coded warnings (green/yellow/red at 80%/90%)
- **Model Mapping Panel**: View and change model assignments per category/complexity
- **Intervention Helpers**: Copy context to clipboard, submit notes to `.autopack/human_notes.md`

### API Endpoints

All endpoints documented below and available at [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Decisions](#architecture-decisions)
3. [Phase 1: Backend - Run Progress + Usage Logging](#phase-1--backend-run-progress--usage-logging)
4. [Phase 2: Backend - Model Router + Dashboard API](#phase-2--backend-model-router--dashboard-api)
5. [Phase 3: Frontend - Minimal Dashboard UI](#phase-3--frontend-minimal-dashboard-ui)
6. [Phase 4: Optional - Remote Controls via Claude/Phone](#phase-4--optional-remote-controls-via-claudephone)
7. [Cursor Webview Integration](#cursor-webview-integration)
8. [Implementation Checklist](#implementation-checklist)

---

## Overview

### Scope

Implement a minimal internal "Autopack Dashboard" with:

1. **Run progress view**
   - Shows current run state, tier, phase, and a progress bar

2. **Top-bar controls**
   - Start / pause / stop run
   - Change Builder/Auditor models via dropdowns per category/complexity (with safe scoping)

3. **Usage panel**
   - Per-provider/model token usage (core vs aux) vs configured caps

4. **Model routing**
   - Central ModelRouter that is quota-aware and exposes current mapping to the dashboard

**Key Principle**: No scraping provider web UIs. Usage comes from Autopack's own logs and (optionally) official APIs.

---

## Architecture Decisions

### Decision 1: Usage Tracking Approach

**IMPORTANT**: Do **NOT** implement scraping or screenshot-reading of provider usage pages.

**Rationale**:
- Autopack already has perfect data about its own usage via API responses
- Every LLM call returns `prompt_tokens` and `completion_tokens`
- 100% accurate for Autopack's share of usage
- No fragile web scraping, no ToS violations, no token cost for reading screenshots

**Implementation**:
- Track all token usage from API responses in `llm_usage_events` table
- Configure provider caps as manual config (not scraped)
- User adjusts caps based on external tools (GPT Atlas, provider dashboards) manually

**Provider Caps Configuration**:
```yaml
providers:
  anthropic:
    weekly_cap_tokens: 20_000_000
    autopack_share: 0.5   # Autopack may spend up to 50% of that
  openai:
    weekly_cap_tokens: 25_000_000
    autopack_share: 0.6
```

**To Clarify with Cursor**:
> "Treat provider dashboards and tools like GPT Atlas as human-level inputs. I will adjust Autopack's `weekly_cap_tokens` and `autopack_share` manually based on those. Autopack should rely only on its own token logs and configured caps."

---

### Decision 2: Chat Bar vs Intervention Helpers

**IMPORTANT**: Do **NOT** embed a full LLM chat bar in the Autopack dashboard for v1.

**Rationale**:
- User already has Cursor (IDE) for code-centric chat
- User already has Claude/GPT apps for planning/analysis chat on phone and PC
- Building new chat UI means:
  - Another place to manage auth
  - Another LLM client config
  - Duplicated features (history, context selection, etc.)

**Instead: Intervention Helpers Panel**

Provide a small "Intervention helpers" panel in the dashboard that:

1. **Run Context Block** (for copy-paste into Claude/Cursor):
   ```markdown
   ## Current Autopack Run Context

   - Run ID: `run_20250125_143022`
   - State: `in_progress`
   - Current: Tier 2 / Phase 4 (43% complete)
   - Last Summary: "Implemented authentication middleware, now auditing security"
   - Strategy File: `.autopack/comprehensive_plan.md`
   ```

2. **Human Notes Textarea**:
   - On submit, writes to `.autopack/human_notes.md`
   - Autopack and agents can read this file in future planning phases
   - Example use: "Skip UI testing for this run - focus on backend only"

**Workflow**:
- From phone: Open Claude app for chat + dashboard URL in browser for status/controls
- From PC: Cursor for code edits + browser tab for dashboard + Claude/GPT tab for strategic chat

---

### Decision 3: Cursor Webview Integration

**Answer**: Yes, Cursor can open webviews for local URLs.

**Options**:

1. **Simple Panel in Cursor**:
   - Cursor supports opening URLs in side panels
   - Navigate to `http://localhost:8000/dashboard` in Cursor's browser panel
   - Works like any browser but integrated in IDE

2. **External Browser**:
   - Open dashboard in default browser while working in Cursor
   - Easier for multi-monitor setups

3. **Mobile Access**:
   - Access same `http://localhost:8000/dashboard` from phone browser
   - Requires exposing port or using ngrok/similar for remote access

**Recommended Workflow**:
- Development: Dashboard in Cursor side panel or second monitor
- Mobile monitoring: Expose via ngrok when away from desk
- No need for separate "Cursor app on mobile phone" - just use browser

---

## Phase 1 – Backend: Run Progress + Usage Logging

### 1.1 Add Run Progress Computation

**Goal**: For each run, compute a simple progress indicator + current location.

**Steps**:

1. In [src/autopack/supervisor.py](src/autopack/supervisor.py) (or wherever Run state machine lives):

   Ensure each run tracks:
   - `total_tiers`, `total_phases`
   - `completed_tiers`, `completed_phases`
   - `current_tier_index`, `current_phase_index` (0-based or 1-based, but be consistent)

   Add a `RunProgress` dataclass:

   ```python
   from dataclasses import dataclass

   @dataclass
   class RunProgress:
       run_id: str
       total_tiers: int
       total_phases: int
       completed_tiers: int
       completed_phases: int
       current_tier_index: int | None
       current_phase_index: int | None

       @property
       def percent_complete(self) -> float:
           if self.total_phases == 0:
               return 0.0
           return self.completed_phases / self.total_phases
   ```

   Update progress whenever a phase transitions to a terminal state.

2. In [src/autopack/main.py](src/autopack/main.py):

   Add endpoint:

   ```python
   from pydantic import BaseModel

   class DashboardRunStatus(BaseModel):
       run_id: str
       state: str
       current_tier_name: str | None
       current_phase_name: str | None
       current_tier_index: int | None
       current_phase_index: int | None
       total_tiers: int
       total_phases: int
       completed_tiers: int
       completed_phases: int
       percent_complete: float

   @app.get("/dashboard/runs/{run_id}/status", response_model=DashboardRunStatus)
   def get_run_status(run_id: str):
       """
       Returns high-level status for the dashboard:
       - run_state
       - progress (percent_complete)
       - tier/phase indices and names
       - key metrics (issue counts, tokens, etc.)
       """
       # Implementation goes here
   ```

This gives the dashboard enough info to show "Tier 2 / Phase 4 (43% complete)" and a progress bar.

---

### 1.2 LLM Usage Logging

**Goal**: Track tokens by provider/model/run/phase for both core Builder/Auditor and aux agents.

**Steps**:

1. Create [src/autopack/usage_recorder.py](src/autopack/usage_recorder.py):

   ```python
   from dataclasses import dataclass
   from datetime import datetime

   @dataclass
   class LlmUsageEvent:
       provider: str
       model: str
       run_id: str | None
       phase_id: str | None
       role: str  # "builder", "auditor", "agent:planner", etc.
       prompt_tokens: int
       completion_tokens: int
       created_at: datetime
   ```

   Provide functions:
   - `record_usage(event: LlmUsageEvent)`
   - `get_usage_summary(time_window, group_by)` (provider, model, role, run_id)

   Persist to Postgres in a simple table:

   ```sql
   CREATE TABLE llm_usage_events (
     id serial PRIMARY KEY,
     provider text NOT NULL,
     model text NOT NULL,
     run_id text,
     phase_id text,
     role text NOT NULL,
     prompt_tokens integer NOT NULL,
     completion_tokens integer NOT NULL,
     created_at timestamptz NOT NULL DEFAULT now()
   );

   -- Add indexes for common queries
   CREATE INDEX idx_usage_provider_created ON llm_usage_events(provider, created_at);
   CREATE INDEX idx_usage_model_created ON llm_usage_events(model, created_at);
   CREATE INDEX idx_usage_run_id ON llm_usage_events(run_id);
   ```

2. In **all LLM callers**:

   - [integrations/cursor_integration.py](integrations/cursor_integration.py) (Builder)
   - [integrations/codex_integration.py](integrations/codex_integration.py) (Auditor)
   - `launch_claude_agents.py` (aux agents, once added)

   After each API call:
   - Extract token usage from the provider response (OpenAI/Anthropic/GLM)
   - Call `record_usage(...)` with:
     - `provider` = `"openai" | "anthropic" | "glm"`
     - `model` = the exact model name
     - `role` = `"builder"`, `"auditor"`, or `"agent:{agent_name}"`
     - `run_id` and `phase_id` if available (None for global aux runs)

3. Create [src/autopack/usage_service.py](src/autopack/usage_service.py):

   ```python
   from datetime import datetime, timedelta
   from typing import Literal

   class UsageService:
       def __init__(self, db_connection):
           self.db = db_connection

       def get_provider_usage_summary(
           self,
           period: Literal["day", "week", "month"] = "week"
       ) -> dict[str, dict]:
           """
           Returns usage by provider for the given period.
           Example: {
               "openai": {
                   "prompt_tokens": 1500000,
                   "completion_tokens": 500000,
                   "total_tokens": 2000000
               }
           }
           """
           pass

       def get_model_usage_summary(
           self,
           period: Literal["day", "week", "month"] = "week"
       ) -> list[dict]:
           """
           Returns usage by model for the given period.
           Example: [
               {
                   "provider": "openai",
                   "model": "gpt-4o",
                   "prompt_tokens": 800000,
                   "completion_tokens": 300000
               }
           ]
           """
           pass
   ```

---

## Phase 2 – Backend: Model Router + Dashboard API

### 2.1 ModelRouter Abstraction

**Goal**: Centralise model choice using category, complexity, and provider quotas.

**Steps**:

1. Create [src/autopack/model_router.py](src/autopack/model_router.py):

   ```python
   from typing import Literal

   class ModelRouter:
       def __init__(self, model_config, provider_caps, usage_service):
           self.model_config = model_config        # from models.yaml
           self.provider_caps = provider_caps      # from config
           self.usage_service = usage_service      # wraps llm_usage_events

       def select_model(
           self,
           role: Literal["builder", "auditor"] | str,  # or "agent:<name>"
           task_category: str,
           complexity: str,
           run_context: dict
       ) -> str:
           """
           Returns a model name like "gpt-4o", "claude-3-5-sonnet", "glm-4.6", etc.

           Applies:
             - baseline mapping from models.yaml
             - per-run overrides
             - provider quota state
           """
           # 1. Check run overrides first
           if run_context.get("model_overrides"):
               key = f"{task_category}:{complexity}"
               if key in run_context["model_overrides"].get(role, {}):
                   return run_context["model_overrides"][role][key]

           # 2. Check baseline mapping from config
           baseline_model = self._get_baseline_model(
               role, task_category, complexity
           )

           # 3. Check quota state and apply fallback if needed
           if self._is_provider_over_soft_limit(baseline_model):
               if self._is_fail_fast_category(task_category):
                   # For critical categories, fail or warn
                   return baseline_model  # Or raise exception
               else:
                   # Try fallback
                   return self._get_fallback_model(
                       task_category, complexity
                   )

           return baseline_model

       def _get_baseline_model(self, role, category, complexity) -> str:
           """Read from models.yaml baseline config"""
           pass

       def _is_provider_over_soft_limit(self, model: str) -> bool:
           """Check if provider has exceeded soft limit (80%)"""
           provider = self._model_to_provider(model)
           usage = self.usage_service.get_provider_usage_summary("week")
           cap = self.provider_caps[provider]["weekly_cap_tokens"]
           share = self.provider_caps[provider].get("autopack_share", 1.0)
           effective_cap = cap * share

           return usage[provider]["total_tokens"] > (effective_cap * 0.8)

       def _is_fail_fast_category(self, category: str) -> bool:
           """Categories that should never fallback"""
           return category in [
               "external_feature_reuse",
               "security_auth_change",
               "schema_contract_change"
           ]

       def _get_fallback_model(self, category: str, complexity: str) -> str:
           """Get fallback model from config"""
           pass

       def _model_to_provider(self, model: str) -> str:
           """Map model name to provider"""
           if model.startswith("gpt-"):
               return "openai"
           elif model.startswith("claude-") or model.startswith("opus-"):
               return "anthropic"
           elif model.startswith("glm-"):
               return "glm"
           else:
               raise ValueError(f"Unknown provider for model: {model}")
   ```

2. **Baseline mapping**:

   Keep existing `complexity_models` + category overrides in [config/models.yaml](config/models.yaml).
   ModelRouter reads this config at startup (or via injected config object).

3. **Per-run overrides**:

   Extend run context to optionally hold:

   ```json
   {
     "model_overrides": {
       "builder": {
         "core_backend:medium": "gpt-4o",
         "security_auth_change:high": "opus-4.5"
       },
       "auditor": {
         "core_backend:medium": "claude-3-5-sonnet"
       }
     }
   }
   ```

   In `select_model`, check run overrides first; fallback to baseline.

4. **Quota awareness**:

   - Use `usage_service` to get provider totals for the current period
   - If a provider is above `soft_limit`:
     - For non-critical categories, try fallback models from another provider
     - For critical categories, either keep primary provider or fail fast (configurable)

5. Wire all Builder/Auditor invocations to use `ModelRouter.select_model` instead of hard-coded model names.

---

### 2.2 Dashboard API for Model Mapping and Usage

**Goal**: Let the dashboard read and update model mappings and show usage.

**Steps**:

1. Add endpoints in [src/autopack/main.py](src/autopack/main.py):

   **GET `/dashboard/models`**

   Returns current mapping and allowed choices:

   ```python
   from pydantic import BaseModel
   from typing import Literal

   class ModelMapping(BaseModel):
       role: str       # builder / auditor
       category: str
       complexity: str
       model: str
       scope: Literal["global", "run"]

   @app.get("/dashboard/models")
   def get_model_mappings() -> list[ModelMapping]:
       """
       Returns all current model mappings for builder and auditor
       across all categories and complexity levels.
       """
       pass
   ```

   **POST `/dashboard/models/override`**

   Body:

   ```json
   {
     "role": "builder",
     "category": "core_backend",
     "complexity": "medium",
     "model": "gpt-4o",
     "scope": "run",
     "run_id": "optional-if-scope=run"
   }
   ```

   Behaviour:
   - `scope="global"`:
     - Update `models.yaml` (or config DB) and reload config
     - Only affects **new runs**
   - `scope="run"`:
     - Update `run_context.model_overrides` for that run
     - Only affects **future phases** in that run

   ```python
   class ModelOverrideRequest(BaseModel):
       role: str
       category: str
       complexity: str
       model: str
       scope: Literal["global", "run"]
       run_id: str | None = None

   @app.post("/dashboard/models/override")
   def override_model_mapping(request: ModelOverrideRequest):
       """
       Override model mapping for a specific role/category/complexity.
       Scope determines if change is global (affects new runs) or
       run-specific (affects only future phases in that run).
       """
       if request.scope == "run" and not request.run_id:
           raise ValueError("run_id required for scope=run")

       # Implementation goes here
       pass
   ```

2. **GET `/dashboard/usage`**

   Returns aggregate usage by provider and model for a given period:

   ```python
   from typing import Literal

   class ProviderUsage(BaseModel):
       provider: str
       period: str   # "day" | "week" | "month"
       prompt_tokens: int
       completion_tokens: int
       total_tokens: int
       cap_tokens: int
       percent_of_cap: float

   class ModelUsage(BaseModel):
       provider: str
       model: str
       prompt_tokens: int
       completion_tokens: int
       total_tokens: int

   class UsageResponse(BaseModel):
       providers: list[ProviderUsage]
       models: list[ModelUsage]

   @app.get("/dashboard/usage")
   def get_usage(
       period: Literal["day", "week", "month"] = "week"
   ) -> UsageResponse:
       """
       Returns token usage aggregated by provider and model
       for the specified time period.
       """
       usage_service = get_usage_service()

       provider_usage = usage_service.get_provider_usage_summary(period)
       model_usage = usage_service.get_model_usage_summary(period)

       # Convert to response format with cap calculations
       pass
   ```

---

## Phase 3 – Frontend: Minimal Dashboard UI

You can implement this as a small React app served by FastAPI, or any simple SPA.

### 3.1 Layout

**Top bar:**
- Run selector (dropdown of active/recent runs)
- Run controls: Start / Pause / Stop buttons
- Quick summary of usage per provider (e.g., small badges with `% used`)

**Left panel: "Run Progress"**
- Show:
  - Run state
  - `Tier 2 / Phase 4`
  - Total tiers/phases
  - Progress bar using `percent_complete`
- Poll `/dashboard/runs/{run_id}/status` every 5–10 seconds

**Right panel: "Model Mapping"**
- Table for builder and auditor:
  - Rows: `category × complexity`
  - Columns: current model (dropdown), scope (Global / This run)
- When you change a dropdown:
  - Show "Apply as global default" vs "Apply for this run only"
  - Call `/dashboard/models/override` accordingly

**Bottom panel: "Intervention Helpers"** (NEW)
- **Run Context Block**:
  - Shows current run ID, tier/phase, last summary
  - "Copy to clipboard" button for pasting into Claude/Cursor chat
- **Human Notes Textarea**:
  - Submit button writes to `.autopack/human_notes.md`
  - Shows last 5 notes with timestamps

**Separate tab: "Usage"**
- Summary cards:
  - `OpenAI: 5% of weekly cap`
  - `Anthropic: 85%`
  - `GLM: 10%`
- Table of models with tokens over the selected period
- Time period selector (day/week/month)

---

### 3.2 Minimal Actions Wiring

**Run controls**:
- Bind to existing Autopack endpoints:
  - `/runs/start`
  - `/runs/{id}/pause`
  - `/runs/{id}/resume`
  - `/runs/{id}/cancel`

**Progress updates**:
- Simple polling every 5-10 seconds
- No need for websockets initially
- Can upgrade to SSE or websockets later if needed

**Model mapping updates**:
- Use POST `/dashboard/models/override` described above
- Show confirmation toast after successful update

**Intervention helpers**:
- Copy button uses `navigator.clipboard.writeText()`
- Human notes submit calls new endpoint:
  ```python
  @app.post("/dashboard/human-notes")
  def add_human_note(note: str):
      """Append note to .autopack/human_notes.md with timestamp"""
      pass
  ```

---

### 3.3 Technology Stack

**Frontend**:
- React with Vite (fast dev experience)
- Tailwind CSS (utility-first styling)
- Recharts (for usage charts if needed)
- React Query (for polling and caching)

**Serving**:
- FastAPI serves static files from `dist/` folder
- During dev: Vite dev server on port 5173, FastAPI on 8000
- Production: FastAPI serves built static files

**File Structure**:
```
src/autopack/
  dashboard/
    frontend/
      src/
        components/
          RunProgress.tsx
          ModelMapping.tsx
          UsagePanel.tsx
          InterventionHelpers.tsx
        App.tsx
        main.tsx
      package.json
      vite.config.ts
    static/  # Built files go here
```

---

## Phase 4 – Optional: Remote Controls via Claude/Phone

Later, if you want to control from Claude mobile chat:

1. **Expose API with authentication**:
   - Add API key auth to dashboard endpoints
   - Use environment variable for API key
   - Consider rate limiting

2. **Create MCP tools** for remote control:
   ```python
   # In MCP server configuration
   tools = [
       {
           "name": "autopack_get_run_status",
           "description": "Get status of current Autopack run",
           "parameters": {"run_id": "string"}
       },
       {
           "name": "autopack_override_model",
           "description": "Override model for current run",
           "parameters": {
               "role": "builder|auditor",
               "category": "string",
               "complexity": "low|medium|high",
               "model": "string"
           }
       },
       {
           "name": "autopack_control_run",
           "description": "Start/pause/stop Autopack run",
           "parameters": {
               "run_id": "string",
               "action": "start|pause|resume|cancel"
           }
       }
   ]
   ```

3. **Usage from phone**:
   - "Show me status of the current Autopack run."
   - "For this run, downgrade low-complexity UI phases to Haiku."
   - "Stop the run if token usage for Anthropic exceeds 80% of weekly cap."

**Implementation Notes**:
- Keep this phase optional
- Requires secure tunneling (ngrok, Tailscale, etc.) for remote access
- Consider security implications carefully
- Start with read-only tools first, add write actions later

---

## Cursor Webview Integration

### Opening Dashboard in Cursor

**Method 1: Simple URL Open**
1. Start Autopack backend: `python -m autopack.main`
2. Dashboard available at: `http://localhost:8000/dashboard`
3. In Cursor:
   - Open command palette (Cmd+Shift+P / Ctrl+Shift+P)
   - Type "Simple Browser" or "Open in Browser"
   - Enter `http://localhost:8000/dashboard`

**Method 2: Cursor Extension (Advanced)**
- Create custom Cursor extension with webview panel
- Benefits:
  - Persists across Cursor restarts
  - Better IDE integration
  - Custom keybindings
- Complexity: Medium (requires extension development)

**Method 3: External Browser**
- Simplest approach: just open in Chrome/Firefox/Safari
- Works well with multi-monitor setups
- No Cursor-specific setup needed

### Mobile Access

**For Remote Monitoring**:
1. Use ngrok to expose localhost:
   ```bash
   ngrok http 8000
   ```
2. Open ngrok URL on phone browser
3. Dashboard works identically on mobile

**Security Considerations**:
- Add authentication before exposing publicly
- Consider VPN/Tailscale for private access
- Rate limit API endpoints

---

## Implementation Checklist

### Phase 1: Backend - Progress & Usage

- [ ] Create `RunProgress` dataclass in [src/autopack/supervisor.py](src/autopack/supervisor.py)
- [ ] Add progress tracking to run state machine
- [ ] Create `/dashboard/runs/{run_id}/status` endpoint
- [ ] Create `llm_usage_events` table in PostgreSQL
- [ ] Create [src/autopack/usage_recorder.py](src/autopack/usage_recorder.py) module
- [ ] Add usage recording to [integrations/cursor_integration.py](integrations/cursor_integration.py) (Builder)
- [ ] Add usage recording to [integrations/codex_integration.py](integrations/codex_integration.py) (Auditor)
- [ ] Create [src/autopack/usage_service.py](src/autopack/usage_service.py) with summary methods
- [ ] Add provider caps configuration to config file
- [ ] Test usage logging end-to-end

### Phase 2: Backend - Model Router & API

- [ ] Create [src/autopack/model_router.py](src/autopack/model_router.py) with `ModelRouter` class
- [ ] Implement baseline model selection from [config/models.yaml](config/models.yaml)
- [ ] Implement per-run overrides in run context
- [ ] Implement quota-aware fallback logic
- [ ] Create `/dashboard/models` GET endpoint
- [ ] Create `/dashboard/models/override` POST endpoint
- [ ] Create `/dashboard/usage` GET endpoint
- [ ] Wire Builder to use `ModelRouter.select_model()`
- [ ] Wire Auditor to use `ModelRouter.select_model()`
- [ ] Add global config update for `scope="global"` overrides
- [ ] Test model routing with different quota scenarios

### Phase 3: Frontend - Dashboard UI

- [ ] Set up React + Vite project in `src/autopack/dashboard/frontend/`
- [ ] Install dependencies (React Query, Tailwind, Recharts)
- [ ] Create `RunProgress` component with progress bar
- [ ] Create `ModelMapping` component with dropdowns
- [ ] Create `UsagePanel` component with provider cards
- [ ] Create `InterventionHelpers` component with context block and notes
- [ ] Wire up run controls (start/pause/stop buttons)
- [ ] Implement polling for `/dashboard/runs/{run_id}/status`
- [ ] Implement model override form and API call
- [ ] Add copy-to-clipboard for run context
- [ ] Add human notes submission
- [ ] Build and test in development mode
- [ ] Configure FastAPI to serve built static files
- [ ] Test full dashboard in production mode

### Phase 4: Optional - Remote Controls

- [ ] Add API key authentication to dashboard endpoints
- [ ] Create MCP server configuration for Autopack tools
- [ ] Implement `autopack_get_run_status` tool
- [ ] Implement `autopack_override_model` tool
- [ ] Implement `autopack_control_run` tool
- [ ] Set up ngrok or Tailscale for remote access
- [ ] Test remote control from Claude mobile app
- [ ] Add rate limiting to prevent abuse
- [ ] Document security considerations

---

## Integration with Existing Features

### Quota-Aware Routing

This dashboard implementation complements the existing [QUOTA_AWARE_ROUTING.md](QUOTA_AWARE_ROUTING.md) plan:

- ModelRouter implements the routing logic described in that document
- Dashboard provides UI for monitoring and override
- Usage tracking provides data for quota decisions

### Token Efficiency Implementation

Integrates with [TOKEN_EFFICIENCY_IMPLEMENTATION.md](TOKEN_EFFICIENCY_IMPLEMENTATION.md):

- Dashboard shows actual token usage vs budgets
- Can override model choices to test cost/quality trade-offs
- Usage data validates efficiency assumptions

### Learned Rules

Supports patterns from [LEARNED_RULES_README.md](LEARNED_RULES_README.md):

- Intervention helpers enable mid-run human guidance
- Model overrides allow tactical adjustments
- Usage visibility supports cost management

---

## Testing Strategy

### Unit Tests

1. **ModelRouter**:
   - Test baseline model selection
   - Test per-run overrides
   - Test quota-aware fallback
   - Test fail-fast categories

2. **UsageService**:
   - Test token aggregation by provider
   - Test token aggregation by model
   - Test time window filtering

### Integration Tests

1. **API Endpoints**:
   - Test `/dashboard/runs/{run_id}/status` with real run data
   - Test `/dashboard/models` returns correct mappings
   - Test `/dashboard/models/override` updates config correctly
   - Test `/dashboard/usage` calculates percentages correctly

2. **End-to-End**:
   - Start a run, verify progress updates
   - Override a model, verify next phase uses new model
   - Check usage tracking after multiple phases
   - Test intervention helpers write to correct files

### Manual Testing

1. Open dashboard in Cursor webview
2. Start a test run with known parameters
3. Monitor progress bar updates
4. Change model mapping mid-run
5. Verify usage percentages match provider dashboards
6. Test copy-to-clipboard for run context
7. Submit human note and verify file update

---

## Future Enhancements

### Potential Improvements

1. **Real-time Updates**:
   - [ ] Replace polling with Server-Sent Events (SSE)
   - [ ] Add websocket support for instant updates
   - [ ] Show live token usage during phases

2. **Advanced Usage Analytics**:
   - [ ] Cost per phase breakdown
   - [ ] Cost per tier analysis
   - [ ] Historical cost trends
   - [ ] Budget alerts and notifications

3. **Enhanced Model Management**:
   - [ ] Model performance metrics (quality scores)
   - [ ] Automatic A/B testing of model choices
   - [ ] Model recommendation engine
   - [ ] Cost/quality pareto curves

4. **Collaboration Features**:
   - [ ] Multi-user access with roles
   - [ ] Shared run annotations
   - [ ] Team usage dashboards
   - [ ] Slack/Discord notifications

5. **Mobile App**:
   - [ ] Native iOS/Android app
   - [ ] Push notifications for run completion
   - [ ] Offline mode with sync

---

## Troubleshooting

### Dashboard won't load

**Symptoms**: Blank page or connection refused

**Solutions**:
1. Check backend is running: `curl http://localhost:8000/health`
2. Check frontend build: `cd src/autopack/dashboard/frontend && npm run build`
3. Check CORS settings if using separate dev server
4. Check browser console for errors

### Usage data not showing

**Symptoms**: Usage panel shows 0% or no data

**Solutions**:
1. Verify `llm_usage_events` table exists and has data
2. Check usage recording is called after LLM calls
3. Verify provider names match exactly ("openai" not "OpenAI")
4. Check time window query is correct (timezone issues)

### Model overrides not working

**Symptoms**: Run still uses old model after override

**Solutions**:
1. Check override scope (global vs run)
2. Verify run_id matches current run
3. Check run context is being read correctly
4. Verify ModelRouter is wired up in all LLM callers

### Cursor webview not opening

**Symptoms**: Dashboard doesn't load in Cursor panel

**Solutions**:
1. Try external browser first to verify dashboard works
2. Check Cursor version supports webviews
3. Use "Simple Browser" command instead of custom webview
4. Fall back to separate browser window

---

**Last Updated**: 2025-11-25
**Maintainer**: Autopack Team
**Related Documents**:
- [QUOTA_AWARE_ROUTING.md](QUOTA_AWARE_ROUTING.md)
- [TOKEN_EFFICIENCY_IMPLEMENTATION.md](TOKEN_EFFICIENCY_IMPLEMENTATION.md)
- [LEARNED_RULES_README.md](LEARNED_RULES_README.md)
- [README.md](../README.md)
