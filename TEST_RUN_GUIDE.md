# Test Run Guide - Fresh Start with Failure Monitoring

## Setup Steps

### 1. Start the API Server (if not running)
```bash
# In one terminal
cd C:\dev\Autopack
python -m uvicorn src.autopack.main:app --reload --port 8000
```

### 2. Create a New Run
```bash
# In another terminal
cd C:\dev\Autopack
python scripts/create_phase3_delegated_run.py
```

This will output a run ID like: `phase3-delegated-20251202-171248`

### 3. Run Executor with Stop-on-First-Failure
```bash
# In the same terminal
python src/autopack/autonomous_executor.py \
    --run-id <RUN_ID_FROM_STEP_2> \
    --run-type autopack_maintenance \
    --stop-on-first-failure \
    --verbose
```

### 4. Monitor Progress (Optional - in another terminal)
```bash
# Watch for failures
python scripts/monitor_and_stop.py <RUN_ID>
```

## What Happens

1. **Executor starts** and loads all new code (PLAN2 + PLAN3)
2. **Polls API** for QUEUED phases
3. **Executes phases** one by one:
   - Uses new pre-flight guards
   - Routes to structured edit mode for files >1000 lines
   - Shows files with line numbers in prompts
   - Applies structured edits safely
4. **Stops immediately** if any phase fails (saves tokens)
5. **Logs everything** so you can see what happened

## What to Watch For

### Success Indicators:
- ✅ "Using structured edit mode for large file: <file> (<lines> lines)"
- ✅ "Generated structured edit plan with N operations"
- ✅ "Structured edits applied successfully (N operations)"
- ✅ Phase completes with status COMPLETE

### Failure Indicators:
- ❌ Phase fails with status FAILED
- ❌ Executor stops immediately (due to --stop-on-first-failure)
- ❌ Error messages in logs

## Token Usage Savings

With `--stop-on-first-failure`:
- **Before**: Would continue through all phases even if early ones fail (wastes tokens)
- **After**: Stops immediately on first failure (saves remaining token budget)

## Manual Stop

If you need to stop manually:
- Press `Ctrl+C` in the executor terminal
- Or create the stop signal file:
  ```bash
  echo "stop:<RUN_ID>:manual" > .autonomous_runs/.stop_executor
  ```

## After Testing

1. Check logs for structured edit mode usage
2. Verify files were modified correctly (no truncation)
3. Review any failures to understand what went wrong
4. Check token usage vs. what would have been used without stopping

