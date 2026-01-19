# Connection Error Handler - Visual Detection + Coordinate-Based Clicking
# Detects error dialog by pixel sampling and clicks Resume button at known coordinates
# Only acts when error is actually detected - no interference with normal operation

# Configuration - Resume Button Coordinates (from user)
$RESUME_BUTTON_COORDS = @{
    1 = @{ X = 3121; Y = 337 }   # Slot 1 (top-left)
    2 = @{ X = 3979; Y = 337 }   # Slot 2 (top-center)
    3 = @{ X = 4833; Y = 337 }   # Slot 3 (top-right)
    4 = @{ X = 3121; Y = 801 }   # Slot 4 (mid-left)
    5 = @{ X = 3979; Y = 801 }   # Slot 5 (mid-center)
    6 = @{ X = 4833; Y = 801 }   # Slot 6 (mid-right)
    7 = @{ X = 3121; Y = 1264 }  # Slot 7 (bot-left)
    8 = @{ X = 3979; Y = 1264 }  # Slot 8 (bot-center)
    9 = @{ X = 4833; Y = 1264 }  # Slot 9 (bot-right)
}

# Grid window positions (5120x1440 monitor with 3x3 layout, each ~1707x480)
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

$MONITOR_INTERVAL_MS = 2000          # Check every 2 seconds
$PIXEL_SAMPLE_OFFSET_PERCENT = 0.5   # Sample from center of window
$BRIGHTNESS_THRESHOLD = 500          # Dialog overlay is brighter than editor
$ERROR_DEBOUNCE_MS = 5000            # Wait 5 seconds between actions in same slot

Write-Host ""
Write-Host "========== CONNECTION ERROR HANDLER (VISUAL DETECTION) ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status: MONITORING ACTIVE" -ForegroundColor Green
Write-Host "Method: Pixel sampling + coordinate-based clicking"
Write-Host "Press Ctrl+C to stop"
Write-Host ""
Write-Host "This handler:"
Write-Host "  [+] Samples pixel in each grid window"
Write-Host "  [+] Detects error dialog by brightness change"
Write-Host "  [+] Clicks Resume button at known coordinates"
Write-Host "  [+] Only acts when error is actually detected"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Gray
Write-Host ""

# Tracking variables
$sessionStartTime = Get-Date
$errorCount = 0
$handledCount = 0
$lastActionTime = @{}  # Track last action per slot to debounce
$baselinePixels = @{}  # Store baseline pixel colors for each slot

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

# Get pixel color at specified coordinates
function Get-PixelColor {
    param([int]$X, [int]$Y)

    try {
        Add-Type -AssemblyName System.Windows.Forms
        $bitmap = New-Object System.Drawing.Bitmap(1, 1)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)

        $graphics.CopyFromScreen($X, $Y, 0, 0, $bitmap.Size)
        $graphics.Dispose()

        $pixel = $bitmap.GetPixel(0, 0)
        $bitmap.Dispose()

        return @{ R = $pixel.R; G = $pixel.G; B = $pixel.B; A = $pixel.A }
    } catch {
        return $null
    }
}

# Detect if error dialog is present in a grid slot by checking pixel brightness
function Detect-ErrorDialog {
    param([int]$Slot)

    try {
        $gridInfo = $GRID_POSITIONS[$Slot]

        # Sample pixel from center of window
        $sampleX = $gridInfo.x + ($gridInfo.width / 2)
        $sampleY = $gridInfo.y + ($gridInfo.height / 2)

        $pixel = Get-PixelColor -X $sampleX -Y $sampleY

        if ($null -eq $pixel) {
            return $false
        }

        # Calculate brightness
        $brightness = $pixel.R + $pixel.G + $pixel.B

        # Error dialog typically has gray/white background overlay
        # Normal Cursor editor has darker colors
        # Threshold of 500 works for distinguishing dialog from editor
        $isDialog = $brightness -gt $BRIGHTNESS_THRESHOLD

        return $isDialog
    } catch {
        return $false
    }
}

# Click the Resume button at the configured coordinates for a slot
function Click-ResumeButton {
    param([int]$Slot)

    try {
        $coords = $RESUME_BUTTON_COORDS[$Slot]

        # C# code for mouse movement and clicking
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
"@ -ErrorAction SilentlyContinue

        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [+] Clicking Resume button at ($($coords.X), $($coords.Y))" -ForegroundColor Green
        [MouseClicker]::Click($coords.X, $coords.Y)

        # Wait for dialog to close
        Start-Sleep -Milliseconds 500

        return $true
    } catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [!] Error clicking button: $_" -ForegroundColor Red
        return $false
    }
}

# Initialize baseline pixels for each slot
function Initialize-Baseline {
    Write-Host "Initializing baseline pixel colors for each grid slot..." -ForegroundColor Yellow

    foreach ($slot in 1..9) {
        try {
            $gridInfo = $GRID_POSITIONS[$slot]
            $sampleX = $gridInfo.x + ($gridInfo.width / 2)
            $sampleY = $gridInfo.y + ($gridInfo.height / 2)

            $pixel = Get-PixelColor -X $sampleX -Y $sampleY
            if ($null -ne $pixel) {
                $baselinePixels[$slot] = $pixel
                $brightness = $pixel.R + $pixel.G + $pixel.B
                Write-Host "  Slot $slot baseline brightness: $brightness" -ForegroundColor Gray
            }
        } catch {
            Write-Host "  Slot $slot initialization failed" -ForegroundColor Gray
        }
    }

    Write-Host ""
}

# Main monitoring loop
try {
    Write-Host "Initializing visual monitoring..." -ForegroundColor Yellow
    Write-Host ""

    Initialize-Baseline

    Write-Host "Ready. Monitoring grid for connection errors..." -ForegroundColor Green
    Write-Host ""

    while ($true) {
        # Check if Cursor is running
        if (-not (Test-CursorRunning)) {
            Start-Sleep -Milliseconds $MONITOR_INTERVAL_MS
            continue
        }

        # Check each grid slot for error dialog
        foreach ($slot in 1..9) {
            try {
                # Detect if error dialog is present
                if (Detect-ErrorDialog -Slot $slot) {
                    $errorCount++

                    # Check debounce - don't act twice in same slot within 5 seconds
                    $lastAction = $lastActionTime["slot_$slot"]
                    $timeSinceLastAction = $null
                    if ($null -ne $lastAction) {
                        $timeSinceLastAction = ((Get-Date) - $lastAction).TotalMilliseconds
                    }

                    if ($null -eq $lastAction -or $timeSinceLastAction -gt $ERROR_DEBOUNCE_MS) {
                        Write-Host ""
                        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [!] CONNECTION ERROR DETECTED IN GRID SLOT $slot" -ForegroundColor Yellow
                        Write-Host "  Attempting to recover..." -ForegroundColor Yellow

                        if (Click-ResumeButton -Slot $slot) {
                            $handledCount++
                            Write-Host "  [+] Recovery action sent" -ForegroundColor Green
                        } else {
                            Write-Host "  [!] Failed to click Resume button" -ForegroundColor Red
                        }

                        Write-Host ""
                        $lastActionTime["slot_$slot"] = Get-Date
                    }
                }
            } catch {
                # Continue to next slot on error
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
