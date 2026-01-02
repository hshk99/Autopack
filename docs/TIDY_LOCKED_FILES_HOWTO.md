# How to Handle Locked Files During Tidy

**Date**: 2026-01-02
**Context**: BUILD-145 tidy system encounters Windows file locks on historical databases

---

## The Problem

On Windows, certain background processes (Windows Search Indexer, antivirus, backup tools) can hold file handles on `.db` files, preventing them from being moved or deleted. When you run tidy, you'll see:

```
[SKIPPED] C:\dev\Autopack\telemetry_seed*.db (locked by another process)
```

**This is expected and safe** - the tidy system is designed to handle this gracefully.

---

## Solutions (in order of preference)

### Option A: Exclude from Windows Search (Recommended for prevention)

**What it does**: Tells Windows Search Indexer to ignore database files, preventing future locks.

**How to run**:
```bash
# Exclude all .db files from Windows Search indexing
python scripts/tidy/exclude_db_from_indexing.py

# Exclude specific pattern
python scripts/tidy/exclude_db_from_indexing.py --pattern "telemetry_seed*.db"
```

**Note**: This prevents *future* locks but doesn't release *existing* locks. You'll still need Option B or C to move already-locked files.

### Option B: Accept Partial Tidy (Recommended for daily use)

**What it does**: Tidy skips locked files and cleans everything else. Rerun later (after reboot/idle) to finish.

**How to run**:
```bash
# Run tidy normally - it will skip locked files
python scripts/tidy/tidy_up.py --execute

# Locked files are reported but don't block cleanup
# Re-run after reboot to clean up leftovers
```

**Why this works**: The tidy system is idempotent - you can run it multiple times safely. Most locked files are historical databases that don't change, so they'll still be there to clean up later.

**When to use**:
- Daily tidy runs
- When you can't stop background processes
- When you want to clean *most* clutter without disrupting your workflow

### Option C: Stop Locking Processes (Recommended for complete cleanup)

**What it does**: Identify and stop the processes holding locks, then run tidy.

**How to identify lockers**:

1. **Resource Monitor** (built-in, no admin required):
   ```
   - Press Win+R, type "resmon.exe", press Enter
   - Go to CPU tab → Associated Handles
   - Search for: .autonomous_runs or telemetry_seed
   - Look at "Image" column to see which process has the lock
   ```

2. **Sysinternals Handle.exe** (most precise, requires download):
   ```bash
   # Download from https://live.sysinternals.com/handle.exe
   handle.exe C:\dev\Autopack\telemetry_seed_debug.db

   # Output shows:
   # SearchIndexer.exe   pid: 135896   type: File   C:\dev\Autopack\telemetry_seed_debug.db
   ```

**Common lockers and how to stop them**:

| Process | How to Stop | Safe? | Notes |
|---------|-------------|-------|-------|
| **SearchIndexer.exe** | `net stop WSearch` (as admin) | ✅ Yes | Safe to stop temporarily, will restart on reboot |
| **MsMpEng.exe** (Windows Defender) | Exclude `C:\dev\Autopack\*.db` via Windows Security settings | ✅ Yes | Don't stop the process, just exclude the files |
| **python.exe** | `taskkill /PID <pid>` | ⚠️ Check first | Make sure it's not your active dev environment |
| **Code.exe** / **Cursor.exe** | Close the editor | ✅ Yes | Close VS Code/Cursor if it has a DB file open |

**Steps for complete cleanup**:
```bash
# 1. Stop SearchIndexer (requires admin PowerShell)
net stop WSearch

# 2. Run tidy immediately
python scripts/tidy/tidy_up.py --execute

# 3. Restart SearchIndexer (optional, it will auto-restart anyway)
net start WSearch
```

### Option D: Reboot + Early Tidy (Recommended for stubborn locks)

**What it does**: Reboot to release all locks, then run tidy before opening editors/starting work.

**How to run**:
```bash
# 1. Reboot Windows
# 2. Don't open VS Code/Cursor yet
# 3. Run tidy in fresh terminal
cd C:\dev\Autopack
python scripts/tidy/tidy_up.py --execute

# 4. Now open your workspace
```

**When to use**:
- When you have "mystery locks" that don't show up in Resource Monitor
- When you want a completely clean workspace
- Before major commits or releases

---

## What NOT to Do

❌ **Don't force-delete `.autonomous_runs/` while Autopack is running**
   → This risks corrupting active runs/checkpoints

❌ **Don't use `rm -rf` or `shutil.rmtree` on locked directories**
   → This will fail and may leave partial state

❌ **Don't kill SearchIndexer.exe process directly**
   → Use `net stop WSearch` instead (cleaner shutdown)

❌ **Don't disable Windows Search permanently**
   → Just exclude database files using Option A

---

## Current Status (2026-01-02)

**Locked files**: 13 telemetry seed databases at root
**Root cause**: Windows Search Indexer (SearchIndexer.exe)
**Mitigation**:
- ✅ Excluded from indexing via `attrib +N` (prevents future locks)
- ✅ Tidy system skips locked files gracefully (no crashes)
- ⚠️ Need reboot or `net stop WSearch` to move existing locked files

**Next action**:
- Option B (partial tidy) is already working - no immediate action needed
- Option C or D when user wants complete cleanup (requires admin or reboot)

---

## Related Documents

- [BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md](./BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md) - Tidy system implementation
- [README.md](../README.md) - Tidy system intentions and known gaps
- [scripts/tidy/exclude_db_from_indexing.py](../scripts/tidy/exclude_db_from_indexing.py) - Prevent Windows Search locks
- [scripts/tidy/tidy_up.py](../scripts/tidy/tidy_up.py) - Main tidy entrypoint
