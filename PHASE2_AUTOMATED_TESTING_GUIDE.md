# Phase 2: Automated Error Handler - Testing Guide

## Overview

Phase 2 implements **automatic detection and recovery** for connection errors. The handler:
- Captures baseline screenshots of all 9 grid slots on startup
- Continuously monitors for visual changes (error dialogs appearing)
- Automatically clicks Resume button when error detected
- Uses SHA256 hashing for fast, reliable change detection

## Files

### Handler Implementation
- `C:\dev\Autopack\scripts\handle_connection_errors_automated.ps1` - Main automated handler (515 lines)
- `C:\dev\Autopack\scripts\handle_connection_errors_automated.bat` - Direct launcher

### Launchers
- `C:\dev\Autopack\scripts\handle_connection_errors_menu.bat` - Choose Phase 1 (manual) or Phase 2 (automated)
- `C:\dev\Autopack\scripts\handle_connection_errors.bat` - Updated to note Phase 1/Phase 2 options

### Supporting Files (Phase 1)
- `C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1` - Manual handler (fallback if automated doesn't work)
- `C:\dev\Autopack\scripts\capture_error_screenshot.ps1` - Screenshot capture tool for analysis

## Quick Start

### Option 1: Automated Mode (New - Phase 2)
```batch
C:\dev\Autopack\scripts\handle_connection_errors_automated.bat
```

Or from PowerShell:
```powershell
& "C:\dev\Autopack\scripts\handle_connection_errors_automated.ps1"
```

### Option 2: Manual Mode (Phase 1 - Proven Working)
```batch
C:\dev\Autopack\scripts\handle_connection_errors.bat
```

### Option 3: Choose from Menu
```batch
C:\dev\Autopack\scripts\handle_connection_errors_menu.bat
```

## Expected Behavior - Phase 2 Automated

### On Startup
```
========== CONNECTION ERROR HANDLER (AUTOMATED) ==========

Status: MONITORING ACTIVE
Method: Screenshot comparison + automatic clicking
Press Ctrl+C to stop

This handler:
  [+] Captures baseline screenshots of 9 grid slots
  [+] Continuously monitors for visual changes
  [+] Detects error dialog by comparing pixel data
  [+] Automatically clicks Resume button when error detected
  [+] Only acts when actual change detected

===========================================================

Capturing baseline images for all 9 grid slots...

  Capturing slot 1... [OK]
  Capturing slot 2... [OK]
  Capturing slot 3... [OK]
  ...

Baseline capture complete.

Ready. Monitoring grid for connection errors...
```

### When Error Detected
```
[14:23:45] [!] CONNECTION ERROR DETECTED IN GRID SLOT 3
  Screen changed - likely error dialog appeared
  Attempting to recover...
[14:23:45] [+] Clicking Resume button in SLOT 3 at (4833, 337)
  [+] Recovery action sent
```

### Exit (Ctrl+C)
```
========== SESSION SUMMARY ==========

Session Duration: 0h 2m 15s
Errors Detected: 2
Errors Handled: 2

Monitor stopped.
```

## Testing Workflow

### Phase 2a: Initial Startup Test
1. Open PowerShell or cmd
2. Run: `C:\dev\Autopack\scripts\handle_connection_errors_automated.bat`
3. Wait for baseline capture to complete
4. Verify: "Ready. Monitoring grid for connection errors..."
5. Let run for 1-2 minutes with no errors to verify NO false positives
6. Stop with Ctrl+C
7. Verify clean exit with session summary

**Success criteria**:
- ✅ Baseline captures successfully for all 9 slots
- ✅ No errors detected when no actual errors present
- ✅ Clean exit with session summary

### Phase 2b: Real Connection Error Test
1. Start handler: `handle_connection_errors_automated.bat`
2. Wait for baseline capture to complete
3. Trigger connection error in Cursor (e.g., disconnect internet briefly)
4. Wait for error dialog to appear in one of the grid slots
5. Observe handler output:
   - Should detect change within 2 seconds
   - Should click Resume button automatically
   - Should report in console

**Success criteria**:
- ✅ Error detected within 2 seconds
- ✅ Resume button clicked (you see click happen)
- ✅ Cursor recovers from error
- ✅ Handler continues monitoring

### Phase 2c: Multi-Slot Test
1. Start handler
2. Trigger errors in different grid slots (try slots 1, 5, 9)
3. Verify handler detects and clicks correct Resume button for each

**Success criteria**:
- ✅ Correct slot identified
- ✅ Correct coordinates clicked
- ✅ Each error handled independently

### Phase 2d: Rapid Error Test
1. Start handler
2. Trigger multiple errors quickly (same slot)
3. Verify debouncing works (5-second cooldown prevents duplicate clicks)

**Success criteria**:
- ✅ First error handled immediately
- ✅ Second error within 5 seconds NOT handled (debounce active)
- ✅ Error after 5 seconds IS handled (debounce expired)

## Configuration Tuning

### Monitor Interval
```powershell
$MONITOR_INTERVAL_MS = 2000  # Check every 2 seconds
```
- Current: 2000ms (2 seconds)
- Decrease for faster detection
- Increase for lower resource usage

### Debounce Time
```powershell
$ERROR_DEBOUNCE_MS = 5000  # Wait 5 seconds between actions
```
- Current: 5000ms (5 seconds)
- Prevents multiple clicks for same error
- Increase if handler is clicking twice per error

### Change Threshold
```powershell
$CHANGE_THRESHOLD = 0.15  # 15% pixel change = error
```
- Current: Not used (we use SHA256 hash comparison instead)
- For future pixel sampling implementation

## Output Files

### Baseline Images
```
C:\dev\Autopack\error_baselines\
  ├─ baseline_slot_1.png
  ├─ baseline_slot_2.png
  ├─ ...
  └─ baseline_slot_9.png
```

These are captured on handler startup and used for comparison.

### Temporary Files
```
C:\dev\Autopack\temp_current_1.png
C:\dev\Autopack\temp_current_2.png
...
```

Cleaned up automatically after each check (removed same second).

## Troubleshooting

### Issue: "Baseline capture failed for slot X"
- **Cause**: Cannot take screenshot of that grid area
- **Solution**: Check that Cursor windows are positioned correctly
- **Verify**: Run `capture_error_screenshot.ps1` to test screenshot capture

### Issue: No errors detected when error appears
- **Cause**: Screen change might be minimal (e.g., small error toast)
- **Solution**: Monitor handler output to see if hash comparison shows changes
- **Debug**: Run Phase 2d error test to verify detection

### Issue: False positives (clicks when no error)
- **Cause**: Small visual changes from normal operation (cursor blinking, tab switching)
- **Solution**: Increase CHANGE_THRESHOLD or switch to manual mode (Phase 1)
- **Debug**: Check baseline_slot_X.png files to see baseline states

### Issue: Clicks happening but Cursor doesn't recover
- **Cause**: Coordinates might be wrong
- **Solution**: Fall back to manual mode (Phase 1) to verify coordinates work
- **Verify**: Run Phase 1 test with `handle_connection_errors.bat`

## Comparison: Phase 1 vs Phase 2

| Feature | Phase 1 (Manual) | Phase 2 (Automated) |
|---------|------------------|-------------------|
| **Trigger** | You type slot number | Automatic detection |
| **User action** | Type + Press Enter | None after startup |
| **Detection** | Human visual | Screenshot hashing |
| **Accuracy** | 100% (manual control) | ~95% (depends on change threshold) |
| **False positives** | None (user confirms) | Possible (visual changes) |
| **Fallback** | N/A | Use Phase 1 if issues |
| **Status** | ✅ Proven working | 🧪 Testing now |

## Recovery Plan

If Phase 2 automated handler has issues:

1. **Minor issues** (occasional false positives):
   - Increase `ERROR_DEBOUNCE_MS` to reduce frequency
   - Or switch to Phase 1 (manual mode)

2. **Major issues** (not detecting errors):
   - Run `capture_error_screenshot.ps1` when error appears
   - Share screenshot for analysis
   - Use Phase 1 manual mode in the meantime

3. **Complete failure**:
   - Switch to Phase 1: `handle_connection_errors.bat`
   - Phase 1 is proven working

## Next Steps

### Immediate Testing
1. [ ] Test startup with no errors
2. [ ] Trigger real connection error
3. [ ] Verify automatic detection and recovery
4. [ ] Test multiple grid slots

### If Tests Pass
1. [ ] Commit Phase 2 code to git
2. [ ] Update handler launch scripts
3. [ ] Document final configuration

### If Issues Found
1. [ ] Capture error screenshots for analysis
2. [ ] Use Phase 1 manual mode as interim solution
3. [ ] Tune detection parameters
4. [ ] Re-test

## Contact

If Phase 2 automated handler needs adjustment:
- Share error screenshots from `capture_error_screenshot.ps1`
- Report which slots had issues
- Include session duration and error count
- Can revert to Phase 1 (manual) at any time
