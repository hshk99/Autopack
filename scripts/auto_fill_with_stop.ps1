# Multi-action toggle for Button 2
# First press: Start auto-filling empty slots
# Second press: Stop the currently running auto-fill process
# Saves state to: C:\dev\Autopack\scripts\BUTTON2_STATE.txt

param(
    [int]$WaveNumber = 0,
    [string]$WaveFile = "",
    [switch]$Force  # Force start even if already running
)

$stateFile = "C:\dev\Autopack\scripts\BUTTON2_STATE.txt"

Write-Host ""
Write-Host "============ BUTTON 2 - AUTO-FILL TOGGLE ============" -ForegroundColor Cyan
Write-Host ""

# Check if Button 2 is currently running
if (Test-Path $stateFile) {
    $state = Get-Content $stateFile -Raw

    if (-not [string]::IsNullOrWhiteSpace($state)) {
        Write-Host "[RUNNING] Auto-fill is currently active" -ForegroundColor Yellow
        Write-Host "[ACTION] Stopping auto-fill process..." -ForegroundColor Yellow
        Write-Host ""

        # Kill any running auto_fill_empty_slots processes
        $runningProcesses = Get-Process | Where-Object { $_.CommandLine -like "*auto_fill_empty_slots*" }

        if ($runningProcesses) {
            foreach ($proc in $runningProcesses) {
                try {
                    Stop-Process -Id $proc.Id -Force
                    Write-Host "✅ Stopped process ID: $($proc.Id)" -ForegroundColor Green
                } catch {
                    Write-Host "⚠️  Could not stop process ID: $($proc.Id)" -ForegroundColor Yellow
                }
            }
        }

        # Kill any running cursor launch processes spawned by auto_fill
        $cursorProcesses = Get-Process "cursor" -ErrorAction SilentlyContinue
        if ($cursorProcesses) {
            Write-Host ""
            Write-Host "[INFO] $($cursorProcesses.Count) Cursor windows still running (left for manual review)" -ForegroundColor Cyan
            Write-Host "[INFO] To close all cursors, run: Get-Process cursor | Stop-Process -Force" -ForegroundColor Cyan
        }

        # Clear state file
        Remove-Item $stateFile -Force -ErrorAction SilentlyContinue
        Write-Host ""
        Write-Host "✅ Auto-fill stopped successfully" -ForegroundColor Green
        Write-Host ""
        exit 0
    }
}

# Not running, so start auto-fill
Write-Host "[STARTING] Auto-fill empty slots..." -ForegroundColor Green
Write-Host ""

# Create state file to indicate running
Set-Content $stateFile "RUNNING" -Encoding UTF8

# Launch auto_fill_empty_slots with parameters
try {
    if ($WaveNumber -gt 0) {
        & "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1" -WaveNumber $WaveNumber -WaveFile $WaveFile
    } else {
        & "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1"
    }
} finally {
    # Always clear state when done
    Remove-Item $stateFile -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "[INFO] Auto-fill completed. Press Button 2 to start a new fill cycle." -ForegroundColor Cyan
}

Write-Host ""
