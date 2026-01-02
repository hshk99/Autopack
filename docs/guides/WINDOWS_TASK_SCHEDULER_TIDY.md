# Windows Task Scheduler for Autopack Tidy

**Purpose**: Automate tidy runs to handle locked files after reboot/logon, ensuring "auto-archive after locks release" happens without manual intervention.

**Date**: 2026-01-02
**Build**: BUILD-145 Follow-up

---

## Why Use Task Scheduler?

Windows file locks (from Search Indexer, antivirus, editors, etc.) prevent tidy from moving files during active sessions. The tidy system now **queues locked files for retry**, but requires another tidy run to actually complete those moves.

**Task Scheduler solves this by**:
- Running tidy automatically after reboot (when locks are released)
- Running tidy periodically to catch any newly-released locks
- Ensuring workspace stays clean without manual intervention

---

## Recommended Tasks

We recommend **two complementary tasks**:

### Task 1: Tidy at Logon (Best for post-reboot cleanup)

**When it runs**: Every time you log in
**Why useful**: After reboot, all file locks are released. This task completes all queued moves immediately.

### Task 2: Daily Tidy at 3am (Best for steady-state)

**When it runs**: Daily at 3:00 AM
**Why useful**: Catches any locks that were released during idle time (closed editors, stopped services).

---

## Setup Instructions

### Prerequisites

1. **Python environment**: Ensure `python` command works from Command Prompt:
   ```cmd
   python --version
   ```

2. **Working tidy script**: Test tidy manually first:
   ```cmd
   cd C:\dev\Autopack
   python scripts/tidy/tidy_up.py --execute
   ```

3. **Administrator access** (for Task Scheduler creation)

---

### Task 1: Tidy at Logon

1. **Open Task Scheduler**:
   - Press `Win+R`
   - Type `taskschd.msc`
   - Press Enter

2. **Create Basic Task**:
   - Click "Create Basic Task..." in right pane
   - Name: `Autopack Tidy - At Logon`
   - Description: `Run Autopack workspace tidy after logon to process queued moves`

3. **Trigger**:
   - Select: "When I log on"
   - Click Next

4. **Action**:
   - Select: "Start a program"
   - Program/script: `python`
   - Add arguments: `scripts/tidy/tidy_up.py --execute`
   - Start in: `C:\dev\Autopack`
   - Click Next

5. **Finish**:
   - Check "Open the Properties dialog when I click Finish"
   - Click Finish

6. **Properties - Advanced Settings**:
   - **Security options**:
     - Run whether user is logged on or not: NO (keep unchecked)
     - Run with highest privileges: NO (keep unchecked)
   - **Settings tab**:
     - Allow task to be run on demand: YES (checked)
     - Stop the task if it runs longer than: `30 minutes`
     - If the running task does not end when requested, force it to stop: YES
   - Click OK

---

### Task 2: Daily Tidy at 3am

1. **Open Task Scheduler** (as above)

2. **Create Basic Task**:
   - Name: `Autopack Tidy - Daily 3am`
   - Description: `Run Autopack workspace tidy daily to process queued moves`

3. **Trigger**:
   - Select: "Daily"
   - Click Next
   - Start date: Today
   - Recur every: `1` days
   - Time: `03:00:00`
   - Click Next

4. **Action**:
   - Select: "Start a program"
   - Program/script: `python`
   - Add arguments: `scripts/tidy/tidy_up.py --execute`
   - Start in: `C:\dev\Autopack`
   - Click Next

5. **Finish** and configure properties (same as Task 1)

---

## Verifying Task Configuration

### Check Task Properties

1. Open Task Scheduler
2. Find your task in "Task Scheduler Library"
3. Right-click → Properties
4. Verify:
   - **General tab**: Description is correct
   - **Triggers tab**: Shows your trigger (logon or daily 3am)
   - **Actions tab**:
     - Action: "Start a program"
     - Program/script: `python`
     - Arguments: `scripts/tidy/tidy_up.py --execute`
     - Start in: `C:\dev\Autopack`

### Manual Test Run

1. Right-click task → **Run**
2. Open Command Prompt and check queue status:
   ```cmd
   cd C:\dev\Autopack
   python -c "import json; print(json.dumps(json.load(open('.autonomous_runs/tidy_pending_moves.json')), indent=2))"
   ```
3. Check for reduced queue size (succeeded items should be gone)

---

## Monitoring Tidy Runs

### Check Last Run Status

1. Open Task Scheduler
2. Select your task
3. **History tab** (enable via Action → Enable All Tasks History if needed)
4. Look for:
   - Event ID 102: Task completed
   - Event ID 103: Task failed
   - Return code: `0` = success, `1` = structure violations (see verifier output)

### Check Queue File

The persistent queue is at: `.autonomous_runs/tidy_pending_moves.json`

**Quick check**:
```cmd
cd C:\dev\Autopack
python -c "import json; q=json.load(open('.autonomous_runs/tidy_pending_moves.json')); print(f'Total: {len(q[\"items\"])}, Pending: {sum(1 for x in q[\"items\"] if x[\"status\"]==\"pending\")}')"
```

**Expected behavior**:
- After reboot + logon task: pending count should drop significantly (locked files now moved)
- Between tidies: pending count may increase (new locked files)
- Over time: pending count should stabilize (only truly-stuck files remain)

---

## Troubleshooting

### Task runs but doesn't complete moves

**Possible causes**:
1. **Still locked**: The files may still be locked at task runtime
   - Check `queue["items"][N]["last_error"]` for error details
   - Check `queue["items"][N]["attempt_count"]` - if >= 10, item is abandoned

2. **Wrong working directory**: Task must start in `C:\dev\Autopack`
   - Verify "Start in" field in task action

3. **Python environment issues**: Task may use different Python than your interactive shell
   - Solution: Use absolute path to Python executable in "Program/script" field
   - Example: `C:\Python\python.exe` or `C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe`

### How to find your Python path

```cmd
where python
```

Use the full path in Task Scheduler.

### Task doesn't run at all

1. **Check Task Scheduler service**:
   - Press `Win+R`, type `services.msc`
   - Find "Task Scheduler"
   - Status should be "Running"
   - Startup type: Automatic

2. **Check task conditions**:
   - Properties → Conditions tab
   - Uncheck "Start the task only if the computer is on AC power" (if laptop)

### Disable Tasks Temporarily

**To pause automation** (e.g., during development):
1. Right-click task → **Disable**
2. Manual tidy still works: `python scripts/tidy/tidy_up.py --execute`

**To resume**:
1. Right-click task → **Enable**

---

## Safety Notes

- **No data loss**: Tidy uses move operations (not delete), and queued items are persistent
- **Idempotent**: Safe to run multiple times; won't re-move already-moved files
- **Graceful failures**: If a move fails, it's queued for retry (max 10 attempts, 30 days)
- **Git integration**: If using `--git-checkpoint`, tidy creates commits before/after changes
- **Dry-run first**: Test manually with `--dry-run` (default) before enabling scheduled tasks

---

## Advanced: Custom Retry Behavior

You can tune queue retry parameters by modifying [pending_moves.py](../../scripts/tidy/pending_moves.py):

```python
DEFAULT_MAX_ATTEMPTS = 10           # Max retries before abandoning
DEFAULT_ABANDON_AFTER_DAYS = 30     # Days before abandoning
DEFAULT_BASE_BACKOFF_SECONDS = 300  # Initial backoff (5 minutes)
DEFAULT_MAX_BACKOFF_SECONDS = 86400 # Max backoff (24 hours)
```

**Exponential backoff formula**:
```
backoff = base * (2 ^ (attempt - 1))
capped at max_backoff
```

---

## Related Documentation

- [TIDY_LOCKED_FILES_HOWTO.md](../TIDY_LOCKED_FILES_HOWTO.md) - General guidance on handling locked files
- [BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md](../BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md) - Tidy system implementation
- [scripts/tidy/pending_moves.py](../../scripts/tidy/pending_moves.py) - Queue implementation
- [scripts/tidy/tidy_up.py](../../scripts/tidy/tidy_up.py) - Main tidy entrypoint

---

**Status**: Ready to use (2026-01-02)
**Tested on**: Windows 11
**Python version**: 3.10+
