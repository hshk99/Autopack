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
        $data = Get-Content $filePath -Raw | ConvertFrom-Json
        # Check both old format (issues) and new format (failureGroups)
        $hasOldFormat = ($null -ne $data.issues -and $data.issues.Count -gt 0)
        $hasNewFormat = ($null -ne $data.failureGroups -and $data.failureGroups.Count -gt 0)
        if ($hasOldFormat -or $hasNewFormat) {
            return $data
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

        # Auto-detect wave number from file content (look for "# Wave N" header)
        if ($WaveNumber -eq 0) {
            $fileContent = Get-Content $promptsFile -Raw
            if ($fileContent -match '# Wave (\d+)') {
                $WaveNumber = [int]$Matches[1]
                Write-Host "[AUTO-DETECT] Wave number: $WaveNumber"
            } else {
                # Default to wave 1 if not found
                $WaveNumber = 1
                Write-Host "[AUTO-DETECT] Wave number defaulting to: $WaveNumber"
            }
        }
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

# Check for unresolved issues that need to be appended
$unresolvedData = Get-UnresolvedIssuesSummary $WaveNumber
# Check both old format (issues) and new format (failureGroups)
$hasUnresolvedToAppend = ($null -ne $unresolvedData -and (
    ($null -ne $unresolvedData.issues -and $unresolvedData.issues.Count -gt 0) -or
    ($null -ne $unresolvedData.failureGroups -and $unresolvedData.failureGroups.Count -gt 0)
))

if ($completedPrompts.Count -eq 0 -and -not $hasUnresolvedToAppend) {
    Write-Host "[INFO] No [COMPLETED] phases found"
    Write-Host "[INFO] No unresolved issues to append"
    Write-Host "[INFO] Nothing to cleanup"
    exit 0
}

if ($completedPrompts.Count -gt 0) {
    Write-Host "[OK] Found $($completedPrompts.Count) [COMPLETED] phase(s)"
} else {
    Write-Host "[INFO] No [COMPLETED] phases found"
}
if ($hasUnresolvedToAppend) {
    Write-Host "[OK] Found $($unresolvedData.issues.Count) unresolved issue(s) to append"
}
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

# Helper function to get human-readable title for failure type
function Get-FailureTypeTitle {
    param([string]$FailureType)
    switch ($FailureType) {
        "core-tests" { return "Core Tests Failure" }
        "codeql" { return "CodeQL Security Scan Failure" }
        "lint-verify-structure" { return "Lint and Verify-Structure Failure" }
        "verify-structure" { return "Verify-Structure Failure" }
        "lint" { return "Lint Failure" }
        default { return "CI Failure" }
    }
}

# $unresolvedData already loaded at start of script
# Support both old format (issues array) and new format (failureGroups array)
$hasNewFormat = ($null -ne $unresolvedData.failureGroups -and $unresolvedData.failureGroups.Count -gt 0)
$hasOldFormat = ($null -ne $unresolvedData.issues -and $unresolvedData.issues.Count -gt 0)
$hasUnresolvedToAppend = $hasNewFormat -or $hasOldFormat

if ($hasUnresolvedToAppend) {
    if ($hasNewFormat) {
        $totalPhases = ($unresolvedData.failureGroups | ForEach-Object { $_.affectedPhases.Count } | Measure-Object -Sum).Sum
        Write-Host "  [INFO] Found $($unresolvedData.failureGroups.Count) failure group(s) affecting $totalPhases phase(s)"
    } else {
        Write-Host "  [INFO] Found $($unresolvedData.issues.Count) unresolved issue(s) (old format)"
    }

    # First, remove any existing "Unresolved Issues" sections to avoid duplicates
    $currentContent = Get-Content $WaveFile -Raw

    # Remove everything from "## Unresolved Issues" to end of file
    # This includes all [UNRESOLVED] phases that come after it
    $unresolvedSectionPattern = '(?s)\r?\n---\s*\r?\n+## Unresolved Issues \(Wave \d+\).*$'
    $currentContent = $currentContent -replace $unresolvedSectionPattern, ''

    # Also remove any standalone [UNRESOLVED] phase sections that might be scattered
    $unresolvedPhasePattern = '(?s)\r?\n---\s*\r?\n+## Phase: [^\]]+\[UNRESOLVED\].*?(?=\r?\n---\s*\r?\n+## Phase:|\Z)'
    $currentContent = $currentContent -replace $unresolvedPhasePattern, ''

    # Clean up multiple consecutive separators and blank lines
    $currentContent = $currentContent -replace '(\r?\n---\s*){2,}', "`n---`n"
    $currentContent = $currentContent -replace '(\r?\n){3,}', "`n`n"
    $currentContent = $currentContent.TrimEnd()

    # Write cleaned content back
    Set-Content $WaveFile $currentContent -Encoding UTF8
    Write-Host "  [OK] Removed any existing Unresolved Issues sections to avoid duplicates"

    # Re-read prompts after cleaning to get fresh list
    $prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile

    # Get existing phase IDs to avoid duplicates (only count READY/PENDING/COMPLETED phases)
    $existingPhaseIds = @($prompts | Where-Object { $_.Status -ne "UNRESOLVED" } | ForEach-Object { $_.ID })

    # Create unresolved issues section header
    $issuesSummary = @"

---

## Unresolved Issues (Wave $WaveNumber)

**Summary**: CI failures grouped by type. Similar failures are consolidated into a single fix PR.

"@

    $appendedCount = 0

    # Handle NEW FORMAT: failureGroups (grouped by failure type)
    if ($hasNewFormat) {
        foreach ($group in $unresolvedData.failureGroups) {
            $failureType = $group.failureType
            $description = $group.description
            $affectedPhases = @($group.affectedPhases)

            # SPECIAL CASE: core-tests failures should NOT be here
            # They should be fixed on the SAME branch, not a new PR
            # Skip them and warn - they shouldn't have been recorded as unresolved
            if ($failureType -eq "core-tests") {
                Write-Host "  [WARN] Skipping 'core-tests' failures - these should be fixed on the original branch"
                Write-Host "  [INFO] Core Tests failures for phases: $(($affectedPhases | ForEach-Object { $_.phaseId }) -join ', ')"
                Write-Host "  [INFO] Fix by pushing to the original PR, not creating a new PR"
                continue
            }

            # Filter out phases that already exist as READY/PENDING/COMPLETED
            $phasesToInclude = @($affectedPhases | Where-Object { $_.phaseId -notin $existingPhaseIds })

            if ($phasesToInclude.Count -eq 0) {
                Write-Host "  [SKIP] All phases in '$failureType' group already exist as active phases"
                continue
            }

            $failureTitle = Get-FailureTypeTitle $failureType
            $prList = ($phasesToInclude | ForEach-Object { "#$($_.prNumber)" }) -join ", "
            $phaseList = ($phasesToInclude | ForEach-Object { $_.phaseId }) -join ", "

            # Work from main repo for consolidated fixes
            $worktreePath = "C:\dev\Autopack"
            $fixBranchName = "wave${WaveNumber}/fix-${failureType}"

            # Create consolidated prompt for this failure type
            # Use a synthetic phaseId for the group (for manage_prompt_state.ps1 regex matching)
            $groupPhaseId = "fix-${failureType}"

            $issuesSummary += @"

---

## Phase: $groupPhaseId [UNRESOLVED]

**Title**: $failureTitle (Affects $($phasesToInclude.Count) PRs)
**Path**: $worktreePath

I'm working in: $worktreePath
Branch: $fixBranchName

**CONSOLIDATED FIX**: This single PR will fix the same issue across multiple original PRs.

**Affected PRs**: $prList
**Affected Phases**: $phaseList

Task: Create ONE PR to fix the "$failureType" failure affecting all listed PRs

The CI runs failed with: $description

Please investigate and fix the issue:

1. First, sync with main branch:
   ``````
   cd $worktreePath
   git fetch origin main
   git checkout main
   git pull origin main
   ``````

2. Create a consolidated fix branch:
   ``````
   git checkout -b $fixBranchName
   ``````

3. Check the CI logs for any of the affected PRs ($prList) to identify the specific failure

4. Fix the root cause:
   - For "lint" failure: Run linter locally, fix formatting issues
   - For "verify-structure" failure: Ensure file structure matches expected layout
   - For "CodeQL" failure: Address security findings in the code

5. Commit and push to create ONE consolidated PR:
   ``````
   git add .
   git commit -m "fix: Resolve $failureType failure affecting PRs $prList"
   git push -u origin $fixBranchName
   ``````

6. Create the PR with title: "fix: Resolve $failureType failure"
   - In the PR description, list all affected original PRs
   - Verify CI passes on this fix PR

"@
            $appendedCount++
            Write-Host "  [OK] Added consolidated prompt for '$failureType' ($($phasesToInclude.Count) phases)"
        }
    }
    # Handle OLD FORMAT: issues array (per-phase, for backwards compatibility)
    elseif ($hasOldFormat) {
        Write-Host "  [INFO] Processing old format - will be migrated on next check_pr_status run"

        # Group old issues by failure type for consolidated prompts
        $groupedIssues = @{}
        foreach ($issue in $unresolvedData.issues) {
            $desc = $issue.issue.ToLower()
            $category = "other"

            if ($desc -match "core tests") { $category = "core-tests" }
            elseif ($desc -match "codeql") { $category = "codeql" }
            elseif ($desc -match "lint" -and $desc -match "verify-structure") { $category = "lint-verify-structure" }
            elseif ($desc -match "verify-structure") { $category = "verify-structure" }
            elseif ($desc -match "lint") { $category = "lint" }

            if (-not $groupedIssues.ContainsKey($category)) {
                $groupedIssues[$category] = @{
                    description = $issue.issue
                    phases = @()
                }
            }
            $groupedIssues[$category].phases += $issue
        }

        foreach ($category in $groupedIssues.Keys) {
            # SPECIAL CASE: core-tests failures should NOT be here
            # They should be fixed on the SAME branch, not a new PR
            if ($category -eq "core-tests") {
                $coreTestPhases = $groupedIssues[$category].phases
                Write-Host "  [WARN] Skipping 'core-tests' failures - these should be fixed on the original branch"
                Write-Host "  [INFO] Core Tests failures for phases: $(($coreTestPhases | ForEach-Object { $_.phaseId }) -join ', ')"
                Write-Host "  [INFO] Fix by pushing to the original PR, not creating a new PR"
                continue
            }

            $groupData = $groupedIssues[$category]
            $phasesToInclude = @($groupData.phases | Where-Object { $_.phaseId -notin $existingPhaseIds })

            if ($phasesToInclude.Count -eq 0) {
                continue
            }

            $failureTitle = Get-FailureTypeTitle $category
            $prList = ($phasesToInclude | ForEach-Object { "#$($_.prNumber)" }) -join ", "
            $phaseList = ($phasesToInclude | ForEach-Object { $_.phaseId }) -join ", "
            $worktreePath = "C:\dev\Autopack"
            $fixBranchName = "wave${WaveNumber}/fix-${category}"
            $groupPhaseId = "fix-${category}"

            $issuesSummary += @"

---

## Phase: $groupPhaseId [UNRESOLVED]

**Title**: $failureTitle (Affects $($phasesToInclude.Count) PRs)
**Path**: $worktreePath

I'm working in: $worktreePath
Branch: $fixBranchName

**CONSOLIDATED FIX**: This single PR will fix the same issue across multiple original PRs.

**Affected PRs**: $prList
**Affected Phases**: $phaseList

Task: Create ONE PR to fix the "$category" failure affecting all listed PRs

The CI runs failed with: $($groupData.description)

Please investigate and fix the issue:

1. First, sync with main branch:
   ``````
   cd $worktreePath
   git fetch origin main
   git checkout main
   git pull origin main
   ``````

2. Create a consolidated fix branch:
   ``````
   git checkout -b $fixBranchName
   ``````

3. Check the CI logs for any of the affected PRs ($prList) to identify the specific failure

4. Fix the root cause:
   - For "lint" failure: Run linter locally, fix formatting issues
   - For "verify-structure" failure: Ensure file structure matches expected layout
   - For "CodeQL" failure: Address security findings in the code

5. Commit and push to create ONE consolidated PR:
   ``````
   git add .
   git commit -m "fix: Resolve $category failure affecting PRs $prList"
   git push -u origin $fixBranchName
   ``````

6. Create the PR with title: "fix: Resolve $category failure"
   - In the PR description, list all affected original PRs
   - Verify CI passes on this fix PR

"@
            $appendedCount++
            Write-Host "  [OK] Added consolidated prompt for '$category' ($($phasesToInclude.Count) phases)"
        }
    }

    if ($appendedCount -gt 0) {
        $issuesSummary += "`n**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

        # Append to wave file
        Add-Content -Path $WaveFile -Value $issuesSummary -Encoding UTF8
        Write-Host "  [OK] Appended $appendedCount consolidated prompt(s)"
    } else {
        Write-Host "  [INFO] All unresolved issues already exist or were duplicates"
    }
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
