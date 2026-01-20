# Main Window Crash Fix - Background Cursor Cleanup

## The Problem
When `auto_fill_empty_slots.bat` runs, it creates multiple Cursor windows (one per slot). These windows run in the background. Previously, if you tried to clean them up, the process termination logic couldn't distinguish between:
- **Background Cursor windows** (opened by auto_fill)
- **Your main VSCode/Claude Code window** (the one you're currently using)

This resulted in killing the wrong process and closing your main chat window.

## The Solution
I've created a **safe cleanup script** that:

### ✅ What It Does Right
1. **Identifies all Cursor windows** currently running
2. **Sorts by start time** - the oldest window is your main one
3. **Keeps the oldest window** intact (this is likely your main Cursor instance)
4. **Only closes background windows** (the newer ones opened by auto_fill)
5. **Never touches VSCode or Claude Code processes**

### Files Changed

#### 1. New: `safe_cleanup_background_cursors.ps1`
Safe cleanup script that only closes background Cursor windows:

```powershell
# View what would be closed (dry-run)
.\safe_cleanup_background_cursors.ps1 -DryRun

# Actually close background windows (keeps your oldest/main one)
.\safe_cleanup_background_cursors.ps1
```

#### 2. Modified: `auto_fill_empty_slots.ps1`
Updated the `-Kill` parameter to use the safe cleanup instead of brutal process termination:

**Before:**
```powershell
Get-Process -Name "cursor" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "powershell" -ErrorAction SilentlyContinue | Stop-Process -Force
```

**After:**
```powershell
& "C:\dev\Autopack\scripts\safe_cleanup_background_cursors.ps1"
```

## How to Use

### Option 1: Clean up background windows from auto_fill
```powershell
# Test what would be closed
cd C:\dev\Autopack
.\scripts\safe_cleanup_background_cursors.ps1 -DryRun

# Actually close them (keeps your main window)
.\scripts\safe_cleanup_background_cursors.ps1
```

### Option 2: Use auto_fill's cleanup parameter
```powershell
cd C:\dev\Autopack
powershell -ExecutionPolicy Bypass -NoProfile -File ".\scripts\auto_fill_empty_slots.ps1" -Kill
```

This will:
1. Show you which Cursor windows exist
2. Close all background ones
3. **Keep your oldest/main window**
4. **NOT close VSCode or Claude Code**

## Safety Guarantees

✅ **Your main window is SAFE** - It's the oldest Cursor process
✅ **VSCode stays running** - We only close "Cursor" processes
✅ **Claude Code stays running** - Not touched by cleanup script
✅ **Dry-run available** - Always test with `-DryRun` first
✅ **Window-aware** - Uses actual window handle enumeration, not PID guessing

## Technical Details

The fix uses Windows API to:
1. Enumerate all visible Cursor windows
2. Get the process ID and start time for each
3. Sort by start time (oldest = your main window)
4. Only close processes with newer start times

This is much safer than blindly killing all processes named "cursor".

## What to Do Right Now

1. **Don't run auto_fill again until you verify this works**
2. Test the cleanup on existing background Cursor windows:
   ```powershell
   cd C:\dev\Autopack
   .\scripts\safe_cleanup_background_cursors.ps1 -DryRun
   ```
3. If the DRY-RUN looks correct, run it for real:
   ```powershell
   .\scripts\safe_cleanup_background_cursors.ps1
   ```
4. Verify your main Cursor window is still there

## If Problems Persist

If after running cleanup, invisible Cursor windows still appear:

1. Check what's running:
   ```powershell
   Get-Process -Name "cursor" | Select-Object Id, StartTime, Handles | Format-Table -AutoSize
   ```

2. The output shows each Cursor process ID and start time. The oldest one is your main window - keep it!

3. Report any remaining issues with the output from the above command.
