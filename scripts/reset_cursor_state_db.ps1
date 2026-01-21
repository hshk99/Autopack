# Reset Cursor's state database to clear cached workspace references
# This removes cached data about previously opened workspaces
# Usage: .\reset_cursor_state_db.ps1

Write-Host ""
Write-Host "============ RESET CURSOR STATE DATABASE ============" -ForegroundColor Cyan
Write-Host ""

# Check if Cursor is running
$cursorProcs = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
if ($cursorProcs) {
    Write-Host "[ERROR] Cursor is still running!" -ForegroundColor Red
    Write-Host "[INFO] Please close ALL Cursor windows and try again"
    Write-Host ""
    exit 1
}

Write-Host "[OK] Cursor is not running - safe to proceed"
Write-Host ""

# State database path
$globalStoragePath = "$env:APPDATA\Cursor\User\globalStorage"
$stateDb = Join-Path $globalStoragePath "state.vscdb"
$stateBackup = "$stateDb.backup"
$stateWal = "$stateDb-wal"
$stateShmFile = "$stateDb-shm"

Write-Host "[INFO] State database location:"
Write-Host "  $stateDb"
Write-Host ""

if (Test-Path $stateDb) {
    $sizeGb = (Get-Item $stateDb).Length / 1GB
    Write-Host "[INFO] Current size: $($sizeGb.ToString('F2')) GB"
    Write-Host ""
    Write-Host "[ACTION] Deleting state database..."
    Write-Host "[INFO] This will clear cached workspace history and restoration data"
    Write-Host ""
} else {
    Write-Host "[INFO] State database not found"
    exit 0
}

# Confirm before deletion
Write-Host "[CONFIRM] Type 'RESET DATABASE' to confirm deletion:" -ForegroundColor Yellow
$confirm = Read-Host "Enter confirmation"

if ($confirm -ne "RESET DATABASE") {
    Write-Host "[CANCELLED] Deletion cancelled"
    exit 0
}

Write-Host ""
Write-Host "[ACTION] Deleting files..."

$deletedCount = 0
$failCount = 0

# Delete main database
try {
    Remove-Item -Path $stateDb -Force -ErrorAction Stop
    Write-Host "[OK] Deleted state.vscdb"
    $deletedCount++
} catch {
    Write-Host "[FAIL] Could not delete state.vscdb: $_" -ForegroundColor Yellow
    $failCount++
}

# Delete backup
if (Test-Path $stateBackup) {
    try {
        Remove-Item -Path $stateBackup -Force -ErrorAction Stop
        Write-Host "[OK] Deleted state.vscdb.backup"
        $deletedCount++
    } catch {
        Write-Host "[FAIL] Could not delete backup: $_" -ForegroundColor Yellow
        $failCount++
    }
}

# Delete WAL file (write-ahead log)
if (Test-Path $stateWal) {
    try {
        Remove-Item -Path $stateWal -Force -ErrorAction Stop
        Write-Host "[OK] Deleted state.vscdb-wal"
        $deletedCount++
    } catch {
        Write-Host "[FAIL] Could not delete WAL: $_" -ForegroundColor Yellow
        $failCount++
    }
}

# Delete SHM file (shared memory)
if (Test-Path $stateShmFile) {
    try {
        Remove-Item -Path $stateShmFile -Force -ErrorAction Stop
        Write-Host "[OK] Deleted state.vscdb-shm"
        $deletedCount++
    } catch {
        Write-Host "[FAIL] Could not delete SHM: $_" -ForegroundColor Yellow
        $failCount++
    }
}

Write-Host ""
Write-Host "============ DELETION COMPLETE ============" -ForegroundColor Green
Write-Host "Deleted: $deletedCount files"
Write-Host "Failed: $failCount"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Reopen Cursor - it will create a NEW state database"
Write-Host "2. Only your main workspace will be restored (no cached 14 workspaces)"
Write-Host "3. No invisible windows should appear"
Write-Host ""
