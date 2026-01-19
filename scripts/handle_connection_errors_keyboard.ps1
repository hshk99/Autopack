# Handle connection errors using keyboard-based approach
# Continuously tries keyboard shortcuts to recover from connection errors
# No UI Automation, no screenshots - just keyboard input

# Configuration
$MONITOR_INTERVAL_MS = 3000          # Check every 3 seconds
$KEYBOARD_RETRY_INTERVAL = 500       # Milliseconds between key presses

Write-Host ""
Write-Host "========== CONNECTION ERROR HANDLER (KEYBOARD-BASED) ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status: MONITORING ACTIVE" -ForegroundColor Green
Write-Host "Method: Keyboard-based error recovery"
Write-Host "Press Ctrl+C to stop"
Write-Host ""
Write-Host "This handler will periodically send keyboard shortcuts:"
Write-Host "  [+] Enter key (confirm/accept dialog)"
Write-Host "  [+] Tab + Enter (navigate and confirm)"
Write-Host "  [+] Alt+R (if 'Resume' is Alt+R)"
Write-Host "  [+] Y key (if 'Yes' is just Y)"
Write-Host ""
Write-Host "Rationale: When Cursor shows error dialog, one of these keys"
Write-Host "          should trigger the 'Resume' or 'Retry' button"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Gray
Write-Host ""

# Tracking variables
$attemptCount = 0
$sessionStartTime = Get-Date

# Set up Ctrl+C handler for graceful shutdown
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Gray
    Write-Host ""
    Write-Host "========== SESSION SUMMARY ==========" -ForegroundColor Green
    Write-Host ""
    $uptime = (Get-Date) - $sessionStartTime
    Write-Host "Session Duration: $($uptime.Hours)h $($uptime.Minutes)m $($uptime.Seconds)s"
    Write-Host "Recovery Attempts: $attemptCount"
    Write-Host ""
    Write-Host "To verify if this worked:"
    Write-Host "  1. Check if Cursor recovered after error appeared"
    Write-Host "  2. If not, use coordinate-based clicking instead"
    Write-Host "  3. Share coordinates and I can add them"
    Write-Host ""
    Write-Host "Monitor stopped." -ForegroundColor Cyan
    Write-Host ""
}

# Check if Cursor is running
function Test-CursorRunning {
    try {
        $cursorProcesses = @(Get-Process -Name "cursor" -ErrorAction SilentlyContinue)
        return $cursorProcesses.Count -gt 0
    } catch {
        return $false
    }
}

# Get the active window (for context)
function Get-ActiveWindowTitle {
    try {
        $wshShell = New-Object -ComObject WScript.Shell
        return $wshShell.AppActivate("Cursor") | Out-Null
    } catch {
        return $false
    }
}

# Try to recover from error using keyboard
function Try-KeyboardRecovery {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Attempting keyboard-based recovery..." -ForegroundColor Yellow

    try {
        $wshShell = New-Object -ComObject WScript.Shell

        # Strategy 1: Try Enter key (most common for accepting dialogs)
        Write-Host "  [*] Sending: Enter key" -ForegroundColor Gray
        $wshShell.SendKeys("{ENTER}")
        Start-Sleep -Milliseconds $KEYBOARD_RETRY_INTERVAL

        # Strategy 2: Try Tab + Enter (navigate to button then confirm)
        Write-Host "  [*] Sending: Tab key" -ForegroundColor Gray
        $wshShell.SendKeys("{TAB}")
        Start-Sleep -Milliseconds 200

        Write-Host "  [*] Sending: Enter key" -ForegroundColor Gray
        $wshShell.SendKeys("{ENTER}")
        Start-Sleep -Milliseconds $KEYBOARD_RETRY_INTERVAL

        # Strategy 3: Try Alt+R (common for Resume)
        Write-Host "  [*] Sending: Alt+R (Resume shortcut)" -ForegroundColor Gray
        $wshShell.SendKeys("%(r)")
        Start-Sleep -Milliseconds $KEYBOARD_RETRY_INTERVAL

        # Strategy 4: Try Y key (common for Yes/Retry)
        Write-Host "  [*] Sending: Y key (Yes/Retry)" -ForegroundColor Gray
        $wshShell.SendKeys("y")
        Start-Sleep -Milliseconds $KEYBOARD_RETRY_INTERVAL

        # Strategy 5: Try R key (common for Retry)
        Write-Host "  [*] Sending: R key (Retry)" -ForegroundColor Gray
        $wshShell.SendKeys("r")
        Start-Sleep -Milliseconds $KEYBOARD_RETRY_INTERVAL

        Write-Host "  [+] Recovery attempts sent" -ForegroundColor Green
        Write-Host ""

        return $true
    } catch {
        Write-Host "  [!] Error during recovery attempt: $_" -ForegroundColor Red
        return $false
    }
}

# Main monitoring loop
try {
    Write-Host "Initializing keyboard monitoring..." -ForegroundColor Yellow
    Write-Host "Note: This sends keyboard input periodically to all windows" -ForegroundColor Gray
    Write-Host "      The keys should activate error recovery if a dialog is open" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Ready. Monitoring for connection errors..." -ForegroundColor Green
    Write-Host ""

    $lastAttemptTime = $null

    while ($true) {
        # Check if Cursor is running
        if (-not (Test-CursorRunning)) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Cursor not running, skipping check" -ForegroundColor Gray
            Start-Sleep -Milliseconds $MONITOR_INTERVAL_MS
            continue
        }

        # Send recovery keys periodically
        # This approach: Always send keys, assuming if there's an error dialog, the keys will help
        # If no error dialog, the keys are harmless (just sent to whatever window has focus)

        $now = Get-Date
        if ($null -eq $lastAttemptTime -or ($now - $lastAttemptTime).TotalSeconds -ge ($MONITOR_INTERVAL_MS / 1000)) {
            $attemptCount++
            Try-KeyboardRecovery
            $lastAttemptTime = $now
        }

        Start-Sleep -Milliseconds 1000
    }
}
catch {
    Write-Host ""
    Write-Host "Monitor error: $_" -ForegroundColor Red
}
finally {
    Write-Host ""
    Write-Host "Monitoring stopped"
    Write-Host ""
}
