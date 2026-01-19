# Test to display phase status after auto-fill

$prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile "C:\Users\hshk9\OneDrive\Backup\Desktop\Wave1_All_Phases.md"

Write-Host ""
Write-Host "=== PHASE STATUS AFTER AUTO-FILL ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "First 12 phases:" -ForegroundColor Yellow
$prompts | Select-Object -First 12 | ForEach-Object {
    Write-Host "ID: $($_.ID) | Status: $($_.Status) | Path: $($_.Path)"
}

Write-Host ""
Write-Host "Status Summary:" -ForegroundColor Yellow
$readyCount = @($prompts | Where-Object { $_.Status -eq "READY" }).Count
$pendingCount = @($prompts | Where-Object { $_.Status -eq "PENDING" }).Count
$completedCount = @($prompts | Where-Object { $_.Status -eq "COMPLETED" }).Count
Write-Host "  READY: $readyCount"
Write-Host "  PENDING: $pendingCount"
Write-Host "  COMPLETED: $completedCount"
Write-Host ""

Write-Host "Pending phases (being worked on):" -ForegroundColor Yellow
$prompts | Where-Object { $_.Status -eq "PENDING" } | ForEach-Object {
    Write-Host "  - $($_.ID) ($($_.Path))"
}
