# Kill all Cursor processes and PowerShell instances spawned by auto_fill_empty_slots
# Usage: .\kill_all_cursor.ps1

Write-Host ""
Write-Host "============ KILL ALL CURSOR PROCESSES ============" -ForegroundColor Red
Write-Host ""

# Kill all Cursor processes
Write-Host "[ACTION] Killing all Cursor processes..."
try {
    Get-Process -Name "cursor" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] All Cursor processes killed" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Error killing Cursor: $_" -ForegroundColor Yellow
}

Start-Sleep -Milliseconds 500

# Kill all PowerShell processes except this one
Write-Host "[ACTION] Killing all related PowerShell instances..."
try {
    $currentPID = $PID
    Get-Process -Name "powershell" -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $currentPID } | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] PowerShell processes cleaned up" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Error killing PowerShell: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[DONE] All processes terminated" -ForegroundColor Green
Write-Host ""
