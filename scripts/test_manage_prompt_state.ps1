# Test manage_prompt_state to verify Path extraction works

Write-Host "Testing manage_prompt_state.ps1..." -ForegroundColor Cyan
Write-Host ""

$prompts = & 'C:\dev\Autopack\scripts\manage_prompt_state.ps1' -Action Load -WaveFile 'C:\Users\hshk9\OneDrive\Backup\Desktop\Wave1_All_Phases.md'

Write-Host "First 5 phases with paths:" -ForegroundColor Yellow
$prompts | Select-Object -First 5 | ForEach-Object {
    Write-Host "ID: $($_.ID) | Status: $($_.Status)"
    Write-Host "  Path: $($_.Path)"
    Write-Host ""
}
