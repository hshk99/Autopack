```text
You are implementing the Autopack “Pivot Intentions → Gap Taxonomy → Autonomy Loop + Safe Parallelism” plan.

Follow this plan exactly (single source of truth):
docs/IMPLEMENTATION_PLAN_PIVOT_INTENTIONS_AUTONOMY_PARALLELISM.md

Non-negotiable direction (aligned to README):
- SOT ledgers in docs/ are canonical memory.
- Execution writes run-local only (.autonomous_runs/...); NEVER write SOT directly from the executor/autopilot.
- Tidy consolidates with explicit gating (--execute) and bounded allowlists.
- Default-deny governance; narrow auto-approval only.
- Parallelism is multi-run only with Four-Layer Safety Model (worktrees + leases + per-run locks + run-scoped artifacts). Do NOT attempt parallel phases within a run.

Work order (do not reorder):
1) Phase 0: add JSON schemas under docs/schemas/ + contract tests.
2) Phase 1: implement Intention Anchor v2 model + write/read alongside existing v1 without breaking changes.
3) Phase 2: implement deterministic gap scanner + CLI (report-only default; --write persists run-local artifact).
4) Phase 3: implement plan proposer (bounded actions; integrates governance + cost estimation).
5) Phase 4: implement autopilot wiring (default OFF; generates artifacts; executes only auto-approved actions).
6) Phase 5: implement/strengthen parallelism contract enforcement + tests (multi-run only).

If you hit ambiguity:
- Do NOT invent policies.
- Check evidence sources referenced in docs/CHAT_HISTORY_EXTRACT_PIVOT_INTENTIONS.md and README/DEC docs.
- Add an “Ambiguity note” comment in the code and a short TODO in the relevant test explaining what decision is needed.

Definition of done:
- All new artifacts validate against schemas.
- All new code is deterministic-first (no LLM required to scan/propose).
- Tests pass: pytest -q
- No writes outside run-local unless explicitly part of tidy’s gated apply.
```
