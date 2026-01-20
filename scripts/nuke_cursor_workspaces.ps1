# AGGRESSIVE: Delete all but main workspace from Cursor
# This removes all the extra workspace entries that Cursor tries to restore
# Usage: .\nuke_cursor_workspaces.ps1

Write-Host ""
Write-Host "============ NUKE CURSOR WORKSPACES ============" -ForegroundColor Red
Write-Host ""
Write-Host "WARNING: This will DELETE all but ONE workspace from Cursor!" -ForegroundColor Yellow
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

# Find the main workspace (largest state.vscdb file = most active workspace)
$wsStoragePath = "$env:APPDATA\Cursor\User\workspaceStorage"

if (-not (Test-Path $wsStoragePath)) {
    Write-Host "[ERROR] workspaceStorage not found"
    exit 1
}

Write-Host "[ACTION] Analyzing workspaces..."
$workspaces = Get-ChildItem -Path $wsStoragePath -Directory

Write-Host "Found $($workspaces.Count) workspace(s)"
Write-Host ""

# Find workspace with largest state.vscdb (usually the main one being used)
$mainWs = $null
$maxSize = 0

foreach ($ws in $workspaces) {
    $stateDb = Join-Path $ws.FullName "state.vscdb"
    if (Test-Path $stateDb) {
        $size = (Get-Item $stateDb).Length
        if ($size -gt $maxSize) {
            $maxSize = $size
            $mainWs = $ws
        }
    }
}

if ($null -eq $mainWs) {
    Write-Host "[ERROR] Could not find main workspace"
    exit 1
}

$mainWsName = $mainWs.Name
$mainWsJson = Join-Path $mainWs.FullName "workspace.json"
if (Test-Path $mainWsJson) {
    $mainWsInfo = Get-Content $mainWsJson | ConvertFrom-Json
    Write-Host "Main workspace identified:" -ForegroundColor Green
    Write-Host "  ID: $mainWsName"
    Write-Host "  Folder: $($mainWsInfo.folder)"
    Write-Host "  Size: $maxSize bytes"
} else {
    Write-Host "Main workspace identified:" -ForegroundColor Green
    Write-Host "  ID: $mainWsName"
    Write-Host "  Size: $maxSize bytes"
}

Write-Host ""
Write-Host "Workspaces to DELETE: $($workspaces.Count - 1)"
Write-Host ""

# Confirm before deletion
Write-Host "[CONFIRM] Type 'DELETE ALL' to confirm and delete all other workspaces:" -ForegroundColor Yellow
$confirm = Read-Host "Enter confirmation"

if ($confirm -ne "DELETE ALL") {
    Write-Host "[CANCELLED] Deletion cancelled"
    exit 0
}

Write-Host ""
Write-Host "[ACTION] Deleting workspaces..."

$deleted = 0
$failed = 0

foreach ($ws in $workspaces) {
    if ($ws.Name -eq $mainWsName) {
        Write-Host "[KEEP] $($ws.Name)"
        continue
    }

    try {
        Remove-Item -Path $ws.FullPath -Recurse -Force -ErrorAction Stop
        Write-Host "[OK] Deleted $($ws.Name)"
        $deleted++
    } catch {
        Write-Host "[FAIL] Could not delete $($ws.Name): $_" -ForegroundColor Yellow
        $failed++
    }
}

Write-Host ""
Write-Host "============ DELETION COMPLETE ============" -ForegroundColor Green
Write-Host "Deleted: $deleted"
Write-Host "Failed: $failed"
Write-Host "Remaining: 1 (main workspace)"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Reopen Cursor - it will open with ONLY the main workspace"
Write-Host "2. No invisible windows should appear"
Write-Host "3. Test auto_fill_empty_slots.bat"
Write-Host ""
