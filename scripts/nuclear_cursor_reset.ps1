# NUCLEAR CURSOR RESET
# Deletes ALL Cursor state/cache data while preserving settings and LOGIN
# This is a last resort to fix the orphaned window problem

Write-Host "========== NUCLEAR CURSOR RESET ==========" -ForegroundColor Red
Write-Host "This will delete Cursor state data (preserves settings AND login)" -ForegroundColor Yellow

# Check if Cursor is running
$cursorProcesses = Get-Process cursor -ErrorAction SilentlyContinue
if ($cursorProcesses) {
    Write-Host "[ERROR] Cursor is still running!" -ForegroundColor Red
    Write-Host "Please close ALL Cursor windows first (use Task Manager)"
    exit 1
}

Write-Host "[OK] Cursor is not running" -ForegroundColor Green
Write-Host ""

$cursorRoot = "$env:APPDATA\Cursor"
$cursorHome = "$env:USERPROFILE\.cursor"

# Folders to DELETE (state/cache data - NOT login data)
# PRESERVED for login: Network, Local Storage, Partitions
$foldersToDelete = @(
    "$cursorRoot\Backups",
    "$cursorRoot\blob_storage",
    "$cursorRoot\Cache",
    "$cursorRoot\CachedConfigurations",
    "$cursorRoot\CachedData",
    "$cursorRoot\CachedExtensionVSIXs",
    "$cursorRoot\CachedProfilesData",
    "$cursorRoot\Code Cache",
    "$cursorRoot\Crashpad",
    "$cursorRoot\DawnGraphiteCache",
    "$cursorRoot\DawnWebGPUCache",
    "$cursorRoot\GPUCache",
    # "$cursorRoot\Local Storage",    # PRESERVED - contains login tokens
    "$cursorRoot\logs",
    # "$cursorRoot\Network",          # PRESERVED - contains auth cookies
    # "$cursorRoot\Partitions",       # PRESERVED - contains session tokens
    "$cursorRoot\sentry",
    "$cursorRoot\Service Worker",
    "$cursorRoot\Session Storage",
    "$cursorRoot\Shared Dictionary",
    "$cursorRoot\WebStorage",
    "$cursorRoot\User\globalStorage",
    "$cursorRoot\User\History",
    "$cursorRoot\User\workspaceStorage",
    "$cursorHome\projects",
    "$cursorHome\ai-tracking",
    "$cursorHome\browser-logs"
)

# Files to DELETE (NOT login-related files)
# PRESERVED for login: Local State (contains encryption keys)
$filesToDelete = @(
    "$cursorRoot\DIPS",
    "$cursorRoot\DIPS-wal",
    # "$cursorRoot\Local State",      # PRESERVED - contains credential encryption keys
    "$cursorRoot\Preferences",
    "$cursorRoot\SharedStorage",
    "$cursorRoot\SharedStorage-wal",
    "$cursorHome\ide_state.json"
)

# KEEP these files (user settings AND login data)
Write-Host "[INFO] Will PRESERVE:" -ForegroundColor Cyan
Write-Host "  - $cursorRoot\User\settings.json (your settings)"
Write-Host "  - $cursorRoot\User\keybindings.json (your keybindings)"
Write-Host "  - $cursorHome\extensions (your extensions)"
Write-Host "  - $cursorRoot\Network (login cookies)"
Write-Host "  - $cursorRoot\Local Storage (login tokens)"
Write-Host "  - $cursorRoot\Local State (encryption keys)"
Write-Host ""

Write-Host "[CONFIRM] Type 'NUCLEAR RESET' to proceed:" -ForegroundColor Yellow
$confirm = Read-Host "Enter confirmation"

if ($confirm -ne "NUCLEAR RESET") {
    Write-Host "[CANCELLED] Reset cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "[ACTION] Deleting folders..." -ForegroundColor Yellow

$deletedFolders = 0
$failedFolders = 0

foreach ($folder in $foldersToDelete) {
    if (Test-Path $folder) {
        try {
            Remove-Item -Path $folder -Recurse -Force -ErrorAction Stop
            Write-Host "  [OK] Deleted: $folder" -ForegroundColor Green
            $deletedFolders++
        } catch {
            Write-Host "  [ERROR] Failed: $folder - $_" -ForegroundColor Red
            $failedFolders++
        }
    }
}

Write-Host ""
Write-Host "[ACTION] Deleting files..." -ForegroundColor Yellow

$deletedFiles = 0
$failedFiles = 0

foreach ($file in $filesToDelete) {
    if (Test-Path $file) {
        try {
            Remove-Item -Path $file -Force -ErrorAction Stop
            Write-Host "  [OK] Deleted: $file" -ForegroundColor Green
            $deletedFiles++
        } catch {
            Write-Host "  [ERROR] Failed: $file - $_" -ForegroundColor Red
            $failedFiles++
        }
    }
}

Write-Host ""
Write-Host "========== NUCLEAR RESET COMPLETE ==========" -ForegroundColor Cyan
Write-Host "Deleted: $deletedFolders folders, $deletedFiles files"
Write-Host "Failed: $failedFolders folders, $failedFiles files"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Open Cursor - it will recreate all state from scratch"
Write-Host "2. You may need to sign in again"
Write-Host "3. Extensions should auto-reinstall"
Write-Host "4. Your settings.json and keybindings.json are preserved"
