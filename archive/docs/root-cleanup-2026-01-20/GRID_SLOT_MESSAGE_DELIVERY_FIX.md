# Grid Slot Message Delivery Fix - Implementation Summary

## Problem
`check_pr_status.bat` was not sending messages to Cursor windows in the 3x3 grid, even though Claude Chat was open and the default interface.

## Root Cause
Previous implementation tried to:
1. Send keyboard events blindly to "first available Cursor window"
2. Assumed chat coordinates were needed for proper message delivery
3. Didn't properly route messages to the correct grid slot window

## Solution: SetForegroundWindow Approach
Implemented the proven working approach from `paste_prompts_to_cursor_single_window.ps1`:

### How It Works
1. **Find the window at target slot**
   - Enumerate all Cursor windows using `EnumWindows` API
   - Match window position to expected grid slot coordinates
   - Grid positions from STREAMDECK_REFERENCE.md (verified 2026-01-19):
     - Columns: X=2560, 3413, 4266
     - Rows: Y=0, 463, 926
     - Slots 1-9 in standard 3x3 grid layout

2. **Focus the window**
   - Call `SetForegroundWindow(targetWindow)` to bring it to foreground
   - Wait 500ms for window to fully settle

3. **Send message**
   - Put message in clipboard using `Set-Clipboard`
   - Send `Ctrl+V` to paste (keyboard injection via `keybd_event`)
   - Send `Enter` to submit
   - Keyboard events automatically go to foreground window

### Key Insight
**No chat box clicking is required!** Window focus + clipboard + keyboard injection is sufficient because:
- Keyboard events are sent to the foreground window
- `Ctrl+V` works in any focused application with clipboard support
- `Enter` submits the message in Claude Chat
- This eliminates coordinate dependency and works regardless of UI layout

## Files Modified

### [send_message_to_cursor_slot.ps1](scripts/send_message_to_cursor_slot.ps1)
- **Removed**: Mouse clicking at chat coordinates
- **Removed**: Dependency on chat input box positions
- **Added**: Window enumeration (WindowHelper class)
- **Added**: SetForegroundWindow call before sending keys
- **Added**: Grid position matching logic (same as paste_prompts script)

### [check_pr_status.ps1](scripts/check_pr_status.ps1)
- Updated `Get-WindowSlotNumber()` function with correct grid coordinates
  - Old: X: 3121/3979/4833, Y: 144/610/1264 (incorrect, old screen resolution)
  - New: X: 2560/3413/4266, Y: 0/463/926 (verified, current ultra-wide layout)
- Grid slot detection now accurately maps windows to 1-9 based on position

## Grid Coordinates Reference

| Slot | Row | Col | X Pos | Y Pos | Position |
|------|-----|-----|-------|-------|----------|
| 1 | 1 | 1 | 2560 | 0 | Top-Left |
| 2 | 1 | 2 | 3413 | 0 | Top-Center |
| 3 | 1 | 3 | 4266 | 0 | Top-Right |
| 4 | 2 | 1 | 2560 | 463 | Mid-Left |
| 5 | 2 | 2 | 3413 | 463 | Mid-Center |
| 6 | 2 | 3 | 4266 | 463 | Mid-Right |
| 7 | 3 | 1 | 2560 | 926 | Bot-Left |
| 8 | 3 | 2 | 3413 | 926 | Bot-Center |
| 9 | 3 | 3 | 4266 | 926 | Bot-Right |

**Source**: STREAMDECK_REFERENCE.md, section "Window Grid Coordinates", verified 2026-01-19

## Testing

### Command to Test
```powershell
.\scripts\send_message_to_cursor_slot.ps1 -SlotNumber 1 -Message "test message"
```

### Expected Output
```
[OK] Message sent to slot 1
```

### What Happens
1. Script finds Cursor window at slot 1 position (X~2560, Y~0)
2. Brings it to foreground
3. Puts "test message" in clipboard
4. Sends Ctrl+V to paste
5. Sends Enter to submit
6. Message appears in Claude Chat in that window

## Commits
- **2ac72b1f**: Initial grid-slot-based implementation
- **2efbfd0d**: Fixed with SetForegroundWindow approach (this commit)

## Why This Works

The SetForegroundWindow approach:
- ✅ Proven to work (used in paste_prompts_to_cursor_single_window.ps1)
- ✅ Reliable window targeting (matches by grid position)
- ✅ No coordinate dependencies (no chat box clicking)
- ✅ Works with Claude Chat by default
- ✅ Simple and maintainable (fewer moving parts)
- ✅ Handles window focus correctly (SetForegroundWindow API)

## Related Scripts Using Same Pattern
- `paste_prompts_to_cursor_single_window.ps1` - pastes prompts using SetForegroundWindow
- `position_cursors_single_slot.ps1` - uses same window enumeration
- `switch_cursor_models_single_window.ps1` - uses same window detection

All proven working scripts use this pattern, confirming it's the right approach.
