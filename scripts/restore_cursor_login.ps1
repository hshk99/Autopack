# Restore Cursor Login Data
# This restores authentication data from the backup created before nuclear reset

$cursorPath = "$env:APPDATA\Cursor"
$backupPath = "$env:APPDATA\Cursor.bak_20251101160446"

Write-Host "=== Cursor Login Restore Script ===" -ForegroundColor Cyan
Write-Host ""

# Check if Cursor is running
$cursorProcs = Get-Process cursor -ErrorAction SilentlyContinue
if ($cursorProcs) {
    Write-Host "[ERROR] Cursor is running! Please close ALL Cursor windows first." -ForegroundColor Red
    Write-Host ""
    Write-Host "Run this command to close Cursor:" -ForegroundColor Yellow
    Write-Host "  Get-Process cursor | Stop-Process -Force" -ForegroundColor White
    Write-Host ""
    Write-Host "Then run this script again." -ForegroundColor Yellow
    exit 1
}

# Check if backup exists
if (-not (Test-Path $backupPath)) {
    Write-Host "[ERROR] Backup not found at: $backupPath" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Cursor is not running" -ForegroundColor Green
Write-Host "[OK] Backup found at: $backupPath" -ForegroundColor Green
Write-Host ""

# Restore Network folder (contains Cookies database with auth tokens)
Write-Host "Restoring Network folder (auth cookies)..." -ForegroundColor Yellow
$networkSrc = "$backupPath\Network"
$networkDst = "$cursorPath\Network"
if (Test-Path $networkSrc) {
    if (Test-Path $networkDst) {
        Remove-Item $networkDst -Recurse -Force
    }
    Copy-Item $networkSrc $networkDst -Recurse -Force
    Write-Host "  [OK] Restored Network folder" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] Network folder not in backup" -ForegroundColor Yellow
}

# Restore Local Storage (contains session tokens)
Write-Host "Restoring Local Storage (session tokens)..." -ForegroundColor Yellow
$lsSrc = "$backupPath\Local Storage"
$lsDst = "$cursorPath\Local Storage"
if (Test-Path $lsSrc) {
    if (Test-Path $lsDst) {
        Remove-Item $lsDst -Recurse -Force
    }
    Copy-Item $lsSrc $lsDst -Recurse -Force
    Write-Host "  [OK] Restored Local Storage" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] Local Storage not in backup" -ForegroundColor Yellow
}

# Restore Local State (contains encryption keys for credentials)
Write-Host "Restoring Local State (encryption keys)..." -ForegroundColor Yellow
$stateSrc = "$backupPath\Local State"
$stateDst = "$cursorPath\Local State"
if (Test-Path $stateSrc) {
    Copy-Item $stateSrc $stateDst -Force
    Write-Host "  [OK] Restored Local State" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] Local State not in backup" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Restore Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Now open Cursor - you should be logged in automatically!" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTE: If you still need to log in once, that's normal." -ForegroundColor Yellow
Write-Host "After that first login, it should persist across new windows." -ForegroundColor Yellow
