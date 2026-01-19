# Manage prompt state (load, save, update status)
# Tracks prompt status: [READY], [PENDING], [COMPLETED]
# Stores state in Wave[N]_All_Phases.md file
# Usage: .\manage_prompt_state.ps1 -Action Load -WaveFile "Wave1_All_Phases.md"

param(
    [ValidateSet("Load", "Save", "Update")]
    [string]$Action = "Load",
    [string]$WaveFile = "",
    [string]$PhaseId = "",
    [string]$NewStatus = ""  # [READY], [PENDING], [COMPLETED]
)

# Determine wave file if not provided
if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
    $waveFiles = @(Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)

    if ($waveFiles.Count -gt 0) {
        $WaveFile = $waveFiles[0].FullName
        Write-Host "[AUTO-DETECT] Using: $($waveFiles[0].Name)"
    } else {
        Write-Host "[ERROR] No Wave*_All_Phases.md file found" -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path $WaveFile)) {
    Write-Host "[ERROR] Wave file not found: $WaveFile" -ForegroundColor Red
    exit 1
}

# ============ LOAD ACTION ============
if ($Action -eq "Load") {
    Write-Host "[INFO] Loading prompt state from: $WaveFile"

    $content = Get-Content $WaveFile -Raw

    # Extract all phases with their status, path, and branch name
    # Pattern: ## Phase: <id> [<status>] ... **Path**: <path> ... Branch: <branch>
    $phasePattern = "## Phase: (\S+) \[(READY|PENDING|COMPLETED|UNIMPLEMENTED)\].*?\*\*Path\*\*: (.+?)(?=\n|`n).*?Branch: (\S+)"
    $matches = [regex]::Matches($content, $phasePattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)

    $phases = @()
    foreach ($match in $matches) {
        $phaseId = $match.Groups[1].Value
        $status = $match.Groups[2].Value
        $path = $match.Groups[3].Value.Trim()
        $branch = $match.Groups[4].Value.Trim()

        $phases += @{
            ID = $phaseId
            Status = $status
            Path = $path
            Branch = $branch
        }
    }

    Write-Host "[OK] Loaded $($phases.Count) phases"

    # Count statuses
    $readyCount = ($phases | Where-Object { $_.Status -eq "READY" }).Count
    $pendingCount = ($phases | Where-Object { $_.Status -eq "PENDING" }).Count
    $completedCount = ($phases | Where-Object { $_.Status -eq "COMPLETED" }).Count

    Write-Host "Status: $readyCount READY | $pendingCount PENDING | $completedCount COMPLETED"

    # Return as objects for pipeline
    $phases
}

# ============ UPDATE ACTION ============
elseif ($Action -eq "Update") {
    if ([string]::IsNullOrWhiteSpace($PhaseId) -or [string]::IsNullOrWhiteSpace($NewStatus)) {
        Write-Host "[ERROR] Update requires -PhaseId and -NewStatus parameters" -ForegroundColor Red
        exit 1
    }

    if ($NewStatus -notmatch "READY|PENDING|COMPLETED|UNIMPLEMENTED") {
        Write-Host "[ERROR] Status must be [READY], [PENDING], [COMPLETED], or [UNIMPLEMENTED]" -ForegroundColor Red
        exit 1
    }

    Write-Host "[INFO] Updating $PhaseId to [$NewStatus]"

    $content = Get-Content $WaveFile -Raw

    # Find and replace phase status
    $oldPattern = "## Phase: $PhaseId \[(READY|PENDING|COMPLETED|UNIMPLEMENTED)\]"
    $newText = "## Phase: $PhaseId [$NewStatus]"

    $newContent = $content -replace $oldPattern, $newText

    if ($newContent -eq $content) {
        Write-Host "[ERROR] Phase $PhaseId not found or already has status [$NewStatus]" -ForegroundColor Red
        exit 1
    }

    # Update header status counts
    $readyCount = ([regex]::Matches($newContent, '\[READY').Count)
    $pendingCount = ([regex]::Matches($newContent, '\[PENDING').Count)
    $completedCount = ([regex]::Matches($newContent, '\[COMPLETED').Count)
    $unimplementedCount = ([regex]::Matches($newContent, '\[UNIMPLEMENTED').Count)

    # Try both header formats (old and new style)
    $headerPattern1 = 'READY: \d+, PENDING: \d+, COMPLETED: \d+, UNIMPLEMENTED: \d+'
    $headerReplacement1 = "READY: $readyCount, PENDING: $pendingCount, COMPLETED: $completedCount, UNIMPLEMENTED: $unimplementedCount"
    $newContent = $newContent -replace $headerPattern1, $headerReplacement1

    # Also try alternate format if present
    $headerPattern2 = '\*\*Status\*\*: \d+ READY \| \d+ PENDING \| \d+ COMPLETED'
    $headerReplacement2 = "**Status**: $readyCount READY | $pendingCount PENDING | $completedCount COMPLETED"
    $newContent = $newContent -replace $headerPattern2, $headerReplacement2

    # Also update "Last Updated" field
    $datePattern = '\*\*Last Updated\*\*: [^\n]+'
    $dateReplacement = "**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

    $newContent = $newContent -replace $datePattern, $dateReplacement

    Set-Content $WaveFile $newContent -Encoding UTF8

    Write-Host "[OK] Updated $PhaseId to [$NewStatus]"
    Write-Host "Status: $readyCount READY | $pendingCount PENDING | $completedCount COMPLETED"
}

# ============ SAVE ACTION ============
elseif ($Action -eq "Save") {
    Write-Host "[INFO] Save action requires -WaveFile parameter (saves current state)"
    Write-Host "Current workflow uses automatic saves via Update action"
}
