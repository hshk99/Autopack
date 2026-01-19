# Analyze what detection threshold would work for actual errors
# This tool helps understand what pixel changes actually occur

Write-Host ""
Write-Host "========== ERROR DETECTION ANALYSIS ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "This tool will help identify the right detection threshold"
Write-Host "by analyzing pixel changes in your grid slots"
Write-Host ""

$BASELINE_DIR = "C:\dev\Autopack\error_baselines"
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
    $currentPath = "C:\dev\Autopack\temp_analysis_$Slot.png"

    # Take current screenshot
    if (-not (Take-ScreenshotOfArea -X $gridInfo.x -Y $gridInfo.y -Width $gridInfo.width -Height $gridInfo.height -OutputPath $currentPath)) {
        Write-Host "  [!] Failed to capture slot $Slot" -ForegroundColor Red
        return
    }

    try {
        Add-Type -AssemblyName System.Drawing

        $baselineImg = [System.Drawing.Image]::FromFile($baselinePath)
        $currentImg = [System.Drawing.Image]::FromFile($currentPath)

        $baselineBmp = New-Object System.Drawing.Bitmap($baselineImg)
        $currentBmp = New-Object System.Drawing.Bitmap($currentImg)

        # Analyze with different thresholds
        $thresholds = @(30, 50, 80, 100, 150)
        $results = @{}

        foreach ($threshold in $thresholds) {
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

                    if ($maxDiff -gt $threshold) {
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

            $results[$threshold] = @{
                percent = $percentChanged
                brightRatio = $brightRatio
            }
        }

        # Clean up
        $baselineBmp.Dispose()
        $currentBmp.Dispose()
        $baselineImg.Dispose()
        $currentImg.Dispose()
        Remove-Item $currentPath -ErrorAction SilentlyContinue

        return $results
    } catch {
        Write-Host "  [!] Error analyzing slot $Slot : $_" -ForegroundColor Red
        Remove-Item $currentPath -ErrorAction SilentlyContinue
        return $null
    }
}

Write-Host "INSTRUCTIONS:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. When you see a connection error in a slot, note the slot number"
Write-Host "2. This tool will analyze pixel changes at different thresholds"
Write-Host "3. Look at the results to find detection threshold that works"
Write-Host ""
Write-Host "Enter slot number to analyze (1-9), or 'all' to check all slots"
Write-Host "Or press Ctrl+C to exit"
Write-Host ""

while ($true) {
    Write-Host ""
    $input = Read-Host "Slot to analyze (1-9, 'all', or 'quit')"

    if ($input -eq "quit" -or $input -eq "q") {
        break
    }

    if ($input -eq "all") {
        Write-Host ""
        Write-Host "Analyzing all slots..." -ForegroundColor Yellow
        Write-Host ""

        foreach ($slot in 1..9) {
            Write-Host "Analyzing Slot $slot..." -ForegroundColor Cyan
            $results = Analyze-Slot -Slot $slot

            if ($null -ne $results) {
                Write-Host "  Results:" -ForegroundColor Green
                foreach ($threshold in (30, 50, 80, 100, 150)) {
                    $data = $results[$threshold]
                    $percent = [Math]::Round($data.percent, 1)
                    $bright = [Math]::Round($data.brightRatio * 100, 1)
                    Write-Host "    Threshold $threshold RGB: $percent% changed, $bright% bright"
                }
            }
            Write-Host ""
        }
    } else {
        try {
            $slot = [int]$input
            if ($slot -lt 1 -or $slot -gt 9) {
                Write-Host "  [!] Please enter 1-9" -ForegroundColor Red
                continue
            }

            Write-Host ""
            Write-Host "Analyzing Slot $slot..." -ForegroundColor Cyan
            $results = Analyze-Slot -Slot $slot

            if ($null -ne $results) {
                Write-Host "  Results:" -ForegroundColor Green
                Write-Host ""
                Write-Host "  RGB Threshold  |  % Changed  |  % Bright  |  Likely" -ForegroundColor Cyan
                Write-Host "  ───────────────┼─────────────┼────────────┼─────────────" -ForegroundColor Gray

                foreach ($threshold in (30, 50, 80, 100, 150)) {
                    $data = $results[$threshold]
                    $percent = [Math]::Round($data.percent, 1)
                    $bright = [Math]::Round($data.brightRatio * 100, 1)

                    $status = ""
                    if ($percent -lt 30) {
                        $status = "No error"
                    } elseif ($percent -lt 50) {
                        $status = "Small change"
                    } elseif ($percent -lt 75) {
                        $status = "Maybe error?"
                    } else {
                        if ($bright -gt 60) {
                            $status = "LIKELY ERROR"
                        } else {
                            $status = "Dark overlay"
                        }
                    }

                    Write-Host "  $threshold                |  $percent%       |  $bright%       |  $status"
                }

                Write-Host ""
                Write-Host "  Current Detection Threshold:" -ForegroundColor Yellow
                Write-Host "    • RGB difference: 80"
                Write-Host "    • % change: 75%"
                Write-Host "    • Bright ratio: 60%"
                Write-Host ""

                $data75 = $results[80]
                if ($data75.percent -gt 75 -and $data75.brightRatio -gt 0.6) {
                    Write-Host "  ✓ Error WOULD BE DETECTED with current thresholds" -ForegroundColor Green
                } else {
                    Write-Host "  ✗ Error would NOT be detected" -ForegroundColor Red
                    Write-Host ""
                    Write-Host "  Recommendation:" -ForegroundColor Yellow
                    if ($data75.percent -lt 75) {
                        Write-Host "    - Lower PERCENT_CHANGE_THRESHOLD to $([Math]::Round($data75.percent - 5, 0))%"
                    }
                    if ($data75.brightRatio -lt 0.6) {
                        Write-Host "    - Lower BRIGHT_PIXEL_RATIO to $([Math]::Round($data75.brightRatio - 0.1, 1))"
                    }
                }
            }

            Write-Host ""
        } catch {
            Write-Host "  [!] Invalid input. Please enter 1-9 or 'all'" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Analysis complete." -ForegroundColor Green
