# Cleanup completed phases from Prompts_All_Waves.md and JSON files
# Removes [COMPLETED] phases from:
#   1. Prompts_All_Waves.md
#   2. AUTOPACK_IMPS_MASTER.json
#   3. AUTOPACK_WAVE_PLAN.json
#   4. AUTOPACK_WORKFLOW.md (removes detailed prompt sections for completed phases)
# Also appends unresolved issues from Wave[N]_Unresolved_Issues.json to wave file
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

# Get unresolved issues file path
function Get-UnresolvedIssuesFile {
    param([int]$WaveNumber)
    $fileName = "Wave${WaveNumber}_Unresolved_Issues.json"
    return Join-Path $backupDir $fileName
}

# Load and format unresolved issues summary
function Get-UnresolvedIssuesSummary {
    param([int]$WaveNumber)
    $filePath = Get-UnresolvedIssuesFile $WaveNumber

    if (-not (Test-Path $filePath)) {
        return $null
    }

    try {
        $issues = Get-Content $filePath -Raw | ConvertFrom-Json
        if ($null -ne $issues.issues -and $issues.issues.Count -gt 0) {
            return $issues
        }
    } catch {
        Write-Host "  [WARN] Could not load unresolved issues: $_"
    }

    return $null
}

# Auto-detect wave number and file if not provided
if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $promptsFile = Join-Path $backupDir "Prompts_All_Waves.md"

    if (Test-Path $promptsFile) {
        $WaveFile = $promptsFile
        Write-Host "[AUTO-DETECT] Using: Prompts_All_Waves.md"
    } else {
        # Fallback to old Wave*_All_Phases.md format for backwards compatibility
        $WaveFile = Get-DynamicFilePath "Wave*_All_Phases.md"

        if ([string]::IsNullOrWhiteSpace($WaveFile)) {
            Write-Host "[ERROR] No Prompts_All_Waves.md or Wave*_All_Phases.md file found" -ForegroundColor Red
            exit 1
        }

        Write-Host "[AUTO-DETECT] Using: $(Split-Path -Leaf $WaveFile) (legacy format)"

        if ((Split-Path -Leaf $WaveFile) -match "Wave(\d)_") {
            $WaveNumber = [int]$Matches[1]
        }
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

# ============ CLEANUP 1: Prompts_All_Waves.md ============
Write-Host "CLEANUP 1: Cleaning Prompts_All_Waves.md" -ForegroundColor Yellow

$content = Get-Content $WaveFile -Raw

# Remove all [COMPLETED] phase sections
# Pattern: ## Phase: <ID> [COMPLETED] ... followed by everything until next ## Phase or end
$regex = New-Object System.Text.RegularExpressions.Regex('## Phase: \S+ \[COMPLETED\].*?(?=## Phase:|\Z)', [System.Text.RegularExpressions.RegexOptions]::Singleline)
$content = $regex.Replace($content, '')

# Update status counts in header
$readyCount = ([regex]::Matches($content, '\[READY\]').Count)
$unresolvedCount = ([regex]::Matches($content, '\[UNRESOLVED\]').Count)
$pendingCount = ([regex]::Matches($content, '\[PENDING\]').Count)
$completedCount = ([regex]::Matches($content, '\[COMPLETED\]').Count)

# Try both header formats (old and new style)
$headerPattern1 = 'READY: \d+, PENDING: \d+, COMPLETED: \d+, UNIMPLEMENTED: \d+'
$headerReplacement1 = "READY: $readyCount, UNRESOLVED: $unresolvedCount, PENDING: $pendingCount, COMPLETED: $completedCount, UNIMPLEMENTED: 0"
$content = $content -replace $headerPattern1, $headerReplacement1

# Also try alternate format if present (with optional UNRESOLVED)
$headerPattern2 = '\*\*Status\*\*: \d+ READY( \| \d+ UNRESOLVED)? \| \d+ PENDING \| \d+ COMPLETED'
$headerReplacement2 = "**Status**: $readyCount READY | $unresolvedCount UNRESOLVED | $pendingCount PENDING | $completedCount COMPLETED"
$content = $content -replace $headerPattern2, $headerReplacement2

# Update "Last Updated"
$datePattern = '\*\*Last Updated\*\*: [^\n]+'
$dateReplacement = "**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$content = $content -replace $datePattern, $dateReplacement

Set-Content $WaveFile $content -Encoding UTF8
Write-Host "  [OK] Removed $($completedPrompts.Count) [COMPLETED] sections"
Write-Host "  [OK] Updated header: $readyCount READY | $unresolvedCount UNRESOLVED | $pendingCount PENDING | 0 COMPLETED"
Write-Host ""

# ============ CLEANUP 2: AUTOPACK_IMPS_MASTER.json ============
Write-Host "CLEANUP 2: Cleaning AUTOPACK_IMPS_MASTER.json" -ForegroundColor Yellow

$masterFile = Get-DynamicFilePath "AUTOPACK_IMPS_MASTER.json"

if ($null -ne $masterFile -and (Test-Path $masterFile)) {
    $masterJson = Get-Content $masterFile -Raw | ConvertFrom-Json

    # Get the array - could be "improvements" or "unimplemented_imps"
    $impsArray = if ($null -ne $masterJson.improvements) { $masterJson.improvements }
                 elseif ($null -ne $masterJson.unimplemented_imps) { $masterJson.unimplemented_imps }
                 else { @() }

    $originalCount = @($impsArray).Count

    # Get completed IMP IDs (convert phase ID like "sec001" to IMP ID like "IMP-SEC-001")
    $completedImpIds = @()
    foreach ($prompt in $completedPrompts) {
        # Phase ID format: "sec001" -> IMP ID format: "IMP-SEC-001"
        if ($prompt.ID -match '^([a-z]+)(\d+)$') {
            $prefix = $Matches[1].ToUpper()
            $num = $Matches[2].PadLeft(3, '0')
            $completedImpIds += "IMP-$prefix-$num"
        }
        # Also add the raw ID in case it's already in IMP format
        $completedImpIds += $prompt.ID
    }

    Write-Host "  [DEBUG] Looking for IMP IDs: $($completedImpIds -join ', ')"

    # Filter out completed phases - check both 'id' and 'imp_id' fields
    $filteredArray = @($impsArray | Where-Object {
        $itemId = if ($_.imp_id) { $_.imp_id } else { $_.id }
        $itemId -notin $completedImpIds
    })

    # Update the correct property
    if ($null -ne $masterJson.improvements) {
        $masterJson.improvements = $filteredArray
    } elseif ($null -ne $masterJson.unimplemented_imps) {
        $masterJson.unimplemented_imps = $filteredArray
    }

    $newCount = @($filteredArray).Count
    $removedCount = $originalCount - $newCount

    $masterJson | ConvertTo-Json -Depth 10 | Set-Content $masterFile -Encoding UTF8
    Write-Host "  [OK] Removed $removedCount entries from improvements list"
} else {
    Write-Host "  [WARN] File not found (skipping): $masterFile"
}

Write-Host ""

# ============ CLEANUP 3: AUTOPACK_WAVE_PLAN.json ============
Write-Host "CLEANUP 3: Cleaning AUTOPACK_WAVE_PLAN.json" -ForegroundColor Yellow

$planFile = Get-DynamicFilePath "AUTOPACK_WAVE_PLAN.json"

if ($null -ne $planFile -and (Test-Path $planFile)) {
    $planJson = Get-Content $planFile -Raw | ConvertFrom-Json

    # Get completed phase IDs
    $completedIds = $completedPrompts | ForEach-Object { $_.ID }

    Write-Host "  [DEBUG] Looking for phase IDs: $($completedIds -join ', ')"

    # Find all wave keys (wave_1, wave_2, etc.) and clean each
    $waveKeys = $planJson.PSObject.Properties.Name | Where-Object { $_ -match '^wave_\d+$' }
    $totalRemoved = 0

    foreach ($waveKey in $waveKeys) {
        if ($null -ne $planJson.$waveKey.phases) {
            $beforeCount = @($planJson.$waveKey.phases).Count

            # Filter out completed phases
            $planJson.$waveKey.phases = @(
                $planJson.$waveKey.phases |
                Where-Object { $_.id -notin $completedIds }
            )

            $afterCount = @($planJson.$waveKey.phases).Count
            $removedCount = $beforeCount - $afterCount

            if ($removedCount -gt 0) {
                Write-Host "  [OK] Removed $removedCount phase(s) from $waveKey"
                $totalRemoved += $removedCount
            }
        }
    }

    $planJson | ConvertTo-Json -Depth 10 | Set-Content $planFile -Encoding UTF8
    Write-Host "  [OK] Total removed from WAVE_PLAN: $totalRemoved phase(s)"
} else {
    Write-Host "  [WARN] File not found (skipping): $planFile"
}

Write-Host ""

# ============ CLEANUP 4: Append Unresolved Issues as Actionable Prompts ============
Write-Host "CLEANUP 4: Appending unresolved issues as actionable prompts" -ForegroundColor Yellow

$unresolvedData = Get-UnresolvedIssuesSummary $WaveNumber

if ($null -ne $unresolvedData -and $unresolvedData.issues.Count -gt 0) {
    Write-Host "  [INFO] Found $($unresolvedData.issues.Count) unresolved issue(s)"

    # Create unresolved issues section with actionable prompts
    $issuesSummary = @"

---

## Unresolved Issues (Wave $WaveNumber)

**Summary**: The following phases have CI failures that need to be fixed. Each phase below is formatted as an actionable prompt.

"@

    foreach ($issue in $unresolvedData.issues) {
        $phaseId = $issue.phaseId
        $prNumber = $issue.prNumber
        $issueDesc = $issue.issue
        $recorded = $issue.recorded

        # Format as actionable prompt following the same template as regular phases
        $issuesSummary += @"

---

## Phase: $phaseId [UNRESOLVED]

**Title**: Fix CI Failure for $phaseId
**PR**: #$prNumber
**Issue**: $issueDesc
**Recorded**: $recorded

I'm working in this git worktree to fix the CI failure.

Task: Fix the CI failure for PR #$prNumber

The CI run has failed with: $issueDesc

Please investigate and fix the issue:

1. Check the CI logs for PR #$prNumber to identify the specific failure
2. If it's a "Core Tests (Must Pass)" failure:
   - Review the test output to find which tests failed
   - Fix the code to make tests pass
   - Run tests locally before pushing
3. If it's a lint/verify-structure failure:
   - Run the linter locally to see the issues
   - Fix formatting/style issues
   - Ensure file structure is correct
4. Push the fix and verify CI passes
5. Once CI passes, the PR can be merged

"@
    }

    $issuesSummary += "`n**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

    # Append to wave file
    Add-Content -Path $WaveFile -Value $issuesSummary -Encoding UTF8
    Write-Host "  [OK] Appended $($unresolvedData.issues.Count) issue(s) as actionable prompts"
} else {
    Write-Host "  [INFO] No unresolved issues to append"
}

Write-Host ""

# ============ CLEANUP 5: Remove completed phase details from AUTOPACK_WORKFLOW.md ============
Write-Host "CLEANUP 5: Removing completed phase details from AUTOPACK_WORKFLOW.md" -ForegroundColor Yellow

$workflowFile = Join-Path $backupDir "AUTOPACK_WORKFLOW.md"

if (Test-Path $workflowFile) {
    $workflowContent = Get-Content $workflowFile -Raw

    $removedSections = 0
    foreach ($prompt in $completedPrompts) {
        $phaseId = $prompt.ID

        # Map phaseId to IMP identifier pattern
        # e.g., "sec001" -> "IMP-SEC-001", "feat003" -> "IMP-FEAT-003"
        $impId = $phaseId -replace '([a-z]+)(\d+)', 'IMP-$1-$2'
        $impId = $impId.ToUpper()

        Write-Host "  [DEBUG] Looking for $impId in WORKFLOW..."

        # Try multiple patterns to match different workflow formats
        # Pattern 1: ## 🔵 WAVE N: Cursor #X ([IMP-XXX-NNN] Title) ... until next ## or ---
        $pattern1 = "(?s)##[^\r\n]*\[?$impId\]?[^\r\n]*\r?\n.*?(?=\r?\n##|\r?\n---|\Z)"

        # Pattern 2: Just look for the IMP ID in a header and remove that section
        $pattern2 = "(?s)##[^\r\n]*$impId[^\r\n]*\r?\n.*?(?=\r?\n##[^#]|\r?\n---|\Z)"

        $beforeLen = $workflowContent.Length
        $workflowContent = $workflowContent -replace $pattern1, ""

        if ($workflowContent.Length -eq $beforeLen) {
            # Pattern 1 didn't match, try pattern 2
            $workflowContent = $workflowContent -replace $pattern2, ""
        }

        if ($workflowContent.Length -lt $beforeLen) {
            $removedSections++
            Write-Host "  [OK] Removed section for $phaseId ($impId)"
        }
    }

    # Clean up multiple consecutive "---" separators and blank lines
    $workflowContent = $workflowContent -replace '(\r?\n---\s*){2,}', "`n---`n"
    $workflowContent = $workflowContent -replace '(\r?\n){3,}', "`n`n"

    if ($removedSections -gt 0) {
        Set-Content $workflowFile $workflowContent -Encoding UTF8
        Write-Host "  [OK] Removed $removedSections phase section(s) from AUTOPACK_WORKFLOW.md"
    } else {
        Write-Host "  [INFO] No matching sections found to remove (checked $($completedPrompts.Count) phases)"
    }
} else {
    Write-Host "  [WARN] AUTOPACK_WORKFLOW.md not found (skipping)"
}

Write-Host ""

# ============ Final Summary ============
Write-Host "============ CLEANUP COMPLETE ============" -ForegroundColor Green
Write-Host ""
Write-Host "Files cleaned:"
Write-Host "  [OK] Prompts_All_Waves.md"
Write-Host "  [OK] AUTOPACK_IMPS_MASTER.json"
Write-Host "  [OK] AUTOPACK_WAVE_PLAN.json"
Write-Host "  [OK] AUTOPACK_WORKFLOW.md"
if ($null -ne $unresolvedData -and $unresolvedData.issues.Count -gt 0) {
    Write-Host "  [OK] Unresolved issues appended to Prompts_All_Waves.md"
}
Write-Host ""
Write-Host "Completed phases removed: $($completedPrompts.Count)"
if ($null -ne $unresolvedData -and $unresolvedData.issues.Count -gt 0) {
    Write-Host "Unresolved issues documented: $($unresolvedData.issues.Count)"
}
Write-Host ""

# Reload and display new status
$promptsAfter = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile
$readyAfter = @($promptsAfter | Where-Object { $_.Status -eq "READY" }).Count
$unresolvedAfter = @($promptsAfter | Where-Object { $_.Status -eq "UNRESOLVED" }).Count
$pendingAfter = @($promptsAfter | Where-Object { $_.Status -eq "PENDING" }).Count

Write-Host "Remaining phases: $readyAfter READY | $unresolvedAfter UNRESOLVED | $pendingAfter PENDING | 0 COMPLETED"
Write-Host ""

if ($pendingAfter -gt 0) {
    Write-Host "[INFO] Wave $WaveNumber still has $pendingAfter [PENDING] phase(s)"
    Write-Host "[INFO] Wait for PRs to merge, then use Button 2 again"
} elseif ($readyAfter -gt 0) {
    Write-Host "[INFO] Wave $WaveNumber has $readyAfter [READY] phase(s) remaining"
    Write-Host "[INFO] Use Button 2 to continue filling slots"
} else {
    Write-Host "[OK] Wave $WaveNumber complete!"
    Write-Host "[INFO] Ready for Wave $($WaveNumber + 1)"
    Write-Host "[INFO] Use Button 1 to generate Wave $($WaveNumber + 1) prompts"
}

Write-Host ""
