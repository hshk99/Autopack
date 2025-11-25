Yes, it’s all compatible: real‑time progress + top‑bar controls + usage view + model routing in one small dashboard.

Below is an implementation plan you can hand directly to Cursor to build into Autopack.

---

## DASHBOARD + MODEL ROUTING IMPLEMENTATION PLAN (for Autopack)

### Scope

Implement a minimal internal “Autopack Dashboard” with:

1. **Run progress view**

   * Shows current run state, tier, phase, and a progress bar.
2. **Top‑bar controls**

   * Start / pause / stop run.
   * Change Builder/Auditor models via dropdowns per category/complexity (with safe scoping).
3. **Usage panel**

   * Per‑provider/model token usage (core vs aux) vs configured caps.
4. **Model routing**

   * Central ModelRouter that is quota‑aware and exposes current mapping to the dashboard.

No scraping provider web UIs. Usage comes from Autopack’s own logs and (optionally) official APIs.

---

## Phase 1 – Backend: run progress + usage logging

### 1.1 Add run progress computation

**Goal:** For each run, compute a simple progress indicator + current location.

**Steps:**

1. In `src/autopack/supervisor.py` (or wherever Run state machine lives):

   * Ensure each run tracks:

     * total_tiers, total_phases,
     * completed_tiers, completed_phases,
     * current_tier_index, current_phase_index (0‑based or 1‑based, but be consistent).

   * If this doesn’t exist yet, add a `RunProgress` dataclass:

     ```python
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

   * Update progress whenever a phase transitions to a terminal state.

2. In `src/autopack/main.py`:

   * Add endpoint:

     ```python
     @app.get("/dashboard/runs/{run_id}/status", response_model=DashboardRunStatus)
     def get_run_status(run_id: str):
         """
         Returns high-level status for the dashboard:
         - run_state
         - progress (percent_complete)
         - tier/phase indices and names
         - key metrics (issue counts, tokens, etc.)
         """
     ```

   * `DashboardRunStatus` should include:

     ```python
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
     ```

This gives the dashboard enough info to show “Tier 2 / Phase 4 (43% complete)” and a progress bar.

---

### 1.2 LLM usage logging

**Goal:** Track tokens by provider/model/run/phase for both core Builder/Auditor and aux agents.

**Steps:**

1. Define a small usage recorder module, e.g.:

   * `src/autopack/usage_recorder.py`:

     ```python
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

   * Provide functions:

     * `record_usage(event: LlmUsageEvent)`
     * `get_usage_summary(time_window, group_by)` (provider, model, role, run_id)

   * Persist to Postgres in a simple table:

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
     ```

2. In **all LLM callers**:

   * `integrations/cursor_integration.py` (Builder),
   * `integrations/codex_integration.py` (Auditor),
   * `launch_claude_agents.py` (aux agents, once added),

   after each API call:

   * extract token usage from the provider response (OpenAI/Anthropic/Gemini/GLM),
   * call `record_usage(...)` with:

     * `provider` = `"openai" | "anthropic" | "google_gemini" | "glm"`,
     * `model` = the exact model name,
     * `role` = `"builder"`, `"auditor"`, or `"agent:{agent_name}"`,
     * `run_id` and `phase_id` if available (None for global aux runs).

3. Add a small service module, e.g. `src/autopack/usage_service.py`, that exposes:

   * `get_provider_usage_summary(period="week")`
   * `get_model_usage_summary(period="week")`

---

## Phase 2 – Backend: model router + API for dashboard controls

### 2.1 ModelRouter abstraction

**Goal:** Centralise model choice using:

* category,
* complexity,
* provider quotas.

**Steps:**

1. Create `src/autopack/model_router.py`:

   ```python
   class ModelRouter:
       def __init__(self, model_config, provider_caps, usage_service):
           self.model_config = model_config        # from models.yaml
           self.provider_caps = provider_caps      # from config
           self.usage_service = usage_service      # wraps llm_usage_events

       def select_model(self, role, task_category, complexity, run_context) -> str:
           """
           role: "builder" | "auditor" | "agent:<name>"
           Returns a model name like "gpt-4o", "claude-3-5-sonnet", "glm-4.5", etc.
           Applies:
             - baseline mapping from models.yaml
             - per-run overrides
             - provider quota state
           """
   ```

2. **Baseline mapping**:

   * Keep existing `complexity_models` + category overrides in `config/models.yaml`.
   * ModelRouter reads this config at startup (or via injected config object).

3. **Per‑run overrides**:

   * Extend run context to optionally hold:

     ```json
     {
       "model_overrides": {
         "builder": {
           "core_backend:medium": "gpt-4o",
           "security_auth_change:high": "opus-4.5"
         },
         "auditor": { ... }
       }
     }
     ```

   * In `select_model`, check run overrides first; fallback to baseline.

4. **Quota awareness (later):**

   * Use `usage_service` to get provider totals for the current period.
   * If a provider is above `soft_limit`:

     * for non‑critical categories, try fallback models from another provider,
     * for critical categories, either keep primary provider or fail fast (configurable).

5. Wire all Builder/Auditor invocations to use `ModelRouter.select_model` instead of hard‑coded model names.

---

### 2.2 Dashboard API for model mapping and usage

**Goal:** Let the dashboard read and update model mappings and show usage.

**Steps:**

1. Add endpoints in `src/autopack/main.py`:

   * **GET `/dashboard/models`**

     Returns current mapping and allowed choices:

     ```python
     class ModelMapping(BaseModel):
         role: str       # builder / auditor
         category: str
         complexity: str
         model: str
         scope: str      # "global" or "run"
     ```

   * **POST `/dashboard/models/override`**

     Body:

     ```json
     {
       "role": "builder",
       "category": "core_backend",
       "complexity": "medium",
       "model": "gpt-4o",
       "scope": "run",   // or "global"
       "run_id": "optional-if-scope=run"
     }
     ```

     Behaviour:

     * `scope="global"`:

       * Update `models.yaml` (or config DB) and reload config.
       * Only affects **new runs**.
     * `scope="run"`:

       * Update `run_context.model_overrides` for that run.
       * Only affects **future phases** in that run.

2. **GET `/dashboard/usage`**

   * Returns aggregate usage by provider and model for a given period, e.g.:

     ```python
     class ProviderUsage(BaseModel):
         provider: str
         period: str   # "day" | "week" | "month"
         tokens_in: int
         tokens_out: int
         percent_of_cap: float

     class ModelUsage(BaseModel):
         provider: str
         model: str
         tokens_in: int
         tokens_out: int

     class UsageResponse(BaseModel):
         providers: list[ProviderUsage]
         models: list[ModelUsage]
     ```

   * Implementation uses `usage_service`.

---

## Phase 3 – Frontend: minimal dashboard UI

You can implement this as a small React app served by FastAPI, or any simple SPA.

### 3.1 Layout

* **Top bar:**

  * Run selector (dropdown of active/recent runs).
  * Run controls: Start / Pause / Stop.
  * Quick summary of usage per provider (e.g. small badges with `% used`).

* **Left panel: “Run Progress”**

  * Show:

    * run state,
    * `Tier 2 / Phase 4`,
    * total tiers/phases,
    * a progress bar using `percent_complete`.
  * Poll `/dashboard/runs/{run_id}/status` every 5–10 seconds.

* **Right panel: “Model Mapping”**

  * Table for builder and auditor:

    * Rows: `category × complexity`.
    * Columns: current model (dropdown), scope (Global / This run).
  * When you change a dropdown:

    * show “Apply as global default” vs “Apply for this run only”.
    * Call `/dashboard/models/override` accordingly.

* **Bottom panel / separate tab: “Usage”**

  * Summary cards:

    * `OpenAI: 32% of weekly cap`
    * `Anthropic: 18%`
    * `Gemini: 7%`
    * `GLM: 3%`
  * Table of models with tokens over the selected period.

### 3.2 Minimal actions wiring

* **Run controls**:

  * Bind to existing Autopack endpoints (`/runs/start`, `/runs/{id}/pause`, `/runs/{id}/cancel` etc.).
* **Progress updates**:

  * Simple polling; no need for websockets initially.
* **Model mapping updates**:

  * Use the POST `/dashboard/models/override` described above.

---

## Phase 4 – Optional: expose minimal controls to Claude / phone

Later, if you want to control from Claude mobile chat:

* Expose Autopack dashboard API publicly behind auth.
* Give Claude a tool/MCP that can:

  * call `/dashboard/runs/{id}/status`,
  * call `/dashboard/models/override` with limited scope,
  * call run controls (`/runs/start`, `/runs/{id}/cancel`).

Then from your phone you can say:

* “Show me status of the current Autopack run.”
* “For this run, downgrade low‑complexity UI phases to Haiku.”
* “Stop the run if token usage for Anthropic exceeds 80% of weekly cap.”

---

This plan keeps:

* minimal human input (just high‑level steering via dashboard),
* real‑time visibility (tier/phase + progress bar),
* safe model switching (global vs per‑run scope),
* clean usage accounting (internal logs, no scraping).

You can drop this into the repo as `DASHBOARD_AND_MODEL_ROUTER_IMPLEMENTATION_PLAN.md` and let Cursor implement step by step.

Note: some older files you uploaded earlier in the project are no longer available on my side. If you need me to reuse any of those older artefacts for this work, you’ll have to re‑upload them.

if scraping is not possible, and if I keep the usage url open for each llms, can we use tools like gpt atlas to head to the url and screenshot or whatever it is needed then read the usage from there? (if using this method, the update doesn't need to be real time since this might cost us token each time we do this, it can be done every at the end of phases?) and also, since this doens't seem to require complex reasoning, we probably use low llm model for this task to keep the token usage to optimal. (=> if you think this is feasible, please mention to cursor on top of the plan above as a fall back option? - unless you believe retrieving usage information from Autopack log will accurately capture the usage.

Also, also in the above planning, there isn't seem to be a chat bar where I can direct the cursor if there's any change of plan or if there's a need for human intervention (I know we designed so that there shouldn't be but in case unexpected intervention is needed)? or is it best if I do this through cursor app on mobil phone? or can I open dashboard on the cursor app? 

1. **Usage: scraping / GPT Atlas vs Autopack logs**

### 1.1 Is GPT‑Atlas‑style scraping feasible?

Technically possible, but for Autopack I would **not** build this in as an automated mechanism:

* You’d need to:

  * automate login to each provider UI,
  * drive a headless browser to `https://claude.ai/settings/usage`, `https://platform.openai.com/settings/organization/limits`, etc.,
  * grab a screenshot or DOM text,
  * send it to an LLM (Atlas or otherwise) to read the numbers.

* Problems:

  * Fragile: any CSS/HTML change breaks it.
  * Security: you are now storing or scripting with highly sensitive session cookies / tokens.
  * ToS: many providers explicitly forbid automated scraping of their web UIs.
  * Extra cost: you pay tokens every time you ask an LLM to “read” the screenshot/HTML.

For Autopack itself, you **already have perfect data** about Autopack’s own usage:

* Every LLM call Autopack makes can log `provider, model, tokens_in, tokens_out` from the API response.
* That is 100% accurate for Autopack’s share of usage.
* You don’t need an external tool to know what Autopack is spending.

Where Atlas or similar tools make sense is for **you as a human** to get a consolidated view of *all* your usage (Autopack + manual Claude/GPT/etc.) outside Autopack’s concern.

### 1.2 What about plan limits and “global” usage?

You have two usage “domains”:

1. **Autopack usage** (known exactly from internal logs).
2. **Everything else** you do with Claude, GPT, Gemini, GLM (chat, coding, other projects).

Autopack should:

* enforce **its own budgets** based on its logs;
* respect **plan limits** via configuration, not scraping:

  * you tell Autopack:
    `anthropic.weekly_cap = 20M tokens`,
    `autopack_share = 0.5` (Autopack allowed to use 50% of that).

Then its soft limit for Anthropic is:

* `effective_cap = weekly_cap * autopack_share`.

No scraping needed. You adjust these numbers occasionally based on your manual inspection or Atlas.

### 1.3 My recommendation to Cursor

Tell Cursor explicitly:

* **Primary**: Implement usage tracking and budgeting based on **Autopack’s own logs** (as in the previous plan).

* **Optional fallback**: Allow manual override fields in config:

  ```yaml
  providers:
    anthropic:
      weekly_cap_tokens: 20_000_000
      autopack_share: 0.5   # Autopack may spend up to 50% of that
  ```

* Do **not** implement automated scraping or “ask an LLM to read screenshots” in Autopack itself.

* If the user wants to use GPT Atlas or similar:

  * they can do it manually,
  * then adjust `weekly_cap_tokens` or `autopack_share` in Autopack’s config accordingly.

This is simpler, safer, and enough for dynamic model routing and quota‑aware decisions.

If you really want to mention it as a fallback to Cursor, phrase it as:

> “Do not automate scraping/Atlas inside Autopack. Treat provider dashboards and tools like GPT Atlas as human‑level inputs. I will adjust Autopack’s `weekly_cap_tokens` and `autopack_share` manually based on those. Autopack should rely only on its own token logs and configured caps.”

That keeps Autopack clean.

---

2. **Chat / manual intervention from dashboard vs Cursor app**

You’re right: the plan I gave is **status + controls**, not a chat bar.

### 2.1 Do you need a chat bar in the Autopack dashboard?

For v1, I would **not** embed a full chat in the dashboard. Reasons:

* You already have:

  * Cursor (IDE) for code‑centric chat,
  * Claude/GPT apps for planning/analysis chat on phone and PC.
* Building a new chat UI inside Autopack means:

  * another place to manage auth,
  * another LLM client config,
  * duplicated features (history, context selection, etc.).

Better pattern:

* Use the dashboard for:

  * run status,
  * controls (pause/resume/abort, model routing, usage view),
  * links.

* And for **human intervention / plan change**, use:

  * Cursor or Claude chat as you do now,
  * or a button in the dashboard that helps you open the right context there.

### 2.2 Simple integration point instead of chat bar

If you want minimal integration:

* Add a small panel “Intervention helpers” in the dashboard with:

  * A link “Open run context for chat” that:

    * serves a small markdown block with:

      * current run id,
      * last run summary,
      * current tier/phase,
      * maybe links to `comprehensive_plan.md` and strategy file.
    * You copy‑paste that into Claude/Cursor chat on mobile or PC.

* Optionally, have a “Notes to supervisor” textarea:

  * On submit, writes to a file like `human_notes.md` under `.autopack/`.
  * Autopack and your agents can read that file in future planning phases.

Both are far simpler than embedding a full LLM chat in the dashboard.

### 2.3 Using Cursor app and dashboard together

* The Autopack dashboard is just a URL (e.g. `http://localhost:8000/dashboard` or whatever).
* You can:

  * open it in a browser next to Cursor on desktop,
  * open the same URL on your phone browser,
  * in some setups, open it inside a webview in Cursor, but that’s purely an IDE concern.

So your realistic workflow:

* From phone:

  * open Claude app to chat (for plan edits, questions),
  * open dashboard URL in browser to watch progress and press buttons if needed.

* From PC:

  * Cursor for code edits and Autopack implementation,
  * browser tab for Autopack dashboard,
  * Claude/GPT tab for strategic chat.

Autopack itself stays focused: state, control, routing, usage.

---

### What to tell Cursor on top of the existing plan

Add two extra notes:

1. **Usage / Atlas fallback**

   > Do not implement scraping or screenshot‑reading of provider usage pages. Autopack will track its own token usage and respect configured provider caps. I may use external tools (GPT Atlas, provider dashboards) manually, then adjust caps in Autopack config. Treat those as human inputs, not automated flows.

2. **Chat / intervention**

   > Do not embed a full LLM chat bar in the Autopack dashboard for v1. Instead:
   >
   > * Provide a small “Intervention helpers” panel that:
   >
   >   * surfaces current run context (run id, tier/phase, last summary) in a copy‑paste block,
   >   * optionally allows writing a short human note into `.autopack/human_notes.md`.
   > * I’ll use Cursor/Claude apps for actual chat and plan modifications, and the dashboard only for status and control.

That keeps Autopack’s design clean and lets you still intervene from PC or phone when you want.
