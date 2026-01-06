# Implementation Plan: Pivot Intentions → Gap Taxonomy → Autonomy Loop + Safe Parallelism (Universal)

**Audience**: implementation cursor / engineering agent  
**Status**: plan only (do not implement in this doc)  
**Aligned to README “ideal state”**: safe, deterministic, mechanically enforceable; SOT ledgers as canonical memory; execution writes run-local; tidy consolidates; explicit gating and approvals.

---

## Direction (explicit, no ambiguity)

1. **Canonical truth** is the SOT ledgers in `docs/` (plus other SOT sources already treated as canonical by this repo’s contracts, e.g., `docs/PROJECT_INDEX.json`, `docs/LEARNED_RULES.json`).
2. **Execution writes run-local only** under `.autonomous_runs/<project>/runs/<family>/<run_id>/...` (never writes SOT ledgers directly).
3. **Tidy consolidates** run-local artifacts into SOT ledgers **only** via explicit operator intent (`--execute`) and strict allowlists (bounded, idempotent, append-only).
4. **Autonomy is bounded**: Autopack may propose plans without being asked, but may only execute plans that pass:
   - deterministic gates
   - budget gates
   - governance approval gates (default-deny; narrow auto-approval only)
5. **Parallelism** is allowed **only** with the Four-Layer Safety Model (worktrees + workspace leases + per-run executor locks + run-scoped artifacts). Parallel phases within a single run remain “not recommended.”

---

## Inputs (source of requirements)

Primary requirements should be derived from the repository’s documented “pivot intentions” and contracts:
- `docs/CHAT_HISTORY_EXTRACT_PIVOT_INTENTIONS.md` / `.json` (taxonomy + evidence + blockers)
- `README.md` (core principles + “one stream” flow)
- `docs/ARCHITECTURE_DECISIONS.md` (DEC-041, DEC-042, governance/budget decisions)
- `docs/GOVERNANCE.md` (default-deny, NEVER_AUTO_APPROVE list)
- `docs/PARALLEL_RUNS.md` (Four-Layer Safety Model)
- `docs/DEBUG_LOG.md` + `docs/BUILD_HISTORY.md` (failure modes, drift patterns)

---

## Key Concepts (pivot intention types; universal)

Autopack must explicitly capture and enforce these **pivot intention types** (do not chase technical details):

1. **NorthStar/Value**: desired outcomes + success signals + non-goals
2. **Safety/Risk**: what must never happen; what requires approval
3. **Evidence/Verification**: hard blocks; required checks; proof artifacts
4. **Scope/Boundaries**: allowed write roots; protected paths; network allowlist
5. **Budget/Cost**: token/time caps; cost escalation policy
6. **Memory/Continuity**: what persists to SOT; derived indexes; retention rules
7. **Governance/Review**: default-deny; auto-approval rules; approval channels
8. **Parallelism/Isolation** (optional unless enabled): isolation model requirements

---

## Deliverable Set (what must be built)

### Deliverable 1: Canonical schemas (machine-readable)

Add strict JSON schemas under `docs/schemas/`:

- `docs/schemas/intention_anchor_v2.schema.json`
- `docs/schemas/gap_report_v1.schema.json`
- `docs/schemas/plan_proposal_v1.schema.json`

**Design rule**: schemas must be strict enough to be mechanically enforceable, but small enough to stay stable. All schemas must have `format_version`.

### Deliverable 2: Run-local artifacts (runtime outputs)

Standardize run-local artifact paths (resolved via `RunFileLayout`, no hardcoded paths):

- `.../intention/intention_anchor_v2.json`
- `.../gaps/gap_report_v1.json`
- `.../plans/plan_proposal_v1.json`
- `.../proofs/<phase_id>.json` (already exists for phase proofs; keep consistent)

### Deliverable 3: Deterministic gap scanner (read-only)

Add a “gap scanner” that produces `GapReportV1` without needing LLM calls.

### Deliverable 4: Plan proposer (bounded)

Create a proposer that maps `(IntentionAnchorV2 + GapReportV1 + optional SOT retrieval)` → `PlanProposalV1`.

### Deliverable 5: Autonomy loop wiring (safe-by-default)

An opt-in loop that can:
- periodically generate gap reports
- propose plans
- execute only low-risk auto-approved actions
- otherwise request approvals (PR/Telegram/CLI) but still record proposals

### Deliverable 6: Parallelism contract enforcement (Four-Layer model)

Implement (or harden if already present) the explicit contract to run multiple runs concurrently safely using isolated worktrees and leases.

---

## Phase Plan (implementation steps; in order)

### Phase 0 — Schema contracts first (mechanical enforcement)

**Goal**: make the new artifacts enforceable before wiring them into autonomy.

**Work**
- Add the 3 JSON schema files under `docs/schemas/`.
- Add a schema validator utility:
  - `src/autopack/schema_validation/json_schema.py` (or similar)
  - Must validate using `jsonschema` or a minimal validator already in repo; if new dependency is required, justify it and gate it.
- Add contract tests:
  - `tests/schemas/test_intention_anchor_v2_schema.py`
  - `tests/schemas/test_gap_report_v1_schema.py`
  - `tests/schemas/test_plan_proposal_v1_schema.py`

**Acceptance criteria**
- Valid sample JSON passes.
- Invalid JSON fails with clear error messages.
- Tests run offline and deterministically.

**Ambiguity resolution**
- If you must avoid new deps: implement a minimal schema checker for required keys/types only (but prefer `jsonschema` if already present / acceptable).

---

### Phase 1 — Intention Anchor v2 (pivot intentions only)

**Goal**: standardize “pivot intention types” as a single artifact that works for any future project.

**Work**
- Create `src/autopack/intention_anchor/v2.py`
  - `IntentionAnchorV2` model (Pydantic recommended, matching schema)
  - `create_from_inputs(...)` that merges:
    - explicit user inputs (preferred)
    - deterministic inference (optional)
  - `validate_pivot_completeness()` returns missing pivot types as questions
- Extend `ProjectIntentionManager` to optionally write v2 alongside existing v1 artifacts:
  - No breaking changes; v1 remains supported.

**Acceptance criteria**
- Can write v2 anchor deterministically given minimal inputs.
- If missing pivots, produces a bounded “clarifying questions” list (max 8).
- Never writes outside run-local paths.

**Ambiguity resolution**
- **Who authors the intention?** Direction: human-provided is canonical; Autopack can propose clarifications, not silently invent intent.

---

### Phase 2 — Gap scanner (deterministic-first)

**Goal**: replace “search prior chats” with durable `GapReportV1`.

**Work**
- Add `src/autopack/gaps/scanner.py`
  - Scans for the known gap types (from `docs/CHAT_HISTORY_EXTRACT_PIVOT_INTENTIONS.json`):
    - doc drift, root clutter, SOT duplicates, test infra drift, memory budget issues, Windows encoding issues,
      baseline policy drift, protected path violations, DB lock contention, git state corruption
  - Each gap must include:
    - detection signal(s)
    - evidence pointers (file path, failing test name, excerpt hash)
    - risk classification
    - whether it blocks autopilot
- Add CLI:
  - `python -m autopack.gaps.scan --run-id ... --project-id ... [--write]`
  - Default is report-only (prints + returns JSON to stdout); `--write` persists run-local artifact.

**Acceptance criteria**
- Gap scanner is read-only unless `--write`.
- Outputs are stable for the same workspace state.

**Ambiguity resolution**
- “Doc drift” should be detected via existing doc contract tests/scripts when possible (do not invent new heuristics if existing gates exist).

---

### Phase 3 — Plan proposer (bounded, governed)

**Goal**: map gaps → actions under strict governance and budgets.

**Work**
- Add `src/autopack/planning/plan_proposer.py`
  - Input: `IntentionAnchorV2`, `GapReportV1`, optional memory retrieval summaries
  - Output: `PlanProposalV1` with bounded actions
- Add risk scoring + approval classification
  - Must integrate with existing governance ideas:
    - default-deny
    - narrow auto-approval rules
    - NEVER_AUTO_APPROVE paths
- Add CLI:
  - `python -m autopack.planning.propose --run-id ... --project-id ... [--write]`

**Acceptance criteria**
- No action can target disallowed paths.
- High-risk actions are always “proposal only” unless approved.
- Cost estimates are conservative; if uncertain, mark “requires approval”.

**Ambiguity resolution (explicit)**
- **What can auto-apply?** Direction: only low-risk, small diffs, allowed paths, and not in NEVER_AUTO_APPROVE.

---

### Phase 4 — Autonomy loop wiring (opt-in, safe)

**Goal**: Autopack can push forward without prompting, but only within safe gates.

**Work**
- Add an “autopilot controller”:
  - `src/autopack/autonomy/autopilot.py`
  - Steps:
    1) load anchor (v2)
    2) scan gaps
    3) propose plan
    4) if all actions auto-approved: execute bounded batch
    5) else: emit approval requests + stop (but record artifacts)
- Emit run-local “autopilot session” log:
  - `.../autonomy/autopilot_session_v1.json`

**Acceptance criteria**
- Default OFF (explicit enable flag required).
- On enable: still respects approvals; never silently escalates budgets.
- Always records what it *would* do when blocked.

---

### Phase 5 — Parallelism enforcement (Four-Layer model; run-level parallelism)

**Goal**: safe multi-run execution without workspace contamination.

**Work**
- Standardize “parallel run” orchestrator behavior (prefer existing structures if present):
  - Ensure each run uses:
    - git worktree isolated checkout
    - workspace lease
    - per-run executor lock
    - run-scoped artifacts (no shared `baseline.json`, no shared retry files)
- Add explicit “parallelism policy” gate:
  - If `IntentionAnchorV2.parallelism_policy.allowed != true`, block parallel execution.

**Acceptance criteria**
- Two runs can execute concurrently without git state corruption.
- Failures in one run do not pollute the other run’s workspace or artifacts.

**Ambiguity resolution**
- Parallelism within a single run remains out of scope (per repo guidance); parallelism is **multi-run only**.

---

## Skeleton Structure (files to create/modify)

### New files (suggested)
- `docs/schemas/intention_anchor_v2.schema.json`
- `docs/schemas/gap_report_v1.schema.json`
- `docs/schemas/plan_proposal_v1.schema.json`
- `src/autopack/intention_anchor/v2.py`
- `src/autopack/gaps/scanner.py`
- `src/autopack/planning/plan_proposer.py`
- `src/autopack/autonomy/autopilot.py`
- `tests/schemas/test_intention_anchor_v2_schema.py`
- `tests/schemas/test_gap_report_v1_schema.py`
- `tests/schemas/test_plan_proposal_v1_schema.py`
- `tests/autonomy/test_gap_scanner_determinism.py`
- `tests/autonomy/test_plan_proposer_governance.py`
- `tests/autonomy/test_autopilot_blocks_without_approval.py`
- `tests/parallelism/test_parallelism_policy_gate.py`

### Existing files likely to be extended (avoid breaking changes)
- `src/autopack/project_intention.py` (add v2 write/read alongside v1)
- `src/autopack/autonomous_executor.py` (optional: entrypoints to run autopilot loop; default off)
- `src/autopack/file_layout.py` (ensure directories exist for new artifact categories)

---

## Mechanical policies (must be enforced by tests)

- **No SOT writes** from report/plan/autopilot unless explicitly in a gated tidy apply step.
- **Deterministic ordering** for all arrays in JSON artifacts.
- **No secrets** written into artifacts (strip env vars, tokens).
- **Budget telemetry** recorded for retrieval/embedding decisions.
- **Approval traceability**: every executed action references:
  - `anchor_id`
  - `gap_report_id`
  - `plan_proposal_id`

---

## Known ambiguities (resolved here)

1. **Can Autopack auto-change intentions?**  
   **No.** It may propose clarifying questions or a revised anchor, but requires explicit user approval to update the canonical intention.

2. **Can Autopack write to SOT directly?**  
   **No.** Execution is run-local; tidy consolidates (gated, idempotent).

3. **Can Autopack run parallel phases within a run?**  
   **No (out of scope).** Parallelism is multi-run only under the Four-Layer model.

4. **Can Autopack auto-approve risky changes?**  
   **No.** Default-deny; narrow auto-approval only. Any uncertainty → requires approval.

---

## Validation commands (for implementer)

- `pytest -q`
- Schema tests subset:
  - `pytest -q tests/schemas/`
- Gap/proposer tests subset:
  - `pytest -q tests/autonomy/`
- Parallelism tests subset:
  - `pytest -q tests/parallelism/`


