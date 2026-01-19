# Cleanup completed phases from Wave[N]_All_Phases.md and JSON files
# Removes [COMPLETED] phases from:
#   1. Wave[N]_All_Phases.md
#   2. AUTOPACK_IMPS_MASTER.json
#   3. AUTOPACK_WAVE_PLAN.json
# Usage: .\cleanup_wave_prompts.ps1 -WaveNumber 1

param(
    [int]$WaveNumber = 0,
    [string]$WaveFile = ""
)

Write-Host ""
Write-Host "============ CLEANUP COMPLETED PHASES ============" -ForegroundColor Cyan
Write-Host ""

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

# Auto-detect wave number and file if not provided
if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $WaveFile = Get-DynamicFilePath "Wave*_All_Phases.md"

    if ([string]::IsNullOrWhiteSpace($WaveFile)) {
        Write-Host "[ERROR] No Wave*_All_Phases.md file found" -ForegroundColor Red
        exit 1
    }

    Write-Host "[AUTO-DETECT] Using: $(Split-Path -Leaf $WaveFile)"

    if ((Split-Path -Leaf $WaveFile) -match "Wave(\d)_") {
        $WaveNumber = [int]$Matches[1]
    }
}

if (-not (Test-Path $WaveFile)) {
    Write-Host "[ERROR] Wave file not found: $WaveFile" -ForegroundColor Red
    exit 1
}

Write-Host "Wave: $WaveNumber"
Write-Host "File: $WaveFile"
Write-Host ""

# ============ Load Current State ============
Write-Host "Loading prompt state..." -ForegroundColor Yellow
$prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile

$completedPrompts = @($prompts | Where-Object { $_.Status -eq "COMPLETED" })

if ($completedPrompts.Count -eq 0) {
    Write-Host "[INFO] No [COMPLETED] phases found"
    Write-Host "[INFO] Nothing to cleanup"
    exit 0
}

Write-Host "[OK] Found $($completedPrompts.Count) [COMPLETED] phase(s)"
Write-Host ""

# ============ CLEANUP 1: Wave[N]_All_Phases.md ============
Write-Host "CLEANUP 1: Cleaning Wave${WaveNumber}_All_Phases.md" -ForegroundColor Yellow

$content = Get-Content $WaveFile -Raw

# Remove all [COMPLETED] phase sections
# Pattern: ## Phase: <ID> [COMPLETED] ... followed by everything until next ## Phase or end
$regex = New-Object System.Text.RegularExpressions.Regex('## Phase: \S+ \[COMPLETED\].*?(?=## Phase:|\Z)', [System.Text.RegularExpressions.RegexOptions]::Singleline)
$content = $regex.Replace($content, '')

# Update status counts in header
$readyCount = ([regex]::Matches($content, '\[READY').Count)
$pendingCount = ([regex]::Matches($content, '\[PENDING').Count)
$completedCount = ([regex]::Matches($content, '\[COMPLETED').Count)

# Try both header formats (old and new style)
$headerPattern1 = 'READY: \d+, PENDING: \d+, COMPLETED: \d+, UNIMPLEMENTED: \d+'
$headerReplacement1 = "READY: $readyCount, PENDING: $pendingCount, COMPLETED: $completedCount, UNIMPLEMENTED: 0"
$content = $content -replace $headerPattern1, $headerReplacement1

# Also try alternate format if present
$headerPattern2 = '\*\*Status\*\*: \d+ READY \| \d+ PENDING \| \d+ COMPLETED'
$headerReplacement2 = "**Status**: $readyCount READY | $pendingCount PENDING | $completedCount COMPLETED"
$content = $content -replace $headerPattern2, $headerReplacement2

# Update "Last Updated"
$datePattern = '\*\*Last Updated\*\*: [^\n]+'
$dateReplacement = "**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$content = $content -replace $datePattern, $dateReplacement

Set-Content $WaveFile $content -Encoding UTF8
Write-Host "  ✅ Removed $($completedPrompts.Count) [COMPLETED] sections"
Write-Host "  ✅ Updated header: $readyCount READY | $pendingCount PENDING | 0 COMPLETED"
Write-Host ""

# ============ CLEANUP 2: AUTOPACK_IMPS_MASTER.json ============
Write-Host "CLEANUP 2: Cleaning AUTOPACK_IMPS_MASTER.json" -ForegroundColor Yellow

$masterFile = Get-DynamicFilePath "AUTOPACK_IMPS_MASTER.json"

if ($null -ne $masterFile -and (Test-Path $masterFile)) {
    $masterJson = Get-Content $masterFile -Raw | ConvertFrom-Json
    $originalCount = @($masterJson.improvements).Count

    # Get completed phase IDs
    $completedIds = $completedPrompts | ForEach-Object { $_.ID }

    # Filter out completed phases
    if ($null -ne $masterJson.improvements) {
        $masterJson.improvements = @($masterJson.improvements | Where-Object { $_.id -notin $completedIds })
    }

    $newCount = @($masterJson.improvements).Count
    $removedCount = $originalCount - $newCount

    $masterJson | ConvertTo-Json -Depth 10 | Set-Content $masterFile -Encoding UTF8
    Write-Host "  ✅ Removed $removedCount entries from improvements list"
} else {
    Write-Host "  ⚠️  File not found (skipping): $masterFile"
}

Write-Host ""

# ============ CLEANUP 3: AUTOPACK_WAVE_PLAN.json ============
Write-Host "CLEANUP 3: Cleaning AUTOPACK_WAVE_PLAN.json" -ForegroundColor Yellow

$planFile = Get-DynamicFilePath "AUTOPACK_WAVE_PLAN.json"

if ($null -ne $planFile -and (Test-Path $planFile)) {
    $planJson = Get-Content $planFile -Raw | ConvertFrom-Json

    # Find the wave key
    $waveKey = "wave_$WaveNumber"

    if ($planJson.PSObject.Properties[$waveKey]) {
        $beforeCount = @($planJson.PSObject.Properties[$waveKey].Value.phases).Count

        # Get completed phase IDs
        $completedIds = $completedPrompts | ForEach-Object { $_.ID }

        # Filter out completed phases
        if ($null -ne $planJson.PSObject.Properties[$waveKey].Value.phases) {
            $planJson.PSObject.Properties[$waveKey].Value.phases = @(
                $planJson.PSObject.Properties[$waveKey].Value.phases |
                Where-Object { $_.id -notin $completedIds }
            )
        }

        $afterCount = @($planJson.PSObject.Properties[$waveKey].Value.phases).Count
        $removedCount = $beforeCount - $afterCount

        $planJson | ConvertTo-Json -Depth 10 | Set-Content $planFile -Encoding UTF8
        Write-Host "  ✅ Removed $removedCount phase entries from Wave $WaveNumber"
    } else {
        Write-Host "  ⚠️  Wave $WaveNumber not found in plan (skipping)"
    }
} else {
    Write-Host "  ⚠️  File not found (skipping): $planFile"
}

Write-Host ""

# ============ Final Summary ============
Write-Host "============ CLEANUP COMPLETE ============" -ForegroundColor Green
Write-Host ""
Write-Host "Files cleaned:"
Write-Host "  ✅ Wave${WaveNumber}_All_Phases.md"
Write-Host "  ✅ AUTOPACK_IMPS_MASTER.json"
Write-Host "  ✅ AUTOPACK_WAVE_PLAN.json"
Write-Host ""
Write-Host "Completed phases removed: $($completedPrompts.Count)"
Write-Host ""

# Reload and display new status
$promptsAfter = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile
$readyAfter = @($promptsAfter | Where-Object { $_.Status -eq "READY" }).Count
$pendingAfter = @($promptsAfter | Where-Object { $_.Status -eq "PENDING" }).Count

Write-Host "Remaining phases: $readyAfter READY | $pendingAfter PENDING | 0 COMPLETED"
Write-Host ""

if ($pendingAfter -gt 0) {
    Write-Host "[INFO] Wave $WaveNumber still has $pendingAfter [PENDING] phase(s)"
    Write-Host "[INFO] Wait for PRs to merge, then use Button 2 again"
} elseif ($readyAfter -gt 0) {
    Write-Host "[INFO] Wave $WaveNumber has $readyAfter [READY] phase(s) remaining"
    Write-Host "[INFO] Use Button 2 to continue filling slots"
} else {
    Write-Host "[INFO] ✅ Wave $WaveNumber complete!"
    Write-Host "[INFO] Ready for Wave $($WaveNumber + 1)"
    Write-Host "[INFO] Use Button 1 to generate Wave $($WaveNumber + 1) prompts"
}

Write-Host ""
