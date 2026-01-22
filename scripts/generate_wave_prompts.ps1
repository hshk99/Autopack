param(
    [string]$WavePlanFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_WAVE_PLAN.json",
    [switch]$Preserve  # Preserve existing statuses instead of resetting to [READY] (default: reset to READY)
)

Write-Host ""
Write-Host "============ GENERATE ALL WAVE PROMPTS ============" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $WavePlanFile)) {
    Write-Host "[ERROR] Wave plan file not found: $WavePlanFile" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Reading wave plan from JSON..."
$wavePlan = Get-Content $WavePlanFile -Raw | ConvertFrom-Json

# Find all wave keys (wave_1, wave_2, etc.)
$waveKeys = $wavePlan.PSObject.Properties.Name |
    Where-Object { $_ -match '^wave_(\d+)$' } |
    Sort-Object { [int]($_ -replace 'wave_', '') }

if ($waveKeys.Count -eq 0) {
    Write-Host "[ERROR] No waves found in wave plan" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Found $($waveKeys.Count) waves in wave plan"

# Helper function to convert IMP ID to phase ID and derive other metadata
# e.g., "IMP-SEC-001" -> phaseId: "sec001", branch: "wave1/sec-001-...", path: "C:\dev\Autopack_w1_sec001"
function Convert-ImpToPhase {
    param(
        [string]$ImpId,
        [int]$WaveNumber
    )

    # Parse IMP ID: "IMP-SEC-001" -> prefix="SEC", num="001"
    if ($ImpId -match '^IMP-([A-Z]+)-(\d+)$') {
        $prefix = $Matches[1].ToLower()
        $numPadded = $Matches[2]

        # Generate phase ID: "sec001"
        $phaseId = "$prefix$numPadded"

        # Generate worktree path: "C:\dev\Autopack_w1_sec001"
        $worktreePath = "C:\dev\Autopack_w$($WaveNumber)_$phaseId"

        # Generate branch name: "wave1/sec-001-..."
        # We'll use a simplified branch name since full names are in AUTOPACK_WORKFLOW.md
        $branchName = "wave$WaveNumber/$prefix-$numPadded"

        return @{
            PhaseId = $phaseId
            ImpId = $ImpId
            WorktreePath = $worktreePath
            Branch = $branchName
            Prefix = $prefix
            Number = $numPadded
        }
    }
    return $null
}

# Collect all prompts across all waves
$allPrompts = @()
$totalDirsCreated = 0
$totalDirsExist = 0

foreach ($waveKey in $waveKeys) {
    $waveNumber = [int]($waveKey -replace 'wave_', '')
    $waveData = $wavePlan.$waveKey

    # Support both 'imps' array (actual format) and 'phases' array (legacy)
    $impsList = $null
    if ($waveData.imps) {
        $impsList = $waveData.imps
    } elseif ($waveData.phases) {
        # Legacy format with full phase objects
        $impsList = $waveData.phases | ForEach-Object { $_.imp_id }
    }

    if (-not $impsList -or $impsList.Count -eq 0) {
        Write-Host "[WARN] No imps found for $waveKey - skipping" -ForegroundColor Yellow
        continue
    }

    Write-Host "[INFO] Processing Wave $waveNumber ($($impsList.Count) IMPs)..."

    foreach ($impId in $impsList) {
        $phaseInfo = Convert-ImpToPhase -ImpId $impId -WaveNumber $waveNumber

        if ($null -eq $phaseInfo) {
            Write-Host "  [WARN] Could not parse IMP ID: $impId" -ForegroundColor Yellow
            continue
        }

        # Create worktree directory if it doesn't exist
        if (-not (Test-Path $phaseInfo.WorktreePath)) {
            New-Item -ItemType Directory -Path $phaseInfo.WorktreePath -Force | Out-Null
            Write-Host "  Created: $($phaseInfo.WorktreePath)"
            $totalDirsCreated++
        } else {
            $totalDirsExist++
        }

        $allPrompts += @{
            Wave = $waveNumber
            ID = $phaseInfo.PhaseId
            ImpId = $impId
            Title = $impId  # Title will reference AUTOPACK_WORKFLOW.md for details
            Path = $phaseInfo.WorktreePath
            Branch = $phaseInfo.Branch
            Files = ""
        }
    }
}

# Convert hashtables to PSObjects for proper grouping
$prompts = $allPrompts | ForEach-Object { [PSCustomObject]$_ }

if ($prompts.Count -eq 0) {
    Write-Host "[ERROR] No phases found" -ForegroundColor Red
    exit 1
}

# Single output file for ALL waves
$outputFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\Prompts_All_Waves.md"
$existingStatuses = @{}
$existingPhaseIds = @{}

# Load existing statuses if file exists (for re-runs)
if (Test-Path $outputFile) {
    Write-Host "[INFO] Existing file found - preserving statuses..."
    $existingContent = Get-Content $outputFile -Raw
    $statusPattern = "## Phase: (\S+) \[(READY|PENDING|COMPLETED|UNIMPLEMENTED)\]"
    $statusMatches = [regex]::Matches($existingContent, $statusPattern)

    foreach ($match in $statusMatches) {
        $phaseId = $match.Groups[1].Value
        $status = $match.Groups[2].Value
        $existingStatuses[$phaseId] = $status
        $existingPhaseIds[$phaseId] = $true
    }
    Write-Host "[INFO] Found $($existingStatuses.Count) existing phases with statuses"
}

# Count statuses
$readyCount = 0
$pendingCount = 0
$completedCount = 0
$unimplementedCount = 0

foreach ($prompt in $prompts) {
    if ($existingStatuses.ContainsKey($prompt.ID)) {
        # Always preserve existing status (no need for -Preserve flag on re-runs)
        $status = $existingStatuses[$prompt.ID]
    } else {
        # New phase - default to READY
        $status = "READY"
    }

    switch ($status) {
        "READY" { $readyCount++ }
        "PENDING" { $pendingCount++ }
        "COMPLETED" { $completedCount++ }
        "UNIMPLEMENTED" { $unimplementedCount++ }
    }
}

# Group prompts by wave for organized output
$promptsByWave = $prompts | Group-Object -Property Wave | Sort-Object { [int]$_.Name }

# Build markdown content
$markdown = "# All Phases`n`n"
$markdown += "**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm')`n"
$markdown += "**Total Phases**: $($prompts.Count)`n"
$markdown += "**Waves**: $($promptsByWave.Count)`n`n"
$markdown += "READY: $readyCount | PENDING: $pendingCount | COMPLETED: $completedCount | UNIMPLEMENTED: $unimplementedCount`n`n"
$markdown += "---`n`n"

foreach ($waveGroup in $promptsByWave) {
    $waveNum = $waveGroup.Name
    $wavePrompts = $waveGroup.Group

    # Wave header - use ASCII-safe markers to avoid encoding issues
    $waveMarker = switch ($waveNum) {
        "1" { "[W1]" }
        "2" { "[W2]" }
        "3" { "[W3]" }
        "4" { "[W4]" }
        "5" { "[W5]" }
        "6" { "[W6]" }
        default { "[W?]" }
    }

    $markdown += "# $waveMarker WAVE $waveNum ($($wavePrompts.Count) phases)`n`n"

    foreach ($prompt in $wavePrompts) {
        # Preserve existing status or default to READY
        $status = if ($existingStatuses.ContainsKey($prompt.ID)) { $existingStatuses[$prompt.ID] } else { "READY" }

        $markdown += "## Phase: $($prompt.ID) [$status]`n`n"
        $markdown += "**Wave**: $($prompt.Wave)`n"
        $markdown += "**IMP**: $($prompt.ImpId)`n"
        $markdown += "**Title**: $($prompt.ImpId)`n"
        $markdown += "**Path**: $($prompt.Path)`n"
        $markdown += "**Branch**: $($prompt.Branch)`n"
        $markdown += "`n"
        # Shortened prompt - references AUTOPACK_WORKFLOW.md for full implementation details
        # This keeps Prompts_All_Waves.md small while providing all info needed by automation scripts
        $markdown += "I'm working in git worktree: $($prompt.Path)`n"
        $markdown += "Branch: $($prompt.Branch)`n`n"
        $markdown += "Task: Implement $($prompt.ImpId)`n`n"
        $markdown += "**IMPORTANT**: Read the full implementation details for this IMP in:`n"
        $markdown += "C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_WORKFLOW.md`n`n"
        $markdown += "Search for ``$($prompt.ImpId)`` in that file to find the complete prompt with:`n"
        $markdown += "- Specific files to modify`n"
        $markdown += "- Before/After code examples`n"
        $markdown += "- Step-by-step implementation instructions`n"
        $markdown += "- Test requirements`n"
        $markdown += "- Commit message format`n"
        $markdown += "- PR creation command`n`n"
        $markdown += "**CRITICAL - Branch and PR Naming**:`n"
        $markdown += "- Branch: Use EXACTLY ``$($prompt.Branch)`` - do NOT add any suffix`n"
        $markdown += "- PR Title: ``[$($prompt.ImpId)] <brief description>```n"
        $markdown += "- Example: ``git push -u origin $($prompt.Branch) && gh pr create --title `"[$($prompt.ImpId)] Add feature X`" --body `"...`"```n`n"
        $markdown += "---`n`n"
    }
}

Set-Content $outputFile $markdown -Encoding UTF8

Write-Host ""
Write-Host "============ GENERATION COMPLETE ============" -ForegroundColor Green
Write-Host ""
Write-Host "Waves: $($promptsByWave.Count)"
Write-Host "Total Phases: $($prompts.Count)"
Write-Host "Directories Created: $totalDirsCreated"
Write-Host "Directories Existed: $totalDirsExist"
Write-Host ""
Write-Host "Status: READY=$readyCount | PENDING=$pendingCount | COMPLETED=$completedCount | UNIMPLEMENTED=$unimplementedCount"
Write-Host ""
Write-Host "Output: $outputFile"
Write-Host ""
