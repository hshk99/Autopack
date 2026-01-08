# Autopilot Operations Runbook (BUILD-179)

**Purpose**: Operator guide for running the autonomy loop (gap scan → plan → autopilot → supervise)

**Last Updated**: 2026-01-06

---

## Overview

The Autopack autonomy loop provides bounded, governance-gated autonomous execution:

1. **Gap Scan**: Identify drift, violations, and issues (deterministic)
2. **Plan Propose**: Map gaps to actions with governance checks
3. **Autopilot Run**: Execute auto-approved actions (single run)
4. **Autopilot Supervise**: Parallel execution with policy gates

All operations are **safe-by-default**:
- Gap scan is read-only unless `--write` is specified
- Autopilot is disabled unless `--enable` is explicitly passed
- Parallel execution requires `IntentionAnchorV2` with `parallelism_isolation.allowed=true`

---

## Prerequisites

### 1. Create an Intention Anchor

Every run requires an `IntentionAnchorV2` anchor file that defines:
- Allowed operations and scope
- Protected paths (never modify)
- Budget limits (tokens, time, file count)
- Parallelism isolation settings

**Example anchor** (`.autonomous_runs/<project>/runs/<family>/<run_id>/intention_v2.json`):

```json
{
  "schema_version": "2.0",
  "anchor_id": "anchor-20260106-001",
  "run_id": "my-run-001",
  "project_id": "autopack",
  "created_at": "2026-01-06T12:00:00Z",
  "intent": {
    "goal": "Clean up documentation drift and fix test failures",
    "scope": "docs/ and tests/ directories only"
  },
  "constraints": {
    "allowed_paths": ["docs/", "tests/", "scripts/"],
    "protected_paths": ["src/autopack/", ".git/", ".env"],
    "max_file_changes": 50,
    "max_token_budget": 100000
  },
  "parallelism_isolation": {
    "allowed": false,
    "max_concurrent_runs": 1,
    "isolation_level": "worktree"
  }
}
```

### 2. Run Directory Structure

The canonical layout follows `RunFileLayout` from `src/autopack/file_layout.py`:

```
.autonomous_runs/<project>/runs/<family>/<run_id>/
├── intention_v2.json       # Anchor (required)
├── gaps/
│   └── gap_report_v1.json  # Output from gap scan
├── planning/
│   └── plan_proposal_v1.json  # Output from plan propose
├── autopilot/
│   └── session_<id>.json   # Output from autopilot run
├── tiers/                  # Tier summaries
├── phases/                 # Phase summaries
└── run_summary.md          # Overall run summary
```

Where:
- `<project>`: Project identifier (e.g., `autopack`, `file-organizer-app-v1`)
- `<family>`: Run family extracted from run_id prefix (e.g., `build-193` from `build-193-fix-gaps`)
- `<run_id>`: Full run identifier (e.g., `build-193-fix-gaps`)

---

## CLI Commands

All commands use the unified CLI: `python -m autopack.cli <command>`

### Gap Scan

Scan workspace for gaps (documentation drift, violations, test failures).

```bash
# Report only (prints JSON to stdout, no artifact written):
python -m autopack.cli gaps scan \
  --run-id my-run-001 \
  --project-id autopack

# Write gap report to run-local artifact:
python -m autopack.cli gaps scan \
  --run-id my-run-001 \
  --project-id autopack \
  --write
```

**Options**:
- `--run-id`: Run identifier (required)
- `--project-id`: Project identifier (required)
- `--write`: Write gap report to `.autonomous_runs/<project>/runs/<family>/<run_id>/gaps/`
- `--workspace`: Workspace root (default: current directory)
- `-v, --verbose`: Enable debug logging

**Output**: JSON gap report with gaps categorized by type, severity, and autopilot-blocking status.

### Plan Propose

Generate a plan from anchor and gap report.

```bash
# Report only:
python -m autopack.cli plan propose \
  --run-id my-run-001 \
  --project-id autopack

# Write plan proposal:
python -m autopack.cli plan propose \
  --run-id my-run-001 \
  --project-id autopack \
  --write
```

**Options**:
- `--run-id`: Run identifier (required)
- `--project-id`: Project identifier (required)
- `--write`: Write plan to `.autonomous_runs/<project>/runs/<family>/<run_id>/planning/`
- `--anchor-path`: Override anchor location
- `--gap-report-path`: Override gap report location
- `-v, --verbose`: Enable debug logging

**Output**: JSON plan with actions, governance checks, and approval status.

### Autopilot Run (Single Run)

Execute autopilot session for a single run.

```bash
# Dry-run (DISABLED by default, safe):
python -m autopack.cli autopilot run \
  --run-id my-run-001 \
  --project-id autopack

# ENABLE autopilot and execute:
python -m autopack.cli autopilot run \
  --run-id my-run-001 \
  --project-id autopack \
  --enable \
  --write
```

**Options**:
- `--run-id`: Run identifier (required)
- `--project-id`: Project identifier (required)
- `--enable`: **REQUIRED** to actually execute actions (default: OFF)
- `--write`: Write session to `.autonomous_runs/<project>/runs/<family>/<run_id>/autopilot/`
- `--anchor-path`: Override anchor location
- `-v, --verbose`: Enable debug logging

**Safety**:
- Without `--enable`, autopilot runs in dry-run mode (no changes)
- Only auto-approved actions are executed
- Actions requiring approval are queued for human review

### Autopilot Supervise (Parallel Runs)

Execute multiple runs in parallel with policy enforcement.

```bash
# Run 3 workers with Postgres (requires anchor with parallelism allowed):
python -m autopack.cli autopilot supervise \
  --run-ids run1,run2,run3 \
  --anchor-path anchor.json \
  --workers 3 \
  --database-url postgresql://autopack:autopack@localhost:5432/autopack

# Run 2 workers with per-run SQLite:
python -m autopack.cli autopilot supervise \
  --run-ids run1,run2 \
  --anchor-path anchor.json \
  --workers 2 \
  --per-run-sqlite

# List existing worktrees:
python -m autopack.cli autopilot supervise --list-worktrees

# Cleanup all worktrees:
python -m autopack.cli autopilot supervise --cleanup
```

**Options**:
- `--run-ids`: Comma-separated run IDs (required for execution)
- `--anchor-path`: Path to IntentionAnchorV2 JSON (**REQUIRED** for parallel execution)
- `--workers`: Max concurrent workers (default: 3)
- `--database-url`: Database URL (Postgres recommended for parallel)
- `--per-run-sqlite`: Use per-run SQLite (limits aggregation)
- `--list-worktrees`: List existing worktrees and exit
- `--cleanup`: Remove all worktrees and exit

**Safety**:
- **BLOCKED** unless anchor has `parallelism_isolation.allowed=true`
- Each run gets isolated git worktree
- Workspace leases prevent concurrent access
- Database must be Postgres for parallel writes (or use `--per-run-sqlite`)

---

## Parallelism Policy Gate

Parallel execution requires explicit authorization via the intention anchor.

### Enable Parallelism

1. Set `parallelism_isolation.allowed = true` in anchor
2. Set appropriate `max_concurrent_runs` limit
3. Choose isolation level (`worktree` recommended)

**Example anchor with parallelism enabled**:

```json
{
  "parallelism_isolation": {
    "allowed": true,
    "max_concurrent_runs": 5,
    "isolation_level": "worktree"
  }
}
```

### Parallelism Blocked Errors

If you see:
```
[Supervisor] PARALLELISM BLOCKED: ...
```

Check:
1. Anchor file exists at specified path
2. Anchor has `parallelism_isolation.allowed = true`
3. Requested workers ≤ `max_concurrent_runs`

---

## Artifact Types

### GapReportV1

Location: `.autonomous_runs/<project>/runs/<family>/<run_id>/gaps/gap_report_v1.json`

Contains:
- List of gaps with type, severity, evidence
- Summary (total gaps, blockers, by category)
- Timestamp and run metadata

### PlanProposalV1

Location: `.autonomous_runs/<project>/runs/<family>/<run_id>/planning/plan_proposal_v1.json`

Contains:
- List of proposed actions with target paths
- Governance checks (protected paths, budget compliance)
- Approval status (auto_approved, requires_approval, blocked)

### AutopilotSessionV1

Location: `.autonomous_runs/<project>/runs/<family>/<run_id>/autopilot/session_<id>.json`

Contains:
- Session metadata (enabled, status)
- Execution summary (actions attempted/succeeded/failed)
- Approval requests for blocked actions
- Error log for failures

---

## Common Workflows

### Full Loop (Single Run)

```bash
RUN_ID="maintenance-$(date +%Y%m%d)"
PROJECT_ID="autopack"

# 1. Scan for gaps
python -m autopack.cli gaps scan \
  --run-id $RUN_ID \
  --project-id $PROJECT_ID \
  --write

# 2. Propose plan
python -m autopack.cli plan propose \
  --run-id $RUN_ID \
  --project-id $PROJECT_ID \
  --write

# 3. Review plan (check auto-approved vs requires-approval)
# Note: Full path is .autonomous_runs/$PROJECT_ID/runs/$FAMILY/$RUN_ID/...
# The CLI automatically resolves paths using RunFileLayout
cat .autonomous_runs/$PROJECT_ID/runs/maintenance/maintenance-$(date +%Y%m%d)/planning/plan_proposal_v1.json | jq '.summary'

# 4. Execute autopilot
python -m autopack.cli autopilot run \
  --run-id $RUN_ID \
  --project-id $PROJECT_ID \
  --enable \
  --write
```

### Parallel Batch Execution

```bash
# Create anchor with parallelism enabled
cat > batch_anchor.json << 'EOF'
{
  "schema_version": "2.0",
  "parallelism_isolation": {
    "allowed": true,
    "max_concurrent_runs": 5,
    "isolation_level": "worktree"
  }
}
EOF

# Execute batch
python -m autopack.cli autopilot supervise \
  --run-ids batch-001,batch-002,batch-003 \
  --anchor-path batch_anchor.json \
  --workers 3 \
  --per-run-sqlite
```

---

## Troubleshooting

### Gap Scan Fails

```
[Gap Scanner] ERROR: Workspace root does not exist
```
**Fix**: Ensure `--workspace` points to valid directory (or omit for cwd).

### Plan Propose Fails

```
[Plan Proposer] ERROR: Intention anchor not found
```
**Fix**: Create anchor at `.autonomous_runs/<project>/runs/<family>/<run_id>/intention_v2.json` or specify `--anchor-path`.

### Autopilot Disabled Warning

```
[Autopilot] WARNING: Autopilot is DISABLED by default.
```
**Expected**: Pass `--enable` to actually execute actions.

### Parallelism Blocked

```
[Supervisor] PARALLELISM BLOCKED: Parallelism not allowed by anchor
```
**Fix**: Set `parallelism_isolation.allowed = true` in anchor.

### Database Concurrency Error

```
SupervisorError: Parallel runs require Postgres database
```
**Fix**: Either:
- Use `--database-url postgresql://...`
- Or use `--per-run-sqlite` for isolated SQLite per run

---

## Related Documentation

- [GOVERNANCE.md](GOVERNANCE.md) - Approval workflow and risk tiers
- [PARALLEL_RUNS.md](PARALLEL_RUNS.md) - Four-layer isolation model
- [docs/BUILD-179_AUTONOMY_CLI_AND_SUPERVISOR_CONSOLIDATION.md](BUILD-179_AUTONOMY_CLI_AND_SUPERVISOR_CONSOLIDATION.md) - Implementation plan

---

**Total Lines**: ~300 (focused operator runbook)

**Coverage**: CLI usage, parallelism gates, artifact types, common workflows, troubleshooting
