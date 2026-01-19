# Debug script to check branch names and PR detection
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "DEBUG: Branch Name and PR Detection" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Load wave file
$backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
$waveFiles = Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
$WaveFile = $waveFiles[0].FullName

Write-Host "Wave file: $WaveFile"
Write-Host ""

$prompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })

Write-Host "PENDING phases and their branches:" -ForegroundColor Yellow
$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" })

foreach ($p in $pendingPrompts) {
    Write-Host "  $($p.ID): Branch='$($p.Branch)'"
}

Write-Host ""
Write-Host "Testing PR detection for each PENDING phase:" -ForegroundColor Yellow
Write-Host ""

foreach ($p in $pendingPrompts) {
    $phaseId = $p.ID
    $branchName = $p.Branch

    Write-Host "$phaseId (branch: $branchName)..."

    # Query GitHub - same as check_pr_status.ps1
    $prJson = gh pr list --head $branchName --state all --json number,state,statusCheckRollup 2>$null | ConvertFrom-Json

    if ($null -ne $prJson -and $prJson.Count -gt 0) {
        $pr = if ($prJson -is [array]) { $prJson[0] } else { $prJson }
        $state = $pr.state
        $prNumber = $pr.number

        Write-Host "  -> Found PR #$prNumber (state: $state)" -ForegroundColor Green

        if ($state -eq "OPEN") {
            $hasChecks = $null -ne $pr.statusCheckRollup -and $pr.statusCheckRollup -is [array]
            if ($hasChecks) {
                $failedChecks = @($pr.statusCheckRollup | Where-Object { $_.conclusion -eq "FAILURE" })
                $runningChecks = @($pr.statusCheckRollup | Where-Object { $_.status -eq "IN_PROGRESS" })

                if ($runningChecks.Count -gt 0) {
                    Write-Host "  -> CI running ($($runningChecks.Count) checks in progress)"
                } elseif ($failedChecks.Count -gt 0) {
                    $failedNames = ($failedChecks | ForEach-Object { $_.name }) -join ", "
                    Write-Host "  -> CI FAILED: $failedNames" -ForegroundColor Red
                } else {
                    Write-Host "  -> CI PASSING" -ForegroundColor Green
                }
            } else {
                Write-Host "  -> No CI checks found"
            }
        }
    } else {
        Write-Host "  -> NO PR FOUND for branch '$branchName'" -ForegroundColor Red
    }
    Write-Host ""
}
