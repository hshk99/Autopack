# Reset phase status back to READY or UNIMPLEMENTED for testing
# Useful for reverting failed test runs before retrying
# Usage: .\reset_phase_status.ps1 -PhaseId "sec001" -NewStatus "READY"

param(
    [string]$PhaseId = "",
    [string]$NewStatus = "READY",  # READY or UNIMPLEMENTED
    [string]$WaveFile = ""
)

if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
    $promptsFile = Join-Path $backupDir "Prompts_All_Waves.md"

    if (Test-Path $promptsFile) {
        $WaveFile = $promptsFile
        Write-Host "[AUTO-DETECT] Using: Prompts_All_Waves.md"
    } else {
        # Fallback to old Wave*_All_Phases.md format for backwards compatibility
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
Write-Host "============ RESET PHASE STATUS ============" -ForegroundColor Yellow
Write-Host ""

if ([string]::IsNullOrWhiteSpace($PhaseId)) {
    # Interactive mode - show all phases and let user choose
    Write-Host "Available phases to reset:"
    Write-Host ""

    $content = Get-Content $WaveFile -Raw
    $phaseMatches = [regex]::Matches($content, "## Phase: (\S+) \[(READY|UNRESOLVED|PENDING|COMPLETED|UNIMPLEMENTED)\]")

    $phases = @()
    foreach ($match in $phaseMatches) {
        $id = $match.Groups[1].Value
        $status = $match.Groups[2].Value
        $phases += @{ ID = $id; Status = $status }
        Write-Host "  $id [$status]"
    }

    Write-Host ""
    Write-Host "Usage: .\reset_phase_status.ps1 -PhaseId ""sec001"" -NewStatus ""READY"""
    exit 0
}

# Single phase reset
Write-Host "Resetting phase: $PhaseId"
Write-Host "New status: $NewStatus"
Write-Host ""

$content = Get-Content $WaveFile -Raw

# Find current status
if ($content -match "## Phase: $PhaseId \[(READY|UNRESOLVED|PENDING|COMPLETED|UNIMPLEMENTED)\]") {
    $currentStatus = $Matches[1]
    Write-Host "Current status: $currentStatus"

    # SAFETY CHECK: Prevent resetting [COMPLETED] phases
    if ($currentStatus -eq "COMPLETED") {
        Write-Host "[ERROR] Cannot reset [COMPLETED] phases - they are locked" -ForegroundColor Red
        Write-Host "[INFO] Only [READY] and [PENDING] phases can be reset for testing"
        exit 1
    }

    if ($currentStatus -eq $NewStatus) {
        Write-Host "[INFO] Phase already has status [$NewStatus]"
        exit 0
    }

    # Replace status
    $oldPattern = "## Phase: $PhaseId \[.*?\]"
    $newText = "## Phase: $PhaseId [$NewStatus]"

    $newContent = $content -replace $oldPattern, $newText

    # Write back
    Set-Content $WaveFile $newContent -Encoding UTF8

    Write-Host "[OK] Phase reset: $currentStatus → $NewStatus"

    # Update header counts
    $readyCount = ([regex]::Matches($newContent, '\[READY\]').Count)
    $unresolvedCount = ([regex]::Matches($newContent, '\[UNRESOLVED\]').Count)
    $pendingCount = ([regex]::Matches($newContent, '\[PENDING\]').Count)
    $completedCount = ([regex]::Matches($newContent, '\[COMPLETED\]').Count)

    Write-Host ""
    Write-Host "Updated status: $readyCount READY | $unresolvedCount UNRESOLVED | $pendingCount PENDING | $completedCount COMPLETED"

} else {
    Write-Host "[ERROR] Phase $PhaseId not found" -ForegroundColor Red
    exit 1
}

Write-Host ""
