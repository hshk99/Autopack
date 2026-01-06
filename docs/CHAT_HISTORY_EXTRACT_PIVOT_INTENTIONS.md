# Chat History Extract (SOT-Derived): Pivot Intentions, Gap Types, Autonomy Loop, Parallelism Contract

**Purpose**: Provide an evidence-backed, portable substitute for “Cursor chat history” by extracting the durable decision-making trail from Autopack’s SOT/docs.  
**Scope**: Pivot intentions + recurring gap types + observed autonomy loop + parallelism isolation model.  
**Source**: Repository SOT/docs (not live Cursor chat transcripts).  
**Extraction Date**: 2026-01-06

---

## A) Pivot Intentions (PI)

> **Definition**: “Pivot intentions” are the few intention types that determine safe autonomous progress. They are intentionally higher-level than implementation details.

### PI-001: Safe, deterministic, mechanically enforceable
- **Type**: NorthStar/Value
- **Statement**: Autopack prioritizes safety contracts that are mechanically enforceable via CI and deterministic by design, preventing silent drift/regression.
- **Enforcement**: CI contract tests; PR-blocking checks; deterministic scripts; explicit gates.
- **Evidence**:
  - README: “safe, deterministic, mechanically enforceable via CI contracts”

### PI-002: SOT ledgers as canonical memory (“one stream”)
- **Type**: Memory/Continuity
- **Statement**: Durable memory lives in `docs/` ledgers; derived indexes are rebuildable; LLMs should rely on SOT, not ephemeral chat.
- **Evidence**:
  - README: SOT ledgers + “one stream” plan→build→tidy→memory→reuse
  - DEC-042: execution writes run-local; tidy consolidates

### PI-003: Intention Anchor as first-class, versioned artifact
- **Type**: NorthStar/Value
- **Statement**: Capture “user intent” as a compact, explicit, versioned anchor threaded through plan/build/audit/SOT/retrieval.
- **Evidence**:
  - DEC-041: intention anchor lifecycle as first-class artifact

### PI-004: Execution writes run-local; tidy consolidates (never autonomous SOT writes)
- **Type**: Scope/Boundaries
- **Evidence**:
  - DEC-042

### PI-005: Default-deny governance; narrow auto-approval rules
- **Type**: Governance/Review
- **Evidence**:
  - `docs/GOVERNANCE.md` (default-deny; NEVER_AUTO_APPROVE)

### PI-006: Baseline updates explicit; never automatic
- **Type**: Safety/Risk
- **Evidence**:
  - `docs/SECURITY_LOG.md` + DEC-043/DEC-045

### PI-007: High-signal security gating (shift-tolerant normalization)
- **Type**: Evidence/Verification
- **Evidence**:
  - DEC-045 (fingerprint-based SARIF normalization)

### PI-008: Token budgets are enforced (global + per-call) with telemetry
- **Type**: Budget/Cost
- **Evidence**:
  - DEC-017 (two-stage budget enforcement)

### PI-009: Derived indexes are rebuildable and must be explicitly targeted (no surprises)
- **Type**: Memory/Continuity
- **Evidence**:
  - `docs/REMAINING_IMPROVEMENTS_AFTER_BUILD_162.md` definitions (“markdown SOT is canonical; DB/Qdrant derived”)

### PI-010: Boundary tests must hit real routes (avoid false-green)
- **Type**: Evidence/Verification
- **Evidence**:
  - DEC-040

### PI-011: “Contract tests over promises” (encode desired behavior mechanically)
- **Type**: Evidence/Verification
- **Evidence**:
  - DEC-039

### PI-012: Tidy is manual-only and safe-by-default (dry-run; explicit `--execute`)
- **Type**: Safety/Risk
- **Evidence**:
  - `docs/TIDY_SYSTEM_USAGE.md`, `docs/CURSOR_PROMPT_TIDY.md`

### PI-013: Windows-first resilience where applicable (encoding/locks)
- **Type**: Evidence/Verification
- **Evidence**:
  - `docs/TIDY_LOCKED_FILES_HOWTO.md` + multiple BUILD/DBG entries

### PI-014: Parallelism requires full isolation (Four-Layer Safety Model)
- **Type**: Parallelism/Isolation
- **Evidence**:
  - `docs/PARALLEL_RUNS.md`

### PI-015: No parallel phases within a single run (merge/ordering risk)
- **Type**: Parallelism/Isolation
- **Evidence**:
  - `docs/PARALLEL_RUNS.md` (“Not recommended: parallel phases within single run”)

### PI-016: Approval artifacts required for destructive operations
- **Type**: Governance/Review
- **Evidence**:
  - Storage optimizer execution guides (approval artifact gate)

### PI-017: Record decisions, not just outcomes (append-only audit trail)
- **Type**: Governance/Review
- **Evidence**:
  - SOT ledgers (BUILD/DEBUG/ADR) + governance docs

---

## B) Gap Types (with detection signals)

> **Definition**: A gap type is a recurring “current vs ideal” mismatch that Autopack can detect deterministically and either fix or propose fixes for.

1) **doc_drift**
- **Signals**: docs-sot-integrity CI job; README SOT summary drift; link checker drift
- **Safe remediation**: report-only → plan → apply with gating; idempotent marker updates

2) **root_clutter**
- **Signals**: tidy root routing; verifier reports disallowed root files
- **Safe remediation**: tidy dry-run, then `--execute` with checkpoints

3) **sot_duplicate**
- **Signals**: tidy root-vs-docs duplicate detection reports
- **Safe remediation**: block on divergent duplicates; route identical duplicates to superseded

4) **test_infra_drift**
- **Signals**: flaky/false-green tests; boundary tests not hitting real routes
- **Safe remediation**: rewrite tests to exercise real runtime paths (DEC-040)

5) **memory_budget_cap_issue**
- **Signals**: retrieval truncation; cap telemetry; missing SOT retrieval toggles
- **Safe remediation**: enforce two-stage budgets; fallback behavior; record telemetry

6) **windows_encoding_issue**
- **Signals**: UnicodeEncodeError/charmap failures; lock status output issues
- **Safe remediation**: ASCII mode; stdout reconfigure; avoid emoji in critical CLIs

7) **baseline_policy_drift**
- **Signals**: security baseline diffs; non-canonical baseline updates
- **Safe remediation**: explicit baseline refresh SOP + security log entry

8) **protected_path_violation**
- **Signals**: governed apply rejects; deliverables validator wrong roots
- **Safe remediation**: strict allowlists; manifest gates; protected paths communicated upfront

9) **db_lock_contention**
- **Signals**: SQLite write contention; lock errors; flaky concurrent writes
- **Safe remediation**: per-run isolation; avoid shared SQLite writes; use Postgres when enabled

10) **git_state_corruption**
- **Signals**: merge markers; reset/clean side effects; workspace collisions
- **Safe remediation**: isolate workspaces via git worktrees; leases; per-run rollback boundaries

---

## C) Autonomy Loop Observations (SOT-derived)

Observed loop (intended “one stream”):
1. **Detect** gaps (deterministic checks/scripts)
2. **Plan** bounded actions (proposal artifacts)
3. **Build/Execute** run-local only
4. **Verify** (tests/validators; hard blocks enforced)
5. **Govern** (approval gate if not auto-approvable)
6. **Apply** (only when gated; never silently)
7. **Audit** (independent reviewer/auditor role)
8. **Record** outcomes + decisions (run-local + SOT consolidation)
9. **Consolidate** via tidy (append-only)
10. **Index** SOT if enabled (dirty marker → one re-index)
11. **Retrieve** under budget caps in later runs

---

## D) Parallelism Blockers + Minimum Contract

### Concrete blockers (why “parallel by default” is unsafe)
- Workspace-global git rollback/reset/clean is not compatible with shared workspaces.
- SQLite does not safely support concurrent writers for this workload.
- Shared `.autonomous_runs` artifacts collide unless run-scoped.
- Without leases, two processes can mutate same path.

### Minimum viable safe parallelism contract (multi-run only)
- **Worktree isolation** per run
- **Workspace lease** per physical path
- **Per-run executor lock** (one executor per run_id)
- **Run-scoped artifacts** (no shared baseline/retry files)

---

## E) Missing info (if you want “real chat quotes”)

This extract is intentionally SOT-derived. If you want verbatim Cursor chat quotations, those must be exported from Cursor and committed as artifacts; Autopack should not depend on vendor chat APIs.


