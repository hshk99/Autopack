# Connection Error Handler Guide

## Overview

The connection error handler automatically detects and responds to connection error dialogs that appear in Cursor windows when internet connectivity is interrupted. Instead of manually clicking "Resume" or "Try again" buttons, this tool monitors your Cursor windows and handles these errors automatically.

## Problem Statement

When running long automation workflows (like Button 1, 2, or 3), internet disconnections can cause error dialogs to appear in Cursor windows with options to "Resume" or "Try again". Without automated handling, you need to manually intervene to click these buttons for each affected window, which interrupts the workflow.

## Solution

The `handle_connection_errors.ps1` script:

1. **Monitors continuously** - Scans every 2 seconds for connection error dialogs
2. **Detects error dialogs** - Uses Windows UI Automation to find error dialogs
3. **Prioritizes Resume** - Clicks "Resume" button if available (preferred recovery)
4. **Falls back to Try again** - Clicks "Try again" if Resume not available
5. **Works across all windows** - Handles errors in any Cursor window simultaneously
6. **Runs for 5 minutes** - Monitor runs for up to 5 minutes, then stops

## Usage

### Option 1: Direct Launch (Easiest)

Run the batch file wrapper:
```
handle_connection_errors.bat
```

This will:
- Start the connection error monitor in a new console window
- Display status messages as errors are detected and handled
- Run for up to 5 minutes
- Close when done or when you press Ctrl+C

### Option 2: From PowerShell

```powershell
.\handle_connection_errors.ps1
```

### Option 3: Scheduled/Background

Run in PowerShell with no window:
```powershell
Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `C:\dev\Autopack\scripts\handle_connection_errors.ps1`"
```

## Recommended Workflow

### For Long-Running Tasks

1. **Before starting Button workflows:**
   ```
   handle_connection_errors.bat
   ```
   (Leave this running in a separate window/terminal)

2. **Start your workflow:**
   - Button 1, 2, 3, or other long-running task
   - The error handler will automatically manage any connection errors
   - Continue with your work without interruption

3. **Error handler automatically:**
   - Detects connection error dialogs
   - Clicks appropriate button
   - Logs what was handled
   - Continues monitoring

4. **When done:**
   - Error handler stops after 5 minutes
   - Or press Ctrl+C to stop manually

## Output Examples

### Successful Resume
```
[FOUND] Detected connection error dialog with 'Resume' button
  → Clicking 'Resume' button...
```

### Successful Try Again
```
[FOUND] Detected connection error dialog with 'Try again' button
  → Clicking 'Try again' button...
```

### Summary
```
========== SUMMARY ==========
Errors detected: 3
Resume buttons clicked: 2
Try again buttons clicked: 1

Monitor stopped after 5 minutes
```

## How It Works (Technical)

1. **Window Detection:**
   - Looks for active Cursor or VS Code processes
   - Finds visible windows that might contain error dialogs

2. **UI Automation:**
   - Uses .NET System.Windows.Automation APIs
   - Searches for buttons with text "Resume" or "Try again"
   - Traverses the entire window tree looking for these elements

3. **Button Invocation:**
   - Attempts to invoke (click) the button using InvokePattern
   - If successful, logs the action
   - Waits 500ms before continuing scan

4. **Error Logging:**
   - Displays any UI Automation errors that occur
   - Shows which buttons were clicked
   - Provides summary statistics

## Limitations

1. **Text-based detection:** Only finds buttons with exact text "Resume" or "Try again"
   - If error dialogs use different button text, handler won't detect them
   - Future: Can be enhanced to detect by button position/image recognition

2. **UI Automation requirements:**
   - Requires UI Automation APIs available on Windows 7+
   - Works with standard Windows dialogs
   - May not work with custom/non-standard dialogs

3. **5-minute timeout:**
   - Script automatically stops after 5 minutes
   - This is a safety measure to prevent infinite monitoring
   - Can be manually stopped with Ctrl+C

4. **No visual indication in Cursor:**
   - Error handler runs in separate console window
   - You won't see which specific window had the error (yet)
   - Future enhancement: Show Cursor window name that had error

## Future Enhancements

Potential improvements for next version:

1. **Window identification:** Show which Cursor window (slot #) had the error
2. **Longer timeouts:** Allow configurable monitoring duration
3. **Visual notifications:** Toast notifications or logging to file
4. **Error analysis:** Log error details for troubleshooting
5. **Image recognition:** Detect error dialogs even with different text
6. **Selective monitoring:** Option to only monitor specific windows/projects

## Troubleshooting

### Handler doesn't detect errors

**Possible causes:**
- Button text is different from "Resume" or "Try again"
- Error dialog uses custom UI elements (not standard Windows)
- UI Automation APIs not available on your system

**Solution:**
- Check the exact button text in the error dialog
- Provide screenshot or coordinates and we can implement coordinate-based clicking

### Handler crashes or errors

**Check:**
- PowerShell execution policy allows script execution
- UI Automation assemblies are available
- No conflicting scripts running

**Fix:**
- Run: `Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser`
- Try running with `-WindowStyle Normal` to see error messages

### Some errors aren't handled

**Possible causes:**
- Error dialog appears after handler started (timing issue)
- Handler was stopped (5 minute limit)
- Button text varies or uses special characters

**Solution:**
- Start handler before running Button workflows
- Keep handler running for entire duration of workflows

## Related Scripts

- **reset_all_pending_phases.ps1** - Reset PENDING phases to READY for retesting
- **auto_fill_empty_slots.ps1** - Button 2: Fill empty Cursor slots with prompts
- **check_pr_status.ps1** - Button 3: Check PR status and mark completed
- **cleanup_wave_prompts.ps1** - Button 4: Remove completed phases

## Support

If you encounter issues or need customizations:

1. Check coordinates if you prefer coordinate-based approach
2. Provide error dialog screenshots
3. Note specific button text if different
4. Report any pattern that the script should handle
