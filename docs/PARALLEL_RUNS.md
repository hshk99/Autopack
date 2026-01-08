# Parallel Runs Guide

**Status:** ✅ Implemented (P2.0-P2.4)
**Build:** Phase A.P11 Observability + Parallel Runs v1
**Safety Level:** Production-ready with Postgres; Beta with per-run SQLite

---

## Overview

Autopack now supports **safe parallel execution** of multiple autonomous runs. This enables:

- **Concurrent run execution** across multiple workers
- **Isolated git workspaces** per run (no cross-run contamination)
- **Centralized artifact storage** for dashboard aggregation
- **Database concurrency** via Postgres or per-run SQLite

## Architecture

### Four-Layer Safety Model

Parallel runs are made safe through four complementary mechanisms:

#### 1. **Workspace Isolation** (`WorkspaceManager`)
- Each run gets its own **git worktree** (isolated working tree, shared object DB)
- Prevents git state pollution between concurrent runs
- Automatic cleanup on completion
- Location: `.autonomous_runs/workspaces/{run_id}/`

#### 2. **Workspace Leasing** (`WorkspaceLease`)
- Prevents concurrent access to the **same physical workspace**
- Global lock keyed by absolute workspace path
- Protects against parallel executor bugs
- Independent from per-run locking

#### 3. **Per-Run Locking** (`ExecutorLockManager`)
- Prevents **duplicate execution of same run_id**
- One executor per run-id at a time
- Now respects `AUTONOMOUS_RUNS_DIR` setting
- Upgraded from hardcoded `.autonomous_runs/.locks`

#### 4. **Run-Scoped Artifacts** (`TestBaselineTracker`, `RunFileLayout`)
- Test baselines, retry reports → `.autonomous_runs/{run_id}/ci/`
- No more global `baseline.json` / `retry.json` collisions
- Backward-compatible (legacy mode if `run_id` not provided)

---

## Quick Start

### Prerequisites

**Required:**
- Postgres database (recommended) OR per-run SQLite (limited aggregation)
- Git 2.25+ (for `git worktree` support)

**Recommended:**
- Python 3.9+
- Sufficient disk space for worktrees (each run duplicates working tree)

### Basic Usage

**BUILD-179 Update:** Parallel execution now requires an IntentionAnchorV2 with `parallelism_isolation.allowed=true`. This is a safety gate to prevent accidental parallel execution.

```bash
# Run 3 parallel runs with Postgres (requires anchor)
python scripts/autopack_supervisor.py \
  --run-ids build130-phase-a,build130-phase-b,build130-phase-c \
  --anchor-path anchor.json \
  --workers 3 \
  --database-url postgresql://autopack:autopack@localhost:5432/autopack

# Or use the unified CLI:
python -m autopack.cli autopilot supervise \
  --run-ids build130-phase-a,build130-phase-b,build130-phase-c \
  --anchor-path anchor.json \
  --workers 3 \
  --database-url postgresql://autopack:autopack@localhost:5432/autopack

# Run 2 parallel runs with per-run SQLite
python scripts/autopack_supervisor.py \
  --run-ids experiment-001,experiment-002 \
  --anchor-path anchor.json \
  --workers 2 \
  --per-run-sqlite

# List existing worktrees
python scripts/autopack_supervisor.py --list-worktrees

# Cleanup all worktrees
python scripts/autopack_supervisor.py --cleanup
```

### Configuration

Environment variables:

```bash
# Override autonomous runs directory
export AUTONOMOUS_RUNS_DIR=/path/to/shared/artifacts

# Database URL (Postgres recommended for parallel)
export DATABASE_URL=postgresql://autopack:autopack@localhost:5432/autopack

# Source repository (default: current directory)
# Set if running supervisor from different location
export AUTOPACK_REPO_PATH=/path/to/autopack
```

---

## Safety Guarantees

### What's Protected

✅ **Git state isolation**
Each run operates in its own worktree with independent HEAD, index, and working tree.

✅ **Database write concurrency**
Postgres handles concurrent writes safely. Per-run SQLite uses separate DB files.

✅ **Artifact isolation**
Each run writes to `.autonomous_runs/{run_id}/` (no collisions).

✅ **Lock file isolation**
Locks stored in `{autonomous_runs_dir}/.locks/` and `.workspace_leases/`.

✅ **Rollback correctness**
`RollbackManager` operates on per-worktree git state (no cross-run contamination).

### What's NOT Protected

❌ **Shared resources outside workspace**
External APIs, databases, network resources are not isolated.

❌ **Filesystem quotas**
Each worktree duplicates the working tree (not git objects). Plan disk usage accordingly.

❌ **Dashboard aggregation with per-run SQLite**
Per-run SQLite databases can't be queried together without manual merging.

---

## Database Strategies

### Option 1: Postgres (Recommended)

**Use when:**
- You need centralized dashboard with all runs
- You have Postgres available (docker-compose default)
- You want production-grade concurrency

**Setup:**

```bash
# Start Postgres (via docker-compose)
docker-compose up -d db

# Run parallel jobs
python scripts/autopack_supervisor.py \
  --run-ids run1,run2,run3 \
  --workers 3 \
  --database-url postgresql://autopack:autopack@localhost:5432/autopack
```

**Pros:**
- True concurrent writes (MVCC, row-level locking)
- Centralized dashboard aggregation
- Production-tested concurrency

**Cons:**
- Requires Postgres instance
- Slightly more setup

---

### Option 2: Per-Run SQLite

**Use when:**
- You can't use Postgres (local dev, air-gapped environments)
- Dashboard aggregation is not critical
- You want simplest setup

**Setup:**

```bash
# No Postgres needed - each run gets its own SQLite file
python scripts/autopack_supervisor.py \
  --run-ids run1,run2,run3 \
  --workers 3 \
  --per-run-sqlite
```

Each run creates: `.autonomous_runs/{run_id}/{run_id}.db`

**Pros:**
- No Postgres dependency
- Simple setup
- Each run fully independent

**Cons:**
- Dashboard can only show one run at a time
- No cross-run SQL queries
- WAL mode helps but SQLite concurrency is limited

---

## Advanced Usage

### Custom Worktree Location

```python
from autopack.workspace_manager import WorkspaceManager

manager = WorkspaceManager(
    run_id="my-run",
    source_repo=Path("/path/to/repo"),
    worktree_base=Path("/fast/ssd/worktrees"),  # Custom location
    cleanup_on_exit=True
)

with manager as workspace:
    # Execute run in isolated workspace
    execute_run(workspace)
```

### Manual Workspace Management

```python
# Create workspace
workspace = manager.create_worktree(branch="main")  # Checkout branch
# ... or ...
workspace = manager.create_worktree()  # Detached HEAD

# Execute work
run_autonomous_executor(workspace)

# Cleanup
manager.remove_worktree(force=True)  # Force even with uncommitted changes
```

### Workspace Lease (Prevent Concurrent Access)

```python
from autopack.workspace_lease import WorkspaceLease

# Acquire exclusive access to workspace
with WorkspaceLease(workspace_path) as lease:
    # Safe to run git operations
    subprocess.run(["git", "status"], cwd=workspace_path)
    # Lease auto-released on exit
```

### Per-Run Test Baseline Tracking

```python
from autopack.test_baseline_tracker import TestBaselineTracker

# Legacy mode (global paths - NOT safe for parallel)
tracker_legacy = TestBaselineTracker(workspace)

# Parallel-safe mode (run-scoped paths)
tracker = TestBaselineTracker(workspace, run_id="my-run-001")

# Baseline stored in: .autonomous_runs/my-run-001/baselines/
baseline = tracker.capture_baseline("my-run-001", commit_sha, timeout=120)
```

---

## Troubleshooting

### "Workspace lease already held"

**Cause:** Another executor is using the same workspace directory.

**Fix:**
```bash
# List active worktrees
python scripts/autopack_supervisor.py --list-worktrees

# Force cleanup if executor crashed
python scripts/autopack_supervisor.py --cleanup

# Or manually remove stale lock
rm .autonomous_runs/.workspace_leases/workspace_*.lock
```

---

### "Executor lock already held for run_id"

**Cause:** Another process is executing the same run_id.

**Fix:**
```bash
# Check if process is actually running
ps aux | grep autonomous_executor

# If crashed, force unlock
rm .autonomous_runs/.locks/{run_id}.lock
```

---

### "git worktree add failed"

**Cause:** Worktree directory already exists or git state is corrupt.

**Fix:**
```bash
# Cleanup stale worktrees
git worktree prune

# Or use supervisor cleanup
python scripts/autopack_supervisor.py --cleanup

# Check git worktree list
git worktree list
```

---

### Per-run SQLite: "database is locked"

**Cause:** SQLite WAL mode not enabled, or high write contention.

**Fix:**
- Use Postgres instead (recommended)
- Reduce `--workers` count
- Ensure runs don't share SQLite file (check `--per-run-sqlite` is set)

---

## Performance Considerations

### Disk Usage

Each worktree duplicates the **working tree** (not git objects):

```
Source repo:      100 MB working tree + 500 MB .git
3 worktrees:      300 MB working trees + 500 MB .git (shared)
Total:            800 MB (not 1.8 GB)
```

**Recommendation:** Use fast SSD for `worktree_base` if running many parallel jobs.

### Concurrency Limits

**Recommended workers:**
- **Postgres:** Up to CPU core count (DB handles concurrency)
- **Per-run SQLite:** 2-4 workers max (SQLite write bottleneck)

**Memory:**
- Each executor: ~500MB-1GB depending on codebase size
- Plan for: `workers * 1GB + overhead`

### Network/API Rate Limits

Parallel runs **do NOT** prevent:
- Concurrent API calls to external services
- Rate limit exhaustion
- Network bandwidth saturation

**Mitigation:**
- Implement rate limiting in your code
- Use `--workers` to control concurrency
- Consider staggered starts

---

## Testing

### Run Unit Tests

```bash
# Test WorkspaceManager
PYTHONUTF8=1 pytest tests/autopack/test_workspace_manager.py -v

# Test WorkspaceLease
PYTHONUTF8=1 pytest tests/autopack/test_workspace_lease.py -v

# Integration tests
PYTHONUTF8=1 pytest tests/integration/test_parallel_runs.py -v
```

### Run Integration Test (End-to-End)

```bash
# Create test runs in database
python scripts/seed_parallel_test_runs.py

# Execute in parallel
python scripts/autopack_supervisor.py \
  --run-ids test-run-001,test-run-002,test-run-003 \
  --workers 3 \
  --database-url postgresql://autopack:autopack@localhost:5432/autopack

# Verify no artifacts collided
ls -la .autonomous_runs/test-run-*/ci/
```

---

## Migration Guide

### From Single-Run to Parallel

**Before (single run):**
```bash
python src/autopack/autonomous_executor.py --run-id my-run
```

**After (parallel via supervisor):**
```bash
python scripts/autopack_supervisor.py \
  --run-ids my-run-1,my-run-2,my-run-3 \
  --workers 3 \
  --database-url postgresql://autopack:autopack@localhost:5432/autopack
```

### Backward Compatibility

All components maintain backward compatibility:

- `TestBaselineTracker(workspace)` → global paths (legacy)
- `TestBaselineTracker(workspace, run_id="...")` → run-scoped (parallel-safe)
- `ExecutorLockManager(run_id)` → respects `AUTONOMOUS_RUNS_DIR`
- Single-run execution works unchanged

---

## Security Considerations

### Isolation Boundaries

**What's isolated:**
- Git working trees (filesystem)
- Database writes (Postgres transactions)
- Artifact files (per-run directories)
- Lock files (per-run or per-workspace)

**What's shared:**
- Git object database (`.git/objects/`)
- Network access (API calls, external services)
- System resources (CPU, memory, disk I/O)

### Recommended Practices

1. **Use Postgres for production parallel runs** (better concurrency + audit trail)
2. **Set `AUTONOMOUS_RUNS_DIR` to shared NFS** if running across machines
3. **Monitor disk usage** (worktrees can accumulate)
4. **Run cleanup regularly** (`--cleanup` or cron job)
5. **Don't share workspaces** across different repos (git object conflicts)

---

## Implementation Details

### Components

| Component | Purpose | Location |
|-----------|---------|----------|
| `WorkspaceManager` | Git worktree creation/cleanup | [src/autopack/workspace_manager.py](../src/autopack/workspace_manager.py) |
| `WorkspaceLease` | Workspace-level locking | [src/autopack/workspace_lease.py](../src/autopack/workspace_lease.py) |
| `ExecutorLockManager` | Per-run locking (upgraded) | [src/autopack/executor_lock.py](../src/autopack/executor_lock.py) |
| `TestBaselineTracker` | Run-scoped artifacts (upgraded) | [src/autopack/test_baseline_tracker.py](../src/autopack/test_baseline_tracker.py) |
| `ParallelRunSupervisor` | Orchestration CLI | [scripts/autopack_supervisor.py](../scripts/autopack_supervisor.py) |

### Build History

- **P2.0:** WorkspaceManager + Supervisor CLI
- **P2.1:** TestBaselineTracker run-scoped artifacts
- **P2.2:** ExecutorLockManager respects `autonomous_runs_dir`
- **P2.3:** Concurrency policy enforcement (Postgres requirement)
- **P2.4:** WorkspaceLease (workspace-level locking)
- **BUILD-179:** Library-first architecture + IntentionAnchorV2 policy gate for parallelism

---

## Future Enhancements

### Potential Improvements

- [ ] **Phase-level parallelism** (branch-based, complex merge logic)
- [ ] **Subtask parallelism** (parallel read-only analysis within phase)
- [ ] **Distributed workers** (across multiple machines)
- [ ] **Dashboard per-run filtering** (better SQLite support)
- [ ] **Automatic cleanup policy** (age-based worktree removal)
- [ ] **Resource quotas** (CPU, memory limits per worker)

### Not Recommended

- ❌ **Parallel phases within single run** (merge conflicts, ordering complexity)
- ❌ **Shared workspace without lease** (git state corruption risk)
- ❌ **Single SQLite DB for parallel writes** (lock contention, corruption risk)

---

## References

- [README.md](../README.md) - Main Autopack documentation
- [LEARNED_RULES.json](../docs/LEARNED_RULES.json) - Safety policies
- [rerf5.md](c:\Users\hshk9\OneDrive\Backup\Desktop\rerf5.md) - Original parallelization requirements
- [Git Worktree Docs](https://git-scm.com/docs/git-worktree) - Git worktree reference

---

## Support

**Issues/Questions:**
- GitHub: https://github.com/autopack/autopack/issues
- Tag: `parallel-runs`, `p2.0-p2.4`

**Maintainer:** Autopack Core Team
**Last Updated:** 2026-01-06
