## Autopack Self-Healing & Provider-Routing Implementation Plan

This document captures the implementation plan to make Autopack robustly self-heal and handle provider issues (GLM, Gemini, Claude, GPT‑5) while avoiding long failure loops.

### A. Environment & Provider Health

1. **Centralize `.env` loading**
   - Add explicit `load_dotenv()` in `main.py` and `autonomous_executor.py` so all entrypoints load environment variables automatically.
   - Log presence/absence of critical vars: `OPENAI_API_KEY`, `GLM_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`.

2. **Provider health checks (T0 checks)**
   - Implement `health_checks.py` with:
     - `check_glm_connectivity()`
     - `check_gemini_client()` (import + test call)
     - `check_openai_connectivity()`
     - `check_anthropic_connectivity()`
   - Run these at executor startup; if a provider fails, mark it disabled for this run.

3. **Integrate provider status into `ModelSelector`**
   - Track a `disabled_providers` set.
   - When selecting models from escalation chains or routing policies, skip disabled providers and log the decision.
   - When repeated infra errors are detected for a provider during a run, mark it disabled and route around it.

### B. Fix Core Bugs Blocking Self-Healing

4. **Doctor `json` bug**
   - Ensure `json` is imported in all Doctor paths (e.g., `_parse_doctor_json` in `llm_service.py`).
   - Add tests that simulate Doctor JSON responses and verify no `NameError` occurs.

5. **`LearnedRule` dataclass vs dict mismatch**
   - In `learned_rules.py` and prompt builders, normalize rules before formatting:
     - Accept both `LearnedRule` instances and dicts.
     - Use `asdict(rule)` or attribute access instead of `rule.get(...)`.
   - Add tests for mixed lists of rules.

6. **GPT‑5 parameter compatibility**
   - Update OpenAI client wrappers so GPT‑5 calls use `max_completion_tokens` instead of `max_tokens`.
   - Keep `max_tokens` for earlier models.
   - Add regression tests to confirm correct parameter selection.

7. **Gemini client robustness**
   - Ensure `google-generativeai` is treated as an optional dependency.
   - If the package is missing or initial call fails, clearly log and mark Gemini as disabled for the run.

### C. Controlled Self-Patching of Core Modules

8. **Refine isolation rules**
   - Introduce a `core_maintenance` task category or tier.
   - Allow patches to a small whitelist of core files (e.g., `llm_service.py`, `*_clients.py`, `learned_rules.py`, `config/models.yaml`) when the phase category is `core_maintenance`.
   - Keep the strict block on critical bootstrapping files except in explicit maintenance runs.

9. **Doctor awareness of infra vs code failures**
   - Classify failures into `infra_error`, `patch_apply_error`, `auditor_reject`, etc.
   - Extend Doctor prompts and schema to reason about infra and isolation errors.
   - When Doctor diagnoses infra issues, it should recommend:
     - Disabling or downgrading providers.
     - Scheduling dedicated maintenance phases rather than endlessly retrying feature phases.

10. **Self-maintenance phases**
    - Define Phase 3 maintenance phases such as:
      - `phase3-provider-maintenance`: update `config/models.yaml`, adjust escalation chains, disable bad providers.
      - `phase3-core-bugfix`: patch `llm_service`, client wrappers, `learned_rules` for known error patterns.
    - These phases run with relaxed isolation on the core whitelist and stronger quality/Doctor gating.

### D. Improved Run-Level Self-Healing Behavior

11. **Better failure classification**
    - In `llm_service.py` and `autonomous_executor.py`:
      - Map connection errors, missing library errors, and parameter incompatibilities to `infra_error`.
      - Reserve `auditor_reject` and `patch_apply_error` for true code issues.
    - Use this classification to:
      - Drive provider health updates.
      - Avoid burning Doctor/replan budgets on pure infra faults.

12. **Dynamic Doctor/Replan budgets for infra**
    - For infra-heavy runs, allow extra Doctor/replan calls but only for `core_maintenance` phases.
    - Once providers are stabilized or explicitly disabled, enforce the normal budgets again for application phases.

13. **Unify usage logging across DBs**
    - Ensure API server, executor, and analysis scripts share the same `DATABASE_URL` / DB backend.
    - This lets health checks and Doctor reason about historical provider failures and costs.


