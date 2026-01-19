# Capture only the grid area (all 9 slots in one image)
# Much more efficient than full screen or individual slots

$OUTPUT_DIR = "C:\dev\Autopack\error_analysis"
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

# Grid area coordinates
# Rightmost grid position: x: 3414, width: 1707 = 5121
# Bottommost grid position: y: 960, height: 480 = 1440

$GRID_START_X = 0
$GRID_START_Y = 0
$GRID_WIDTH = 5121
$GRID_HEIGHT = 1440

Write-Host ""
Write-Host "========== CAPTURE GRID AREA (ALL 9 SLOTS) ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Capturing 9-slot grid area ($($GRID_WIDTH)x$($GRID_HEIGHT))..."
Write-Host "Shows all 9 Cursor windows in one screenshot"
Write-Host ""

# Create output directory
if (-not (Test-Path $OUTPUT_DIR)) {
    New-Item -ItemType Directory -Path $OUTPUT_DIR -ErrorAction SilentlyContinue | Out-Null
}

# Function to capture grid area
function Capture-GridArea {
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
        Write-Host "  Error: $_" -ForegroundColor Red
        return $false
    }
}

Write-Host "Capturing grid at $(Get-Date -Format 'HH:mm:ss')..." -ForegroundColor Yellow
Write-Host ""

try {
    $outputPath = "$OUTPUT_DIR\error_grid_$TIMESTAMP.png"

    Write-Host -NoNewline "  Capturing grid area... "

    if (Capture-GridArea -X $GRID_START_X -Y $GRID_START_Y -Width $GRID_WIDTH -Height $GRID_HEIGHT -OutputPath $outputPath) {
        $fileSize = (Get-Item $outputPath).Length / 1MB
        Write-Host "[OK]" -ForegroundColor Green
        Write-Host ""
        Write-Host "========== CAPTURE COMPLETE ==========" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Screenshot saved successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "File: error_grid_$TIMESTAMP.png" -ForegroundColor Yellow
        Write-Host "Size: $([Math]::Round($fileSize, 2)) MB" -ForegroundColor Yellow
        Write-Host "Dimensions: $($GRID_WIDTH)x$($GRID_HEIGHT) pixels" -ForegroundColor Yellow
        Write-Host "Location: $outputPath" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "This screenshot shows:" -ForegroundColor Green
        Write-Host "  * All 9 grid slots (3x3 layout)"
        Write-Host "  * Which slot(s) have error dialog"
        Write-Host "  * Error appearance and position"
        Write-Host ""
        Write-Host "NEXT STEPS:" -ForegroundColor Green
        Write-Host "  1. Review the screenshot"
        Write-Host "  2. Identify slot with error (1-9)"
        Write-Host "  3. Open Phase 1 handler:"
        Write-Host "     C:\dev\Autopack\scripts\handle_connection_errors.bat"
        Write-Host "  4. Type the slot number to recover"
        Write-Host ""
        Write-Host "For Phase 2 improvement:"
        Write-Host "  -> Share this screenshot for error analysis"
        Write-Host "  -> Helps improve automated detection"
        Write-Host ""
    } else {
        Write-Host "[FAILED]" -ForegroundColor Red
        Write-Host ""
        Write-Host "Could not capture grid area" -ForegroundColor Red
    }
} catch {
    Write-Host "[ERROR]" -ForegroundColor Red
    Write-Host "Exception: $_" -ForegroundColor Red
}

Write-Host "========================================" -ForegroundColor Gray
Write-Host ""
