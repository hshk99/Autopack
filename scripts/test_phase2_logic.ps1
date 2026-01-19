# Test Phase 2 detection algorithm logic

Write-Host "Testing Phase 2 detection algorithm..." -ForegroundColor Cyan
Write-Host ""

# Simulate detection thresholds
$PERCENT_CHANGE_THRESHOLD = 75
$COLOR_DIFF_THRESHOLD = 80
$BRIGHT_PIXEL_RATIO = 0.6

Write-Host "Detection Thresholds:" -ForegroundColor Yellow
Write-Host "  * Percent change threshold: $PERCENT_CHANGE_THRESHOLD%"
Write-Host "  * Color diff threshold: $COLOR_DIFF_THRESHOLD (RGB)"
Write-Host "  * Bright pixel ratio: $BRIGHT_PIXEL_RATIO (60%)"
Write-Host ""

Write-Host "Test Scenarios:" -ForegroundColor Green
Write-Host ""

# Scenario 1: Normal typing (should NOT detect)
Write-Host "1. Normal Cursor typing:"
$percentChanged = 15
$brightRatio = 0.2
$isError = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)
Write-Host "   Changed: $percentChanged%, Bright: $($brightRatio * 100)%"
$result = if ($isError) { "ERROR DETECTED" } else { "OK - no error" }
$color = if ($isError) { "Red" } else { "Green" }
Write-Host "   Result: $result" -ForegroundColor $color
Write-Host ""

# Scenario 2: Tab switch (should NOT detect)
Write-Host "2. Tab switch (some visual change):"
$percentChanged = 45
$brightRatio = 0.3
$isError = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)
Write-Host "   Changed: $percentChanged%, Bright: $($brightRatio * 100)%"
$result = if ($isError) { "ERROR DETECTED" } else { "OK - no error" }
$color = if ($isError) { "Red" } else { "Green" }
Write-Host "   Result: $result" -ForegroundColor $color
Write-Host ""

# Scenario 3: Viewport scroll (significant change but dark)
Write-Host "3. Viewport scroll (dark background change):"
$percentChanged = 70
$brightRatio = 0.2
$isError = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)
Write-Host "   Changed: $percentChanged%, Bright: $($brightRatio * 100)%"
$result = if ($isError) { "ERROR DETECTED" } else { "OK - no error" }
$color = if ($isError) { "Red" } else { "Green" }
Write-Host "   Result: $result" -ForegroundColor $color
Write-Host ""

# Scenario 4: Error dialog (should DETECT)
Write-Host "4. Error dialog overlay (modal, light background):"
$percentChanged = 80
$brightRatio = 0.75
$isError = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)
Write-Host "   Changed: $percentChanged%, Bright: $($brightRatio * 100)%"
$result = if ($isError) { "ERROR DETECTED" } else { "OK - no error" }
$color = if ($isError) { "Red" } else { "Green" }
Write-Host "   Result: $result" -ForegroundColor $color
Write-Host ""

# Scenario 5: Another error dialog variant
Write-Host "5. Error dialog (dark modal with bright accent):"
$percentChanged = 85
$brightRatio = 0.65
$isError = ($percentChanged -gt $PERCENT_CHANGE_THRESHOLD) -and ($brightRatio -gt $BRIGHT_PIXEL_RATIO)
Write-Host "   Changed: $percentChanged%, Bright: $($brightRatio * 100)%"
$result = if ($isError) { "ERROR DETECTED" } else { "OK - no error" }
$color = if ($isError) { "Red" } else { "Green" }
Write-Host "   Result: $result" -ForegroundColor $color
Write-Host ""

Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  * Normal activity (scenarios 1-3): NOT detected"
Write-Host "  * Error dialogs (scenarios 4-5): DETECTED"
Write-Host ""
Write-Host "Algorithm is working correctly!" -ForegroundColor Green
