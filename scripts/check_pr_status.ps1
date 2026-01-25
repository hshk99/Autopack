#
# Check PR Status and Record Improvement Effectiveness (PowerShell)
#
# Monitors PR merge status and records improvement outcomes to LEARNING_MEMORY.json
# for feedback loop analysis. Extracts IMP IDs from PR titles and tracks metrics.
#
# Usage:
#   powershell -File scripts/check_pr_status.ps1 -PrNumber 123
#   .\scripts\check_pr_status.ps1 -PrNumber 123
#
# Features:
#   - Detects PR merged state via gh CLI
#   - Extracts IMP ID from PR title pattern [IMP-XXX-NNN]
#   - Records outcome with PR metrics (merge time, CI status, review cycles)
#   - Integrates with learning_memory_manager.py for persistence

param(
    [Parameter(Mandatory=$true)]
    [int]$PrNumber,

    [Parameter(Mandatory=$false)]
    [string]$MemoryPath = "LEARNING_MEMORY.json"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "PR Status Check & Effectiveness Tracker" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if gh CLI is available
try {
    $null = gh --version
} catch {
    Write-Host "Error: GitHub CLI (gh) is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

Write-Host "==> Checking PR #$PrNumber status..." -ForegroundColor Yellow

# Get PR details as JSON
try {
    $prJson = gh pr view $PrNumber --json title,state,mergedAt,createdAt,headRefName,body,number,reviews,statusCheckRollup 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to fetch PR #$PrNumber - $prJson" -ForegroundColor Red
        exit 1
    }
    $pr = $prJson | ConvertFrom-Json
} catch {
    Write-Host "Error: Failed to parse PR data - $_" -ForegroundColor Red
    exit 1
}

Write-Host "  Title: $($pr.title)" -ForegroundColor White
Write-Host "  State: $($pr.state)" -ForegroundColor White
Write-Host "  Branch: $($pr.headRefName)" -ForegroundColor White

# Check if PR is merged
if ($pr.state -ne "MERGED") {
    Write-Host ""
    Write-Host "PR #$PrNumber is not merged (state: $($pr.state))" -ForegroundColor Yellow
    Write-Host "No effectiveness tracking needed yet." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "==> PR #$PrNumber is MERGED - Recording effectiveness..." -ForegroundColor Green

# Extract IMP ID from PR title using pattern [IMP-XXX-NNN]
$impIdPattern = '\[IMP-([A-Z]+)-(\d+)\]'
$match = [regex]::Match($pr.title, $impIdPattern)

if (-not $match.Success) {
    Write-Host ""
    Write-Host "Warning: No IMP ID found in PR title" -ForegroundColor Yellow
    Write-Host "  Expected pattern: [IMP-XXX-NNN] (e.g., [IMP-TEL-002])" -ForegroundColor Yellow
    Write-Host "  PR Title: $($pr.title)" -ForegroundColor Yellow
    exit 0
}

$impId = "IMP-$($match.Groups[1].Value)-$($match.Groups[2].Value)"
Write-Host "  Extracted IMP ID: $impId" -ForegroundColor Cyan

# Calculate metrics
$createdAt = [datetime]::Parse($pr.createdAt)
$mergedAt = [datetime]::Parse($pr.mergedAt)
$mergeTimeHours = [math]::Round(($mergedAt - $createdAt).TotalHours, 2)

Write-Host "  Created: $($pr.createdAt)" -ForegroundColor White
Write-Host "  Merged: $($pr.mergedAt)" -ForegroundColor White
Write-Host "  Time to merge: $mergeTimeHours hours" -ForegroundColor White

# Count review cycles (number of review submissions)
$reviewCycles = 0
if ($pr.reviews -and $pr.reviews.Count -gt 0) {
    $reviewCycles = $pr.reviews.Count
}
Write-Host "  Review cycles: $reviewCycles" -ForegroundColor White

# Calculate CI pass rate from status checks
$ciPassRate = 1.0
$ciTotal = 0
$ciPassed = 0
if ($pr.statusCheckRollup -and $pr.statusCheckRollup.Count -gt 0) {
    foreach ($check in $pr.statusCheckRollup) {
        $ciTotal++
        if ($check.conclusion -eq "SUCCESS") {
            $ciPassed++
        }
    }
    if ($ciTotal -gt 0) {
        $ciPassRate = [math]::Round($ciPassed / $ciTotal, 3)
    }
}
Write-Host "  CI pass rate: $ciPassRate ($ciPassed/$ciTotal checks)" -ForegroundColor White

# Build details JSON for Python
$details = @{
    pr_number = $pr.number
    merge_time_hours = $mergeTimeHours
    ci_pass_rate = $ciPassRate
    ci_checks_passed = $ciPassed
    ci_checks_total = $ciTotal
    review_cycles = $reviewCycles
    created_at = $pr.createdAt
    merged_at = $pr.mergedAt
    branch = $pr.headRefName
}
$detailsJson = $details | ConvertTo-Json -Compress

Write-Host ""
Write-Host "==> Recording improvement outcome..." -ForegroundColor Yellow

# Invoke Python to record the outcome
$pythonScript = @"
import sys
import json
from pathlib import Path
sys.path.insert(0, 'src')
from autopack.learning_memory_manager import LearningMemoryManager

imp_id = '$impId'
details = json.loads('$($detailsJson -replace "'", "''")')

memory_path = Path('$MemoryPath')
manager = LearningMemoryManager(memory_path)
manager.record_improvement_outcome(imp_id, success=True, details=details)
manager.save()

print(f"Recorded outcome for {imp_id}")
print(f"  Memory path: {memory_path.absolute()}")
print(f"  Total outcomes: {manager.outcome_count}")
"@

try {
    $env:PYTHONPATH = "src"
    $result = python -c $pythonScript 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host $result -ForegroundColor Green
        Write-Host ""
        Write-Host "==========================================" -ForegroundColor Cyan
        Write-Host "Effectiveness recorded successfully!" -ForegroundColor Green
        Write-Host "==========================================" -ForegroundColor Cyan
        exit 0
    } else {
        Write-Host "Error: Failed to record outcome" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Error: Failed to execute Python script - $_" -ForegroundColor Red
    exit 1
}
