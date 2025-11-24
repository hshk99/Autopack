> `autonomous_build_playbook_v7_consolidated.md`


# Autonomous Build Playbook v7 — Consolidated Zero‑Intervention Architecture

**Date:** 2025‑11‑22
**Targets:**
- Supervisor: **Autopack** orchestrator (https://github.com/hshk99/Autopack.git)
- Builder: Cursor Cloud Agents (and similar code‑editing agents)
- Auditor: Codex‑class reviewer
- Verifier: CI system

This v7 document **replaces and consolidates**:

- `autonomous_build_playbook_v6.md`
- `autonomous_build_playbook_v6_add_on.md`
- `autonomous_build_playbook_v6_add_on_v2.md`
- `autonomous_build_playbook_v6_operational_add_on.md`

The goal is a **fully zero‑intervention** build pipeline: once a run starts, no human prompt or approval is allowed until the run ends in a terminal state.

Humans may only:

- prepare or update `comprehensive_plan.md` (and related design docs) **before** a run, and  
- inspect `RUN_SUMMARY.md`, tier summaries, backlogs, and incident packs **after** the run.

All governance during a run is implemented by Supervisor, CI, rulesets, StrategyEngine, and Auditor, not by humans.

---

## 1. Core Zero‑Intervention Contract

1. Once `POST /runs/start` succeeds:
   - The run proceeds through the state machine until `DONE_SUCCESS` or some `DONE_FAILED_*` state.
   - There is no “pause and wait for human” state.
2. All code changes are applied via a **governed apply path** to an **integration branch** only.
   - `main` (or equivalent protected branch) is never written by autonomous agents.
3. Any situation that cannot be resolved within configured budgets or policies yields:
   - automatic failure (`DONE_FAILED_*`),  
   - an incident pack, and  
   - artefacts for post‑run analysis (no interactive fix).

---

## 2. Roles and Responsibilities

### 2.1 Supervisor

- Maintains run, tier, and phase lifecycle.
- Owns rulesets and StrategyEngine.
- Manages budgets and thresholds.
- Triggers and interprets CI.
- Controls the governed apply path (integration branch writing).
- Writes and reads all persistent artefacts under `.autonomous_runs/`.

### 2.2 Builder (Cursor Agents)

- Implements planned work for each phase:
  - edits code, tests, configs, scripts,
  - runs local probes (pytest subsets, scripts, linters),
  - suggests issue entries with context.
- Can create and maintain helper scripts, SKILL files, and ToDo lists.
- Cannot directly change run state; it only submits diffs, logs, and issue suggestions.

### 2.3 Auditor (Codex‑class model)

- Invoked when:
  - major issues appear,
  - failure loops or stalls are detected,
  - high‑risk phases fail or appear risky.
- Reviews diffs, logs, and context.
- Suggests minimal patches and additional issue entries.
- Patches are applied via the same governed apply path as Builder patches.

### 2.4 Verifier (CI)

- Owns all authoritative test execution and static checks.
- Supports **CI profiles** (normal vs strict) tied to risk and complexity.
- Emits structured results consumed by Supervisor and issue logic.

---

## 3. Deterministic Run Lifecycle

Each run follows the same state machine:

1. `PLAN_BOOTSTRAP`
   - Convert project description + prior context into:
     - `spec.md`, `architecture.md`, `context.md`, `reference_repos.md`,
     - initial or updated `comprehensive_plan.md`.
   - Zero‑intervention: executed via Supervisor + Cursor + Codex.

2. `RUN_CREATED`
   - `project_implementation_strategy_vN.json` is computed from:
     - `project_ruleset_vN.json`,
     - issue backlog,
     - safety profile and run scope.
   - Strategy is “frozen” for the current run.

3. `PHASE_QUEUEING`
   - `comprehensive_plan.md` is normalised into:
     - a list of **phases**,
     - grouped into **tiers**.
   - Each phase gets:
     - `phase_id`, `tier_id`, `task_category`, `complexity`, builder mode labels, and budgets.

4. For each queued phase:
   - `PHASE_EXECUTION`
     - Builder receives phase spec.
     - Applies edits and runs local probes.
     - Submits a **builder result** with patches, logs, and suggested issues.

   - `GATE`
     - Supervisor validates:
       - patch structure and scope,
       - static checks,
       - phase‑level probes where applicable.
     - Updates per‑phase issue files from Builder suggestions.

   - `CI_RUNNING`
     - Supervisor triggers CI using the phase/tier’s CI profile.
     - Interprets red/green, flakiness, and budgets.

   - `SNAPSHOT_CREATED`
     - On green CI and acceptable tier policy:
       - changes are committed to the integration branch,
       - a tagged snapshot or similar reference is created.

5. Terminal states:
   - `DONE_SUCCESS`
     - all phases processed according to strategy,
     - no policy violations.
   - `DONE_FAILED_*`
     - e.g. `FAILED_BUDGET_EXHAUSTED`, `FAILED_POLICY_VIOLATION`, `FAILED_REQUIRES_HUMAN_REVIEW`, `FAILED_ENVIRONMENT`, etc.
     - run summary + incident pack are emitted.

No state is advanced by Builder or Auditor directly; Supervisor and CI drive all transitions.

---

## 4. Phases, Tiers, and Run Scope

### 4.1 Phases

- Smallest planned unit of work derived from `comprehensive_plan.md`.
- Each phase has:
  - `phase_id`, `tier_id`,
  - `task_category` (e.g. `schema_change`, `cross_cutting_refactor`, `feature_scaffolding`, `security_auth`, `orchestrator`, `docs`, etc.),
  - `complexity` (`low`, `medium`, `high`),
  - optional `builder_mode` label (see §8),
  - budgets and attempt caps from StrategyEngine.

### 4.2 Tiers

- Logical grouping of phases.
- Examples:
  - “Tier‑4” flow for orchestrator/scaffolding/planner work,
  - “Auth & Security” tier,
  - “DB & Schema” tier,
  - “Experimental UI feature” tier.
- Tiers are used to:
  - aggregate issues and CI results,
  - determine “tier cleanliness”,
  - drive promotion and safety decisions.

### 4.3 Run scope and safety profiles

Config per project:

```json
{
  "default_run_scope": "multi_tier",   // or "single_tier"
  "safety_profile": "normal"           // or "safety_critical"
}
````

* `default_run_scope`:

  * `multi_tier`: a single run can process multiple tiers; tier summaries are emitted but do not block progression.
  * `single_tier`: each run handles a single tier; you run one tier at a time for higher control.
* `safety_profile`:

  * `normal`: tolerates more minor issues, uses normal CI for most work.
  * `safety_critical`: stricter budgets and CI profiles, near‑zero tolerance for unresolved major issues in affected tiers.

These settings are interpreted by StrategyEngine and used to pick defaults for complexity, thresholds, and CI profiles.

---

## 5. Issue Model and Silent Failure Handling

### 5.1 Phase‑level issue files

Each phase has an issue file that records problems without directly changing run state.

* Path (suggested):
  `.autonomous_runs/{run_id}/phase_{k:02d}_{phase_id}_issues.json`

Logical schema excerpt:

```jsonc
{
  "phase_id": "F2.3",
  "tier_id": "T2",
  "issues": [
    {
      "issue_key": "schema_contract_change__users_table__missing_index",
      "severity": "minor",
      "effective_severity": "minor",
      "source": "test", // or probe, ci, static_check, cursor_self_doubt
      "category": "schema_contract_change",
      "task_category": "schema_change",
      "complexity": "high",
      "expected_fail": false,
      "occurrence_count": 1,
      "first_seen_run": "run_001",
      "last_seen_run": "run_001",
      "evidence_refs": [
        "backend/tests/test_users_schema.py::test_indexes_present"
      ]
    }
  ],
  "minor_issue_count": 1,
  "major_issue_count": 0,
  "issue_state": "has_minor_issues"
}
```

* `severity`: how the issue is reported (minor/major).
* `effective_severity`: may be upgraded by aging or rules.
* `source`: probe/test/CI/static_check/self‑doubt.
* `category`: maps to a high‑level failure type.
* `task_category`/`complexity`: mirror the phase’s strategy slice.

Issues are stored and committed on the integration branch so that they travel with code snapshots.

### 5.2 Run‑level issue index (de‑duplication)

To avoid counting the same logical problem many times in a run, Supervisor keeps:

* `.autonomous_runs/{run_id}/run_issue_index.json`

Logical schema excerpt:

```jsonc
{
  "run_id": "run_001",
  "issues_by_key": {
    "schema_contract_change__users_table__missing_index": {
      "category": "schema_contract_change",
      "severity": "minor",
      "effective_severity": "minor",
      "first_phase_index": 2,
      "last_phase_index": 5,
      "occurrence_count": 4,
      "seen_in_tiers": ["T2"],
      "seen_in_phases": ["phase-F2.1", "phase-F2.3"]
    }
  }
}
```

Rules:

* `issue_key` is a stable identifier for the logical issue.
* Phase and tier issue counts operate on **distinct `issue_key`s**, not raw occurrences.
* Repeated detection in the same run increments `occurrence_count` but not `minor_issue_count`/`major_issue_count`.

### 5.3 Cross‑run issue backlog and aging

Supervisor also maintains:

* `project_issue_backlog.json`

Logical schema excerpt:

```jsonc
{
  "project_id": "Autopack",
  "issues_by_key": {
    "schema_contract_change__users_table__missing_index": {
      "category": "schema_contract_change",
      "base_severity": "minor",
      "age_in_runs": 3,
      "age_in_tiers": 2,
      "last_seen_run_id": "run_004",
      "last_seen_at": "2025-11-22T10:23:11Z"
    }
  }
}
```

* Aging thresholds (configurable per strategy slice), e.g.:

  * `minor_issue_aging_runs_threshold` (default 3),
  * `minor_issue_aging_tiers_threshold` (default 2).

When creating a **new** run:

* StrategyEngine checks backlog; if `age_in_runs` or `age_in_tiers` exceed thresholds:

  * treat the issue’s **effective severity** as `major` for routing and thresholds, even if base severity is `minor`,
  * optionally schedule a dedicated **debt‑cleanup phase** for this issue.

### 5.4 Debt‑cleanup phases

When aged minor issues accumulate beyond limits:

* StrategyEngine may insert phases with:

  * `task_category = "debt_cleanup"`,
  * scope restricted to affected code paths,
  * `complexity = "medium"`,
  * cheaper models but bounded budgets,
  * no auto‑apply for known high‑risk categories.

Goal: ensure silent failures either **become blocking major issues** or are **explicitly cleaned up**, not ignored indefinitely.

---

## 6. High‑Risk Categories and Severity Defaults

Some work types are disproportionately dangerous and should bias toward Auditor + strict CI.

Example default mapping:

| High‑risk task type                  | `issues[].category`         | Default severity | Default `task_category`      | Default `complexity` | Default handling (summary)                                  |
| ------------------------------------ | --------------------------- | ---------------- | ---------------------------- | -------------------- | ----------------------------------------------------------- |
| Cross‑cutting renames & refactors    | `cross_cutting_refactor`    | major            | `cross_cutting_refactor`     | high                 | Strict CI, few builder attempts, prefer Auditor on failure. |
| Index / registry / mapping changes   | `index_registry_change`     | major            | `index_registry_maintenance` | high                 | Treat as major; strict CI; low tolerance for minors.        |
| Schema and contract changes          | `schema_contract_change`    | major            | `schema_change`              | high                 | High risk; Auditor + strict CI; often no auto‑apply.        |
| Bulk ops across 10s–100s of files    | `bulk_multi_file_operation` | major            | `bulk_operation`             | high                 | Limit attempts; consider extra chunking or separate runs.   |
| Critical security/auth logic changes | `security_auth_change`      | major            | `security_auth`              | high                 | Always strict CI; prefer `security_review` Auditor profile. |

StrategyEngine uses these defaults when no project‑specific override exists.

For such categories:

* `ci_profile = "strict"` by default.
* `complexity = "high"`.
* Low `max_builder_attempts` and `ci_max_retries`.
* Tight token caps and minor‑issue thresholds.
* Often `auto_apply = false` unless rules explicitly allow it.

---

## 7. StrategyEngine, Rulesets, and Profiles

### 7.1 Ruleset and strategy artefacts

Per project:

* `project_ruleset_vN.json`:

  * declarative policy:

    * high‑risk mappings and overrides,
    * severity upgrades,
    * budget and attempt overrides,
    * safety profile and run scope.
* `project_implementation_strategy_vN.json`:

  * compiled per‑run strategy:

    * per‑phase `task_category`, `complexity`, `builder_mode`,
    * per‑category budgets and thresholds,
    * CI profile (`normal`/`strict`),
    * escalation parameters and Auditor profiles.

StrategyEngine:

* Reads ruleset + backlog.
* Emits strategy:

  * simple enough to be logged and inspected,
  * stable for the duration of a run.

### 7.2 Safety vs cost profiles

Two boolean levers:

* `safety_profile`:

  * `normal`: cost‑conscious; minor issues can accumulate more; multi‑tier runs are fine.
  * `safety_critical`: prioritises correctness; any tier with unresolved major issues should fail the run or block promotion.
* `default_run_scope`:

  * `multi_tier`: best for exploratory or feature work.
  * `single_tier`: best for high‑risk or expensive work (schema, auth, cross‑cutting infra).

Recommended combinations:

1. **Experimental features**

   * `safety_profile = normal`, `default_run_scope = multi_tier`.
   * Tolerate more minor issues but block promotion until cleaned or reviewed.

2. **Auth/security work**

   * `safety_profile = safety_critical`, `default_run_scope = single_tier`.
   * Any unresolved major issue or tier `not_clean` forces `DONE_FAILED` requiring human review.

3. **Infra / cross‑cutting refactors**

   * `default_run_scope = single_tier` recommended.
   * `safety_profile` depends on blast radius; often `safety_critical` for large migrations or routing changes.

---

## 8. Builder Modes and Auditor Profiles

### 8.1 Builder modes

Builder specialisation lives in prompts/SKILLs, not in the state machine. Modes are labelled in `phase.builder_mode` and StrategyEngine labels.

Suggested minimal set:

1. `tweak_light`

   * Small UI tweaks, docs, minor bugfixes.
   * `complexity = low`.
   * Small scopes, cheap models, quick CI.

2. `scaffolding_heavy`

   * Creating new modules, LangGraph nodes, pipelines, scaffolding.
   * `complexity = medium` or `high` depending on reach.
   * Split across multiple phases (scaffolding/tests, backend wiring, frontend integration).

3. `refactor_heavy`

   * Cross‑cutting refactors, orchestrator routing changes, renames.
   * `complexity = high`.
   * Strict budgets and CI, prefer Auditor on repeated failures.

4. `schema_heavy`

   * DB migrations, schema and API contract evolution.
   * `complexity = high`, often `safety_critical`.

Builders are instructed via StrategyEngine what mode a phase uses; SKILLs and prompts interpret the mode.

### 8.2 Influence on chunking and strategy

* `tweak_light`:

  * 1–2 files, small LOC deltas.
  * `max_builder_attempts` small (e.g. 2),
  * `builder_token_cap` small,
  * CI profile quick / normal.

* `scaffolding_heavy`:

  * encourage splitting into 2–3 phases to keep diffs traceable.
  * moderate budgets, normal CI.

* `refactor_heavy` / `schema_heavy`:

  * prefer single‑tier runs,
  * `complexity = high` with strict CI and budgets,
  * additional Auditor preference and high‑risk defaults (see §6).

### 8.3 Auditor profiles

Auditor can be specialised by profile to focus on given risks:

* Example profiles:

  * `schema_review`,
  * `security_review`,
  * `orchestrator_review`,
  * `debt_cleanup_review`.

StrategyEngine maps high‑risk `task_category` + `complexity` combos to appropriate Auditor profiles; e.g. `security_auth` → `security_review`.

---

## 9. Cost Controls and Budgets

### 9.1 Initial defaults (per run)

For a single‑developer repo baseline:

* `run.token_cap` ≈ 5M tokens.
* `run.max_phases` ≈ 25.
* `run.max_minor_issues_total` ≈ `phases_in_run * 3`.
* `run.max_duration_minutes` ≈ 120.

If a run exceeds any of these:

* mark `DONE_FAILED` with `FAILED_BUDGET_EXHAUSTED` (or similar),
* emit an incident pack.

### 9.2 Tier‑level budgets

Per tier:

* `tier.token_cap` ≈ `3 × sum(incident_token_cap for phases in tier)`.
* `tier.ci_run_cap` ≈ `2 × phases_in_tier`.
* `tier.max_minor_issues_tolerated`:

  * normal: `phases_in_tier * 2`,
  * safety‑critical: `phases_in_tier`.
* `tier.max_major_issues_tolerated`:

  * typically `0` for safety‑critical tiers.

If caps are hit:

* tier is marked as not clean and may force run failure, especially under `safety_critical` profile.

### 9.3 Phases and incidents

Per phase:

* `max_builder_attempts`: tuned by `task_category`, `complexity`, and Builder mode.
* `max_auditor_attempts`: smaller than builder attempts; used sparingly.
* `incident_token_cap`: per‑incident cap to prevent infinite thrashing.

Escalation logic:

* repeated low‑signal builder attempts vs budgets trigger Auditor.
* repeated low‑signal Auditor attempts trigger run failure and incident emission.

---

## 10. CI Profiles, Gates, and Promotion Policy

### 10.1 CI profiles

Two main profiles:

* `normal`:

  * unit + integration tests for affected areas,
  * selected e2e tests,
  * minimal retries for non‑flaky tests.

* `strict`:

  * unit + integration + e2e + safety‑critical tests,
  * more complete coverage,
  * near‑zero tolerance for red tests, especially for high‑risk categories.

StrategyEngine selects CI profile based on:

* `task_category`,
* `complexity`,
* `safety_profile`,
* tier risk classification.

### 10.2 Preflight gates and scripts

To align with Tier‑4 behaviour:

* Preflight gate script (example) `scripts/preflight_gate.sh`:

  * wraps tests and checks with up to 3 attempts,
  * handles flakiness detection and retry,
  * fails fast if signals are low and budgets are close to exhausted.

Builder may maintain additional helper scripts (e.g. tier/phase gates) as long as they report results via the governed path.

### 10.3 Tier cleanliness

Each tier has a summary:

* `tier.status` (e.g. `complete`, `failed`, `skipped`),
* counts of unique minor and major issues,
* flags for token and CI caps,
* overall `cleanliness`:

  * `clean` (no problematic issues and budgets okay),
  * `not_clean` (issue thresholds or budgets exceeded).

### 10.4 Promotion from integration to main

Promotion is outside the run lifecycle but constrained by run artefacts:

* `run.promotion_eligible_to_main = true` only if:

  * run is `DONE_SUCCESS`,
  * no tier is `not_clean`,
  * no budget failures occurred.

Even when eligible, promotion can be manual or automated; in either case, autonomous phases never write `main` directly.

---

## 11. Operational Calibration and Observability

### 11.1 Staged adoption

Three implementation stages:

1. **Stage 0 — Baseline instrumentation**

   * Run/tier/phase metrics logging.
   * Simple global caps:

     * `run.token_cap`,
     * `run.max_phases`,
     * global `phase.max_builder_attempts`,
     * global `ci_max_retries`.
   * `run.max_minor_issues_total` and `run.debt_status`:

     * treat all issues as minor,
     * no aging or backlog yet.

2. **Stage 1 — Operational core**

   * Enable `task_category` and `complexity` in StrategyEngine.
   * Implement per‑phase and per‑tier budgets as described in §9.
   * Enforce:

     * `run.max_minor_issues_total`,
     * `tier.max_minor_issues_tolerated`,
     * `tier.max_major_issues_tolerated = 0`.
   * Implement `run.max_phases` splitting:

     * if a plan exceeds ~25 phases, split into multiple runs by tier or feature group.
   * Introduce Builder modes as labels; no heavy special prompts yet.

3. **Stage 2 — Stewardship and debt management**

   * Implement issue aging and the project backlog.
   * Promote aged minor issues to effective major or schedule debt‑cleanup phases.
   * Add Auditor profiles and map them to high‑risk categories.
   * Enforce full promotion‑blocking policy:

     * if any tier is `not_clean`, automated promotion from integration to main is disallowed.

### 11.2 Metrics and logs

Per run, log:

* tokens used per phase, tier, run,
* CI runs per tier,
* issue statistics,
* budgets hit,
* failure reasons.

These support:

* threshold tuning,
* cost analysis,
* identifying high‑value improvements (e.g. flake reduction).

### 11.3 Operational views

Minimal views:

1. **Run list**

   * `run_id`, `status`, `debt_status`, `safety_profile`, `default_run_scope`, failure reason, tokens used, CI runs used.

2. **Tier cleanliness**

   * per tier:

     * status, issue counts, budget flags,
     * `promotion_blocked` boolean.

3. **Issue backlog**

   * top `issue_key`s by:

     * `seen_in_runs`,
     * `seen_in_tiers`,
     * `occurrence_count`.

4. **Budget‑related aborts**

   * recent runs that ended due to budget caps:

     * which tiers were responsible,
     * which `task_category:complexity` slices dominated spend,
     * whether Auditor attempts helped.

---

## 12. Implementation Notes for Agents

While this document is mostly conceptual, agents should treat it as **source of truth** when:

* classifying phases into `task_category` and `complexity`,
* deciding Builder modes and chunk sizes,
* selecting severity for issues,
* deciding when to escalate from Builder to Auditor,
* selecting CI profiles and budgets via StrategyEngine.

Supervisor must enforce the invariants:

* no human in the loop once a run starts,
* deterministic progression or failure,
* integration‑only writes,
* tier‑aware promotion controls,
* structured recording of all issues (silent or otherwise).

Agents (Cursor, Codex) are free to:

* create helper scripts and SKILLs,
* propose better chunking of phases,
* suggest ruleset updates based on patterns,

but all of that manifests via changes to rulesets, strategies, and code, not via interactive prompting mid‑run.

---

**End of Autonomous Build Playbook v7 (Consolidated).**
