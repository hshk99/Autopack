<#
.SYNOPSIS
    Rollback Failed Improvements

.DESCRIPTION
    Cleans up worktrees and branches for improvements that reached Level 3+ escalation.
    Identifies failed improvements from escalation reports and performs automated cleanup
    including closing PRs, removing worktrees, and archiving escalation reports.

.PARAMETER DryRun
    When enabled, shows what would be done without making any changes.

.PARAMETER EscalationDir
    Path to the escalation reports directory. Defaults to "escalation_reports" in
    the project root.

.PARAMETER TargetRepo
    Path to the main repository for git operations. Defaults to the project root.

.EXAMPLE
    .\rollback_failed_improvements.ps1 -DryRun
    Shows what would be cleaned up without making changes.

.EXAMPLE
    .\rollback_failed_improvements.ps1
    Performs actual cleanup of Level 3+ escalated improvements.

.NOTES
    IMP-TASK-003: Failed Improvement Rollback Automation
    Automates cleanup of abandoned improvements to prevent accumulation of
    worktrees and branches.
#>

param(
    [switch]$DryRun,

    [string]$EscalationDir = "",

    [string]$TargetRepo = ""
)

$ErrorActionPreference = "Stop"

# Script configuration - determine project root
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
}
if (-not $ScriptDir) {
    $ScriptDir = Get-Location
}

# Check if we're at project root (has .git, pyproject.toml, or src directory)
$ProjectRoot = $ScriptDir
$rootIndicators = @(".git", "pyproject.toml", "src")
$isProjectRoot = $false
foreach ($indicator in $rootIndicators) {
    if (Test-Path (Join-Path $ScriptDir $indicator)) {
        $isProjectRoot = $true
        break
    }
}

# If not at project root, try parent directory
if (-not $isProjectRoot) {
    $parentDir = Split-Path -Parent $ScriptDir
    if ($parentDir) {
        foreach ($indicator in $rootIndicators) {
            if (Test-Path (Join-Path $parentDir $indicator)) {
                $ProjectRoot = $parentDir
                break
            }
        }
    }
}

# Set default paths if not provided
if (-not $TargetRepo) {
    $TargetRepo = $ProjectRoot
}

if (-not $EscalationDir) {
    $EscalationDir = Join-Path $TargetRepo "escalation_reports"
}

function Get-FailedImprovements {
    <#
    .SYNOPSIS
    Read escalation reports and identify Level 3+ failures
    #>
    $failedPhases = @()

    if (Test-Path $EscalationDir) {
        $reports = Get-ChildItem -Path $EscalationDir -Filter "*.json" -ErrorAction SilentlyContinue
        foreach ($report in $reports) {
            try {
                $content = Get-Content $report.FullName -Raw | ConvertFrom-Json
                if ($content.escalation_level -ge 3) {
                    $failedPhases += @{
                        PhaseId      = $content.phase_id
                        Branch       = $content.branch
                        WorktreePath = $content.worktree_path
                        ReportFile   = $report.FullName
                        Level        = $content.escalation_level
                    }
                }
            }
            catch {
                Write-Host "  Warning: Could not parse report: $($report.Name)" -ForegroundColor Yellow
            }
        }
    }

    return $failedPhases
}

function Remove-Worktree {
    param([string]$WorktreePath)

    if (Test-Path $WorktreePath) {
        if ($DryRun) {
            Write-Host "[DRY RUN] Would remove worktree: $WorktreePath" -ForegroundColor Yellow
        }
        else {
            Write-Host "Removing worktree: $WorktreePath" -ForegroundColor Cyan
            Push-Location $TargetRepo
            try {
                git worktree remove --force $WorktreePath 2>$null
            }
            catch {
                Write-Host "  Warning: Failed to remove worktree: $_" -ForegroundColor Yellow
            }
            Pop-Location
        }
    }
    else {
        Write-Host "  Worktree not found (already removed?): $WorktreePath" -ForegroundColor Gray
    }
}

function Remove-Branch {
    param([string]$BranchName)

    if (-not $BranchName) {
        return
    }

    if ($DryRun) {
        Write-Host "[DRY RUN] Would delete branch: $BranchName" -ForegroundColor Yellow
    }
    else {
        Write-Host "Deleting branch: $BranchName" -ForegroundColor Cyan
        Push-Location $TargetRepo
        try {
            git branch -D $BranchName 2>$null
        }
        catch {
            Write-Host "  Warning: Failed to delete branch (may not exist locally): $_" -ForegroundColor Yellow
        }
        Pop-Location
    }
}

function Close-AbandonedPR {
    param([string]$BranchName)

    if (-not $BranchName) {
        return
    }

    # Check if gh CLI is available
    try {
        $null = gh --version 2>$null
    }
    catch {
        Write-Host "  Warning: GitHub CLI (gh) not available, skipping PR close" -ForegroundColor Yellow
        return
    }

    # Find PR for this branch
    try {
        Push-Location $TargetRepo
        $pr = gh pr list --head $BranchName --json number --jq '.[0].number' 2>$null
        Pop-Location
    }
    catch {
        Pop-Location
        return
    }

    if ($pr) {
        if ($DryRun) {
            Write-Host "[DRY RUN] Would close PR #$pr for branch: $BranchName" -ForegroundColor Yellow
        }
        else {
            Write-Host "Closing PR #$pr with automated rollback comment" -ForegroundColor Cyan
            Push-Location $TargetRepo
            try {
                gh pr close $pr --comment "Automated rollback: This improvement reached Level 3+ escalation and is being abandoned."
            }
            catch {
                Write-Host "  Warning: Failed to close PR: $_" -ForegroundColor Yellow
            }
            Pop-Location
        }
    }
}

function Archive-EscalationReport {
    param([string]$ReportFile)

    if (-not (Test-Path $ReportFile)) {
        return
    }

    if ($DryRun) {
        Write-Host "[DRY RUN] Would archive report: $ReportFile" -ForegroundColor Yellow
    }
    else {
        $archiveDir = Join-Path $EscalationDir "archived"
        try {
            New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
            Move-Item $ReportFile $archiveDir -Force
            Write-Host "Archived report to: $archiveDir" -ForegroundColor Gray
        }
        catch {
            Write-Host "  Warning: Failed to archive report: $_" -ForegroundColor Yellow
        }
    }
}

# Main execution
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Failed Improvement Rollback" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN MODE - No changes will be made]" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Configuration:" -ForegroundColor White
Write-Host "  Project Root: $ProjectRoot" -ForegroundColor Gray
Write-Host "  Target Repo: $TargetRepo" -ForegroundColor Gray
Write-Host "  Escalation Dir: $EscalationDir" -ForegroundColor Gray
Write-Host ""

# Check if escalation directory exists
if (-not (Test-Path $EscalationDir)) {
    Write-Host "Escalation reports directory not found: $EscalationDir" -ForegroundColor Yellow
    Write-Host "No failed improvements to clean up." -ForegroundColor Green
    exit 0
}

Write-Host "==> Scanning for Level 3+ escalated improvements..." -ForegroundColor Yellow
$failedImprovements = Get-FailedImprovements

if ($failedImprovements.Count -eq 0) {
    Write-Host ""
    Write-Host "No Level 3+ escalated improvements found." -ForegroundColor Green
    Write-Host "Nothing to clean up." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "Found $($failedImprovements.Count) failed improvement(s) to clean up:" -ForegroundColor Cyan
Write-Host ""

foreach ($failed in $failedImprovements) {
    Write-Host "----------------------------------------" -ForegroundColor Gray
    Write-Host "Processing: $($failed.PhaseId)" -ForegroundColor White
    Write-Host "  Escalation Level: $($failed.Level)" -ForegroundColor Gray
    Write-Host "  Branch: $($failed.Branch)" -ForegroundColor Gray
    Write-Host "  Worktree: $($failed.WorktreePath)" -ForegroundColor Gray
    Write-Host ""

    # Step 1: Close any open PR
    Close-AbandonedPR -BranchName $failed.Branch

    # Step 2: Remove worktree
    Remove-Worktree -WorktreePath $failed.WorktreePath

    # Step 3: Delete branch
    Remove-Branch -BranchName $failed.Branch

    # Step 4: Archive escalation report
    Archive-EscalationReport -ReportFile $failed.ReportFile
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Rollback Complete" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

if ($DryRun) {
    Write-Host ""
    Write-Host "This was a dry run. Run without -DryRun to apply changes." -ForegroundColor Yellow
}
