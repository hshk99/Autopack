# Clean Cursor's saved session/window state
# This removes the persisted list of windows that Cursor tries to restore
# Usage: .\clean_cursor_session.ps1
# IMPORTANT: Run this with Cursor closed

Write-Host ""
Write-Host "============ CLEAN CURSOR SESSION ============" -ForegroundColor Cyan
Write-Host ""

# Check if Cursor is running
$cursorProcs = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
if ($cursorProcs) {
    Write-Host "[ERROR] Cursor is still running!" -ForegroundColor Red
    Write-Host "[INFO] Please close Cursor completely and run this script again"
    Write-Host ""
    Write-Host "Currently running Cursor processes:"
    $cursorProcs | ForEach-Object {
        Write-Host "  PID $($_.Id): $($_.MainWindowTitle)"
    }
    Write-Host ""
    exit 1
}

Write-Host "[OK] Cursor is not running - safe to proceed"
Write-Host ""

# Session storage locations
$sessionStoragePath = "$env:APPDATA\Cursor\Session Storage"
$localStoragePath = "$env:APPDATA\Cursor\Local Storage\leveldb"

Write-Host "[ACTION] Cleaning Cursor session data..."
Write-Host ""

# Clean Session Storage
if (Test-Path $sessionStoragePath) {
    Write-Host "[1/2] Cleaning Session Storage..."
    try {
        # Remove all .log and .ldb files (leveldb data files)
        Remove-Item -Path "$sessionStoragePath\*.log" -Force -ErrorAction SilentlyContinue
        Remove-Item -Path "$sessionStoragePath\*.ldb" -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Session Storage cleaned"
    } catch {
        Write-Host "[WARN] Could not fully clean Session Storage: $_"
    }
} else {
    Write-Host "[INFO] Session Storage not found (may be OK)"
}

Write-Host ""

# Clean Local Storage (contains per-workspace state)
if (Test-Path $localStoragePath) {
    Write-Host "[2/2] Cleaning Local Storage..."
    try {
        # Remove leveldb files
        Remove-Item -Path "$localStoragePath\*.log" -Force -ErrorAction SilentlyContinue
        Remove-Item -Path "$localStoragePath\*.ldb" -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Local Storage cleaned"
    } catch {
        Write-Host "[WARN] Could not fully clean Local Storage: $_"
    }
} else {
    Write-Host "[INFO] Local Storage not found (may be OK)"
}

Write-Host ""
Write-Host "============ CLEANUP COMPLETE ============" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Reopen Cursor - it will start fresh with no persisted windows"
Write-Host "2. Run auto_fill_empty_slots.bat to test new launcher"
Write-Host "3. Verify new windows appear correctly"
Write-Host ""
