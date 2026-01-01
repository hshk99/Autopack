# Batch Drain Controller - Quick Start Guide

## What You Have Now

You now have a **smart batch drain controller** that efficiently processes failed phases across your 57 runs with failures, eliminating the need to manually drain runs one-by-one.

## Quick Start (3 Steps)

### 1. Preview What Will Be Processed (Dry Run)

```powershell
# Windows PowerShell
python scripts/batch_drain_controller.py --batch-size 10 --dry-run
```

This shows you the first 10 failed phases that would be processed, without making any changes.

### 2. Process Your First Batch

```powershell
# Start with a small batch to verify everything works
python scripts/batch_drain_controller.py --batch-size 10
```

The controller will:
- Select the 10 highest-priority failed phases
- Drain them one-by-one
- Save progress after each phase
- Show a summary when done

### 3. Scale Up

```powershell
# Process more phases
python scripts/batch_drain_controller.py --batch-size 25

# Or use the automation script
.\scripts\examples\batch_drain_57_runs.ps1
```

## How It Works

### Smart Priority Selection

The controller automatically picks the best next phase to drain based on:

1. **Failure Type Priority:**
   - Unknown failures (no error message) - likely transient, high success rate
   - Collection/import errors - might be fixed by recent systemic improvements
   - Deliverable errors - might be fixed by no-op guard
   - Other failures

2. **Within Each Category:**
   - Earlier phases in run (lower phase_index)
   - Runs with fewer total failures (easier to complete)

### Progress Tracking

- Session state is saved after each phase to: `.autonomous_runs/batch_drain_sessions/`
- If interrupted (Ctrl+C), you can resume with: `python scripts/batch_drain_controller.py --resume`
- No progress is lost

## Common Workflows

### Workflow 1: Process All Failed Phases in Batches

```powershell
# Process 20 at a time
python scripts/batch_drain_controller.py --batch-size 20

# Check progress
python scripts/list_run_counts.py

# Process another 20
python scripts/batch_drain_controller.py --batch-size 20

# Repeat until satisfied
```

### Workflow 2: Target Specific Run

```powershell
# Focus on one run's failures
python scripts/batch_drain_controller.py --run-id build130-schema-validation-prevention
```

### Workflow 3: Automated Processing

```powershell
# Use the example script to process 100 phases in batches of 20
.\scripts\examples\batch_drain_57_runs.ps1
```

### Workflow 4: Resume After Interruption

```powershell
# Start draining
python scripts/batch_drain_controller.py --batch-size 50

# ... interrupted at phase 23 (Ctrl+C) ...

# Resume from where you left off
python scripts/batch_drain_controller.py --resume

# ... continues from phase 24 ...
```

## Understanding the Output

### During Execution

```
[1/10] Selecting next phase...
  Draining: build130-schema-validation-prevention / phase-0-foundation
  ✓ Success: COMPLETE

[2/10] Selecting next phase...
  Draining: research-system-v1 / phase-1-implementation
  ✗ Failed: FAILED
    Error: No-op detected: no changes applied but required deliverables missing
```

### Summary Report

```
================================================================================
BATCH DRAIN SUMMARY
================================================================================
Total Processed: 10
  ✓ Succeeded: 7
  ✗ Failed: 3
Success Rate: 70.0%

Results by Run:
  build130-schema-validation-prevention: 2/2 succeeded
  research-system-v1: 1/3 succeeded
  research-system-v2: 2/2 succeeded
  ...
================================================================================
```

## What's Different from Manual Draining?

| Manual Approach | Batch Controller |
|----------------|------------------|
| Pick run manually | Automatic smart selection |
| Run `drain_queued_phases.py` | Single command |
| Track progress manually | Automatic session tracking |
| Start over if interrupted | Resume from last phase |
| Process runs sequentially | Process best phases across all runs |
| No failure pattern visibility | Summary reports show patterns |

## Key Advantages

1. **Efficiency:** No manual run selection overhead
2. **Smart:** Prioritizes easier failures for higher success rate
3. **Resilient:** Resume capability means interruptions don't waste work
4. **Insightful:** Summary reports reveal failure patterns
5. **Flexible:** Process all runs or target specific ones

## Next Steps

1. **Start small:** Try a batch of 5-10 phases to verify setup
2. **Review results:** Check the summary to understand failure patterns
3. **Scale up:** Increase batch size once comfortable
4. **Automate:** Use the example scripts for hands-off processing

## Detailed Documentation

For complete documentation, see:
- [docs/guides/BATCH_DRAIN_GUIDE.md](docs/guides/BATCH_DRAIN_GUIDE.md) - Full usage guide
- [scripts/batch_drain_controller.py](scripts/batch_drain_controller.py) - Controller source
- [scripts/examples/](scripts/examples/) - Automation scripts

## Support

If you encounter issues:
1. Check `DATABASE_URL` environment variable points to `sqlite:///autopack.db`
2. Verify failed phases exist: `python scripts/list_run_counts.py`
3. Review session files in `.autonomous_runs/batch_drain_sessions/`
4. Use `--dry-run` to preview without making changes

---

**Ready to start? Run:**

```powershell
python scripts/batch_drain_controller.py --batch-size 10 --dry-run
```
