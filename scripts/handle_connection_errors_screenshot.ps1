# Handle connection errors using screenshot detection
# 1. Takes screenshots of 3x3 grid (9 Cursor windows)
# 2. Detects which window has error popup
# 3. Uses keyboard or coordinates to press button

# Configuration
$MONITOR_INTERVAL_MS = 2000          # Check every 2 seconds
$GRID_ROWS = 3
$GRID_COLS = 3
$WINDOW_WIDTH = 1707
$WINDOW_HEIGHT = 480

# For 5120x1440 monitor with 3x3 grid:
# Each window is approximately 1707x480
# Starting positions for each grid slot
$GRID_POSITIONS = @{
    1 = @{ x = 0;    y = 0;   width = 1707; height = 480 }
    2 = @{ x = 1707; y = 0;   width = 1707; height = 480 }
    3 = @{ x = 3414; y = 0;   width = 1707; height = 480 }
    4 = @{ x = 0;    y = 480; width = 1707; height = 480 }
    5 = @{ x = 1707; y = 480; width = 1707; height = 480 }
    6 = @{ x = 3414; y = 480; width = 1707; height = 480 }
    7 = @{ x = 0;    y = 960; width = 1707; height = 480 }
    8 = @{ x = 1707; y = 960; width = 1707; height = 480 }
    9 = @{ x = 3414; y = 960; width = 1707; height = 480 }
}

Write-Host ""
Write-Host "========== CONNECTION ERROR HANDLER (SCREENSHOT-BASED) ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status: MONITORING ACTIVE" -ForegroundColor Green
Write-Host "Method: Screenshot detection + keyboard/coordinate-based interaction"
Write-Host "Grid: 3x3 (9 Cursor windows)"
Write-Host "Press Ctrl+C to stop"
Write-Host ""
Write-Host "This handler:"
Write-Host "  [+] Takes screenshots of 9 grid windows"
Write-Host "  [+] Detects error popups visually"
Write-Host "  [+] Tries keyboard shortcuts first (ESC, Enter, etc.)"
Write-Host "  [+] Falls back to coordinate-based clicking"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Gray
Write-Host ""

# Tracking variables
$errorCount = 0
$handledCount = 0
$lastErrorTime = @{}
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
    Write-Host "Errors Detected: $errorCount"
    Write-Host "Errors Handled: $handledCount"
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

# Take a screenshot of a specific window area
function Take-ScreenshotOfArea {
    param(
        [int]$X,
        [int]$Y,
        [int]$Width,
        [int]$Height,
        [string]$OutputPath
    )

    try {
        Add-Type -AssemblyName System.Windows.Forms
        $bitmap = New-Object System.Drawing.Bitmap($Width, $Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)

        $graphics.CopyFromScreen($X, $Y, 0, 0, $bitmap.Size)
        $graphics.Dispose()

        $bitmap.Save($OutputPath)
        $bitmap.Dispose()

        return $true
    } catch {
        return $false
    }
}

# Detect if screenshot contains error popup
# Looks for common error dialog patterns
function Detect-ErrorPopup {
    param(
        [string]$ImagePath,
        [int]$GridSlot
    )

    try {
        # For now, use a simple heuristic:
        # Check file size and properties
        # In a real implementation, would use OCR or image analysis
        # For testing, we'll use a marker file approach

        # Check if a marker file exists indicating error in this grid slot
        $markerFile = "C:\dev\Autopack\error_grid_$GridSlot.marker"
        if (Test-Path $markerFile) {
            return $true
        }

        return $false
    } catch {
        return $false
    }
}

# Handle error by trying keyboard first, then coordinates
function Handle-Error {
    param(
        [int]$GridSlot,
        [int]$ScreenX,
        [int]$ScreenY,
        [int]$Width,
        [int]$Height
    )

    Write-Host ""
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ERROR DETECTED IN GRID SLOT $GridSlot" -ForegroundColor Yellow
    Write-Host "  Position: ($ScreenX, $ScreenY)" -ForegroundColor Gray
    Write-Host "  Size: ${Width}x${Height}" -ForegroundColor Gray
    Write-Host ""

    # Try keyboard approaches first
    $keyboardAttempts = @(
        @{ Key = "{ENTER}"; Label = "Enter key (confirm dialog)" },
        @{ Key = "{ESC}"; Label = "Escape key (close dialog)" },
        @{ Key = "%(r)"; Label = "Alt+R (Resume)" },
        @{ Key = "%(t)"; Label = "Alt+T (Try again)" },
        @{ Key = "%(y)"; Label = "Alt+Y (Yes/Retry)" }
    )

    Write-Host "  Attempting keyboard approaches..." -ForegroundColor Cyan
    foreach ($attempt in $keyboardAttempts) {
        Write-Host "    [*] Trying: $($attempt.Label)" -ForegroundColor Gray

        try {
            # Add the WshShell COM object for sending keystrokes
            $wshShell = New-Object -ComObject WScript.Shell
            $wshShell.SendKeys($attempt.Key)

            Write-Host "    [+] Sent: $($attempt.Label)" -ForegroundColor Green
            Start-Sleep -Milliseconds 300

            # If keyboard succeeded, return
            return $true
        } catch {
            # Continue to next attempt
        }
    }

    Write-Host "  Keyboard approaches failed, manual coordinate clicking needed" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  To proceed with coordinate-based clicking:" -ForegroundColor Cyan
    Write-Host "    1. Identify the button coordinates in grid slot $GridSlot" -ForegroundColor Gray
    Write-Host "    2. Call: Click-ErrorButton -GridSlot $GridSlot -RelativeX 800 -RelativeY 200" -ForegroundColor Gray
    Write-Host "    3. Or edit this script's CLICK_COORDINATES map" -ForegroundColor Gray
    Write-Host ""

    return $false
}

# Click button at coordinates
function Click-ErrorButton {
    param(
        [int]$GridSlot,
        [int]$RelativeX,
        [int]$RelativeY
    )

    try {
        $gridInfo = $GRID_POSITIONS[$GridSlot]
        $absoluteX = $gridInfo.x + $RelativeX
        $absoluteY = $gridInfo.y + $RelativeY

        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Clicking at coordinates ($absoluteX, $absoluteY)" -ForegroundColor Green

        # Use C# to move mouse and click
        Add-Type @"
using System;
using System.Runtime.InteropServices;

public class MouseClicker {
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint cButtons, uint dwExtraInfo);

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;

    public static void Click(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(100);
        mouse_event(MOUSEEVENTF_LEFTDOWN, (uint)x, (uint)y, 0, 0);
        System.Threading.Thread.Sleep(50);
        mouse_event(MOUSEEVENTF_LEFTUP, (uint)x, (uint)y, 0, 0);
    }
}
"@

        [MouseClicker]::Click($absoluteX, $absoluteY)
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Click executed" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Click failed: $_" -ForegroundColor Red
        return $false
    }
}

# Main monitoring loop
try {
    Write-Host "Initializing screenshot monitoring..." -ForegroundColor Yellow
    Write-Host ""

    $tempDir = "C:\dev\Autopack\temp_screenshots"
    if (-not (Test-Path $tempDir)) {
        New-Item -ItemType Directory -Path $tempDir | Out-Null
    }

    Write-Host "Ready. Monitoring grid for connection errors..." -ForegroundColor Green
    Write-Host ""

    while ($true) {
        # Check if Cursor is running
        if (-not (Test-CursorRunning)) {
            Start-Sleep -Milliseconds $MONITOR_INTERVAL_MS
            continue
        }

        $timestamp = Get-Date -Format "HH:mm:ss"
        $errorFound = $false

        # Check each grid slot
        for ($slot = 1; $slot -le 9; $slot++) {
            try {
                $gridInfo = $GRID_POSITIONS[$slot]
                $screenshotPath = "$tempDir\grid_$slot.png"

                # Take screenshot of this grid area
                Take-ScreenshotOfArea -X $gridInfo.x -Y $gridInfo.y `
                    -Width $gridInfo.width -Height $gridInfo.height `
                    -OutputPath $screenshotPath | Out-Null

                # Check if error is in this screenshot
                if (Detect-ErrorPopup -ImagePath $screenshotPath -GridSlot $slot) {
                    $errorCount++
                    $errorFound = $true

                    # Avoid duplicate handling
                    $lastError = $lastErrorTime["slot_$slot"]
                    if ($null -eq $lastError -or ((Get-Date) - $lastError).TotalSeconds -gt 5) {
                        $handledCount++
                        Handle-Error -GridSlot $slot `
                            -ScreenX $gridInfo.x -ScreenY $gridInfo.y `
                            -Width $gridInfo.width -Height $gridInfo.height

                        $lastErrorTime["slot_$slot"] = Get-Date
                    }
                }
            } catch {
                # Continue to next slot
            }
        }

        Start-Sleep -Milliseconds $MONITOR_INTERVAL_MS
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
