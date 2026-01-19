# Capture all 9 grid slots simultaneously for Phase 2 error analysis
# Creates screenshots of all slots at the same moment to analyze error patterns

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

$OUTPUT_DIR = "C:\dev\Autopack\error_analysis"
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host ""
Write-Host "========== CAPTURE ALL 9 GRID SLOTS ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Capturing all 9 Cursor windows simultaneously..."
Write-Host "This creates a complete snapshot for Phase 2 analysis"
Write-Host ""

# Create output directory
if (-not (Test-Path $OUTPUT_DIR)) {
    New-Item -ItemType Directory -Path $OUTPUT_DIR -ErrorAction SilentlyContinue | Out-Null
}

# Function to capture screenshot
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

Write-Host "Capturing all slots at $(Get-Date -Format 'HH:mm:ss')..." -ForegroundColor Yellow
Write-Host ""

$successCount = 0
$failCount = 0

# Capture all 9 slots in rapid succession
foreach ($slot in 1..9) {
    try {
        $gridInfo = $GRID_POSITIONS[$slot]
        $outputPath = "$OUTPUT_DIR\error_snapshot_slot_$slot`_$TIMESTAMP.png"

        Write-Host -NoNewline "  Slot $slot... "

        if (Take-ScreenshotOfArea -X $gridInfo.x -Y $gridInfo.y -Width $gridInfo.width -Height $gridInfo.height -OutputPath $outputPath) {
            Write-Host "[OK]" -ForegroundColor Green
            $successCount++
        } else {
            Write-Host "[FAILED]" -ForegroundColor Red
            $failCount++
        }
    } catch {
        Write-Host "[ERROR]" -ForegroundColor Red
        $failCount++
    }
}

Write-Host ""
Write-Host "========== CAPTURE COMPLETE ==========" -ForegroundColor Gray
Write-Host ""
Write-Host "Captured: $successCount / 9 slots" -ForegroundColor Green
Write-Host ""

if ($failCount -eq 0) {
    Write-Host "All 9 screenshots saved successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Output location:" -ForegroundColor Yellow
    Write-Host "  $OUTPUT_DIR" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Timestamp: $TIMESTAMP" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Files created:" -ForegroundColor Yellow
    Get-ChildItem "$OUTPUT_DIR\*_$TIMESTAMP.png" | ForEach-Object {
        Write-Host "  ✓ $($_.Name)"
    }
    Write-Host ""
    Write-Host "NEXT STEP FOR PHASE 2 IMPROVEMENT:" -ForegroundColor Green
    Write-Host "  1. Close this window"
    Write-Host "  2. Open the error_analysis folder"
    Write-Host "  3. Review the 9 screenshots"
    Write-Host "  4. Share them with me for Phase 2 visual analysis"
    Write-Host ""
    Write-Host "These screenshots will help us:" -ForegroundColor Green
    Write-Host "  ✓ See what error dialogs actually look like"
    Write-Host "  ✓ Analyze error patterns across all windows"
    Write-Host "  ✓ Determine accurate detection thresholds"
    Write-Host "  ✓ Build Phase 2 detection based on REAL data"
    Write-Host ""
} else {
    Write-Host "Warning: $failCount slots failed to capture" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Partial output location:" -ForegroundColor Yellow
    Write-Host "  $OUTPUT_DIR" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Please verify Cursor windows are visible and try again"
    Write-Host ""
}

Write-Host "========================================" -ForegroundColor Gray
Write-Host ""

# Keep window open for review
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
