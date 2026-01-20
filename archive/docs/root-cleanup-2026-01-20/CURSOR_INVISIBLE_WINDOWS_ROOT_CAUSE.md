# Cursor Invisible Windows - Root Cause & Solution

## The Problem

When `auto_fill_empty_slots.bat` runs, it attempts to launch new Cursor windows in the background grid slots. However:

1. **New windows never become visible** - they launch as processes but stay hidden
2. **Multiple orphaned Cursor processes accumulate** - they continue running in the background
3. **When you close them manually**, the crash cascades to your main window
4. **When you restart Cursor**, those orphaned processes reappear (Cursor session restoration)

## Root Causes

### 1. Window Detection Failure
The [launch_cursor_for_slot.ps1](scripts/launch_cursor_for_slot.ps1) script waits for NEW visible windows:
- It records existing windows BEFORE launch
- It looks for NEW windows that appear AFTER launch
- **Problem**: New Cursor windows aren't appearing as visible - they stay hidden
- **Result**: Script times out waiting for windows that never materialize

### 2. Cursor Process Behavior
When launching Cursor.exe with `--new-window`:
- The initial process often **terminates immediately** (spawns child process)
- Cursor reuses an existing main process for new windows
- New windows launch but **stay in background/unfocused** state
- Window enumeration only finds **visible windows** - misses hidden ones

### 3. Orphaned Process Accumulation
- Each failed launch attempt leaves a background process running
- When you reopen Cursor, it restores the session (including those orphaned windows)
- They persist until system restart or forced termination
- **We can't safely terminate them** without risking closing your main window

## Why Manual Closing Crashes Your Main Window

The orphaned Cursor windows are tied to your main Cursor process through:
- Shared memory/IPC channels
- Session restoration mechanisms
- Window group relationships

Closing one can trigger a cascade that terminates others, including your main window.

## The Solution Strategy

### Immediate Fix: System Restart Required

1. **Close your main Cursor window** (save any work first!)
2. **Restart your computer** - this will:
   - Kill all Cursor processes (including orphaned ones)
   - Clear Cursor's session restoration data
   - Reset the window state

### After Restart: Use Improved Launch Script

Once you restart, use the fixed launch script that:
- ✅ Properly detects when Cursor processes finish initializing
- ✅ Forces visibility on new windows
- ✅ Avoids timing issues with window detection
- ✅ Positions windows correctly to grid slots

### Prevent Recurrence

The improved script will:
1. **Detect new processes** (not just visible windows)
2. **Wait for proper initialization** (give Cursor time to set up)
3. **Force window visibility** before trying to position
4. **Move windows to correct slots** and bring to foreground

## What NOT To Do

❌ Do **NOT** manually kill Cursor processes - they're interconnected
❌ Do **NOT** try to clean up in Task Manager - cascades to main window
❌ Do **NOT** repeatedly restart Cursor - accumulates more orphaned processes

## What TO Do

✅ **Restart your PC** to clear orphaned processes
✅ **Use improved launch script** after restart
✅ **Report if new windows still don't appear** after restart - indicates different root cause

## Technical Details

### Why This Happens

Cursor is an Electron application. When you launch multiple windows:
- Electron maintains a main process
- New windows are child processes/threads
- Session restoration tries to restore all windows
- Hidden windows stay hidden on restart

### Files Involved

- [launch_cursor_for_slot.ps1](scripts/launch_cursor_for_slot.ps1) - Detects/positions new windows
- [auto_fill_empty_slots.ps1](scripts/auto_fill_empty_slots.ps1) - Orchestrates the slot filling
- [auto_fill_empty_slots.bat](scripts/auto_fill_empty_slots.bat) - Entry point from StreamDeck

### Session Restoration Location

Cursor stores session state in:
```
%APPDATA%\Local\cursor-user-data\Cache
%APPDATA%\Local\cursor-user-data\Session Storage
```

A system restart clears these.

## Next Steps

1. **Close Cursor** (save any work)
2. **Restart your PC**
3. **Reopen this chat**
4. **Run auto_fill_empty_slots.bat again**
5. **Report if new windows appear**

If new windows still don't appear after restart, the issue is different and we'll need to investigate:
- Cursor's session settings
- Window management policies
- Possible monitor/display configuration issues

## Prevention

After restart, new windows should appear because:
1. Clean session state
2. No accumulated orphaned processes
3. Proper window initialization sequence
