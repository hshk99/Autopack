# Cursor Chunk Prompts for Autonomous Build Playbook v7

These prompts assume the file `autonomous_build_playbook_v7_consolidated.md` is present at the repo root.

For each chunk, you paste only the relevant section into Cursor OR say “follow Chunk X from `cursor_chunk_prompts_v7.md`” and let Cursor open the file.

---

## Chunk A — Core run/phase/tier model

**Prompt A**

You are working in the **Autopack** repository to implement **Chunk A** of `autonomous_build_playbook_v7_consolidated.md`.

Goals for this chunk:

- Implement the minimal persistent model for runs, tiers, and phases in the Supervisor.
- Provide basic API endpoints to start a run, inspect run state, and update phase status.
- Do not integrate Cursor or Codex yet; this is purely Supervisor-side state and files.

Instructions:

1. Open `autonomous_build_playbook_v7_consolidated.md` and read Section “Implementation chunk A — Core run/phase/tier model”.
2. Implement:
   - the `runs`, `tiers`, and `phases` persistence (DB models or equivalent),
   - the API endpoints:
     - `POST /runs/start`
     - `GET /runs/{run_id}`
     - `POST /runs/{run_id}/phases/{phase_id}/update_status`
   - the file layout under `.autonomous_runs/{run_id}/` for:
     - `run_summary.md`
     - `tiers/tier_{idx}_{name}.md`
     - `phases/phase_{idx}_{phase_id}.md`
3. Create a script `scripts/autonomous_probe_run_state.sh` that:
   - creates a dummy run,
   - enqueues a dummy tier and phases,
   - advances them through the state machine without touching git,
   - asserts the expected DB entries and files exist.
4. Add unit tests for the run/phase/tier models and endpoints.
5. When done, run:
   - the unit tests you added,
   - `bash scripts/autonomous_probe_run_state.sh`,
   - and show the full output.

Do not change CI workflows yet. You may create or update Supervisor-only modules and configs as needed.

---

## Chunk B — Phase issues, run issue index, and project backlog

**Prompt B**

You are working in the **Autopack** repository to implement **Chunk B** of `autonomous_build_playbook_v7_consolidated.md`.

Goals for this chunk:

- Implement phase-level issue files and a run-level issue index.
- Implement a project-level issue backlog with aging.

Instructions:

1. Open `autonomous_build_playbook_v7_consolidated.md` and read Section “Implementation chunk B — Phase issues, tiers, and backlog”.
2. Implement:
   - helpers in Supervisor to read/write:
     - `.autonomous_runs/{run_id}/issues/phase_{idx}_{phase_id}_issues.json`
     - `.autonomous_runs/{run_id}/issues/run_issue_index.json`
   - a `project_issue_backlog.json` file (or DB table), with aging fields (`seen_in_runs`, `seen_in_tiers`, `last_seen_run`, `status`).
3. Make it easy for Builder and Auditor integrations (later chunks) to append issues by `issue_key` and avoid duplicates within a run.
4. Implement the aging rules:
   - minor issues accumulate `age_in_runs` / `age_in_tiers`,
   - when thresholds are exceeded, mark them as `needs_cleanup` or effective major for future strategies.
5. Create `scripts/autonomous_probe_issues.sh` that:
   - simulates a run with:
     - one phase that logs a minor issue,
     - one phase that logs a major issue,
   - verifies the expected phase files, run index, and backlog entries.
6. Add unit tests around:
   - merging issues into the run index,
   - aging behaviour in the backlog.

Do not integrate StrategyEngine or CI changes yet. Focus on core issue/backlog mechanics.

---

## Chunk C — StrategyEngine, rules, and high-risk mapping

**Prompt C**

You are working in the **Autopack** repository to implement **Chunk C** of `autonomous_build_playbook_v7_consolidated.md`.

Goals for this chunk:

- Implement project rulesets and the StrategyEngine that compiles them into per-run strategies.
- Encode high-risk task categories and Cursor failure-mode mappings.

Instructions:

1. Open `autonomous_build_playbook_v7_consolidated.md` and read Section “Implementation chunk C — StrategyEngine, rules, and high-risk mapping”.
2. Implement:
   - a `project_ruleset_vN.json` format as described,
   - a `project_implementation_strategy_vN.json` format,
   - StrategyEngine code that:
     - loads the current ruleset and issue backlog,
     - maps categories (e.g. `schema_change`, `security_auth`, `cross_cutting_refactor`, `orchestrator`) to:
       - default `complexity`,
       - `ci_profile`,
       - `max_builder_attempts`, `max_auditor_attempts`,
       - `tier.token_cap`, `tier.ci_run_cap`,
       - issue thresholds per tier,
       - `auditor_profile`.
3. Add explicit defaults for high-risk categories as described, including “no auto-apply for destructive changes”.
4. Add a “dry-run” StrategyEngine entry point so we can test rule changes without starting real runs.
5. Create `scripts/autonomous_probe_strategy.sh` that:
   - writes a temporary sample ruleset with at least one high-risk category,
   - runs StrategyEngine,
   - asserts the resulting strategy matches expectations (complexity=high, strict CI, low attempts, etc).
6. Add unit tests for StrategyEngine behaviour and ruleset parsing.

Leave Builder/Auditor integration for Chunk D.

---

## Chunk D — Builder and Auditor integration

**Prompt D**

You are working in the **Autopack** repository to implement **Chunk D** of `autonomous_build_playbook_v7_consolidated.md`.

Goals for this chunk:

- Integrate the Builder (Cursor-Agent) and Auditor (Codex-class) with the Supervisor, without changing the run state machine.

Instructions:

1. Open `autonomous_build_playbook_v7_consolidated.md` and read Section “Implementation chunk D — Builder and Auditor integration”.
2. Implement Supervisor endpoints:
   - `POST /runs/start` (already from Chunk A, now using StrategyEngine),
   - `GET /runs/{run_id}/next_phase` to return the next phase spec,
   - `POST /runs/{run_id}/phases/{phase_id}/builder_result` for Builder results,
   - `POST /runs/{run_id}/phases/{phase_id}/auditor_request` + `/auditor_result`.
3. Define clear payload schemas for:
   - Builder results (diff/patch, probe outputs, suggested issues),
   - Auditor results (review notes, optional patch, suggested issues).
4. Wire the Builder result endpoint so that:
   - patches go through the governed apply path to integration branches,
   - phase status and phase issue files are updated,
   - GATE and CI transitions will be wired in Chunk E.
5. Implement a small “local-only” test harness for Builder/Auditor integration (no real AI calls; just stub them).
6. Create `scripts/autonomous_probe_builder_auditor.sh` that:
   - simulates a failing phase,
   - exercises the builder_result and auditor_result flows with stubs,
   - asserts state transitions and issue logging work end-to-end.

You do not need to connect to real Cursor or Codex here; use stubs or fixtures.

---

## Chunk E — CI profiles, preflight gate, and promotion

**Prompt E**

You are working in the **Autopack** repository to implement **Chunk E** of `autonomous_build_playbook_v7_consolidated.md`.

Goals for this chunk:

- Implement CI profiles (`normal` vs `strict`), preflight gate scripts, and promotion blocking rules.

Instructions:

1. Open `autonomous_build_playbook_v7_consolidated.md` and read Sections:
   - “Implementation chunk E — CI profiles, test tagging, and promotion”
   - “Implementation chunk 7 — CI preflight and preflight gate scripts”
2. Implement:
   - test tagging (`unit`, `integration`, `e2e`, `safety_critical`),
   - `scripts/preflight_gate.sh`:
     - three attempts,
     - backoff,
     - containerized tests,
     - non-zero exit if never green,
   - CI workflows:
     - a preflight workflow that runs `scripts/preflight_gate.sh` on integration branches,
     - a promotion workflow that:
       - reads `run_summary.md` and tier summaries,
       - blocks promotion if any tier is `not_clean` or `debt_status` is `excess_minor_issues`.
3. Create `scripts/autonomous_probe_ci_promotion.sh` that:
   - simulates tier cleanliness combinations and ensures promotion rules behave as specified.
4. Add tests for:
   - CI profile selection given a strategy,
   - promotion blocking logic.

Do not try to fully optimise CI here. Just get the correct behaviour working.

---

## Chunk F — Operational calibration and observability

**Prompt F**

You are working in the **Autopack** repository to implement **Chunk F** of `autonomous_build_playbook_v7_consolidated.md`.

Goals for this chunk:

- Implement basic metrics and logs to support calibration of thresholds and budgets.
- Provide minimal “views” (reports) over runs, tiers, and issues.

Instructions:

1. Open `autonomous_build_playbook_v7_consolidated.md` and read Section “Implementation chunk F — Operational calibration and observability”.
2. Implement:
   - metrics/logging for:
     - tokens used per run/tier/phase (if available),
     - CI runs used per tier,
     - counts of minor/major issues,
     - failure reasons.
   - simple report endpoints or CLI commands to:
     - list recent runs with status and debt_status,
     - show tier cleanliness and promotion eligibility,
     - show top recurring `issue_key`s with aging.
3. Default initial thresholds as described in the playbook and expose them in configuration (not hard-coded magic numbers).
4. Add basic tests to verify:
   - metrics are recorded on state transitions,
   - reports return the expected structure.

Do not add external dashboard tools here; focus on core data and simple text or JSON reports.
