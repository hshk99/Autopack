# Capture screenshots of Cursor error dialogs for analysis
# This helps us understand what the error dialog looks like so we can detect it properly

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

Write-Host ""
Write-Host "========== SCREENSHOT CAPTURE TOOL ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Capture screenshots of Cursor error dialogs"
Write-Host "Usage: capture grid-slot"
Write-Host "Example: capture 3  (captures screenshot of grid slot 3)"
Write-Host ""
Write-Host "=============================================" -ForegroundColor Gray
Write-Host ""

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

function Capture-GridSlot {
    param([int]$Slot)

    if ($slot -lt 1 -or $slot -gt 9) {
        Write-Host "Invalid slot: $slot. Must be 1-9" -ForegroundColor Red
        return $false
    }

    $gridInfo = $GRID_POSITIONS[$Slot]
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outputPath = "C:\dev\Autopack\error_screenshot_slot_${slot}_${timestamp}.png"

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Capturing screenshot of grid slot $slot..."
    Write-Host "  Position: ($($gridInfo.x), $($gridInfo.y))"
    Write-Host "  Size: $($gridInfo.width) x $($gridInfo.height)"

    if (Take-ScreenshotOfArea -X $gridInfo.x -Y $gridInfo.y -Width $gridInfo.width -Height $gridInfo.height -OutputPath $outputPath) {
        Write-Host "  [+] Screenshot saved: $outputPath" -ForegroundColor Green
        return $true
    } else {
        Write-Host "  [!] Failed to capture screenshot" -ForegroundColor Red
        return $false
    }
}

# If argument provided, capture that slot
if ($args.Count -gt 0) {
    $slot = [int]$args[0]
    Capture-GridSlot -Slot $slot
    exit 0
}

# Interactive mode
Write-Host "Interactive mode - Enter grid slot (1-9) to capture:"
Write-Host ""

while ($true) {
    Write-Host -NoNewline "Slot [1-9] to capture or (q)uit? > " -ForegroundColor Yellow
    $input = Read-Host

    if ($input -eq "q") {
        break
    }

    if ([int]::TryParse($input, [ref]$slot)) {
        Capture-GridSlot -Slot $slot
        Write-Host ""
    } else {
        Write-Host "Invalid input" -ForegroundColor Red
        Write-Host ""
    }
}

Write-Host ""
Write-Host "Tool stopped" -ForegroundColor Gray
