# Wave Orchestrator v1.3 - Automates parallel Cursor execution for IMPs
# Usage: .\wave_orchestrator.ps1 -Wave 1 -WorkflowFile "C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_WORKFLOW.md" -StartCursor 9 -EndCursor 27
# Optional: -LaunchDelay 5 (seconds between window launches, default 5)
# Optional: -PromptOutputDir "C:\path\to\folder" (saves prompt .md files here with descriptive names)
#
# NOTE: Cursor model must be set manually in Cursor Settings > Models (Cursor stores this in SQLite, not settings.json)

param(
    [Parameter(Mandatory=$true)]
    [int]$Wave,

    [Parameter(Mandatory=$true)]
    [string]$WorkflowFile,

    [Parameter(Mandatory=$false)]
    [int]$StartCursor = 1,

    [Parameter(Mandatory=$false)]
    [int]$EndCursor = 999,

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [switch]$MonitorOnly,

    [Parameter(Mandatory=$false)]
    [switch]$GeneratePromptsOnly,

    [Parameter(Mandatory=$false)]
    [string]$RepoPath = "C:\dev\Autopack",

    [Parameter(Mandatory=$false)]
    [int]$LaunchDelay = 5,

    [Parameter(Mandatory=$false)]
    [string]$PromptOutputFile = ""
)

$ErrorActionPreference = "Stop"

# Auto-set PromptOutputFile to OneDrive Backup Desktop if not specified
if (-not $PromptOutputFile) {
    $PromptOutputFile = Join-Path $env:USERPROFILE "OneDrive\Backup\Desktop\Wave_Prompts.md"
}

# Global array for collecting prompts (initialized per run)
$global:ConsolidatedPrompts = @()

# Colors for output
function Write-Status { param($msg) Write-Host "[STATUS] $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

# Parse workflow file to extract cursor prompts for a specific wave
function Get-WaveCursors {
    param($WorkflowContent, $WaveNum)

    $cursors = @()

    # Try multiple pattern formats for robustness (match any emoji or text before WAVE)
    $patterns = @(
        "## .{1,4} WAVE $WaveNum`: Cursor #(\d+) \(([^)]+)\)",
        "## WAVE $WaveNum`: Cursor #(\d+) \(([^)]+)\)"
    )

    $allMatches = @()
    foreach ($pat in $patterns) {
        $regexMatches = [regex]::Matches($WorkflowContent, $pat)
        if ($regexMatches.Count -gt 0) {
            $allMatches = $regexMatches
            break
        }
    }

    foreach ($match in $allMatches) {
        $cursorNum = [int]$match.Groups[1].Value
        $impTitle = $match.Groups[2].Value

        # Extract the prompt block after this header
        $startIdx = $match.Index + $match.Length
        $endPattern = "---"
        $endIdx = $WorkflowContent.IndexOf($endPattern, $startIdx)

        if ($endIdx -gt $startIdx) {
            $section = $WorkflowContent.Substring($startIdx, $endIdx - $startIdx)

            # Extract worktree path
            $worktreeMatch = [regex]::Match($section, "git worktree: ([^\r\n]+)")
            $worktreePath = if ($worktreeMatch.Success) { $worktreeMatch.Groups[1].Value.Trim() } else { $null }

            # Extract branch name
            $branchMatch = [regex]::Match($section, "Branch: ([^\r\n]+)")
            $branchName = if ($branchMatch.Success) { $branchMatch.Groups[1].Value.Trim() } else { $null }

            # Extract the full prompt (between ``` markers)
            $promptMatch = [regex]::Match($section, '\*\*Cursor Prompt:\*\*\s*```([\s\S]*?)```')
            $prompt = if ($promptMatch.Success) { $promptMatch.Groups[1].Value.Trim() } else { $null }

            if ($worktreePath -and $branchName -and $prompt) {
                $cursors += @{
                    CursorNum = $cursorNum
                    ImpTitle = $impTitle
                    WorktreePath = $worktreePath
                    BranchName = $branchName
                    Prompt = $prompt
                }
            }
        }
    }

    return $cursors
}

# Check if PR already exists and is merged for a branch
function Test-PRMerged {
    param($BranchName)

    $result = gh pr list --state merged --head $BranchName --json number 2>$null
    if ($result) {
        $prs = $result | ConvertFrom-Json
        return $prs.Count -gt 0
    }
    return $false
}

# Check if PR exists (open or merged)
function Test-PRExists {
    param($BranchName)

    $result = gh pr list --state all --head $BranchName --json number,state 2>$null
    if ($result) {
        $prs = $result | ConvertFrom-Json
        return $prs.Count -gt 0
    }
    return $false
}

# Check if worktree already exists
function Test-WorktreeExists {
    param($WorktreePath)

    # Normalize path for comparison (git outputs C:/dev/... format)
    $normalizedPath = $WorktreePath -replace '\\', '/'

    $worktrees = git -C $RepoPath worktree list 2>$null
    foreach ($line in $worktrees) {
        # Extract just the path from the line (first column)
        $wtPath = ($line -split '\s+')[0]
        if ($wtPath -eq $normalizedPath) {
            return $true
        }
    }
    return $false
}

# Create worktree if it doesn't exist
function New-Worktree {
    param($WorktreePath, $BranchName)

    # Git worktree add accepts Windows paths directly, just convert backslashes
    $unixPath = $WorktreePath -replace '\\', '/'

    if (Test-WorktreeExists -WorktreePath $WorktreePath) {
        Write-Warn "Worktree already exists: $WorktreePath"
        return $true
    }

    Write-Status "Creating worktree: $WorktreePath -> $BranchName"

    if (-not $DryRun) {
        try {
            # Try to create new worktree with new branch
            $output = git -C $RepoPath worktree add $unixPath -b $BranchName 2>&1
            if ($LASTEXITCODE -ne 0) {
                # If branch exists, try to reuse it instead
                if ($output -match "already exists") {
                    Write-Status "Branch '$BranchName' already exists, reusing it"
                    $output = git -C $RepoPath worktree add $unixPath $BranchName 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        Write-Err "Failed to create worktree: $output"
                        return $false
                    }
                } else {
                    Write-Err "Failed to create worktree: $output"
                    return $false
                }
            }
            Write-Success "Created worktree: $WorktreePath"
            return $true
        } catch {
            Write-Err "Failed to create worktree: $_"
            return $false
        }
    } else {
        Write-Status "[DRY RUN] Would create worktree: $WorktreePath"
        return $true
    }
}

# Write prompt file to worktree (and optionally to output directory)
function Write-PromptFile {
    param($WorktreePath, $Prompt, $CursorNum, $BranchName, $ImpTitle)

    $promptFile = Join-Path $WorktreePath ".claude-prompt"

    if (-not $DryRun) {
        # Ensure directory exists with retry (git worktree may have sync delay)
        $maxRetries = 5
        $retryCount = 0
        while (-not (Test-Path $WorktreePath) -and $retryCount -lt $maxRetries) {
            $retryCount++
            Start-Sleep -Milliseconds 500
        }

        if (-not (Test-Path $WorktreePath)) {
            Write-Err "Worktree directory does not exist after retries: $WorktreePath"
            return $false
        }

        $Prompt | Out-File -FilePath $promptFile -Encoding UTF8
        Write-Success "Wrote prompt to: $promptFile"
        return $true
    } else {
        Write-Status "[DRY RUN] Would write prompt to: $promptFile"
        return $true
    }
}

# Collect prompts for consolidated file
function Collect-PromptForConsolidation {
    param($Prompt, $CursorNum, $BranchName, $ImpTitle)

    # Extract IMP ID from title (e.g., "IMP-SEC-001 - Protect API Key" -> "IMP-SEC-001")
    $impId = if ($ImpTitle -match "(IMP-[A-Z]+-\d+)") { $matches[1] } else { "UNKNOWN" }

    # Create title: "Cursor09 - wave1-safety-006-rollback-protected - IMP-SAFETY-006"
    $safeBranch = $BranchName -replace '[\\/:*?"<>|]', '-'
    $title = "Cursor{0:D2} - {1} - {2}" -f $CursorNum, $safeBranch, $impId

    $global:ConsolidatedPrompts += @{
        CursorNum = $CursorNum
        Title = $title
        Prompt = $Prompt
    }
}

# Write all collected prompts to a single consolidated .md file
function Write-ConsolidatedPromptsFile {
    if (-not $PromptOutputFile -or $global:ConsolidatedPrompts.Count -eq 0) {
        return $true
    }

    if (-not $DryRun) {
        # Ensure parent directory exists
        $parentDir = Split-Path -Parent $PromptOutputFile
        if (-not (Test-Path $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }

        # Sort by cursor number
        $sortedPrompts = $global:ConsolidatedPrompts | Sort-Object { [int]$_.CursorNum }

        # Build consolidated file content
        $content = @"
# Wave $Wave - Consolidated Cursor Prompts

**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
**Total Cursors**: $($sortedPrompts.Count)

---

"@

        foreach ($promptEntry in $sortedPrompts) {
            $content += @"
## $($promptEntry.Title)

$($promptEntry.Prompt)

---

"@
        }

        $content | Out-File -FilePath $PromptOutputFile -Encoding UTF8
        Write-Success "Wrote consolidated prompts to: $PromptOutputFile"
        return $true
    } else {
        Write-Status "[DRY RUN] Would write consolidated prompts to: $PromptOutputFile"
        return $true
    }
}

# Launch Cursor for a worktree
function Start-CursorInstance {
    param($WorktreePath, $CursorNum)

    Write-Status "Launching Cursor #$CursorNum for: $WorktreePath"

    if (-not $DryRun) {
        # Try to find Cursor executable
        $cursorPaths = @(
            "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe",
            "$env:PROGRAMFILES\Cursor\Cursor.exe",
            "cursor"  # If in PATH
        )

        $cursorExe = $null
        foreach ($path in $cursorPaths) {
            if ($path -eq "cursor" -or (Test-Path $path)) {
                $cursorExe = $path
                break
            }
        }

        if ($cursorExe) {
            Start-Process $cursorExe -ArgumentList $WorktreePath
            Write-Success "Launched Cursor #$CursorNum"
            return $true
        } else {
            Write-Warn "Cursor executable not found. Please open manually: $WorktreePath"
            return $false
        }
    } else {
        Write-Status "[DRY RUN] Would launch Cursor for: $WorktreePath"
        return $true
    }
}

# Monitor PR status for wave
function Watch-WavePRs {
    param($Cursors)

    Write-Status "Monitoring PRs for Wave $Wave..."
    Write-Status "Press Ctrl+C to stop monitoring"

    while ($true) {
        $allMerged = $true
        $summary = @()

        foreach ($cursor in $Cursors) {
            $branch = $cursor.BranchName

            # Check PR status
            $prResult = gh pr list --state all --head $branch --json number,state,title,mergeable,statusCheckRollup 2>$null

            if ($prResult) {
                $pr = ($prResult | ConvertFrom-Json) | Select-Object -First 1

                if ($pr) {
                    $status = $pr.state
                    $checks = "?"

                    if ($pr.statusCheckRollup) {
                        $pending = ($pr.statusCheckRollup | Where-Object { $_.status -eq "PENDING" }).Count
                        $failure = ($pr.statusCheckRollup | Where-Object { $_.conclusion -eq "FAILURE" }).Count

                        if ($failure -gt 0) { $checks = "[X] $failure failed" }
                        elseif ($pending -gt 0) { $checks = "[...] $pending pending" }
                        else { $checks = "[OK] All passed" }
                    }

                    $summary += "  #$($cursor.CursorNum) PR#$($pr.number): $status - $checks"

                    if ($status -ne "MERGED") { $allMerged = $false }
                } else {
                    $summary += "  #$($cursor.CursorNum) $branch - No PR found"
                    $allMerged = $false
                }
            } else {
                $summary += "  #$($cursor.CursorNum) $branch - No PR found"
                $allMerged = $false
            }
        }

        # Clear and print status
        Clear-Host
        Write-Host "=== Wave $Wave PR Monitor ===" -ForegroundColor Cyan
        Write-Host "Last updated: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Gray
        Write-Host ""
        $summary | ForEach-Object { Write-Host $_ }
        Write-Host ""

        if ($allMerged) {
            Write-Success "All PRs merged! Wave $Wave complete!"
            break
        }

        Write-Host "Refreshing in 30 seconds... (Ctrl+C to stop)" -ForegroundColor Gray
        Start-Sleep -Seconds 30
    }
}

# Main execution
function Main {
    # Reset consolidated prompts array for this run
    $global:ConsolidatedPrompts = @()

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "     WAVE ORCHESTRATOR v1.3            " -ForegroundColor Cyan
    Write-Host "     Launch Delay: ${LaunchDelay}s     " -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Warn "NOTE: Set Cursor model manually via Cursor Settings > Models"
    Write-Host ""

    # Validate inputs
    if (-not (Test-Path $WorkflowFile)) {
        Write-Err "Workflow file not found: $WorkflowFile"
        exit 1
    }

    if (-not (Test-Path $RepoPath)) {
        Write-Err "Repository not found: $RepoPath"
        exit 1
    }

    # Read workflow file
    Write-Status "Reading workflow file..."
    $workflowContent = Get-Content $WorkflowFile -Raw -Encoding UTF8

    # Parse cursors for the wave
    Write-Status "Parsing Wave $Wave cursors..."
    $cursors = Get-WaveCursors -WorkflowContent $workflowContent -WaveNum $Wave

    if ($cursors.Count -eq 0) {
        Write-Err "No cursors found for Wave $Wave"
        exit 1
    }

    Write-Success "Found $($cursors.Count) cursors for Wave $Wave"

    # Filter by cursor range
    $cursors = $cursors | Where-Object { $_.CursorNum -ge $StartCursor -and $_.CursorNum -le $EndCursor }
    $cursorCount = @($cursors).Count
    Write-Status "Processing cursors $StartCursor to $EndCursor ($cursorCount total)"

    if ($MonitorOnly) {
        Watch-WavePRs -Cursors $cursors
        return
    }

    if ($GeneratePromptsOnly) {
        Write-Status "Generating prompts only (skipping worktree creation and Cursor launches)..."
        foreach ($cursor in $cursors) {
            Collect-PromptForConsolidation -Prompt $cursor.Prompt -CursorNum $cursor.CursorNum -BranchName $cursor.BranchName -ImpTitle $cursor.ImpTitle
        }
        Write-ConsolidatedPromptsFile
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Success "Prompts generated: $($cursors.Count) cursors"
        Write-Host "Consolidated prompts: $PromptOutputFile" -ForegroundColor Green
        Write-Host ""
        return
    }

    # Process each cursor
    $launched = 0
    $skipped = 0

    foreach ($cursor in $cursors) {
        Write-Host ""
        Write-Host "--- Cursor #$($cursor.CursorNum): $($cursor.ImpTitle) ---" -ForegroundColor Yellow

        # Check if PR already merged
        if (Test-PRMerged -BranchName $cursor.BranchName) {
            Write-Success "PR already merged for $($cursor.BranchName) - skipping"
            $skipped++
            continue
        }

        # Check if PR already exists (in progress)
        if (Test-PRExists -BranchName $cursor.BranchName) {
            Write-Warn "PR already exists for $($cursor.BranchName) - skipping worktree creation"
            $skipped++
            continue
        }

        # Create worktree
        $created = New-Worktree -WorktreePath $cursor.WorktreePath -BranchName $cursor.BranchName
        if (-not $created) {
            Write-Err "Failed to create worktree for Cursor #$($cursor.CursorNum)"
            continue
        }

        # Write prompt file to worktree
        $written = Write-PromptFile -WorktreePath $cursor.WorktreePath -Prompt $cursor.Prompt -CursorNum $cursor.CursorNum -BranchName $cursor.BranchName -ImpTitle $cursor.ImpTitle
        if (-not $written) {
            Write-Err "Failed to write prompt for Cursor #$($cursor.CursorNum)"
            continue
        }

        # Collect prompt for consolidated file
        Collect-PromptForConsolidation -Prompt $cursor.Prompt -CursorNum $cursor.CursorNum -BranchName $cursor.BranchName -ImpTitle $cursor.ImpTitle

        # Launch Cursor
        $launchedOk = Start-CursorInstance -WorktreePath $cursor.WorktreePath -CursorNum $cursor.CursorNum
        if ($launchedOk) { $launched++ }

        # Delay between launches to avoid overwhelming the system
        if (-not $DryRun -and $LaunchDelay -gt 0) {
            Write-Status "Waiting ${LaunchDelay}s before next launch..."
            Start-Sleep -Seconds $LaunchDelay
        }
    }

    # Write consolidated prompts file
    Write-ConsolidatedPromptsFile

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Success "Launched: $launched cursors"
    Write-Warn "Skipped: $skipped cursors (already have PRs)"
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. In each Cursor, open the chat and paste from .claude-prompt"
    Write-Host "  2. Or run: claude --prompt-file .claude-prompt"
    Write-Host "  3. All prompts consolidated in: $PromptOutputFile" -ForegroundColor Green
    Write-Host "  4. Monitor PRs with: .\wave_orchestrator.ps1 -Wave $Wave -WorkflowFile `"$WorkflowFile`" -MonitorOnly"
    Write-Host ""
}

# Run
Main
