# Reset ALL [PENDING] phases back to [UNIMPLEMENTED] for re-running Button 2
# Usage: .\reset_all_pending_phases.ps1
# This removes phases that haven't been started yet so you can re-run Button 2

param(
    [string]$WaveFile = ""
)

if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
    $waveFiles = @(Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)

    if ($waveFiles.Count -gt 0) {
        $WaveFile = $waveFiles[0].FullName
        Write-Host "[AUTO-DETECT] Using: $($waveFiles[0].Name)"
    } else {
        Write-Host "[ERROR] No Wave*_All_Phases.md file found" -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path $WaveFile)) {
    Write-Host "[ERROR] Wave file not found: $WaveFile" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============ RESET ALL PENDING PHASES ============" -ForegroundColor Yellow
Write-Host ""

# Load current state
$prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile

$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" })

if ($pendingPrompts.Count -eq 0) {
    Write-Host "[INFO] No [PENDING] phases found"
    Write-Host "[INFO] Nothing to reset"
    exit 0
}

Write-Host "[OK] Found $($pendingPrompts.Count) [PENDING] phase(s) to reset"
Write-Host ""

# Reset each pending phase to UNIMPLEMENTED
$resetCount = 0
foreach ($phase in $pendingPrompts) {
    $phaseId = $phase.ID
    Write-Host "Resetting $phaseId..."

    & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus "UNIMPLEMENTED" | Out-Null

    if ($?) {
        $resetCount++
        Write-Host "  ✅ $phaseId → [UNIMPLEMENTED]"
    } else {
        Write-Host "  ❌ Failed to reset $phaseId" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============ RESET COMPLETE ============" -ForegroundColor Green
Write-Host ""
Write-Host "Reset $resetCount phases from [PENDING] → [UNIMPLEMENTED]"
Write-Host ""

# Reload and display new status
$promptsAfter = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile
$readyAfter = @($promptsAfter | Where-Object { $_.Status -eq "READY" }).Count
$pendingAfter = @($promptsAfter | Where-Object { $_.Status -eq "PENDING" }).Count
$unimplementedAfter = @($promptsAfter | Where-Object { $_.Status -eq "UNIMPLEMENTED" }).Count

Write-Host "New status: $readyAfter READY | $pendingAfter PENDING | $unimplementedAfter UNIMPLEMENTED"
Write-Host ""
Write-Host "[INFO] You can now run Button 2 to re-fill the slots"
Write-Host ""
