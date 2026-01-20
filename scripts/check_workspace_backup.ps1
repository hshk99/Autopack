# Check if workspaceStorage is being backed up or synced
Write-Host ""
Write-Host "============ CHECKING FOR WORKSPACE BACKUPS ============" -ForegroundColor Cyan
Write-Host ""

# Check OneDrive
Write-Host "1. Checking OneDrive..." -ForegroundColor Yellow
$oneDrive = "$env:USERPROFILE\OneDrive"
if (Test-Path $oneDrive) {
    $found = Get-ChildItem -Path $oneDrive -Recurse -Filter 'workspaceStorage' -ErrorAction SilentlyContinue
    if ($found) {
        Write-Host "[FOUND] workspaceStorage in OneDrive!" -ForegroundColor Red
        $found | ForEach-Object {
            Write-Host "  Path: $($_.FullName)"
            $itemCount = (Get-ChildItem $_.FullName | Measure-Object).Count
            Write-Host "  Items: $itemCount"
        }
    } else {
        Write-Host "[OK] Not synced to OneDrive"
    }
} else {
    Write-Host "[SKIP] OneDrive not found"
}

Write-Host ""
Write-Host "2. Checking Cursor Backups folder..." -ForegroundColor Yellow
$backupPath = "$env:APPDATA\Cursor\Backups"
if (Test-Path $backupPath) {
    $items = Get-ChildItem -Path $backupPath -Recurse
    $itemCount = ($items | Measure-Object).Count
    Write-Host "[FOUND] Cursor Backups: $itemCount items" -ForegroundColor Yellow
    Get-ChildItem -Path $backupPath -Directory | ForEach-Object {
        Write-Host "  - $($_.Name)"
    }
} else {
    Write-Host "[OK] No Backups folder found"
}

Write-Host ""
Write-Host "3. Checking workspaceStorage timestamps..." -ForegroundColor Yellow
$wsPath = "$env:APPDATA\Cursor\User\workspaceStorage"
$wsFolder = Get-Item $wsPath
Write-Host "workspaceStorage modified: $($wsFolder.LastWriteTime)"
Write-Host "Current time: $(Get-Date)"

$timeDiff = (Get-Date) - $wsFolder.LastWriteTime
if ($timeDiff.TotalSeconds -lt 60) {
    Write-Host "[WARNING] Folder was modified VERY recently (within 1 minute)" -ForegroundColor Red
    Write-Host "[HINT] This suggests something is recreating the workspaces!"
}

Write-Host ""
Write-Host "4. Checking workspaceStorage contents..." -ForegroundColor Yellow
$wsCount = (Get-ChildItem -Path $wsPath -Directory | Measure-Object).Count
Write-Host "Current workspaces: $wsCount"
if ($wsCount -gt 1) {
    Write-Host "[WARNING] More than 1 workspace found!" -ForegroundColor Red
    Write-Host "[HINT] Workspaces may have been recreated"
}

Write-Host ""
