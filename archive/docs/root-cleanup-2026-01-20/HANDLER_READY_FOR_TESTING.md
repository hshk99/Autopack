# Connection Error Handler - READY FOR TESTING

## Status: UPDATED & READY

The keyboard-based handler is now fully configured and ready to test. The `.bat` file has been updated to launch the keyboard approach by default.

---

## Quick Start (2 minutes)

### Step 1: Launch the Handler
```powershell
C:\dev\Autopack\scripts\handle_connection_errors.bat
```

Or manually:
```powershell
cd C:\dev\Autopack\scripts
.\handle_connection_errors_keyboard.ps1
```

You should see output like:
```
========== CONNECTION ERROR HANDLER (KEYBOARD-BASED) ==========

Status: MONITORING ACTIVE
Method: Keyboard-based error recovery
Press Ctrl+C to stop

Ready. Monitoring for connection errors...
```

### Step 2: Trigger a Connection Error
While the handler is running:
1. Open Cursor and one of your workflows
2. Temporarily disconnect your internet (or simulate connection error)
3. Wait for error dialog to appear in Cursor

### Step 3: Observe Recovery
The handler will automatically send keyboard shortcuts every 3 seconds:
- Enter key (confirm/accept)
- Tab + Enter (navigate and confirm)
- Alt+R (Resume shortcut)
- Y key (Yes/Retry)
- R key (Retry)

**If Cursor recovers and reconnects**: ✅ **IT WORKS!**
- Connection restored
- Cursor continues working
- Handler successfully recovered from error

**If Cursor doesn't recover**: ⚠️ Move to coordinate-based approach
- Handler will note that keyboard didn't work
- Share button coordinates with me
- I'll add them to the coordinate-based handler

### Step 4: Stop Handler
```
Press Ctrl+C
```

---

## What This Handler Does

The keyboard-based approach sends keyboard shortcuts every 3 seconds to any window with focus:

```
1. {ENTER}        → Accepts/confirms dialogs
2. {TAB}+{ENTER}  → Navigate to button, then accept
3. %(r) [Alt+R]   → Resume shortcut (common in Cursor)
4. y              → Yes/Retry key
5. r              → Retry key
```

When an error dialog appears in Cursor, one of these keys should trigger the "Resume" or "Try Again" button.

---

## Alternative: Screenshot-Based Handler

If keyboard approach doesn't work, there's an alternative that uses visual detection:

```powershell
C:\dev\Autopack\scripts\handle_connection_errors_screenshot.bat
```

This approach:
1. Takes screenshots of your 3x3 grid (9 Cursor windows)
2. Detects which window has an error popup
3. Tries keyboard shortcuts first
4. Falls back to coordinate-based clicking if needed

---

## Two Approaches Available

### Keyboard-Based (Recommended First) ✅
- **File**: `handle_connection_errors_keyboard.ps1`
- **Bat**: `handle_connection_errors.bat`
- **Pros**: Simple, no configuration needed, works if Cursor responds to keyboard
- **Cons**: May not work if Cursor has focus on different window
- **Try this first**

### Screenshot-Based (Fallback) ⚠️
- **File**: `handle_connection_errors_screenshot.ps1`
- **Bat**: `handle_connection_errors_screenshot.bat`
- **Pros**: Detects which specific window has error, more targeted
- **Cons**: Requires coordinate configuration for reliable clicking
- **Use if keyboard doesn't work**

---

## Expected Outcomes

### Scenario A: Works Immediately ✅
```
1. Launch handler
2. Run Button 2 or your workflow
3. Trigger connection error
4. Error appears in Cursor
5. Handler sends keyboard shortcuts
6. Cursor recovers automatically
7. Workflow continues
```
**Result**: Use this handler for long-running workflows!

### Scenario B: Keyboard Doesn't Work ⚠️
```
1. Launch handler
2. Trigger error
3. Error appears
4. Handler sends keys
5. Cursor doesn't recover
6. Handler stops sending after timeout
```
**Next**: Share error button coordinates, I'll add them to screenshot handler

### Scenario C: Partial Recovery ⚠️
```
1. Some keyboard shortcuts help
2. But not all do
3. Error sometimes recovers, sometimes not
```
**Next**: We can optimize which shortcuts are most effective

---

## Testing Checklist

- [ ] Start handler: `handle_connection_errors.bat`
- [ ] Verify handler shows "MONITORING ACTIVE" status
- [ ] Wait for handler to show status updates
- [ ] Trigger a connection error in Cursor
- [ ] Observe if error dialog appears
- [ ] Check if Cursor recovers within 10 seconds
- [ ] Stop handler (Ctrl+C)
- [ ] Report results

---

## Files Reference

| File | Purpose |
|------|---------|
| `handle_connection_errors.bat` | Main launcher (keyboard-based, recommended) |
| `handle_connection_errors_keyboard.ps1` | Keyboard shortcut approach |
| `handle_connection_errors_screenshot.ps1` | Screenshot detection + keyboard/coordinates |
| `handle_connection_errors_screenshot.bat` | Launcher for screenshot approach |

---

## Next Steps After Testing

### If Keyboard Works ✅
1. Run during long workflows
2. Handler monitors and recovers automatically
3. No manual intervention needed

### If Keyboard Doesn't Work ⚠️
1. When error appears, note which grid slot (1-9)
2. Take screenshot of that window
3. Identify the button coordinates
4. Share coordinates like: "Grid 3: Button at X=850, Y=200"
5. I'll configure coordinate-based handler

### If It's Intermittent ⚠️
1. Try different keyboard shortcuts
2. We can customize the handler
3. Or combine keyboard + coordinates

---

## Troubleshooting

### Handler doesn't start
- Check: `Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser`
- Try running as Administrator
- Check PowerShell version: `$PSVersionTable.PSVersion`

### Handler starts but doesn't seem to do anything
- This is normal if no error is triggered
- Run a workflow that causes connection errors
- Check Cursor has actual error dialog showing

### Handler seems to send keys but Cursor doesn't recover
- Keyboard shortcuts might not be configured in Cursor
- Try moving to coordinate-based approach
- Share button coordinates with me

### Need more diagnostic info
- Run: `.\find_cursor_windows.ps1`
- This shows how many Cursor windows are detected
- Helps verify Cursor is running properly

---

## Ready to Test?

```powershell
# Terminal 1: Start handler
C:\dev\Autopack\scripts\handle_connection_errors.bat

# Terminal 2: Run workflow
button_2.bat
button_3.bat
# or your normal workflow

# Handler will monitor in background
# If connection error occurs, it will attempt recovery automatically
```

**Let me know the results!**

---

## Summary

✅ **Keyboard-based handler is READY**
- Updated .bat file to use keyboard approach
- Handler sends keyboard shortcuts every 3 seconds
- Should recover from most connection errors
- No configuration needed - try it!

⚠️ **If keyboard doesn't work**
- Screenshot-based handler available as fallback
- Requires button coordinates
- More reliable once configured

🚀 **Next**: Test with real connection error and report results!
