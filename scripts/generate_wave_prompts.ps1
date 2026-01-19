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

# Collect all prompts across all waves
$allPrompts = @()
$totalDirsCreated = 0
$totalDirsExist = 0

foreach ($waveKey in $waveKeys) {
    $waveNumber = [int]($waveKey -replace 'wave_', '')
    $waveData = $wavePlan.$waveKey

    if (-not $waveData.phases) {
        Write-Host "[WARN] No phases array found for $waveKey - skipping" -ForegroundColor Yellow
        continue
    }

    Write-Host "[INFO] Processing Wave $waveNumber ($($waveData.phases.Count) phases)..."

    foreach ($phase in $waveData.phases) {
        $phaseId = $phase.id
        $impId = $phase.imp_id
        $title = $phase.title
        $worktreePath = $phase.worktree_path
        $branch = $phase.branch
        $files = if ($phase.files) { $phase.files -join ", " } else { "" }

        # Create worktree directory if it doesn't exist
        if (-not (Test-Path $worktreePath)) {
            New-Item -ItemType Directory -Path $worktreePath -Force | Out-Null
            Write-Host "  Created: $worktreePath"
            $totalDirsCreated++
        } else {
            $totalDirsExist++
        }

        $allPrompts += @{
            Wave = $waveNumber
            ID = $phaseId
            ImpId = $impId
            Title = $title
            Path = $worktreePath
            Branch = $branch
            Files = $files
        }
    }
}

$prompts = $allPrompts

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

    # Wave header
    $waveEmoji = switch ($waveNum) {
        "1" { "🔵" }
        "2" { "🟢" }
        "3" { "🟠" }
        "4" { "🔴" }
        "5" { "🟣" }
        "6" { "🟤" }
        default { "⚪" }
    }

    $markdown += "# $waveEmoji WAVE $waveNum ($($wavePrompts.Count) phases)`n`n"

    foreach ($prompt in $wavePrompts) {
        # Preserve existing status or default to READY
        $status = if ($existingStatuses.ContainsKey($prompt.ID)) { $existingStatuses[$prompt.ID] } else { "READY" }

        $markdown += "## Phase: $($prompt.ID) [$status]`n`n"
        $markdown += "**Wave**: $($prompt.Wave)`n"
        $markdown += "**IMP**: $($prompt.ImpId)`n"
        $markdown += "**Title**: $($prompt.Title)`n"
        $markdown += "**Path**: $($prompt.Path)`n"
        $markdown += "**Branch**: $($prompt.Branch)`n"
        if ($prompt.Files) {
            $markdown += "**Files**: $($prompt.Files)`n"
        }
        $markdown += "`n"
        # Shortened prompt - references AUTOPACK_WORKFLOW.md for full details
        $markdown += "I'm working in git worktree: $($prompt.Path)`n"
        $markdown += "Branch: $($prompt.Branch)`n`n"
        $markdown += "Task: Implement [$($prompt.ImpId)] $($prompt.Title)`n`n"
        $markdown += "See full details in AUTOPACK_WORKFLOW.md`n`n"
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
