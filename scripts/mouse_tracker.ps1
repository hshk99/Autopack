# Mouse Position Tracker
# Shows current mouse position - useful for finding click coordinates
# Press Ctrl+C to stop

Add-Type -AssemblyName System.Windows.Forms

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "     MOUSE POSITION TRACKER            " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Move your mouse to see coordinates." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

$lastX = -1
$lastY = -1

while($true) {
    $pos = [System.Windows.Forms.Cursor]::Position

    # Only print if position changed (reduces spam)
    if ($pos.X -ne $lastX -or $pos.Y -ne $lastY) {
        $timestamp = Get-Date -Format "HH:mm:ss"
        Write-Host "[$timestamp]  X: $($pos.X.ToString().PadLeft(5))   Y: $($pos.Y.ToString().PadLeft(5))" -ForegroundColor Green
        $lastX = $pos.X
        $lastY = $pos.Y
    }

    Start-Sleep -Milliseconds 100
}
