# Test to verify that paths are correctly extracted and can be passed to launch

$WaveFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\Wave1_All_Phases.md"

Write-Host "Loading prompts from Wave file..."
$prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile

Write-Host ""
Write-Host "First 3 prompts that would be filled:" -ForegroundColor Yellow
$prompts | Select-Object -First 3 | ForEach-Object {
    $id = $_.ID
    $path = $_.Path
    Write-Host ""
    Write-Host "Phase ID: $id"
    Write-Host "Path: $path"
    Write-Host "Path is null or empty: $([string]::IsNullOrWhiteSpace($path))"
    Write-Host "Path type: $($path.GetType().Name)"
    Write-Host "Path length: $($path.Length)"
}

Write-Host ""
Write-Host "Testing if paths are valid directories:" -ForegroundColor Yellow
$prompts | Select-Object -First 3 | ForEach-Object {
    $path = $_.Path
    $exists = Test-Path $path
    Write-Host "  $($_.ID): $path -> Exists: $exists"
}
