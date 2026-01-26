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
#   - Logs events to centralized telemetry system

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

# Function to categorize CI failures based on failed job names and errors
function Get-CIFailureCategory {
    param(
        [Parameter(Mandatory=$true)]
        [array]$FailedChecks
    )

    $failedJobNames = $FailedChecks | ForEach-Object { $_.name.ToLower() }
    $allJobNames = $failedJobNames -join " "

    # Categorize based on job names and patterns
    # flaky_test: Known flaky test patterns or intermittent failures
    if ($allJobNames -match "flaky|intermittent|timeout|connection") {
        return "flaky_test"
    }

    # unrelated_ci: Infrastructure/environment issues, not code-related
    if ($allJobNames -match "setup|install|download|cache|network|artifact|deploy") {
        return "unrelated_ci"
    }

    # code_failure: Default - actual code/test failures
    return "code_failure"
}

# Function to record failure category to learning memory
function Record-FailureCategoryToMemory {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Category,
        [Parameter(Mandatory=$true)]
        [string]$PhaseId,
        [Parameter(Mandatory=$true)]
        [hashtable]$Details,
        [Parameter(Mandatory=$false)]
        [string]$MemoryPath = "LEARNING_MEMORY.json"
    )

    $detailsJson = $Details | ConvertTo-Json -Compress

    $pythonScript = @"
import sys
import json
from pathlib import Path
sys.path.insert(0, 'src')
from autopack.learning_memory_manager import LearningMemoryManager

category = '$Category'
phase_id = '$PhaseId'
details = json.loads('$($detailsJson -replace "'", "''")')

memory_path = Path('$MemoryPath')
manager = LearningMemoryManager(memory_path)
manager.record_failure_category(category, phase_id, details)
manager.save()

print(f"Recorded {category} failure for {phase_id}")
"@

    try {
        $env:PYTHONPATH = "src"
        $result = python -c $pythonScript 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  $result" -ForegroundColor Yellow
            return $true
        } else {
            Write-Host "  Warning: Failed to record failure category: $result" -ForegroundColor Yellow
            return $false
        }
    } catch {
        Write-Host "  Warning: Failed to execute failure recording: $_" -ForegroundColor Yellow
        return $false
    }
}

# Function to record a nudge sent to learning memory
function Record-NudgeSent {
    param(
        [Parameter(Mandatory=$true)]
        [string]$TemplateId,
        [Parameter(Mandatory=$true)]
        [int]$SlotId,
        [Parameter(Mandatory=$false)]
        [hashtable]$Context = @{},
        [Parameter(Mandatory=$false)]
        [string]$MemoryPath = "LEARNING_MEMORY.json"
    )

    $contextJson = $Context | ConvertTo-Json -Compress

    $pythonScript = @"
import sys
import json
from pathlib import Path
sys.path.insert(0, 'src')
from autopack.learning_memory_manager import LearningMemoryManager

template_id = '$TemplateId'
slot_id = $SlotId
context = json.loads('$($contextJson -replace "'", "''")')

memory_path = Path('$MemoryPath')
manager = LearningMemoryManager(memory_path)
manager.record_nudge_sent(template_id, slot_id, context)
manager.save()

print(f"Recorded nudge sent: {template_id} for slot {slot_id}")
"@

    try {
        $env:PYTHONPATH = "src"
        $result = python -c $pythonScript 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  $result" -ForegroundColor Cyan
            return $true
        } else {
            Write-Host "  Warning: Failed to record nudge sent: $result" -ForegroundColor Yellow
            return $false
        }
    } catch {
        Write-Host "  Warning: Failed to execute nudge recording: $_" -ForegroundColor Yellow
        return $false
    }
}

# Function to record nudge effectiveness when slot recovers
function Record-NudgeEffectiveness {
    param(
        [Parameter(Mandatory=$true)]
        [int]$SlotId,
        [Parameter(Mandatory=$true)]
        [bool]$Effective,
        [Parameter(Mandatory=$false)]
        [int]$RecoveryTimeSeconds = 0,
        [Parameter(Mandatory=$false)]
        [string]$MemoryPath = "LEARNING_MEMORY.json"
    )

    $effectivePython = if ($Effective) { "True" } else { "False" }

    $pythonScript = @"
import sys
from pathlib import Path
sys.path.insert(0, 'src')
from autopack.learning_memory_manager import LearningMemoryManager

slot_id = $SlotId
effective = $effectivePython
recovery_time = $RecoveryTimeSeconds if $RecoveryTimeSeconds > 0 else None

memory_path = Path('$MemoryPath')
manager = LearningMemoryManager(memory_path)
template_id = manager.resolve_pending_nudge(slot_id, effective, recovery_time)
manager.save()

if template_id:
    print(f"Resolved nudge effectiveness: {template_id} effective={effective}")
else:
    print(f"No pending nudge found for slot {slot_id}")
"@

    try {
        $env:PYTHONPATH = "src"
        $result = python -c $pythonScript 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  $result" -ForegroundColor Cyan
            return $true
        } else {
            Write-Host "  Warning: Failed to record nudge effectiveness: $result" -ForegroundColor Yellow
            return $false
        }
    } catch {
        Write-Host "  Warning: Failed to execute effectiveness recording: $_" -ForegroundColor Yellow
        return $false
    }
}

# Function to get effective nudge templates
function Get-EffectiveNudgeTemplates {
    param(
        [Parameter(Mandatory=$false)]
        [string]$MemoryPath = "LEARNING_MEMORY.json"
    )

    $pythonScript = @"
import sys
import json
from pathlib import Path
sys.path.insert(0, 'src')
from autopack.learning_memory_manager import LearningMemoryManager

memory_path = Path('$MemoryPath')
manager = LearningMemoryManager(memory_path)
templates = manager.get_effective_templates()
print(json.dumps(templates))
"@

    try {
        $env:PYTHONPATH = "src"
        $result = python -c $pythonScript 2>&1
        if ($LASTEXITCODE -eq 0) {
            return $result | ConvertFrom-Json
        } else {
            Write-Host "  Warning: Failed to get effective templates: $result" -ForegroundColor Yellow
            return @()
        }
    } catch {
        Write-Host "  Warning: Failed to execute template query: $_" -ForegroundColor Yellow
        return @()
    }
}

# Function to run feedback loop cycle
function Invoke-FeedbackLoopCycle {
    param(
        [Parameter(Mandatory=$false)]
        [string]$MemoryPath = "LEARNING_MEMORY.json"
    )

    $pythonScript = @"
import sys
sys.path.insert(0, 'src')

from feedback.loop_controller import FeedbackLoopController
from memory.metrics_db import MetricsDatabase
from memory.failure_analyzer import FailureAnalyzer
from feedback.optimization_detector import OptimizationDetector

# Initialize components
metrics_db = MetricsDatabase()
failure_analyzer = FailureAnalyzer(metrics_db)
optimization_detector = OptimizationDetector(metrics_db)

# Create and run feedback loop
controller = FeedbackLoopController(
    metrics_db=metrics_db,
    failure_analyzer=failure_analyzer,
    optimization_detector=optimization_detector
)

actions = controller.run_cycle()
print(f"Feedback loop completed: {len(actions)} actions generated")

for action in actions:
    print(f"  [{action.priority.upper()}] {action.action_type}: {action.description}")
"@

    try {
        $env:PYTHONPATH = "src"
        $result = python -c $pythonScript 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host $result -ForegroundColor Cyan
            return $true
        } else {
            Write-Host "  Warning: Feedback loop cycle failed: $result" -ForegroundColor Yellow
            return $false
        }
    } catch {
        Write-Host "  Warning: Failed to execute feedback loop: $_" -ForegroundColor Yellow
        return $false
    }
}

# Function to log events to centralized telemetry
function Write-TelemetryEvent {
    param(
        [Parameter(Mandatory=$true)]
        [string]$EventType,
        [Parameter(Mandatory=$true)]
        [hashtable]$Data,
        [Parameter(Mandatory=$false)]
        [int]$Slot = -1
    )

    $dataJson = $Data | ConvertTo-Json -Compress

    $slotArg = if ($Slot -ge 0) { "slot=$Slot" } else { "slot=None" }

    $pythonScript = @"
import sys
import json
sys.path.insert(0, 'src')
from telemetry.event_logger import get_logger

event_type = '$EventType'
data = json.loads('$($dataJson -replace "'", "''")')
$slotArg

logger = get_logger()
logger.log(event_type, data, slot)
"@

    try {
        $env:PYTHONPATH = "src"
        $null = python -c $pythonScript 2>&1
    } catch {
        # Silently continue if telemetry fails - don't block main workflow
    }
}

# Function to log structured decisions with reasoning (IMP-LOG-001)
function Write-DecisionLog {
    param(
        [Parameter(Mandatory=$true)]
        [string]$DecisionType,
        [Parameter(Mandatory=$true)]
        [hashtable]$Context,
        [Parameter(Mandatory=$true)]
        [string[]]$OptionsConsidered,
        [Parameter(Mandatory=$true)]
        [string]$ChosenOption,
        [Parameter(Mandatory=$true)]
        [string]$Reasoning,
        [Parameter(Mandatory=$false)]
        [string]$Outcome = ""
    )

    $contextJson = $Context | ConvertTo-Json -Compress
    $optionsJson = $OptionsConsidered | ConvertTo-Json -Compress
    $outcomeArg = if ($Outcome) { "outcome='$($Outcome -replace "'", "''")'" } else { "outcome=None" }

    $pythonScript = @"
import sys
import json
sys.path.insert(0, 'src')
from decision_logging.decision_logger import get_decision_logger

decision_type = '$DecisionType'
context = json.loads('$($contextJson -replace "'", "''")')
options = json.loads('$($optionsJson -replace "'", "''")')
chosen = '$($ChosenOption -replace "'", "''")'
reasoning = '$($Reasoning -replace "'", "''")'
$outcomeArg

logger = get_decision_logger()
logger.create_and_log_decision(
    decision_type=decision_type,
    context=context,
    options_considered=options,
    chosen_option=chosen,
    reasoning=reasoning,
    outcome=outcome
)
"@

    try {
        $env:PYTHONPATH = "src"
        $null = python -c $pythonScript 2>&1
    } catch {
        # Silently continue if decision logging fails - don't block main workflow
    }
}

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

# Log PR status check event
Write-TelemetryEvent -EventType "pr_status_check" -Data @{
    pr_number = $pr.number
    title = $pr.title
    state = $pr.state
    branch = $pr.headRefName
}

# Check for CI failures and categorize them
$failedChecks = @()
if ($pr.statusCheckRollup -and $pr.statusCheckRollup.Count -gt 0) {
    $failedChecks = $pr.statusCheckRollup | Where-Object { $_.conclusion -eq "FAILURE" -or $_.conclusion -eq "TIMED_OUT" }
}

if ($failedChecks.Count -gt 0) {
    Write-Host ""
    Write-Host "==> CI Failures Detected - Categorizing..." -ForegroundColor Yellow

    # Extract IMP ID from PR title for phase tracking
    $impIdPattern = '\[IMP-([A-Z]+)-(\d+)\]'
    $match = [regex]::Match($pr.title, $impIdPattern)
    $phaseId = if ($match.Success) { "IMP-$($match.Groups[1].Value)-$($match.Groups[2].Value)" } else { "PR-$($pr.number)" }

    # Categorize the failure
    $failureCategory = Get-CIFailureCategory -FailedChecks $failedChecks
    Write-Host "  Category: $failureCategory" -ForegroundColor Cyan
    Write-Host "  Phase ID: $phaseId" -ForegroundColor Cyan

    # Log the categorization decision (IMP-LOG-001)
    Write-DecisionLog -DecisionType "ci_failure_categorization" -Context @{
        pr_number = $pr.number
        phase_id = $phaseId
        failed_checks = ($failedChecks | ForEach-Object { $_.name }) -join ", "
        failed_count = $failedChecks.Count
    } -OptionsConsidered @("flaky_test", "unrelated_ci", "code_failure") `
      -ChosenOption $failureCategory `
      -Reasoning "Categorized based on failed job names pattern matching: jobs contained patterns indicative of $failureCategory"

    # Build failure details
    $failedJobNames = ($failedChecks | ForEach-Object { $_.name }) -join ", "
    $failureDetails = @{
        run_id = if ($failedChecks[0].detailsUrl -match "runs/(\d+)") { $Matches[1] } else { "" }
        pr_number = $pr.number
        phase_id = $phaseId
        failed_jobs = $failedJobNames
        failed_count = $failedChecks.Count
        error_summary = "CI failure in: $failedJobNames"
    }

    Write-Host "  Failed Jobs: $failedJobNames" -ForegroundColor White

    # Log CI failure to telemetry
    Write-TelemetryEvent -EventType "ci_failure" -Data @{
        pr_number = $pr.number
        phase_id = $phaseId
        category = $failureCategory
        failed_jobs = $failedJobNames
        failed_count = $failedChecks.Count
    }

    # Record to learning memory for pattern analysis
    Write-Host ""
    Write-Host "==> Recording failure category to learning memory..." -ForegroundColor Yellow
    Record-FailureCategoryToMemory -Category $failureCategory -PhaseId $phaseId -Details $failureDetails -MemoryPath $MemoryPath
}

# Trigger feedback loop cycle after status check
Write-Host ""
Write-Host "==> Running feedback loop cycle..." -ForegroundColor Yellow
Invoke-FeedbackLoopCycle -MemoryPath $MemoryPath

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

# Log PR merged event to telemetry
Write-TelemetryEvent -EventType "pr_merged" -Data @{
    pr_number = $pr.number
    imp_id = $impId
    merge_time_hours = $mergeTimeHours
    ci_pass_rate = $ciPassRate
    review_cycles = $reviewCycles
    branch = $pr.headRefName
}

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

# Log the decision to record this as a successful outcome (IMP-LOG-001)
Write-DecisionLog -DecisionType "phase_transition" -Context @{
    pr_number = $pr.number
    imp_id = $impId
    merge_time_hours = $mergeTimeHours
    ci_pass_rate = $ciPassRate
    review_cycles = $reviewCycles
} -OptionsConsidered @("record_success", "record_failure", "skip_recording") `
  -ChosenOption "record_success" `
  -Reasoning "PR merged successfully with CI pass rate of $ciPassRate after $reviewCycles review cycles"

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
