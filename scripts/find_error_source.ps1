# Find source of "This program does not support the version of Windows" error

Write-Host "=== Checking for incompatible programs ===" -ForegroundColor Cyan

# Check Windows version
Write-Host "`nWindows Version:" -ForegroundColor Yellow
Get-WmiObject Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber

# Check Cursor installation
Write-Host "`nCursor Installation:" -ForegroundColor Yellow
$cursorPath = Get-Command cursor -ErrorAction SilentlyContinue
if ($cursorPath) {
    $cursorExe = (Get-Item $cursorPath.Source).VersionInfo
    Write-Host "  Path: $($cursorPath.Source)"
    Write-Host "  File Version: $($cursorExe.FileVersion)"
    Write-Host "  Product Version: $($cursorExe.ProductVersion)"
}

# Check for 32-bit processes that might have compatibility issues
Write-Host "`n32-bit Cursor-related processes:" -ForegroundColor Yellow
Get-Process cursor -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $is32bit = [IntPtr]::Size -eq 4
        $modules = $_.Modules | Select-Object -First 1
        Write-Host "  PID $($_.Id): $($_.MainModule.FileName)"
    } catch {}
}

# Check recent Application events
Write-Host "`nRecent Application Errors:" -ForegroundColor Yellow
try {
    Get-WinEvent -FilterHashtable @{LogName='Application'; Level=2} -MaxEvents 20 -ErrorAction SilentlyContinue |
        Select-Object TimeCreated, ProviderName, @{N='Message';E={$_.Message.Substring(0, [Math]::Min(100, $_.Message.Length))}} |
        Format-Table -AutoSize
} catch {
    Write-Host "  Could not read event log"
}

# Check if there's an old helper tool
Write-Host "`nChecking for old/incompatible binaries in Cursor:" -ForegroundColor Yellow
$cursorDir = "C:\Users\hshk9\AppData\Local\Programs\Cursor"
if (Test-Path $cursorDir) {
    Get-ChildItem $cursorDir -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        $ver = $_.VersionInfo
        if ($ver.FileVersion) {
            # Check if it might be old
            Write-Host "  $($_.Name): v$($ver.FileVersion)"
        }
    }
}

Write-Host "`n=== Common causes of this error ===" -ForegroundColor Cyan
Write-Host "1. An extension has an incompatible native binary"
Write-Host "2. A helper tool (ripgrep, git, etc.) is outdated"
Write-Host "3. Windows Insider build (26200) has compatibility issues with some tools"
Write-Host "4. An old Cursor updater process is running"
