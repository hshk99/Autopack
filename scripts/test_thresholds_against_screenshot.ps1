# Test if new thresholds would detect the actual error screenshot

Write-Host ""
Write-Host "========== THRESHOLD TEST ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Comparing error screenshot with baseline to determine detection"
Write-Host ""

$BASELINE_DIR = "C:\dev\Autopack\error_baselines"
$ERROR_SCREENSHOT = "C:\dev\Autopack\error_analysis\error_grid_20260119_162456.png"

# Current thresholds (FIXED based on actual error data)
$PERCENT_CHANGE_THRESHOLD = 15
$COLOR_DIFF_THRESHOLD = 45
$BRIGHT_PIXEL_RATIO = 0.02

Write-Host "Current Thresholds:" -ForegroundColor Yellow
Write-Host "  • Percent change: >$PERCENT_CHANGE_THRESHOLD%"
Write-Host "  • Color diff: >$COLOR_DIFF_THRESHOLD RGB"
Write-Host "  • Bright ratio: >$BRIGHT_PIXEL_RATIO (15%)"
Write-Host ""

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

Write-Host "Testing against error screenshot..." -ForegroundColor Green
Write-Host ""

foreach ($slot in 1..9) {
    Write-Host -NoNewline "Slot ${slot}: "

    $baselinePath = "$BASELINE_DIR\baseline_slot_$slot.png"
    if (-not (Test-Path $baselinePath)) {
        Write-Host "No baseline found" -ForegroundColor Yellow
        continue
    }

    try {
        Add-Type -AssemblyName System.Drawing

        # Load baseline
        $baselineImg = [System.Drawing.Image]::FromFile($baselinePath)
        $baselineBmp = New-Object System.Drawing.Bitmap($baselineImg)

        # Extract the corresponding grid region from error screenshot
        $errorImg = [System.Drawing.Image]::FromFile($ERROR_SCREENSHOT)
        $errorBmp = New-Object System.Drawing.Bitmap($errorImg)

        # Get the region for this slot
        $gridInfo = $GRID_POSITIONS[$slot]

        # Sample pixels and calculate changes
        $changedPixels = 0
        $totalSamples = 0
        $brightPixels = 0

        for ($x = 0; $x -lt $baselineBmp.Width; $x += 10) {
            for ($y = 0; $y -lt $baselineBmp.Height; $y += 10) {
                $totalSamples++

                $baselineColor = $baselineBmp.GetPixel($x, $y)

                # Get corresponding pixel from error screenshot
                # Need to offset by grid position
                $errorX = $gridInfo.x + $x
                $errorY = $gridInfo.y + $y

                if ($errorX -ge 0 -and $errorX -lt $errorBmp.Width -and $errorY -ge 0 -and $errorY -lt $errorBmp.Height) {
                    $errorColor = $errorBmp.GetPixel($errorX, $errorY)

                    $rDiff = [Math]::Abs($baselineColor.R - $errorColor.R)
                    $gDiff = [Math]::Abs($baselineColor.G - $errorColor.G)
                    $bDiff = [Math]::Abs($baselineColor.B - $errorColor.B)
                    $maxDiff = [Math]::Max($rDiff, [Math]::Max($gDiff, $bDiff))

                    if ($maxDiff -gt $COLOR_DIFF_THRESHOLD) {
                        $changedPixels++

                        $errorBrightness = ($errorColor.R + $errorColor.G + $errorColor.B) / 3
                        if ($errorBrightness -gt 150) {
                            $brightPixels++
                        }
                    }
                }
            }
        }

        $percentChanged = ($changedPixels / $totalSamples) * 100
        $brightRatio = if ($changedPixels -gt 0) { $brightPixels / $changedPixels } else { 0 }

        $wouldDetect = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)

        $color = if ($wouldDetect) { "Green" } else { "Red" }
        $status = if ($wouldDetect) { "DETECTED" } else { "NOT DETECTED" }

        Write-Host "$status - Changed: $([Math]::Round($percentChanged, 1))%, Bright: $([Math]::Round($brightRatio * 100, 1))%" -ForegroundColor $color

        $baselineBmp.Dispose()
        $baselineImg.Dispose()

    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
    }
}

$errorBmp.Dispose()
$errorImg.Dispose()

Write-Host ""
Write-Host "Analysis complete." -ForegroundColor Green
