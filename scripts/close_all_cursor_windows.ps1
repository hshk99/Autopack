# Close all Cursor windows to start fresh test

Write-Host "============ CLOSING ALL CURSOR WINDOWS ============" -ForegroundColor Cyan
Write-Host ""

$cursorProcesses = Get-Process cursor -ErrorAction SilentlyContinue

if ($null -eq $cursorProcesses) {
    Write-Host "[INFO] No Cursor windows open"
    exit 0
}

if ($cursorProcesses -is [array]) {
    $count = $cursorProcesses.Count
} else {
    $count = 1
}

Write-Host "[ACTION] Closing $count Cursor window(s)..."

$cursorProcesses | ForEach-Object {
    $processName = $_.Name
    $processId = $_.Id
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Write-Host "  Closed: $processName (PID: $processId)"
}

Start-Sleep -Milliseconds 500

Write-Host ""
Write-Host "[OK] All Cursor windows closed"
Write-Host ""
