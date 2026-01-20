# Reset ALL [PENDING] phases back to [READY] or [UNRESOLVED] for re-running Button 2
# Usage: .\reset_all_pending_phases.ps1
# This marks phases as READY/UNRESOLVED (not started) so you can re-run Button 2

param(
    [string]$WaveFile = "",
    [ValidateSet("READY", "UNRESOLVED")]
    [string]$TargetStatus = "READY"  # Default to READY, can also use UNRESOLVED
)

if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"

    # First try Prompts_All_Waves.md (new format)
    $promptsFile = Join-Path $backupDir "Prompts_All_Waves.md"
    if (Test-Path $promptsFile) {
        $WaveFile = $promptsFile
        Write-Host "[AUTO-DETECT] Using: Prompts_All_Waves.md"
    } else {
        # Fallback to old Wave*_All_Phases.md format
        $waveFiles = @(Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)

        if ($waveFiles.Count -gt 0) {
            $WaveFile = $waveFiles[0].FullName
            Write-Host "[AUTO-DETECT] Using: $($waveFiles[0].Name) (legacy format)"
        } else {
            Write-Host "[ERROR] No Prompts_All_Waves.md or Wave*_All_Phases.md file found" -ForegroundColor Red
            exit 1
        }
    }
}

if (-not (Test-Path $WaveFile)) {
    Write-Host "[ERROR] Wave file not found: $WaveFile" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============ RESET ALL PENDING PHASES ============" -ForegroundColor Yellow
Write-Host ""

# Load current state (filter strings)
$prompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })

$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" })

if ($pendingPrompts.Count -eq 0) {
    Write-Host "[INFO] No [PENDING] phases found"
    Write-Host "[INFO] Nothing to reset"
    exit 0
}

Write-Host "[OK] Found $($pendingPrompts.Count) [PENDING] phase(s) to reset"
Write-Host ""

# Reset each pending phase to target status (READY or UNRESOLVED)
$resetCount = 0
foreach ($phase in $pendingPrompts) {
    $phaseId = $phase.ID
    Write-Host "Resetting $phaseId..."

    & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus $TargetStatus | Out-Null

    if ($?) {
        $resetCount++
        Write-Host "  ✅ $phaseId → [$TargetStatus]"
    } else {
        Write-Host "  ❌ Failed to reset $phaseId" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============ RESET COMPLETE ============" -ForegroundColor Green
Write-Host ""
Write-Host "Reset $resetCount phases from [PENDING] → [$TargetStatus]"
Write-Host ""

# Update the header counts in the file
Write-Host "[ACTION] Updating header counts..."
$content = Get-Content $WaveFile -Raw

# CLEANUP: Remove any orphaned content between header and first ## section
# This fixes malformed files where prompt content exists before the first ## Phase: or ## Unresolved header
$orphanedContentPattern = '(?s)(# Wave \d+\s*\r?\n+READY: \d+.*?UNRESOLVED: \d+\s*\r?\n+)---\s*\r?\n.*?(?=## )'
if ($content -match $orphanedContentPattern) {
    Write-Host "  [FIX] Removing orphaned content between header and first section"
    $content = $content -replace $orphanedContentPattern, '$1'
}

# Count actual statuses in the file
$readyCount = ([regex]::Matches($content, '## Phase: \S+ \[READY\]')).Count
$unresolvedCount = ([regex]::Matches($content, '## Phase: \S+ \[UNRESOLVED\]')).Count
$pendingCount = ([regex]::Matches($content, '## Phase: \S+ \[PENDING\]')).Count
$completedCount = ([regex]::Matches($content, '## Phase: \S+ \[COMPLETED\]')).Count

# Update the header line - try multiple formats
# Format 1 (current): "READY: 70 | PENDING: 0 | COMPLETED: 0 | UNIMPLEMENTED: 0"
$headerPattern1 = 'READY: \d+ \| PENDING: \d+ \| COMPLETED: \d+ \| UNIMPLEMENTED: \d+'
$headerReplacement1 = "READY: $readyCount | PENDING: $pendingCount | COMPLETED: $completedCount | UNIMPLEMENTED: $unresolvedCount"
$newContent = $content -replace $headerPattern1, $headerReplacement1

# Format 2 (old comma style): "READY: X, PENDING: Y, COMPLETED: Z, UNRESOLVED: W"
$headerPattern2 = 'READY: \d+, PENDING: \d+, COMPLETED: \d+, UNRESOLVED: \d+'
$headerReplacement2 = "READY: $readyCount, PENDING: $pendingCount, COMPLETED: $completedCount, UNRESOLVED: $unresolvedCount"
$newContent = $newContent -replace $headerPattern2, $headerReplacement2

# Also update "Last Updated" field if present
$datePattern = '\*\*Last Updated\*\*: [^\n]+'
$dateReplacement = "**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$newContent = $newContent -replace $datePattern, $dateReplacement

Set-Content $WaveFile $newContent -Encoding UTF8
Write-Host "[OK] Header counts updated"
Write-Host ""

# Reload and display new status (filter strings)
$promptsAfter = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })
$readyAfter = @($promptsAfter | Where-Object { $_.Status -eq "READY" }).Count
$unresolvedAfter = @($promptsAfter | Where-Object { $_.Status -eq "UNRESOLVED" }).Count
$pendingAfter = @($promptsAfter | Where-Object { $_.Status -eq "PENDING" }).Count
$completedAfter = @($promptsAfter | Where-Object { $_.Status -eq "COMPLETED" }).Count

Write-Host "New status: $readyAfter READY | $unresolvedAfter UNRESOLVED | $pendingAfter PENDING | $completedAfter COMPLETED"
Write-Host ""
Write-Host "[INFO] You can now run Button 2 to re-fill the slots"
Write-Host ""
