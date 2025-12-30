## Implementation Plan Skeleton: True Autonomy (Any Plan → Completed Project)

This document is a **skeleton roadmap** for pushing Autopack toward the “True Autonomy” North Star described in `README.md`.

The goal is **maximum autonomy with minimum token waste**, while keeping safety non-negotiable.

---

## Principles (Do Not Break)

- **Deterministic-first**: Prefer deterministic normalization, scanning, and validation over LLM calls.
- **Semantic intent is a shared invariant**: “Project Intention Memory” is the single source of truth across planning → execution → recovery.
- **Token efficiency is a feature**: Avoid redundant context, avoid re-reading, avoid repeated LLM calls, cache and reuse.
- **Safety & scope are mandatory**: Any write must be in-scope; unsafe operations require human approval or are blocked.
- **Backwards compatible**: New capabilities must not break existing run formats or API clients.

---

## Phase 0: Define the “Project Intention Memory” contract (small, foundational)

### Deliverables
- New file artifact under each run/project:
  - `.autonomous_runs/<project>/intent/intent_v1.json` (or equivalent RunFileLayout location)
- A compact text anchor:
  - `.autonomous_runs/<project>/intent/intent_anchor.txt` (<= ~1–2 KB)

### Intent JSON Schema (v1)
- `project_id`
- `created_at`
- `raw_input_digest` (hash)
- `intent_anchor` (short)
- `intent_facts` (bullet list, normalized constraints)
- `non_goals` (explicit)
- `acceptance_criteria` (high level)
- `constraints` (budget, safety, tech constraints)
- `toolchain_hypotheses` (detected/guessed)
- `open_questions` (must resolve)

### Acceptance Criteria
- Intent artifacts are created deterministically when possible (hashing, file layout).
- Intent anchor is small and stable, and safe to inject in prompts.
- No new mandatory dependencies.

---

## Phase 1: Unstructured Plan → Structured Plan Normalization (tighten the gap)

### Goal
Make Autopack accept “messy plans” (notes, partial requirements) and reliably produce:
- deliverables
- scope.paths + read_only_context
- test/build commands or validation plan
- safe budgets

### Approach
- Add a normalization pipeline (prefer deterministic parsing; LLM only for ambiguity):
  - Extract candidate deliverables from text (regex + heuristics).
  - Infer initial categories (docs/backend/frontend/tests/database) using existing PatternMatcher.
  - Use RepoScanner to ground assumptions in actual repo layout.
  - Run PreflightValidator early; fail fast with actionable errors.
  - Use a minimal LLM call only if confidence is low **and** the questions are specific.

### Memory integration
- Store:
  - raw plan text (truncated + hashed)
  - structured plan result
  - normalization decisions + confidence
in `MemoryService` planning collection so later phases can retrieve it.

### Acceptance Criteria
- For a messy input, Autopack generates a structured plan with:
  - `deliverables` present and normalized
  - `scope.paths` explicit and validated
  - at least one runnable validation step (tests/build or a deterministic probe)
- Added tests for normalization edge cases.

---

## Phase 2: “Project Intention Memory” end-to-end wiring (semantic)

### Goal
Ensure the executor consistently retrieves and uses intention artifacts across:
- manifest generation
- context selection/budgeting
- builder prompts
- auditing
- mid-run replanning / doctor hints

### Work items
- **Planning ingestion**:
  - Add a small script/command to ingest intent + plan into `MemoryService` planning collection.
  - Ensure embeddings are cached and bounded (respect BUILD-145 cap controls).
- **Retrieval usage**:
  - Ensure `retrieve_context(include_planning=True)` returns intention anchor + top-k plan entries.
  - Limit injected context (e.g., max 4k chars) and ensure stable formatting.
- **Goal drift**:
  - Expand goal drift checks to include “intent anchor” (not only run goal/phase description).

### Acceptance Criteria
- Intention is visible in prompts in a compact, stable way.
- Drift detection flags when phases deviate from intent.
- No token-heavy logs; no repeated embedding calls beyond caps.

---

## Phase 3: Universal Toolchain Coverage (pluggable detection + runners)

### Goal
Reduce “works only for Python/Node” risk by making toolchain handling modular:
- detect toolchain(s)
- choose install/build/test commands
- run safely with timeouts and sandboxing

### Approach
- Create a “ToolchainAdapter” interface:
  - `detect(workspace) -> confidence`
  - `install_cmds()`
  - `build_cmds()`
  - `test_cmds()`
  - `smoke_checks()`
- Ship adapters incrementally:
  - Python (pip/uv/poetry)
  - Node (npm/pnpm/yarn)
  - Go
  - Java (maven/gradle)
  - Rust (cargo)
- Keep safety gates: no destructive commands without approval.

### Acceptance Criteria
- For each adapter: detection tests + command selection tests.
- Executor runs appropriate default validation for detected toolchain.

---

## Phase 4: Failure-Mode Hardening Loop (self-improvement, token-cheap)

### Goal
Continuously reduce failure rate by addressing the top recurring failure signatures.

### Approach
- Use DB telemetry + artifacts to cluster failures (phase_outcome + error classifier).
- Add deterministic mitigations:
  - missing dependency detection
  - wrong working directory
  - missing test discovery
  - scope mismatch / outside-scope writes
- Add regression tests for each mitigation.

### Acceptance Criteria
- Top-N failure types show measurable reduction in frequency.
- Hardening changes do not increase token usage materially.

---

## Phase 5: Parallel Execution in “Most Efficient State” (orchestration)

### Goal
Turn existing primitives into a production parallel-run orchestrator:
- `WorkspaceManager` (git worktrees)
- `WorkspaceLease` (exclusive per-workspace)
- `ExecutorLockManager` (one executor per run-id)

### Deliverables
- `scripts/parallel_run_orchestrator.py` (or similar):
  - accepts N run_ids
  - bounded concurrency
  - per-run isolated worktree
  - consolidated report artifact

### Acceptance Criteria
- Two runs can execute concurrently without workspace contamination.
- Locks prevent collisions; failures are isolated per run.
- Throughput improves without compromising safety.

---

## Operational Notes

- Keep all new features opt-in until proven stable.
- Every new “autonomy” feature must come with at least one deterministic test.
- Prefer small artifacts over large context injection.


