# Connection Error Handler - Automated Detection + Clicking
# Captures baseline screenshots, monitors for changes, detects errors, clicks Resume automatically

# Resume button coordinates for each grid slot (confirmed working in Phase 1)
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

# Grid window positions
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

# Configuration
$MONITOR_INTERVAL_MS = 2000          # Check every 2 seconds
$ERROR_DEBOUNCE_MS = 5000            # Wait 5 seconds between actions in same slot
$BASELINE_DIR = "C:\dev\Autopack\error_baselines"

# Enhanced detection thresholds
# Based on ACTUAL error dialogs captured from Cursor:
# - Error dialogs cause 20-40% pixel change (visible but not full-screen)
# - Text and borders have moderate color differences (RGB diff ~45)
# - Only 2-4% of changed pixels are bright (error text is sparse)
$PERCENT_CHANGE_THRESHOLD = 15       # Must be >15% changed (error dialog visible)
$COLOR_DIFF_THRESHOLD = 45           # RGB difference threshold (error text/border colors)
$BRIGHT_PIXEL_RATIO = 0.02           # At least 2% of changes are bright (error text)

Write-Host ""
Write-Host "========== CONNECTION ERROR HANDLER (AUTOMATED) ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status: MONITORING ACTIVE" -ForegroundColor Green
Write-Host "Method: Screenshot comparison + automatic clicking"
Write-Host "Press Ctrl+C to stop"
Write-Host ""
Write-Host "This handler:"
Write-Host "  [+] Captures baseline screenshots of 9 grid slots"
Write-Host "  [+] Continuously monitors for visual changes"
Write-Host "  [+] Detects error dialog by comparing pixel data"
Write-Host "  [+] Automatically clicks Resume button when error detected"
Write-Host "  [+] Only acts when actual change detected"
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Gray
Write-Host ""

# Tracking variables
$sessionStartTime = Get-Date
$errorCount = 0
$handledCount = 0
$lastActionTime = @{}
$baselineImages = @{}

# Set up Ctrl+C handler
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Gray
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

# Take screenshot of grid area
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

# Calculate hash of image file (simple change detection)
function Get-ImageHash {
    param([string]$FilePath)

    try {
        $fileContent = [System.IO.File]::ReadAllBytes($FilePath)
        $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($fileContent)
        return ([BitConverter]::ToString($hash) -replace '-')
    } catch {
        return $null
    }
}

# Capture baseline images for all 9 slots
function Capture-Baseline {
    Write-Host "Capturing baseline images for all 9 grid slots..." -ForegroundColor Yellow
    Write-Host ""

    if (-not (Test-Path $BASELINE_DIR)) {
        New-Item -ItemType Directory -Path $BASELINE_DIR -ErrorAction SilentlyContinue | Out-Null
    }

    foreach ($slot in 1..9) {
        try {
            $gridInfo = $GRID_POSITIONS[$slot]
            $baselinePath = "$BASELINE_DIR\baseline_slot_$slot.png"

            Write-Host -NoNewline "  Capturing slot $slot... "

            if (Take-ScreenshotOfArea -X $gridInfo.x -Y $gridInfo.y -Width $gridInfo.width -Height $gridInfo.height -OutputPath $baselinePath) {
                $hash = Get-ImageHash -FilePath $baselinePath
                $baselineImages[$slot] = $hash
                Write-Host "[OK]" -ForegroundColor Green
            } else {
                Write-Host "[FAILED]" -ForegroundColor Red
            }
        } catch {
            Write-Host "[ERROR]" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "Baseline capture complete." -ForegroundColor Green
    Write-Host ""
}

# Detect error by comparing current screenshot to baseline
# Uses pixel-level comparison to detect modal dialogs (not cursor blinks or typing)
function Detect-ErrorDialog {
    param([int]$Slot)

    try {
        $gridInfo = $GRID_POSITIONS[$Slot]
        $tempPath = "C:\dev\Autopack\temp_current_$Slot.png"

        # Take current screenshot
        if (-not (Take-ScreenshotOfArea -X $gridInfo.x -Y $gridInfo.y -Width $gridInfo.width -Height $gridInfo.height -OutputPath $tempPath)) {
            return $false
        }

        # Open baseline and current images to compare pixel data
        Add-Type -AssemblyName System.Drawing

        try {
            $baselinePath = "$BASELINE_DIR\baseline_slot_$Slot.png"
            $baselineImg = [System.Drawing.Image]::FromFile($baselinePath)
            $currentImg = [System.Drawing.Image]::FromFile($tempPath)

            if ($baselineImg.Width -ne $currentImg.Width -or $baselineImg.Height -ne $currentImg.Height) {
                $baselineImg.Dispose()
                $currentImg.Dispose()
                Remove-Item $tempPath -ErrorAction SilentlyContinue
                return $false
            }

            # Convert to bitmaps for pixel access
            $baselineBmp = New-Object System.Drawing.Bitmap($baselineImg)
            $currentBmp = New-Object System.Drawing.Bitmap($currentImg)

            # Sample multiple points to detect modal dialog overlay
            # Error dialogs typically create significant pixel changes across many areas
            $changedPixels = 0
            $totalSamples = 0

            # Sample every 10th pixel to reduce computation (still accurate enough)
            $brightPixels = 0
            for ($x = 0; $x -lt $baselineBmp.Width; $x += 10) {
                for ($y = 0; $y -lt $baselineBmp.Height; $y += 10) {
                    $totalSamples++

                    $baselineColor = $baselineBmp.GetPixel($x, $y)
                    $currentColor = $currentBmp.GetPixel($x, $y)

                    # Calculate color difference
                    $rDiff = [Math]::Abs($baselineColor.R - $currentColor.R)
                    $gDiff = [Math]::Abs($baselineColor.G - $currentColor.G)
                    $bDiff = [Math]::Abs($baselineColor.B - $currentColor.B)
                    $maxDiff = [Math]::Max($rDiff, [Math]::Max($gDiff, $bDiff))

                    # If pixel changed significantly (high threshold to ignore normal activity)
                    if ($maxDiff -gt $COLOR_DIFF_THRESHOLD) {
                        $changedPixels++

                        # Check if changed pixel is bright (error dialogs are usually light)
                        $currentBrightness = ($currentColor.R + $currentColor.G + $currentColor.B) / 3
                        if ($currentBrightness -gt 150) {  # Bright threshold
                            $brightPixels++
                        }
                    }
                }
            }

            $percentChanged = ($changedPixels / $totalSamples) * 100
            $brightRatio = if ($changedPixels -gt 0) { $brightPixels / $changedPixels } else { 0 }

            # Error dialog detection: check both criteria to reduce false positives
            # 1. Significant percentage change (>30% = error dialog visible)
            # 2. Some bright pixels (error text/accents are usually bright)
            # Both must be true to avoid triggering on normal typing/tab switches
            $isError = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)

            # Clean up
            $baselineBmp.Dispose()
            $currentBmp.Dispose()
            $baselineImg.Dispose()
            $currentImg.Dispose()
            Remove-Item $tempPath -ErrorAction SilentlyContinue

            return $isError
        } catch {
            Remove-Item $tempPath -ErrorAction SilentlyContinue
            return $false
        }
    } catch {
        return $false
    }
}

# Click Resume button
function Click-ResumeButton {
    param([int]$Slot)

    try {
        $coords = $RESUME_BUTTON_COORDS[$Slot]

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

        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [+] Clicking Resume button in SLOT $Slot at ($($coords.X), $($coords.Y))" -ForegroundColor Green
        [MouseClicker]::Click($coords.X, $coords.Y)
        Start-Sleep -Milliseconds 500

        return $true
    } catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [!] Error clicking button: $_" -ForegroundColor Red
        return $false
    }
}

# Main monitoring loop
try {
    Write-Host "Initializing automated monitoring..." -ForegroundColor Yellow
    Write-Host ""

    Capture-Baseline

    Write-Host "Ready. Monitoring grid for connection errors..." -ForegroundColor Green
    Write-Host ""

    while ($true) {
        # Check if Cursor is running
        if (-not (Test-CursorRunning)) {
            Start-Sleep -Milliseconds $MONITOR_INTERVAL_MS
            continue
        }

        # Check each grid slot for changes
        foreach ($slot in 1..9) {
            try {
                if (Detect-ErrorDialog -Slot $slot) {
                    $errorCount++

                    # Debounce - don't act twice in same slot within 5 seconds
                    $lastAction = $lastActionTime["slot_$slot"]
                    $timeSinceLastAction = $null
                    if ($null -ne $lastAction) {
                        $timeSinceLastAction = ((Get-Date) - $lastAction).TotalMilliseconds
                    }

                    if ($null -eq $lastAction -or $timeSinceLastAction -gt $ERROR_DEBOUNCE_MS) {
                        Write-Host ""
                        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [!] CONNECTION ERROR DETECTED IN GRID SLOT $slot" -ForegroundColor Yellow
                        Write-Host "  Screen changed - likely error dialog appeared" -ForegroundColor Yellow
                        Write-Host "  Attempting to recover..." -ForegroundColor Yellow

                        if (Click-ResumeButton -Slot $slot) {
                            $handledCount++
                            Write-Host "  [+] Recovery action sent" -ForegroundColor Green
                            Write-Host "  [+] Cursor should recover now" -ForegroundColor Green
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
