# Check PR status for all PENDING phases and mark completed ones
param(
    [string]$WaveFile = ""
)

$backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"

# Helper function to find dynamically generated files
function Get-DynamicFilePath {
    param([string]$Pattern)
    $files = @(Get-ChildItem -Path $backupDir -Filter $Pattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($files.Count -gt 0) {
        return $files[0].FullName
    }
    return $null
}

if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $WaveFile = Get-DynamicFilePath "Wave*_All_Phases.md"

    if ([string]::IsNullOrWhiteSpace($WaveFile)) {
        Write-Host "ERROR: No Wave file found"
        exit 1
    }
}

Write-Host "PR STATUS CHECK"
Write-Host "==============="
Write-Host ""

# Load all prompts - manage_prompt_state returns phase objects
$prompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })
$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" } 2>/dev/null)

Write-Host "Found $($pendingPrompts.Count) PENDING phases"
Write-Host ""

$completedCount = 0
$mergedPRs = @()

# Check first 9 phases (sec001-006, safety001-003)
foreach ($prompt in $pendingPrompts | Select-Object -First 9) {
    $phaseId = $prompt.ID
    $branchName = $prompt.Branch

    Write-Host "$phaseId..."

    # Query GitHub
    $prJson = gh pr list --head $branchName --state all --json number,state 2>/dev/null | ConvertFrom-Json

    if ($null -ne $prJson -and $prJson.Count -gt 0) {
        $pr = if ($prJson -is [array]) { $prJson[0] } else { $prJson }
        $state = $pr.state

        if ($state -eq "MERGED") {
            Write-Host "  -> MERGED PR #$($pr.number) (marking complete)"
            $mergedPRs += $phaseId
            $completedCount++
        } elseif ($state -eq "OPEN") {
            Write-Host "  -> OPEN PR #$($pr.number)"
        } else {
            Write-Host "  -> PR state: $state"
        }
    } else {
        Write-Host "  -> No PR found"
    }
}

Write-Host ""
Write-Host "RESULTS:"
Write-Host "========="
Write-Host "Merged PRs ready to mark COMPLETED: $completedCount"

if ($mergedPRs.Count -gt 0) {
    Write-Host ""
    Write-Host "Marking phases as COMPLETED..."

    foreach ($phaseId in $mergedPRs) {
        & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus "COMPLETED" 2>&1 | Where-Object { $_ -match "OK|ERROR" }
    }

    # Update AUTOPACK_IMPS_MASTER.json if it exists
    $masterFile = Get-DynamicFilePath "AUTOPACK_IMPS_MASTER.json"
    if ($null -ne $masterFile -and (Test-Path $masterFile)) {
        Write-Host ""
        Write-Host "Updating AUTOPACK_IMPS_MASTER.json..."
        try {
            $masterJson = Get-Content $masterFile -Raw | ConvertFrom-Json
            if ($null -ne $masterJson.improvements) {
                $masterJson.improvements = @($masterJson.improvements | Where-Object { $_.id -notin $mergedPRs })
                $masterJson | ConvertTo-Json -Depth 10 | Set-Content $masterFile -Encoding UTF8
                Write-Host "  ✅ Removed $($mergedPRs.Count) completed phases from improvements"
            }
        } catch {
            Write-Host "  ⚠️  Could not update AUTOPACK_IMPS_MASTER.json: $_"
        }
    }

    # Update AUTOPACK_WAVE_PLAN.json if it exists
    $planFile = Get-DynamicFilePath "AUTOPACK_WAVE_PLAN.json"
    if ($null -ne $planFile -and (Test-Path $planFile)) {
        Write-Host "Updating AUTOPACK_WAVE_PLAN.json..."
        try {
            $planJson = Get-Content $planFile -Raw | ConvertFrom-Json
            $waveNumber = 1
            if ($WaveFile -match "Wave(\d)") {
                $waveNumber = [int]$Matches[1]
            }
            $waveKey = "wave_$waveNumber"

            if ($planJson.PSObject.Properties[$waveKey]) {
                if ($null -ne $planJson.PSObject.Properties[$waveKey].Value.phases) {
                    $planJson.PSObject.Properties[$waveKey].Value.phases = @(
                        $planJson.PSObject.Properties[$waveKey].Value.phases |
                        Where-Object { $_.id -notin $mergedPRs }
                    )
                    $planJson | ConvertTo-Json -Depth 10 | Set-Content $planFile -Encoding UTF8
                    Write-Host "  ✅ Removed $($mergedPRs.Count) completed phases from Wave $waveNumber plan"
                }
            }
        } catch {
            Write-Host "  ⚠️  Could not update AUTOPACK_WAVE_PLAN.json: $_"
        }
    }
}
