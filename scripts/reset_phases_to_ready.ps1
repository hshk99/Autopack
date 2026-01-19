# Reset all phases to READY status for fresh testing

$WaveFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\Wave1_All_Phases.md"

Write-Host "============ RESETTING PHASES TO READY ============" -ForegroundColor Cyan
Write-Host ""

# Read the current file
$content = Get-Content $WaveFile -Raw

# Replace all [PENDING] and [COMPLETED] with [READY]
$newContent = $content -replace '\[(PENDING|COMPLETED)\]', '[READY]'

# Write back
Set-Content $WaveFile -Value $newContent -Encoding UTF8

Write-Host "[OK] Reset all phases to [READY]"
Write-Host ""

# Verify the change
$prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile

Write-Host "Verification:"
$readyCount = @($prompts | Where-Object { $_.Status -eq "READY" }).Count
$pendingCount = @($prompts | Where-Object { $_.Status -eq "PENDING" }).Count
$completedCount = @($prompts | Where-Object { $_.Status -eq "COMPLETED" }).Count
Write-Host "  READY: $readyCount"
Write-Host "  PENDING: $pendingCount"
Write-Host "  COMPLETED: $completedCount"
Write-Host ""
