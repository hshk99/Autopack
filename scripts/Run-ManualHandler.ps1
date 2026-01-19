# Connection Error Handler - Manual Mode
# Double-click this file to run the handler

# Check if running
$scriptPath = "C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1"

if (Test-Path $scriptPath) {
    Write-Host "Launching Connection Error Handler..."
    & $scriptPath
} else {
    Write-Host "ERROR: Script not found at $scriptPath"
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
