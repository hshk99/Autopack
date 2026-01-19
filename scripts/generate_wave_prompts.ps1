param(
    [int]$WaveNumber = 0,
    [string]$WorkflowFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_WORKFLOW.md",
    [switch]$Preserve  # Preserve existing statuses instead of resetting to [READY] (default: reset to READY)
)

if ($WaveNumber -eq 0) {
    Write-Host ""
    Write-Host "============ GENERATE WAVE PROMPTS ============" -ForegroundColor Cyan
    Write-Host ""
    $input_wave = Read-Host "Enter Wave number (1-6)"
    if (-not [int]::TryParse($input_wave, [ref]$WaveNumber)) {
        Write-Host "[ERROR] Invalid input" -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path $WorkflowFile)) {
    Write-Host "[ERROR] Workflow file not found" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Reading workflow..."
$content = Get-Content $WorkflowFile -Raw

$prompts = @()
$phasePattern = '## .*?WAVE ' + $WaveNumber + '\s*:.*?(?===|##|\Z)'
$phaseMatches = [regex]::Matches($content, $phasePattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)

Write-Host "[INFO] Found $($phaseMatches.Count) phases"

foreach ($phaseMatch in $phaseMatches) {
    $phaseSection = $phaseMatch.Value

    $headerMatch = [regex]::Match($phaseSection, 'WAVE ' + $WaveNumber + '.*?\(([^)]+)\)')
    if (-not $headerMatch.Success) { continue }
    $phaseTitle = $headerMatch.Groups[1].Value

    $folderMatch = [regex]::Match($phaseSection, 'I''m working in git worktree: (C:[\\]{1,2}dev[\\]{1,2}Autopack_w' + $WaveNumber + '_[A-Za-z0-9_-]+)')
    if (-not $folderMatch.Success) { continue }

    $folderPath = $folderMatch.Groups[1].Value
    $folderName = [System.IO.Path]::GetFileName($folderPath)
    $phaseId = $folderName -replace '^Autopack_w\d+_', ''

    $promptMatch = [regex]::Match($phaseSection, '\*\*Cursor Prompt:\*\*.*?```(.*?)```', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $promptText = if ($promptMatch.Success) { $promptMatch.Groups[1].Value.Trim() } else { "" }

    # Extract branch name from prompt (usually formatted as "Branch: wave1/...")
    $branchMatch = [regex]::Match($promptText, 'Branch:\s*([^\r\n]+)')
    $branchName = if ($branchMatch.Success) { $branchMatch.Groups[1].Value.Trim() } else { "" }

    if (-not (Test-Path $folderPath)) {
        New-Item -ItemType Directory -Path $folderPath -Force | Out-Null
        Write-Host "Created: $folderPath"
    } else {
        Write-Host "Exists: $folderPath"
    }

    $prompts += @{
        ID = $phaseId
        Title = $phaseTitle
        Folder = $folderName
        Path = $folderPath
        Prompt = $promptText
        Branch = $branchName
    }
}

if ($prompts.Count -eq 0) {
    Write-Host "[ERROR] No phases found" -ForegroundColor Red
    exit 1
}

$outputFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\Wave${WaveNumber}_All_Phases.md"
$existingStatuses = @{}

if (Test-Path $outputFile) {
    Write-Host "Preserving existing statuses..."
    $existingContent = Get-Content $outputFile -Raw
    $statusPattern = "## Phase: (\S+) \[(READY|PENDING|COMPLETED|UNIMPLEMENTED)\]"
    $statusMatches = [regex]::Matches($existingContent, $statusPattern)

    foreach ($match in $statusMatches) {
        $phaseId = $match.Groups[1].Value
        $status = $match.Groups[2].Value
        $existingStatuses[$phaseId] = $status
    }
}

$readyCount = 0
$pendingCount = 0
$completedCount = 0
$unimplementedCount = 0

foreach ($prompt in $prompts) {
    if ($Preserve -and $existingStatuses.ContainsKey($prompt.ID)) {
        # Only preserve if -Preserve flag is set
        $status = $existingStatuses[$prompt.ID]
        switch ($status) {
            "READY" { $readyCount++ }
            "PENDING" { $pendingCount++ }
            "COMPLETED" { $completedCount++ }
            "UNIMPLEMENTED" { $unimplementedCount++ }
        }
    } else {
        # Default: reset all phases to READY
        $readyCount++
    }
}

$markdown = "# Wave $WaveNumber`n`n"
$markdown += "READY: $readyCount, PENDING: $pendingCount, COMPLETED: $completedCount, UNIMPLEMENTED: $unimplementedCount`n`n"
$markdown += "---`n`n"

for ($i = 0; $i -lt $prompts.Count; $i++) {
    $prompt = $prompts[$i]
    # Default: reset all to READY. Only preserve existing if -Preserve flag is set
    $status = if ($Preserve -and $existingStatuses.ContainsKey($prompt.ID)) { $existingStatuses[$prompt.ID] } else { "READY" }

    $markdown += "## Phase: $($prompt.ID) [$status]`n`n"
    $markdown += "**Title**: $($prompt.Title)`n"
    $markdown += "**Path**: $($prompt.Path)`n"
    if ($prompt.Branch) {
        $markdown += "**Branch**: $($prompt.Branch)`n"
    }
    $markdown += "`n$($prompt.Prompt)`n`n"
    $markdown += "---`n`n"
}

Set-Content $outputFile $markdown -Encoding UTF8

Write-Host ""
Write-Host "Generation Complete"
Write-Host "Wave: $WaveNumber"
Write-Host "Phases: $($prompts.Count)"
Write-Host "Status: READY=$readyCount PENDING=$pendingCount COMPLETED=$completedCount UNIMPLEMENTED=$unimplementedCount"
Write-Host ""
Write-Host "Output: $outputFile"
Write-Host ""
