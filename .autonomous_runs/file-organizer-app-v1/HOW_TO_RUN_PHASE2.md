# How to Run FileOrganizer Phase 2 with Autopack

This guide shows how to delegate all Phase 2 tasks to the **real Autopack system** for autonomous execution.

---

## Prerequisites

1. **Autopack FastAPI service** must be running
2. **FileOrganizer Phase 1** must be complete (v1.0 Alpha)
3. **Python 3.11+** with requests library

---

## Step 1: Start Autopack Service

Autopack is a FastAPI-based service. Start it first:

```bash
# Navigate to Autopack root
cd c:/dev/Autopack

# Start Autopack API server
uvicorn src.autopack.main:app --reload --host 0.0.0.0 --port 8000
```

The service will be available at `http://localhost:8000`

**Verify it's running:**
```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

---

## Step 2: Run Phase 2 Autonomous Build

Now run the single command that delegates all 7 tasks to Autopack:

```bash
# Navigate to FileOrganizer project
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1

# Run Phase 2 autonomous build
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

[Step 1/4] Checking Autopack service...
[OK] Autopack service healthy at http://localhost:8000

[Step 2/4] Creating Autopack run...
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

## Step 3: Review Results

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

## Troubleshooting

### Error: "Autopack service not available"
**Solution**: Start the Autopack FastAPI service first:
```bash
cd c:/dev/Autopack
uvicorn src.autopack.main:app --reload
```

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

**Single command to run all Phase 2 tasks:**

```bash
python scripts/autopack_phase2_runner.py
```

This delegates to the **real Autopack autonomous build system** via its FastAPI interface, following the v7 playbook architecture.

