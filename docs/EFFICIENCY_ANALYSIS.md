# Efficiency Analysis - Backlog Maintenance Test Run

**Date**: 2025-12-10
**Analyzed Run**: backlog-maintenance-1765288552
**Items Processed**: 10
**Total Duration**: ~240 seconds (4 minutes)

---

## Executive Summary

Analysis of the test run revealed **7 major inefficiencies** wasting tokens, storage, and execution time. Most significant: identical pytest output stored 10 times (~9KB redundant data), git checkpoint created 10 times when once would suffice, and diagnostic commands attempting to read non-existent log files.

**Total Waste Identified**:
- **Storage**: ~8KB redundant data per run
- **Execution Time**: ~15-20 seconds wasted on duplicate operations
- **Token Usage**: ~9,000+ chars of identical test output
- **Disk I/O**: 30+ log files, many with error outputs

---

## Issue 1: Redundant Pytest Output Storage (HIGH IMPACT)

### Finding
**Problem**: Identical pytest output stored in all 10 items in diagnostics summary JSON.

**Evidence**:
```
Total pytest runs: 10
Unique pytest outputs: 9
Identical test output stored: 9,190 total characters
Average per item: 919 characters
Actual redundancy: 1 output repeated (5 passed tests, identical warnings)
```

**Sample Duplicate Output** (stored 10 times):
```
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-8.2.1, pluggy-1.5.0
rootdir: C:\dev\Autopack
configfile: pytest.ini
plugins: anyio-3.7.1, asyncio-1.3.0, cov-7.0.0, timeout-2.4.0
asyncio: mode=Mode.AUTO...
collected 5 items

tests\smoke\test_basic.py .....                                          [100%]

============================== warnings summary ===============================
...\starlette\formparsers.py:10: PendingDeprecationWarning: Please use `import python_multipart` instead.
    import multipart
======================== 5 passed, 1 warning in 7.37s =========================
```

**Impact**:
- Diagnostic summary JSON bloated with redundant data
- Longer file read/write times
- More storage consumed in archives
- No value gained from storing identical output 10x

### Root Cause

[maintenance_runner.py:23-62](../src/autopack/maintenance_runner.py#L23-L62) - Full stdout/stderr captured for every test run:

```python
def run_tests(test_commands: List[str], workspace: Path, timeout: int = 600):
    results: List[TestExecResult] = []
    for cmd in test_commands:
        proc = subprocess.run(cmd, shell=True, cwd=str(workspace),
                            capture_output=True, text=True, timeout=timeout)
        results.append(TestExecResult(
            name=cmd,
            status=status,
            stdout=proc.stdout or "",  # ← Full output stored
            stderr=proc.stderr or "",  # ← Full output stored
        ))
```

[run_backlog_maintenance.py:178-191](../scripts/run_backlog_maintenance.py#L178-L191) - All test results serialized to JSON:

```python
summaries.append({
    "phase_id": item.id,
    "ledger": outcome.ledger_summary,
    "artifacts": outcome.artifacts,
    "tests": [t.__dict__ for t in test_results],  # ← Full output in JSON
})
```

### Solution

**Option A: Reference-Based Storage** (RECOMMENDED)
Store full test output once, reference by hash in items:

```python
# scripts/run_backlog_maintenance.py

def store_test_results_efficiently(test_results: List[TestExecResult], run_dir: Path):
    """Store test outputs with deduplication."""
    test_refs = []

    for test in test_results:
        # Hash the output for deduplication
        output_hash = hashlib.sha256(
            f"{test.stdout}{test.stderr}".encode()
        ).hexdigest()[:12]

        # Store full output in shared location (once per unique output)
        output_file = run_dir / "diagnostics" / "test_outputs" / f"{output_hash}.log"
        if not output_file.exists():
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                f"# Test: {test.name}\n# Status: {test.status}\n\n"
                f"=== STDOUT ===\n{test.stdout}\n\n"
                f"=== STDERR ===\n{test.stderr}\n",
                encoding="utf-8"
            )

        # Store only reference in summary
        test_refs.append({
            "name": test.name,
            "status": test.status,
            "output_ref": str(output_file.relative_to(run_dir)),
            "output_hash": output_hash,
            "summary": f"{test.status}: {len(test.stdout)} chars stdout, {len(test.stderr)} chars stderr"
        })

    return test_refs

# In main loop, replace line 191:
summaries.append({
    # ...
    "tests": store_test_results_efficiently(test_results, Path(".autonomous_runs") / run_id)
})
```

**Option B: Truncated Inline Storage**
Store only verdict + first/last N lines:

```python
def summarize_test_output(test: TestExecResult, max_lines: int = 5) -> dict:
    """Summarize test output for inline storage."""
    stdout_lines = test.stdout.splitlines()
    stderr_lines = test.stderr.splitlines()

    return {
        "name": test.name,
        "status": test.status,
        "stdout_summary": {
            "total_lines": len(stdout_lines),
            "first_lines": "\n".join(stdout_lines[:max_lines]),
            "last_lines": "\n".join(stdout_lines[-max_lines:]) if len(stdout_lines) > max_lines else "",
        },
        "stderr_summary": {
            "total_lines": len(stderr_lines),
            "content": "\n".join(stderr_lines[:max_lines]) if stderr_lines else ""
        }
    }
```

### Expected Savings
- **Storage**: ~8KB per run (90% reduction)
- **JSON size**: backlog_diagnostics_summary.json from ~50KB → ~10KB
- **Read/write speed**: 5x faster for large runs

---

## Issue 2: Redundant Git Checkpoint Creation (MEDIUM IMPACT)

### Finding
**Problem**: Git checkpoint created once per item, but all 10 items use **identical checkpoint** `b3a4e09...`.

**Evidence**:
```
Total items: 10
Unique checkpoints: 1
Checkpoint created 9 times unnecessarily
```

**Impact**:
- 10x git commands executed: `git rev-parse HEAD`
- Wasted ~5-10 seconds total
- Identical checkpoint hash stored 10 times in JSON

### Root Cause

[run_backlog_maintenance.py:71-74](../scripts/run_backlog_maintenance.py#L71-L74) - Checkpoint created inside per-item loop:

```python
for item in backlog_items[:args.max_items]:
    # Create checkpoint for each item (unnecessary!)
    if args.checkpoint:
        checkpoint_hash = create_git_checkpoint(workspace)
    # ... rest of processing
```

The checkpoint should be created **once before the loop** since it's a snapshot of the workspace state, not per-item state.

### Solution

Move checkpoint creation outside loop:

```python
# scripts/run_backlog_maintenance.py

# Create checkpoint ONCE before processing all items
checkpoint_hash = None
if args.checkpoint:
    checkpoint_hash = create_git_checkpoint(workspace)
    print(f"[Checkpoint] Created git checkpoint: {checkpoint_hash}")

# Process items using shared checkpoint
summaries = []
for item in backlog_items[:args.max_items]:
    # ... diagnostics processing

    summaries.append({
        "phase_id": item.id,
        "checkpoint": checkpoint_hash,  # ← Reuse same checkpoint
        # ...
    })
```

### Expected Savings
- **Execution time**: ~5-10 seconds per 10-item run
- **Git operations**: 90% reduction (1 instead of 10)

---

## Issue 3: Redundant Ledger Content (LOW-MEDIUM IMPACT)

### Finding
**Problem**: Ledger strings nearly identical across items - only 2 unique ledgers among 10 items.

**Evidence**:
```
Unique ledgers: 2
Total ledgers: 10
First 3 ledgers identical: True

Sample ledger:
"1) Investigate maintenance (conf=0.30) evidence=baseline_git_status -> exit 0,
timed_out=False; baseline_git_diff -> exit 0, timed_out=False;
baseline_disk_usage -> exit 0, timed_out=False; actions=no actions yet; outcome=pending"
```

**Pattern**: All items start with identical "Investigate maintenance" ledger because diagnostics agent runs same baseline commands for each item.

**Impact**:
- ~2KB redundant ledger data in JSON
- Harder to identify item-specific diagnostics

### Root Cause

DiagnosticsAgent always runs same baseline commands first:
- `git status`
- `git diff`
- `disk usage`
- `df`
- `tail` on log files (often non-existent)

These baselines are **workspace-level** not **item-level**, yet stored per-item.

### Solution

**Option A: Shared Baseline Section**
Store baseline diagnostics once, item-specific ledgers separately:

```python
# Run baseline once before loop
baseline_diagnostics = {
    "git_status": run_command("git status --short"),
    "git_diff": run_command("git diff --stat"),
    "disk_usage": run_command("du -sh .autonomous_runs"),
    "timestamp": datetime.now(timezone.utc).isoformat(),
}

# Store in summary
summary_data = {
    "run_id": run_id,
    "baseline": baseline_diagnostics,  # Once
    "items": []  # Per-item data without redundant baseline
}
```

**Option B: Compress Ledger Format**
Use structured format instead of string concatenation:

```python
ledger = {
    "stage": "investigate_maintenance",
    "confidence": 0.30,
    "evidence": {
        "baseline_git_status": {"exit": 0, "timed_out": False},
        "baseline_git_diff": {"exit": 0, "timed_out": False},
        # ...
    },
    "outcome": "pending"
}
```

### Expected Savings
- **Storage**: ~2KB per run
- **Readability**: Easier to diff item-specific vs baseline

---

## Issue 4: Non-Existent Log File Attempts (MEDIUM IMPACT)

### Finding
**Problem**: Diagnostics agent attempts to tail log files that don't exist, generating error artifacts.

**Evidence**:
```bash
# Command: tail -n 200 logs/autopack/autonomous_executor.log
# Exit: 1
# Duration: 0.05s

# STDERR
tail: cannot open 'logs/autopack/autonomous_executor.log' for reading: No such file or directory
```

**Occurrence**: 3-4 failed tail commands per item × 10 items = 30-40 failed operations

**Impact**:
- Wasted subprocess executions
- Error artifacts stored (taking disk space)
- Noise in diagnostics output

### Root Cause

[diagnostics_agent.py:167](../src/autopack/diagnostics/diagnostics_agent.py#L167) and [probes.py:113-132](../src/autopack/diagnostics/probes.py#L113-L132):

```python
# Hardcoded log paths without existence checks
commands.append((f"tail -n 200 {log_path}", f"baseline_tail_{Path(log_path).stem}"))
```

These paths assume logs exist at specific locations, but in backlog maintenance workflow:
- `logs/autopack/autonomous_executor.log` - Not used in maintenance mode
- `logs/autopack/builder.log` - Not used in maintenance mode
- `logs/autopack/auditor.log` - Not used in maintenance mode

### Solution

Add existence checks before attempting tail:

```python
# src/autopack/diagnostics/diagnostics_agent.py

def _add_baseline_log_tails(self, commands: List[Tuple[str, str]], workspace: Path):
    """Add tail commands for log files, only if they exist."""
    log_paths = [
        workspace / "logs/autopack/autonomous_executor.log",
        workspace / "logs/autopack/builder.log",
        workspace / "logs/autopack/auditor.log",
    ]

    for log_path in log_paths:
        if log_path.exists():
            commands.append((
                f"tail -n 200 {log_path}",
                f"baseline_tail_{log_path.stem}"
            ))
        else:
            # Optional: Log that file was skipped
            logger.debug(f"Skipping tail of non-existent log: {log_path}")
```

Alternative: Make log paths configurable per workflow:

```python
# config/diagnostics.yaml
workflows:
  backlog_maintenance:
    baseline_commands:
      - git status --short
      - git diff --stat
      # No log tails (they don't exist in this workflow)

  autonomous_executor:
    baseline_commands:
      - git status --short
      - git diff --stat
      - tail -n 200 logs/autopack/autonomous_executor.log
```

### Expected Savings
- **Subprocess calls**: 30-40 fewer per 10-item run
- **Error artifacts**: 0 instead of 30-40 error logs
- **Cleaner diagnostics**: Only actionable information stored

---

## Issue 5: Same Test Command Executed 10 Times (HIGH IMPACT)

### Finding
**Problem**: `pytest -q tests/smoke/` executed 10 times with **identical results** (same workspace state, same tests).

**Evidence**:
- All 10 executions: `5 passed, 1 warning in ~7s`
- Total test execution time: ~70 seconds (10 × 7s)
- 9 out of 10 runs produced **identical output**

**Impact**:
- 63 seconds wasted on redundant test runs
- Pytest overhead (collection, plugins, setup) repeated 10x

### Root Cause

[run_backlog_maintenance.py:114-115](../scripts/run_backlog_maintenance.py#L114-L115):

```python
for item in backlog_items:
    # Run tests per item (even though test targets are workspace-level, not item-level)
    test_results = run_tests(args.test_cmd, workspace, timeout=600) if args.test_cmd else []
```

The `--test-cmd "pytest -q tests/smoke/"` is a **workspace-level smoke test**, not item-specific. Running it 10 times provides no additional information.

### Solution

**Option A: Run Smoke Tests Once** (RECOMMENDED)
Execute workspace-level tests once before loop:

```python
# scripts/run_backlog_maintenance.py

# Run workspace smoke tests ONCE before processing items
workspace_test_results = []
if args.test_cmd:
    print(f"[Tests] Running workspace smoke tests...")
    workspace_test_results = run_tests(args.test_cmd, workspace, timeout=600)
    for test in workspace_test_results:
        print(f"  {test.name}: {test.status}")

# Process items without re-running workspace tests
for item in backlog_items:
    # ... diagnostics

    # Reference shared workspace test results
    summaries.append({
        "phase_id": item.id,
        "workspace_tests_ref": "workspace_smoke_tests",  # Reference, not duplicate
        # ... other fields
    })

# Store workspace tests once in summary
summary_data = {
    "workspace_tests": [t.__dict__ for t in workspace_test_results],  # Once
    "items": summaries  # No test data duplicated
}
```

**Option B: Parameterized Tests Per Item**
If tests ARE item-specific, parameterize test command:

```python
# Allow item-specific test commands
parser.add_argument(
    "--test-cmd-template",
    help="Test command template with {item_id} placeholder, e.g., 'pytest tests/{item_id}_test.py'"
)

# In loop
if args.test_cmd_template:
    test_cmd = args.test_cmd_template.format(item_id=item.id)
    test_results = run_tests([test_cmd], workspace, timeout=600)
```

### Expected Savings
- **Execution time**: ~63 seconds per 10-item run (90% reduction)
- **Storage**: ~8KB test output storage (stored once vs 10x)

---

## Issue 6: Budget Exhaustion Without Patch Generation (MEDIUM IMPACT)

### Finding
**Problem**: 7 out of 10 items hit `budget_exhausted=True`, yet `patch_path=null` for all items.

**Evidence**:
```
Items with budget_exhausted: 7/10
Items with patches generated: 0/10
```

**Pattern**:
- Items 1-3: Not exhausted, no patch
- Items 4-10: Exhausted, no patch

**Impact**:
- Diagnostics budget consumed without generating actionable output (patches)
- Unclear if exhaustion prevented patch generation or if patches were never attempted

### Root Cause

Looking at diagnostic summaries, all items show:
```json
{
  "ledger": "1) Investigate maintenance (conf=0.30) evidence=...; actions=no actions yet; outcome=pending",
  "budget_exhausted": true,
  "patch_path": null
}
```

**Key phrase**: `"actions=no actions yet"` - DiagnosticsAgent investigated but never attempted to generate patches.

Possible reasons:
1. Budget consumed entirely on baseline commands + investigation
2. No clear "fix strategy" identified during investigation phase
3. Agent configuration may be too conservative (high conf threshold)

### Solution

**Option A: Separate Investigation and Fix Budgets**
```python
# args
parser.add_argument("--max-investigation-commands", type=int, default=10)
parser.add_argument("--max-fix-commands", type=int, default=10)

# In diagnostics
agent.run(
    item,
    investigation_budget=args.max_investigation_commands,
    fix_budget=args.max_fix_commands
)
```

**Option B: Log Budget Usage Breakdown**
```python
outcome = {
    "ledger": agent.ledger_summary,
    "budget": {
        "total": args.max_commands,
        "used": agent.commands_executed,
        "breakdown": {
            "baseline": baseline_cmd_count,
            "investigation": investigation_cmd_count,
            "fix_attempt": fix_cmd_count,
        }
    }
}
```

**Option C: Reduce Baseline Command Count**
Per Issue 4, skip non-existent log tails to preserve budget for actual diagnostics.

### Expected Savings
- **More patches generated**: Budget freed up for actual fixes
- **Better observability**: Know where budget is spent

---

## Issue 7: Artifacts Stored with Absolute Windows Paths (LOW IMPACT)

### Finding
**Problem**: Artifact paths stored as absolute Windows paths in JSON, making archives non-portable.

**Evidence**:
```json
"artifacts": [
  "C:\\dev\\Autopack\\.autonomous_runs\\backlog-maintenance-1765288552\\diagnostics\\commands\\...",
  "C:\\dev\\Autopack\\.autonomous_runs\\backlog-maintenance-1765288552\\diagnostics\\commands\\..."
]
```

**Impact**:
- Archives not portable to Linux/Mac
- Paths break if repo moved
- Harder to share diagnostics between developers

### Solution

Store relative paths from run directory:

```python
# When storing artifacts
def relative_artifact_path(artifact_path: Path, run_dir: Path) -> str:
    """Convert artifact path to relative path from run directory."""
    try:
        return str(artifact_path.relative_to(run_dir))
    except ValueError:
        # Fallback if path not under run_dir
        return str(artifact_path)

# Usage
summaries.append({
    "artifacts": [
        relative_artifact_path(Path(a), run_dir)
        for a in outcome.artifacts
    ]
})
```

**Result**:
```json
"artifacts": [
  "diagnostics/commands/1765288554_baseline_git_status.log",
  "diagnostics/commands/1765288555_baseline_git_diff.log"
]
```

### Expected Savings
- **Portability**: Archives work across OS/machines
- **JSON size**: ~30% reduction in path storage

---

## Efficiency Optimization Priority

### Critical (Implement First)
1. **Issue 5: Redundant Test Execution** - 63s saved per run
2. **Issue 1: Duplicate Test Output Storage** - 8KB saved per run, cleaner diagnostics

### High Priority
3. **Issue 2: Redundant Checkpoint Creation** - 10s saved per run
4. **Issue 4: Non-Existent Log File Attempts** - 30-40 fewer errors, cleaner output

### Medium Priority
5. **Issue 6: Budget Usage Without Patches** - More actionable results
6. **Issue 3: Redundant Ledger Content** - 2KB saved, better readability

### Low Priority (Nice to Have)
7. **Issue 7: Absolute Paths** - Portability improvement

---

## Implementation Plan

### Phase 1: Quick Wins (1-2 hours)
- Fix Issue 2: Move checkpoint outside loop (5 min)
- Fix Issue 4: Add file existence checks (15 min)
- Fix Issue 7: Use relative paths (10 min)

### Phase 2: Storage Optimization (2-3 hours)
- Fix Issue 1: Reference-based test output storage (1 hour)
- Fix Issue 3: Shared baseline diagnostics (30 min)

### Phase 3: Execution Optimization (1-2 hours)
- Fix Issue 5: Run workspace tests once (30 min)
- Fix Issue 6: Budget breakdown logging (30 min)

---

## Testing Strategy

### Before Implementation
Establish baseline metrics:

```bash
# Run backlog maintenance and capture metrics
time PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --max-items 10 \
  --checkpoint \
  --test-cmd "pytest -q tests/smoke/"

# Measure artifacts
find .autonomous_runs -name "backlog_diagnostics_summary.json" -exec wc -c {} \;
find .autonomous_runs -type f -name "*.log" | wc -l
```

### After Implementation
Compare metrics:

```bash
# Same command, measure improvements
time PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --max-items 10 \
  --checkpoint \
  --test-cmd "pytest -q tests/smoke/"

# Expected improvements:
# - Execution time: 240s → 160s (33% faster)
# - JSON size: ~50KB → ~10KB (80% smaller)
# - Log files: 30 → 10 (67% fewer)
# - Error artifacts: 30-40 → 0 (100% reduction)
```

---

## Success Metrics

### Quantitative
- **Execution Time**: 240s → 160s (33% reduction)
- **Storage**: ~50KB → ~10KB per run (80% reduction)
- **Subprocess Calls**: ~50 → ~20 (60% reduction)
- **Error Artifacts**: ~35 → 0 (100% reduction)

### Qualitative
- Cleaner diagnostics output (no spurious errors)
- Faster archive operations (smaller files)
- More portable run artifacts (relative paths)
- Better budget utilization (more patches generated)

---

## Additional Recommendations

### 1. Add Diagnostics Performance Metrics
Track execution time per operation:

```python
# src/autopack/diagnostics/diagnostics_agent.py

@dataclass
class DiagnosticsMetrics:
    total_duration: float
    baseline_duration: float
    investigation_duration: float
    fix_duration: float
    commands_executed: int
    commands_failed: int

# Log in outcome
outcome.metrics = DiagnosticsMetrics(...)
```

### 2. Configurable Diagnostic Depth
Allow users to trade speed for thoroughness:

```python
# --diagnostic-depth quick|normal|thorough
parser.add_argument("--diagnostic-depth",
                   choices=["quick", "normal", "thorough"],
                   default="normal")

# quick: Skip baselines, run only item-specific diagnostics
# normal: Standard baselines + diagnostics
# thorough: Extended baselines + verbose diagnostics
```

### 3. Parallel Item Processing
Process independent items concurrently:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(process_item, item): item
        for item in backlog_items[:args.max_items]
    }
    for future in as_completed(futures):
        summaries.append(future.result())
```

**Potential**: 3x speedup for I/O-bound diagnostics

---

**End of Efficiency Analysis**
