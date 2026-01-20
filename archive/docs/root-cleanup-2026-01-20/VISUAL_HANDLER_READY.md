# Connection Error Handler - Visual Detection ✅ READY

## Status: IMPLEMENTED AND READY TO TEST

The connection error handler has been completely rewritten to use **visual detection with coordinate-based clicking** instead of blind keyboard shortcuts.

---

## What Changed

### ❌ Old Approach (Problematic)
- Blindly sent keyboard shortcuts every 3 seconds
- No detection of error dialog presence
- **Caused**: Settings opening, unintended actions, interference with normal operation

### ✅ New Approach (Fixed)
- **Detects** error dialog using pixel sampling
- **Only clicks** when error is actually detected
- **Uses coordinates** you provided for all 9 grid slots
- **No interference** with normal operation

---

## How It Works

### Detection Strategy
1. Samples a single pixel from the center of each grid window
2. Compares brightness to threshold
3. Error dialog typically appears with gray/white overlay (bright)
4. Normal editor is darker
5. When brightness exceeds threshold → Error detected

### Action Strategy
Once error detected in a specific slot:
1. Clicks the Resume button at the exact coordinates you provided
2. Waits for dialog to close
3. Continues monitoring
4. Debounces to avoid clicking twice in same slot within 5 seconds

### Resume Button Coordinates (Configured)
```
SLOT 1: X=3121, Y=337     SLOT 4: X=3121, Y=801     SLOT 7: X=3121, Y=1264
SLOT 2: X=3979, Y=337     SLOT 5: X=3979, Y=801     SLOT 8: X=3979, Y=1264
SLOT 3: X=4833, Y=337     SLOT 6: X=4833, Y=801     SLOT 9: X=4833, Y=1264
```

---

## Testing (2 minutes)

### Step 1: Launch Handler
```powershell
C:\dev\Autopack\scripts\handle_connection_errors.bat
```

You should see:
```
========== CONNECTION ERROR HANDLER (VISUAL DETECTION) ==========

Status: MONITORING ACTIVE
Method: Pixel sampling + coordinate-based clicking
Press Ctrl+C to stop

This handler:
  [+] Samples pixel in each grid window
  [+] Detects error dialog by brightness change
  [+] Clicks Resume button at known coordinates
  [+] Only acts when error is actually detected

...

Initializing baseline pixel colors for each grid slot...
  Slot 1 baseline brightness: 127
  Slot 2 baseline brightness: 124
  ...
```

### Step 2: Test with No Errors (Verify No Interference)
1. Let handler run for 30 seconds
2. Open other windows or work normally
3. Verify **nothing happens** (no clicks, no key presses)
4. This confirms no false positives or interference

### Step 3: Trigger Connection Error
1. While handler is running
2. Go to a Cursor window (any of the 9 slots)
3. Disconnect internet or simulate connection error
4. Wait for error dialog to appear

### Step 4: Observe Recovery
Handler should:
1. Detect error within 2 seconds: `[14:52:30] [!] CONNECTION ERROR DETECTED IN GRID SLOT 2`
2. Click Resume button: `[14:52:30] [+] Clicking Resume button at (3979, 337)`
3. Wait for dialog to close: Waits 500ms
4. Continue monitoring

### Step 5: Verify Cursor Recovers
1. Error dialog closes
2. Cursor reconnects automatically
3. Workflow continues without interruption

### Step 6: Stop Handler
```
Press Ctrl+C
```

Shows summary:
```
========== SESSION SUMMARY ==========

Session Duration: 0h 2m 15s
Errors Detected: 1
Errors Handled: 1

Monitor stopped.
```

---

## Key Improvements

### ✅ Detection First
- Before: Sent keys without checking if error exists
- Now: Samples pixel to confirm error dialog is present

### ✅ Targeted Clicking
- Before: Sent generic shortcuts that could trigger anything
- Now: Clicks only the Resume button at known coordinates

### ✅ No Interference
- Before: Keyboard shortcuts went to wrong windows
- Now: No action taken unless error detected

### ✅ Per-Slot Targeting
- Before: Global keyboard broadcast
- Now: Detects which of 9 slots has error, clicks that slot's button

### ✅ Debouncing
- Before: Could click multiple times
- Now: Waits 5 seconds before acting on same slot again

---

## Technical Details

### Pixel Sampling Method
**Why pixel sampling?**
- Fast: Checks color in milliseconds
- Lightweight: Single pixel instead of full screenshot
- Reliable: Dialog overlay is visually distinct (brighter)
- Simple: No OCR, image comparison, or complex analysis needed

**Brightness Threshold**
- Error dialog background: Light gray/white (brightness ~700+)
- Editor background: Dark colors (brightness ~100-200)
- Threshold set to 500 to safely distinguish

**Grid Window Centers**
- Slot 1: Center at ~(853, 240)
- Slot 2: Center at ~(2560, 240)
- Slot 3: Center at ~(4267, 240)
- Slot 4: Center at ~(853, 720)
- And so on...

### Mouse Clicking Method
Uses Windows API directly:
1. `SetCursorPos()` - Move mouse to coordinates
2. `mouse_event()` - Send left button down
3. Wait 50ms
4. `mouse_event()` - Send left button up

This is the most reliable way to click on web-rendered (Chromium) UI.

---

## File Reference

| File | Purpose |
|------|---------|
| `handle_connection_errors.bat` | Main launcher (updated) |
| `handle_connection_errors_visual.ps1` | New visual detection handler |
| `handle_connection_errors_keyboard.ps1` | Old keyboard handler (do NOT use) |
| `handle_connection_errors_screenshot.ps1` | Skeleton handler (reference only) |

---

## Expected Behaviors

### Scenario A: No Error Present ✅
```
[Run for 2 minutes with no connection error]

Output: Just periodic "Slot X baseline brightness: N"
Result: NO clicks, NO key presses, NO interference
Status: PASS - Handler is working correctly, no false positives
```

### Scenario B: Error in One Slot ✅
```
[Keep handler running, trigger error in Slot 3]

Output:
[14:52:30] [!] CONNECTION ERROR DETECTED IN GRID SLOT 3
[14:52:30] [+] Clicking Resume button at (4833, 337)
[14:52:31] [+] Recovery action sent

Result: Cursor recovers, error dialog closes, workflow continues
Status: PASS - Error detected, button clicked, recovery successful
```

### Scenario C: Multiple Errors ✅
```
[Trigger errors in Slot 2 and Slot 5]

Output:
[14:53:15] [!] CONNECTION ERROR DETECTED IN GRID SLOT 2
[14:53:15] [+] Clicking Resume button at (3979, 337)
[14:53:20] [!] CONNECTION ERROR DETECTED IN GRID SLOT 5
[14:53:20] [+] Clicking Resume button at (3979, 801)

Result: Each error handled independently in correct slot
Status: PASS - Multiple slots handled correctly
```

### Scenario D: Rapid Recovery ⚠️
```
[Error recovers, then happens again within 5 seconds in same slot]

Output:
[14:54:10] [!] CONNECTION ERROR DETECTED IN GRID SLOT 4
[14:54:10] [+] Clicking Resume button at (3121, 801)
[14:54:12] [!] CONNECTION ERROR DETECTED IN GRID SLOT 4
[Debounce active - no second click]

Result: Only one click sent (debounced), avoids double-clicking
Status: PASS - Debouncing working correctly
```

---

## If Something Goes Wrong

### Handler doesn't start
- Check: `Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser`
- Try: Run PowerShell as Administrator
- Check: PowerShell version: `$PSVersionTable.PSVersion`

### Handler runs but nothing detected
1. Normal if no error triggered
2. Let it run while working normally
3. Verify no false positives (good sign)
4. When ready, trigger real connection error

### Handler detects error but doesn't click
1. Verify coordinates are correct (from user's table)
2. Check if error dialog is actually modal
3. Try clicking Resume button manually to verify it works

### Coordinates seem wrong
1. If clicks miss the button:
   - Provide new coordinates
   - I can recalibrate the handler
   - May vary by monitor/resolution

### Need debugging info
Run: `Get-Process cursor` to verify Cursor is running
Check window brightness: Handler logs baseline brightness values

---

## How to Use During Workflows

### Typical Workflow
```powershell
# Terminal 1: Start handler
C:\dev\Autopack\scripts\handle_connection_errors.bat

# Terminal 2: Run your workflow
button_2.bat
button_3.bat
# or your normal process

# Handler monitors in background
# If connection error occurs, it's handled automatically
# No manual intervention needed
```

### Long-Running Processes
```powershell
# Keep handler running continuously
# It monitors all 9 grid slots
# Handles errors in any slot automatically
# No resource consumption when no errors present
```

---

## Summary

✅ **New visual detection handler is READY**
- Detects errors using pixel sampling
- Clicks Resume button at exact coordinates
- No interference with normal operation
- Debounces to avoid duplicate actions
- Works for all 9 grid slots

✅ **Launcher updated**
- `handle_connection_errors.bat` launches new handler
- Old keyboard handler is disabled

✅ **Ready for testing**
- Verify no interference with 30-second idle test
- Trigger connection error
- Verify handler detects and recovers

🚀 **Test now and report results!**

---

## Testing Checklist

- [ ] Launch handler: `handle_connection_errors.bat`
- [ ] Verify "MONITORING ACTIVE" status
- [ ] Wait 30 seconds with no errors → Verify NO clicks happen
- [ ] Trigger connection error in any Cursor window
- [ ] Wait for error dialog to appear
- [ ] Handler detects: "[!] CONNECTION ERROR DETECTED..."
- [ ] Handler clicks: "[+] Clicking Resume button..."
- [ ] Error dialog closes and Cursor recovers
- [ ] Stop handler: Ctrl+C
- [ ] Report results

---

## Next Steps

1. **Test with no errors** (verify no false positives)
2. **Test with real error** (verify detection and clicking)
3. **Test multiple slots** (if you have multiple Cursor windows)
4. **Report any issues** (coordinates, detection timing, etc.)
5. **Deploy for production** (use during long workflows)

Once confirmed working, you can use it for all your long-running workflows!
