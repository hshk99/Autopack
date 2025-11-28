# How to Run FileOrganizer Phase 2 with Autopack

This guide shows how to delegate all Phase 2 tasks to the **real Autopack system** for fully autonomous execution with **zero manual setup required**.

---

## Quick Start (Fully Autonomous - Recommended)

**Single command for complete autonomous execution**:

```bash
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1
python scripts/autopack_phase2_runner.py --non-interactive
```

**Or use the wrapper script**:
```bash
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1
./run_phase2.sh
```

**What this does**:
- Automatically detects if Autopack service is running
- Auto-starts uvicorn if service not found
- Waits for service health check (30s timeout)
- Creates Autopack run with all 9 Phase 2 tasks
- Monitors progress in real-time
- Generates comprehensive reports
- Shuts down service gracefully on exit
- **Zero interactive prompts - truly hands-off execution**

---

## Prerequisites

1. **FileOrganizer Phase 1** must be complete (v1.0 Alpha)
2. **Python 3.11+** with requests library
3. **.claude/settings.json** must allow uvicorn (already configured)

**No need to manually start Autopack service** - the runner handles it automatically!

---

## Step 1: Run Phase 2 Build (Auto-Service-Start)

The canonical command with full automation:

```bash
# Navigate to FileOrganizer project
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1

# Run Phase 2 autonomous build (auto-starts service, zero prompts)
python scripts/autopack_phase2_runner.py --non-interactive
```

**Interactive mode** (asks for confirmation before starting):
```bash
python scripts/autopack_phase2_runner.py
```

### What This Does:

1. **Creates an Autopack Run** with 9 phases (all tasks from WHATS_LEFT_TO_BUILD.md)
2. **Organizes into 3 tiers**:
   - Tier 1 (High Priority): Test fixes, Frontend build
   - Tier 2 (Medium Priority): Docker, Country packs
   - Tier 3 (Low Priority): Search, Batch upload, Auth
3. **Monitors progress** in real-time with token usage tracking
4. **Generates comprehensive report** when complete

### Expected Output:

```
================================================================================
FILEORGANIZER PHASE 2 - AUTOPACK AUTONOMOUS BUILD
================================================================================

[NON-INTERACTIVE MODE] Proceeding with full Phase 2 autonomous build...
[NON-INTERACTIVE MODE] Will auto-start Autopack service if needed...

[Step 1/5] Checking Autopack service...
[INFO] Autopack service not running at http://localhost:8000
[INFO] Auto-starting Autopack service...
[INFO] Starting Autopack service at c:/dev/Autopack...
[INFO] Waiting for Autopack service to be ready...
[OK] Autopack service started successfully
[OK] Autopack service healthy at http://localhost:8000

[Step 2/5] Creating Autopack run...
================================================================================
CREATING AUTOPACK RUN: fileorganizer-phase2-20251128-123456
================================================================================

Phases: 9
Tiers: 3
Token Cap: 150,000
Max Duration: 5 hours

[OK] Run created: fileorganizer-phase2-20251128-123456
State: RUN_CREATED

[Step 3/4] Monitoring run progress...
================================================================================
MONITORING RUN PROGRESS
================================================================================

Polling every 30 seconds...
Press Ctrl+C to stop monitoring (run will continue)

[30s] Progress: 11.1% | Phase: Test Suite Fixes | Tokens: 8245/150000
[60s] Progress: 22.2% | Phase: Frontend Build System | Tokens: 13120/150000
[90s] Progress: 33.3% | Phase: Docker Deployment | Tokens: 25890/150000
...
```

---

## Step 2: Review Results (Manual Service Management - Optional)

When complete, the script generates `PHASE2_AUTOPACK_REPORT_<timestamp>.md` with:

- **Budget Utilization**: Tokens used vs cap
- **Tier Results**: Status of each tier
- **Phase Results**: Detailed status of all 9 tasks
- **Overall Assessment**: Success/failure analysis

Example report structure:

```markdown
================================================================================
FILEORGANIZER PHASE 2 - AUTOPACK AUTONOMOUS BUILD REPORT
================================================================================

Run ID: fileorganizer-phase2-20251128-123456
Run State: DONE_SUCCESS
...

PHASE RESULTS
================================================================================

✅ Phase 0: Test Suite Fixes [COMPLETE]
  Category: testing | Complexity: low
  Builder Attempts: 1 | Auditor Attempts: 0
  Tokens: 8,245
  Issues: 0 minor, 0 major

✅ Phase 1: Frontend Build System [COMPLETE]
  Category: frontend | Complexity: low
  Builder Attempts: 1 | Auditor Attempts: 0
  Tokens: 4,875
  Issues: 0 minor, 0 major

...

OVERALL ASSESSMENT
================================================================================

Phases Completed: 9/9 (100.0%)

[SUCCESS] All Phase 2 tasks completed!
FileOrganizer v1.0 Beta is ready
```

---

## Configuration Options

### Environment Variables:

```bash
# Autopack API URL (default: http://localhost:8000)
export AUTOPACK_API_URL=http://localhost:8000

# Autopack API Key (if authentication enabled)
export AUTOPACK_API_KEY=your-api-key-here
```

### Adjusting Budget/Timeouts:

Edit [autopack_phase2_runner.py:102-107](file://c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1/scripts/autopack_phase2_runner.py#L102-L107):

```python
"run": {
    "run_id": self.run_id,
    "safety_profile": "standard",
    "run_scope": "feature_backlog",
    "token_cap": 150000,  # Increase if needed
    "max_phases": 9,
    "max_duration_minutes": 300,  # 5 hours
}
```

---

## Monitoring While Running

### Option 1: Real-time monitoring (default)
The script polls every 30 seconds and displays progress.

### Option 2: Manual monitoring
Press `Ctrl+C` to stop monitoring. The run continues in background.

Check status manually:
```bash
# Get run status
curl http://localhost:8000/runs/fileorganizer-phase2-YYYYMMDD-HHMMSS

# Get dashboard status
curl http://localhost:8000/dashboard/runs/fileorganizer-phase2-YYYYMMDD-HHMMSS/status
```

---

## Manual Service Management (Advanced - Not Recommended)

If you prefer to manually manage the Autopack service instead of using auto-start:

**Step 1: Start Autopack service**:
```bash
cd c:/dev/Autopack
uvicorn src.autopack.main:app --reload --host 0.0.0.0 --port 8000
```

**Step 2: Run Phase 2** (without --non-interactive):
```bash
cd .autonomous_runs/file-organizer-app-v1
python scripts/autopack_phase2_runner.py
```

This is NOT recommended because:
- Requires two terminal windows
- No automatic service cleanup
- More manual steps prone to errors

**Recommended approach**: Use `--non-interactive` flag which handles everything automatically.

---

## Troubleshooting

### Error: "Autopack service not available after 30s"
**Possible causes**:
1. Port 8000 is already in use
2. Python environment issues
3. Missing dependencies

**Solution**: Check port availability:
```bash
# Windows
netstat -ano | findstr :8000

# Unix/Linux
lsof -i :8000
```

If port is in use, kill the process or change the port in the runner script

### Error: "Failed to create run: 400 - Run already exists"
**Solution**: The run ID already exists. Either:
- Delete the old run from the database, or
- The script generates a new timestamped ID automatically

### Error: "Failed to create run: 403 - Invalid API key"
**Solution**: Set the correct API key:
```bash
export AUTOPACK_API_KEY=your-key
```

Or disable auth in Autopack by unsetting `AUTOPACK_API_KEY` in the Autopack service environment.

---

## What's Different from phase2_orchestrator.py?

| Feature | phase2_orchestrator.py (OLD) | autopack_phase2_runner.py (NEW) |
|---------|------------------------------|----------------------------------|
| **Approach** | Expected pre-written task scripts | Calls real Autopack API |
| **Execution** | Would run Python scripts sequentially | Autopack executes autonomously |
| **Reporting** | Fake success reports (0 tasks, 0 tokens) | Real reports from Autopack database |
| **Scalability** | Required manual task script creation | Fully autonomous |
| **Role** | Violated Cursor Project Rules | Follows correct delegation pattern |

**The old orchestrator was a misunderstanding of Autopack's architecture.** This new runner correctly delegates to the real Autopack system.

---

## Next Steps After Phase 2

1. **Review the generated report** (`PHASE2_AUTOPACK_REPORT_*.md`)
2. **Check Autopack issue backlog**:
   ```bash
   curl http://localhost:8000/project/issues/backlog
   ```
3. **For failed phases**: Review phase logs in `.autonomous_runs/fileorganizer-phase2-*/`
4. **For experimental features** (Country packs): Schedule human expert review per ref6.md guidance
5. **For security-sensitive code** (Authentication): Conduct architecture + security review

---

## Summary

**Recommended single command for fully autonomous execution:**

```bash
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1
python scripts/autopack_phase2_runner.py --non-interactive
```

**Or use the wrapper script:**
```bash
./run_phase2.sh
```

This command:
- Auto-detects and starts Autopack service if needed
- Delegates all 9 Phase 2 tasks to the real Autopack autonomous build system
- Requires zero human interaction (truly hands-off)
- Follows the v7 playbook architecture with correct API delegation pattern
- Generates comprehensive reports automatically

