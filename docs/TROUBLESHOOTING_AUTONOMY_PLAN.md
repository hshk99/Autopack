# Troubleshooting Autonomy Plan (Cursor Tier-4 Parity)

## Goal
Equip Autopack with a governed, evidence-driven troubleshooting agent that can autonomously diagnose failures, run safe probes/commands, and iterate hypotheses—approaching Cursor “tier 4” depth while remaining auditable and budget-aware.

## Principles
- **Safety-first**: Strict allowlist/denylist, timeouts, budget caps, sandboxed worktrees/containers for risky probes.
- **Evidence before action**: Collect logs/traces/stdout/stderr/test output before mutating anything.
- **Hypothesis loop**: Track suspected causes, actions, results; stop when confidence is sufficient or budgets are hit.
- **Minimal disruption**: Read-only probes by default; writes gated behind intent + policy.

## Scope (v1)
- Failure classes: patch/apply, test/CI failures, missing deps/paths, network flakiness, YAML/schema issues.
- Surfaces: executor/doctor flows, manual intent router, future dashboard hook.

## Workstream Breakdown
1) **Governed Command Runner**
   - Command palette: git status/diff, ls/find/du, tail/head, pytest -k <target>, curl/ping/traceroute/dig/nslookup, pip check, python -m site/venv info, disk/mem checks.
   - Policy: allowlist + banned patterns, per-command timeouts, per-run command budget, redaction of secrets in logs.
   - Execution contexts: workspace read-only by default; scratch worktree/container for high-risk probes.

2) **Probe Library**
   - Declarative probes per failure type (e.g., patch apply failure → collect git status/diff, rerun apply with verbose; CI failure → fetch pytest output, rerun targeted test with -vv).
   - Probe selection heuristic: map error signatures to ordered probe sets; short-circuit on resolution.
   - Artifacts: store probe outputs under `.autonomous_runs/<run_id>/diagnostics/` and log summaries to DecisionLog + memory.

3) **Hypothesis & Evidence Tracker**
   - Maintain in-memory ledger per failure: {hypothesis, evidence, actions, outcome, confidence}.
   - Persist short summaries to DecisionLog + vector memory for recall.
   - Escalation rules: stop after N probes or low confidence, suggest human handoff.

4) **Signal Capture**
   - Auto-attach recent stdout/stderr, builder/auditor logs, patch-apply traces, failing test output, env/package versions, disk space, git status.
   - Optional: lightweight perf/network snapshots (latency to API/model endpoints).

5) **Interfaces**
   - Executor/Doctor: when failure occurs, invoke diagnostics agent with context; agent returns suggested action + evidence bundle.
   - Intent router: add intents like “diagnose patch failure”, “why did CI fail?” to trigger probes safely.
   - Dashboard (future): read-only view of hypotheses, probes run, and evidence.

6) **Safety & Budgets**
   - Per-run probe budget (count/time), per-command timeout, max concurrent probes = 1.
   - Explicit denylist (rm -rf, sudo, network egress to unknown hosts); only whitelisted paths.
   - Dry-run mode for verification.

## Milestones
- **M1 (safety shell)**: Command runner with allowlist/timeouts/budgets; basic probes for patch/test failures; evidence capture; persist DecisionLog/memory entries.
- **M2 (hypothesis loop)**: Hypothesis/evidence tracker; heuristic probe selection; structured summaries; intent-router hooks.
- **M3 (coverage)**: Expand probes to deps/env/network; add sandboxed worktree; add CI log ingestion; dashboard read-only panel.

## Risks / Mitigations
- Command safety: keep allowlist tight; log every command + output; sandbox for writes.
+- Cost/time overrun: enforce budgets; short-circuit on confidence; prioritize cheap probes first.
- Signal gaps: add fallbacks (tail logs, rerun targeted test) before marking “needs human”.

