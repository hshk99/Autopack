# Comprehensive handler diagnostic - captures what's happening during detection

Write-Host ""
Write-Host "========== HANDLER DETECTION DIAGNOSTIC ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will run the handler for 60 seconds and capture detailed detection info"
Write-Host ""

$BASELINE_DIR = "C:\dev\Autopack\error_baselines"
$DIAGNOSTIC_LOG = "C:\dev\Autopack\error_analysis\handler_diagnostic_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
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

# Detection thresholds (same as handler)
$PERCENT_CHANGE_THRESHOLD = 15
$COLOR_DIFF_THRESHOLD = 45
$BRIGHT_PIXEL_RATIO = 0.02

function Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "HH:mm:ss"
    $fullMessage = "[$timestamp] $Message"
    Write-Host $fullMessage
    Add-Content -Path $DIAGNOSTIC_LOG -Value $fullMessage
}

function Take-ScreenshotOfArea {
    param([int]$X, [int]$Y, [int]$Width, [int]$Height, [string]$OutputPath)
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

function Analyze-Slot {
    param([int]$Slot)

    $gridInfo = $GRID_POSITIONS[$Slot]
    $baselinePath = "$BASELINE_DIR\baseline_slot_$Slot.png"
    $currentPath = "C:\dev\Autopack\temp_diag_$Slot.png"

    if (-not (Test-Path $baselinePath)) {
        return $null
    }

    # Take screenshot
    if (-not (Take-ScreenshotOfArea -X $gridInfo.x -Y $gridInfo.y -Width $gridInfo.width -Height $gridInfo.height -OutputPath $currentPath)) {
        return $null
    }

    try {
        Add-Type -AssemblyName System.Drawing

        $baselineImg = [System.Drawing.Image]::FromFile($baselinePath)
        $currentImg = [System.Drawing.Image]::FromFile($currentPath)

        $baselineBmp = New-Object System.Drawing.Bitmap($baselineImg)
        $currentBmp = New-Object System.Drawing.Bitmap($currentImg)

        $changedPixels = 0
        $totalSamples = 0
        $brightPixels = 0

        for ($x = 0; $x -lt $baselineBmp.Width; $x += 10) {
            for ($y = 0; $y -lt $baselineBmp.Height; $y += 10) {
                $totalSamples++

                $baselineColor = $baselineBmp.GetPixel($x, $y)
                $currentColor = $currentBmp.GetPixel($x, $y)

                $rDiff = [Math]::Abs($baselineColor.R - $currentColor.R)
                $gDiff = [Math]::Abs($baselineColor.G - $currentColor.G)
                $bDiff = [Math]::Abs($baselineColor.B - $currentColor.B)
                $maxDiff = [Math]::Max($rDiff, [Math]::Max($gDiff, $bDiff))

                if ($maxDiff -gt $COLOR_DIFF_THRESHOLD) {
                    $changedPixels++

                    $currentBrightness = ($currentColor.R + $currentColor.G + $currentColor.B) / 3
                    if ($currentBrightness -gt 150) {
                        $brightPixels++
                    }
                }
            }
        }

        $percentChanged = ($changedPixels / $totalSamples) * 100
        $brightRatio = if ($changedPixels -gt 0) { $brightPixels / $changedPixels } else { 0 }

        $isError = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)

        $baselineBmp.Dispose()
        $currentBmp.Dispose()
        $baselineImg.Dispose()
        $currentImg.Dispose()
        Remove-Item $currentPath -ErrorAction SilentlyContinue

        return @{
            percentChanged = $percentChanged
            brightRatio = $brightRatio
            isError = $isError
            changedPixels = $changedPixels
        }
    } catch {
        Remove-Item $currentPath -ErrorAction SilentlyContinue
        return $null
    }
}

# Create output directory
if (-not (Test-Path "C:\dev\Autopack\error_analysis")) {
    New-Item -ItemType Directory -Path "C:\dev\Autopack\error_analysis" -ErrorAction SilentlyContinue | Out-Null
}

Log "========== HANDLER DETECTION DIAGNOSTIC =========="
Log ""
Log "Configuration:"
Log "  Percent change threshold: >$PERCENT_CHANGE_THRESHOLD%"
Log "  Color diff threshold: >$COLOR_DIFF_THRESHOLD RGB"
Log "  Bright pixel ratio: >$BRIGHT_PIXEL_RATIO (2%)"
Log ""
Log "Checking baselines..."

$baselineCount = 0
foreach ($slot in 1..9) {
    if (Test-Path "$BASELINE_DIR\baseline_slot_$slot.png") {
        $baselineCount++
    }
}

Log "  Found $baselineCount baseline files (expected 9)"
Log ""

if ($baselineCount -ne 9) {
    Log "[ERROR] Missing baseline files! Please start handler first to create baselines."
    Log ""
    Log "To fix:"
    Log "  1. Run: C:\dev\Autopack\scripts\handle_connection_errors_automated.bat"
    Log "  2. Wait for 'Ready. Monitoring grid for connection errors...'"
    Log "  3. Then run this diagnostic again"
    Log ""
    exit 1
}

Log "Baseline files OK. Starting detection analysis..."
Log ""
Log "Monitoring for 60 seconds. Trigger a connection error now!"
Log ""

$startTime = Get-Date
$endTime = $startTime.AddSeconds(60)
$checkInterval = 2000  # ms
$errorCount = 0
$detectionCount = 0

while ((Get-Date) -lt $endTime) {
    $timestamp = Get-Date -Format "HH:mm:ss"

    foreach ($slot in 1..9) {
        $result = Analyze-Slot -Slot $slot

        if ($null -ne $result) {
            $percentChanged = [Math]::Round($result.percentChanged, 1)
            $brightRatio = [Math]::Round($result.brightRatio * 100, 1)
            $isError = $result.isError

            if ($isError) {
                $color = "Red"
                $status = "DETECTED"
                $detectionCount++
                Log "[DETECTION] Slot $slot - $percentChanged% changed, $brightRatio% bright - ERROR DETECTED"
            } else {
                # Only log slots with significant changes
                if ($result.percentChanged -gt 5) {
                    Log "[MONITOR] Slot $slot - $percentChanged% changed, $brightRatio% bright - OK"
                }
            }
        }
    }

    Start-Sleep -Milliseconds $checkInterval
}

Log ""
Log "========== DIAGNOSTIC COMPLETE =========="
Log ""
Log "Results:"
Log "  Detections: $detectionCount"
Log "  Duration: 60 seconds"
Log ""
if ($detectionCount -eq 0) {
    Log "[INFO] No errors detected during monitoring period"
    Log ""
    Log "Possible causes:"
    Log "  1. No connection error occurred (expected - handler is waiting)"
    Log "  2. Error thresholds still need tuning"
    Log "  3. Baseline may have been captured WITH error visible"
    Log ""
    Log "NEXT STEPS:"
    Log "  1. Trigger a connection error in Cursor"
    Log "  2. Run this diagnostic again immediately"
    Log "  3. Share the log file for analysis"
} else {
    Log "[SUCCESS] Handler detected error(s)!"
    Log ""
    Log "Next: Check if handler clicked Resume button (mouse should have moved)"
}

Log ""
Log "Log file: $DIAGNOSTIC_LOG"
Log ""

# Write to console
Write-Host ""
Write-Host "Log saved to: $DIAGNOSTIC_LOG" -ForegroundColor Green
Write-Host ""
