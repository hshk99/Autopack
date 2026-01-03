# Batch Drain Controller Guide

## Overview

The Batch Drain Controller is a smart orchestration tool for efficiently processing failed phases across multiple runs. Instead of manually draining runs one-by-one, it automates the selection, execution, and tracking of drain operations.

## Key Features

### 1. Smart Phase Selection
Automatically picks the best next phase to drain using priority logic:

**Priority Order:**
1. **Unknown failures** - No last_failure_reason (likely transient)
2. **Collection errors** - Import/collection failures (might be fixed by systemic improvements)
3. **Deliverable errors** - Missing deliverables (might be fixed by no-op guard)
4. **Other failures** - Remaining failed phases

Within each category, prefers:
- Lower phase_index (earlier phases in run)
- Runs with fewer total failures (easier to complete)

### 2. Progress Tracking
- Saves session state after each phase
- Can resume interrupted sessions
- Provides detailed summary reports

### 3. Resume Capability
- Sessions are persisted to `.autonomous_runs/batch_drain_sessions/`
- Can stop and resume without losing progress
- Tracks which phases have been processed

### 4. Flexible Operation
- Process specific runs or all failed phases
- Configurable batch sizes
- Dry-run mode to preview operations

## Usage Examples

### Basic Usage

Process 10 failed phases (default batch size):
```bash
python scripts/batch_drain_controller.py
```

### Custom Batch Size

Process 25 failed phases:
```bash
python scripts/batch_drain_controller.py --batch-size 25
```

### Target Specific Run

Process failed phases from a specific run:
```bash
python scripts/batch_drain_controller.py --run-id build130-schema-validation-prevention
```

### Dry Run

Preview what would be processed without making changes:
```bash
python scripts/batch_drain_controller.py --batch-size 5 --dry-run
```

### Resume Interrupted Session

Resume the most recent incomplete session:
```bash
python scripts/batch_drain_controller.py --resume
```

## Workflow Example

### Scenario: Process 50 Failed Phases Across All Runs

```bash
# Step 1: Start batch drain (process 25 at a time)
python scripts/batch_drain_controller.py --batch-size 25

# ... controller runs, processes 25 phases, saves summary ...

# Step 2: Review results
cat .autonomous_runs/batch_drain_sessions/batch-drain-<timestamp>.json

# Step 3: Process another batch
python scripts/batch_drain_controller.py --batch-size 25

# Step 4: Check progress
python scripts/list_run_counts.py
```

### Scenario: Interrupted Session Recovery

```bash
# Start draining
python scripts/batch_drain_controller.py --batch-size 50

# ... process interrupted at phase 23 ...

# Resume from where it left off
python scripts/batch_drain_controller.py --resume

# ... continues from phase 24 ...
```

## Output Format

### During Execution
```
Batch Drain Controller
Session ID: batch-drain-20251228-120000
Target: Process 25 failed phases

[1/25] Selecting next phase...
  Draining: build130-schema-validation-prevention / phase-0-foundation
  ✓ Success: COMPLETE

[2/25] Selecting next phase...
  Draining: research-system-v1 / phase-1-implementation
  ✗ Failed: FAILED
    Error: No-op detected: no changes applied but required deliverables missing
```

### Summary Report
```
================================================================================
BATCH DRAIN SUMMARY
================================================================================
Session ID: batch-drain-20251228-120000
Started: 2025-12-28T12:00:00Z
Completed: 2025-12-28T12:45:00Z

Total Processed: 25
  ✓ Succeeded: 18
  ✗ Failed: 7
Success Rate: 72.0%

Results by Run:
--------------------------------------------------------------------------------
  build130-schema-validation-prevention: 2/2 succeeded
  research-system-v1: 1/3 succeeded
  research-system-v2: 2/4 succeeded
  ...

Session saved to:
  .autonomous_runs/batch_drain_sessions/batch-drain-20251228-120000.json
================================================================================
```

## Session File Format

Session state is saved as JSON:

```json
{
  "session_id": "batch-drain-20251228-120000",
  "started_at": "2025-12-28T12:00:00Z",
  "completed_at": "2025-12-28T12:45:00Z",
  "batch_size": 25,
  "total_processed": 25,
  "total_success": 18,
  "total_failed": 7,
  "results": [
    {
      "run_id": "build130-schema-validation-prevention",
      "phase_id": "phase-0-foundation",
      "phase_index": 0,
      "initial_state": "FAILED",
      "final_state": "COMPLETE",
      "success": true,
      "error_message": null,
      "timestamp": "2025-12-28T12:05:00Z"
    },
    ...
  ]
}
```

## Best Practices

### 1. Start Small
Begin with small batch sizes (5-10 phases) to verify the controller works correctly in your environment:
```bash
python scripts/batch_drain_controller.py --batch-size 5
```

### 2. Use Dry Run First
Preview operations before committing:
```bash
python scripts/batch_drain_controller.py --batch-size 25 --dry-run
```

### 3. Monitor Progress
Check run counts periodically:
```bash
python scripts/list_run_counts.py
```

### 4. Review Failure Patterns
After each batch, review the session file to identify common failure patterns that might benefit from systemic fixes.

### 5. Leverage Resume
Don't worry about interruptions - just resume:
```bash
python scripts/batch_drain_controller.py --resume
```

## Troubleshooting

### No Phases Selected
**Issue:** "No more failed phases to process" appears immediately

**Solutions:**
- Check database connection: `DATABASE_URL` environment variable
- Verify failed phases exist: `python scripts/list_run_counts.py`
- Check if phases were already processed in previous session

### Timeout Errors
**Issue:** Phases timeout after 10 minutes

**Solutions:**
- Reduce batch size to focus on simpler phases first
- Review phase complexity and deliverables
- Check for systemic issues blocking all phases

### Session Not Resuming
**Issue:** `--resume` doesn't find previous session

**Solutions:**
- Check `.autonomous_runs/batch_drain_sessions/` exists
- Verify session files are present
- Ensure previous session wasn't marked complete

## Integration with Existing Tools

### With pick_next_run.py
```bash
# Get next priority run
RUN_ID=$(python scripts/pick_next_run.py | cut -f1)

# Drain its failed phases
python scripts/batch_drain_controller.py --run-id "$RUN_ID" --batch-size 10
```

### With drain_queued_phases.py
Use batch controller for **failed** phases, use drain_queued_phases.py for **queued** phases:

```bash
# Drain queued phases first
python scripts/drain_queued_phases.py --run-id build130-schema --batch-size 25

# Then retry failed phases
python scripts/batch_drain_controller.py --run-id build130-schema --batch-size 10
```

## Performance Characteristics

- **Phase Selection:** ~100ms per selection (database query + sorting)
- **Phase Execution:** Variable (2-10 minutes per phase typically)
- **Session Persistence:** ~10ms per save (JSON write)
- **Memory Usage:** Minimal (~50MB for controller + executor overhead)

## Limitations

1. **Sequential Processing:** Phases are processed one at a time (by design for safety)
2. **Single Run Coordination:** Cannot run multiple batch controllers simultaneously on same database
3. **No Cross-Run Dependencies:** Doesn't model dependencies between phases in different runs
4. **Fixed Timeout:** 10-minute timeout per phase (hardcoded)

## Future Enhancements

Potential improvements for future versions:

1. **Adaptive Timeout:** Adjust timeout based on phase complexity
2. **Failure Clustering:** Group similar failures for batch analysis
3. **Priority Hints:** Allow manual priority overrides for specific runs
4. **Parallel Triage:** Run diagnosis in parallel while draining sequentially
5. **Smart Retry:** Exponential backoff for transient failures

## See Also

- [drain_queued_phases.py](../../scripts/drain_queued_phases.py) - For processing queued phases
- [pick_next_run.py](../../scripts/pick_next_run.py) - For selecting next priority run
- [list_run_counts.py](../../scripts/list_run_counts.py) - For viewing run status
- [BUILD_LOG.md](archive/superseded/reports/BUILD_LOG.md) - Development history and systemic improvements
