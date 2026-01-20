# System Restart & Testing Guide

## What's Ready

I've created an **improved launch script** that will work better after your restart:
- [launch_cursor_for_slot_improved.ps1](scripts/launch_cursor_for_slot_improved.ps1) - Better handles hidden windows and initialization
- Updated [auto_fill_empty_slots.ps1](scripts/auto_fill_empty_slots.ps1) to use the improved script

## Key Improvements in New Script

✅ **Handles Cursor process reuse** - Detects both new processes AND new windows
✅ **Forces window visibility** - Ensures windows aren't hidden before positioning
✅ **Better initialization waiting** - Gives Cursor proper time to set up
✅ **Brings to foreground** - Guarantees window is visible to user
✅ **No process termination** - Never kills anything (safe!)

## Pre-Restart Checklist

Before you restart your PC:

- [ ] Save any work in your main Cursor window
- [ ] Note any important contexts you have open
- [ ] Close your main Cursor window
- [ ] Take a screenshot of your screen before restart (optional, for reference)

## Restart Steps

1. **Save your work** (if any)
2. **Close Cursor** (the one labeled "YOU ARE KEEP CLOSING DOW... - Autopack - Cursor")
3. **Restart your PC**
   - Windows Start → Power → Restart
   - Or: `shutdown /r /t 0` in PowerShell
4. **Wait for restart to complete**
5. **Reopen this chat**
6. **Verify the invisible windows are gone** (run the debug script)

## Post-Restart Testing

Once you restart and reopen this chat:

### Step 1: Verify Clean State

Run this to verify no orphaned processes exist:

```powershell
cd C:\dev\Autopack
.\scripts\debug_cursor_windows.ps1
```

Expected output:
- Only 1 visible Cursor window (your main one with full title)
- All other processes should have empty titles (OS windows only)

### Step 2: Test Auto-Fill

Try running auto_fill:

```batch
cd C:\dev\Autopack
auto_fill_empty_slots.bat
```

Watch for:
- ✅ New Cursor windows appear in grid slots
- ✅ Windows are visible (not hidden)
- ✅ Windows are positioned to the correct slots
- ✅ No crash to your main window

### Step 3: Report Results

Tell me:
1. **Did new windows appear?** (Yes/No)
2. **Were they visible?** (Yes/No)
3. **Were they positioned correctly?** (Yes/No)
4. **Did your main window stay open?** (Yes/No)
5. **Any errors in the output?** (Share them)

## What If New Windows Still Don't Appear?

If after restart and using the improved script, new windows still don't appear, the issue is likely:
1. **Cursor needs CLI flag change** - Different launch parameters needed
2. **Monitor/display configuration** - Windows might be off-screen
3. **Cursor settings** - Session restoration or window management settings
4. **Different root cause** - Something else preventing window creation

In that case, we'll investigate:
- Cursor version and configuration
- Environment variables
- Window positioning logic
- Alternative launch methods

## Safety Guarantees

✅ **Your main window is safe after restart** - Fresh session, no process interdependencies
✅ **No scripts will kill processes** - We learned that lesson!
✅ **Improved script is non-destructive** - Only reads and positions windows
✅ **All changes are in git** - We can revert if needed

## Files Modified

- ✏️ [auto_fill_empty_slots.ps1](scripts/auto_fill_empty_slots.ps1) - Now uses improved launcher
- 📄 [launch_cursor_for_slot_improved.ps1](scripts/launch_cursor_for_slot_improved.ps1) - New improved script
- 📄 [CURSOR_INVISIBLE_WINDOWS_ROOT_CAUSE.md](CURSOR_INVISIBLE_WINDOWS_ROOT_CAUSE.md) - Root cause analysis
- 📄 [RESTART_AND_TEST_GUIDE.md](RESTART_AND_TEST_GUIDE.md) - This file

Original scripts remain unchanged as backup:
- [launch_cursor_for_slot.ps1](scripts/launch_cursor_for_slot.ps1) - Original (still works)

## Timeline

1. **Restart**: ~5-10 minutes
2. **Reopen chat**: ~1 minute
3. **Run test**: ~30 seconds
4. **Report results**: Ready whenever

## Questions?

Before restarting, if you have questions about:
- What will happen
- Why this approach
- Alternative options
- Timeline concerns

Just ask! I'm ready to help.

---

**Ready to restart?** Let me know when you're done and we'll test the improved script!
