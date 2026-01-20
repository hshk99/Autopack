# AGGRESSIVE cleanup - kill ALL Cursor processes except one main window
# This is necessary when background processes accumulate
# Usage: .\aggressive_cleanup_cursors.ps1

Write-Host ""
Write-Host "============ AGGRESSIVE CURSOR CLEANUP ============" -ForegroundColor Red
Write-Host ""

$allCursorProcs = Get-Process -Name "cursor" -ErrorAction SilentlyContinue | Sort-Object -Property StartTime

if ($allCursorProcs.Count -eq 0) {
    Write-Host "[INFO] No Cursor processes found"
    exit 0
}

Write-Host "[WARNING] Found $($allCursorProcs.Count) Cursor processes"
Write-Host ""
Write-Host "Keeping: The oldest process (likely your main window)"
Write-Host "Killing: All other background/orphaned processes"
Write-Host ""

# Keep only the oldest
$mainProc = $allCursorProcs[0]
$killProcs = @($allCursorProcs | Select-Object -Skip 1)

Write-Host "Main process to keep:"
Write-Host "  PID: $($mainProc.Id)"
Write-Host "  Title: $(if ($mainProc.MainWindowTitle) { $mainProc.MainWindowTitle } else { '[NO TITLE]' })"
Write-Host "  Age: $((Get-Date) - $mainProc.StartTime | ForEach-Object {'{0}h {1}m {2}s' -f $_.Hours,$_.Minutes,$_.Seconds})"
Write-Host ""

if ($killProcs.Count -eq 0) {
    Write-Host "[INFO] Only 1 process found - nothing to clean"
    exit 0
}

Write-Host "Processes to kill:"
foreach ($p in $killProcs) {
    Write-Host "  PID: $($p.Id) | Title: $(if ($p.MainWindowTitle) { $p.MainWindowTitle } else { '[BACKGROUND]' })"
}
Write-Host ""

Write-Host "[ACTION] Killing $($killProcs.Count) background process(es)..."
$killed = 0
foreach ($p in $killProcs) {
    try {
        Stop-Process -Id $p.Id -Force -ErrorAction Stop
        $killed++
        Write-Host "  [OK] Killed PID $($p.Id)"
    } catch {
        Write-Host "  [WARN] Failed to kill PID $($p.Id): $_"
    }
}

Write-Host ""
Write-Host "============ CLEANUP COMPLETE ============" -ForegroundColor Green
Write-Host "Killed: $killed processes"
Write-Host "Main window should still be running"
Write-Host ""
