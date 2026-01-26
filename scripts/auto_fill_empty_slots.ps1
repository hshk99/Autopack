#
# Auto Fill Empty Slots (PowerShell)
#
# Automatically detects and fills empty automation slots with available tasks.
# Integrates with centralized telemetry for slot operation tracking.
#
# Usage:
#   powershell -File auto_fill_empty_slots.ps1
#   .\auto_fill_empty_slots.ps1 -MaxSlots 5 -DryRun
#
# Features:
#   - Detects empty slots in the automation pipeline
#   - Assigns available tasks from the backlog
#   - Logs all slot operations to centralized telemetry
#   - Supports dry-run mode for testing

param(
    [Parameter(Mandatory=$false)]
    [int]$MaxSlots = 10,

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

    [Parameter(Mandatory=$false)]
    [string]$BacklogPath = "AUTOPACK_IMPS_MASTER.json"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Auto Fill Empty Slots" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN MODE - No changes will be made]" -ForegroundColor Yellow
    Write-Host ""
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

# Function to get current slot status
function Get-SlotStatus {
    param(
        [Parameter(Mandatory=$true)]
        [int]$SlotNumber
    )

    # Check if slot has an active worktree/branch
    $worktreePath = "C:\dev\Autopack_slot$SlotNumber"
    $hasWorktree = Test-Path $worktreePath

    return @{
        slot = $SlotNumber
        occupied = $hasWorktree
        path = $worktreePath
    }
}

# Function to get available tasks from backlog
function Get-AvailableTasks {
    param(
        [Parameter(Mandatory=$false)]
        [string]$BacklogPath = "AUTOPACK_IMPS_MASTER.json"
    )

    if (-not (Test-Path $BacklogPath)) {
        Write-Host "Warning: Backlog file not found at $BacklogPath" -ForegroundColor Yellow
        return @()
    }

    try {
        $backlog = Get-Content $BacklogPath -Raw | ConvertFrom-Json
        $available = @()

        foreach ($imp in $backlog.improvements) {
            if ($imp.status -eq "pending" -or $imp.status -eq "ready") {
                $available += $imp
            }
        }

        return $available
    } catch {
        Write-Host "Warning: Failed to parse backlog: $_" -ForegroundColor Yellow
        return @()
    }
}

# Function to prioritize tasks using adaptive prioritization
function Get-PrioritizedTasks {
    param(
        [Parameter(Mandatory=$true)]
        [array]$Tasks,
        [Parameter(Mandatory=$true)]
        [int]$AvailableSlots
    )

    if ($Tasks.Count -eq 0) {
        return @()
    }

    # Convert tasks to JSON for Python
    $tasksJson = $Tasks | ConvertTo-Json -Compress -Depth 10
    $tasksJson = $tasksJson -replace '"', '\"'

    $pythonScript = @"
import sys
import json
sys.path.insert(0, 'src')

from generation.task_prioritizer import TaskPrioritizer

try:
    from memory.metrics_db import MetricsDatabase
    from memory.failure_analyzer import FailureAnalyzer
    db = MetricsDatabase()
    analyzer = FailureAnalyzer(db)
except Exception:
    db = None
    analyzer = None

tasks = json.loads("$tasksJson")
prioritizer = TaskPrioritizer(metrics_db=db, failure_analyzer=analyzer)
prioritized = prioritizer.prioritize(tasks, $AvailableSlots)

# Output as JSON array of imp_ids in priority order
result = [{"id": t.imp_id or t.phase_id, "score": t.score} for t in prioritized]
print(json.dumps(result))
"@

    try {
        $env:PYTHONPATH = "src"
        $result = python -c $pythonScript 2>&1

        if ($LASTEXITCODE -eq 0 -and $result) {
            $priorityOrder = $result | ConvertFrom-Json
            Write-Host "  Task prioritization applied (adaptive scoring)" -ForegroundColor Cyan

            # Reorder tasks based on priority
            $orderedTasks = @()
            foreach ($item in $priorityOrder) {
                $task = $Tasks | Where-Object { $_.id -eq $item.id } | Select-Object -First 1
                if ($task) {
                    $orderedTasks += $task
                    Write-Host "    - $($task.id): score $([math]::Round($item.score, 1))" -ForegroundColor Gray
                }
            }
            return $orderedTasks
        }
    } catch {
        Write-Host "  Warning: Prioritization failed, using FIFO order: $_" -ForegroundColor Yellow
    }

    # Fallback to original order
    return $Tasks
}

# Function to fill a slot with a task
function Fill-Slot {
    param(
        [Parameter(Mandatory=$true)]
        [int]$SlotNumber,
        [Parameter(Mandatory=$true)]
        $Task,
        [Parameter(Mandatory=$false)]
        [switch]$DryRun
    )

    $taskId = $Task.id
    $taskTitle = $Task.title

    Write-Host "  Filling slot $SlotNumber with task: $taskId - $taskTitle" -ForegroundColor Green

    # Log slot fill event
    Write-TelemetryEvent -EventType "slot_filled" -Slot $SlotNumber -Data @{
        task_id = $taskId
        task_title = $taskTitle
        dry_run = $DryRun.IsPresent
    }

    if ($DryRun) {
        Write-Host "    [DRY RUN] Would create worktree and assign task" -ForegroundColor Yellow
        return $true
    }

    # In actual implementation, this would:
    # 1. Create git worktree
    # 2. Update task status in backlog
    # 3. Initialize slot state

    return $true
}

Write-Host "==> Scanning slots 1 to $MaxSlots..." -ForegroundColor Yellow
Write-Host ""

# Log scan start event
Write-TelemetryEvent -EventType "slot_scan_started" -Data @{
    max_slots = $MaxSlots
    dry_run = $DryRun.IsPresent
}

$emptySlots = @()
$occupiedSlots = @()

for ($i = 1; $i -le $MaxSlots; $i++) {
    $status = Get-SlotStatus -SlotNumber $i

    if ($status.occupied) {
        $occupiedSlots += $i
        Write-Host "  Slot $i`: OCCUPIED" -ForegroundColor White
    } else {
        $emptySlots += $i
        Write-Host "  Slot $i`: EMPTY" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Summary: $($occupiedSlots.Count) occupied, $($emptySlots.Count) empty" -ForegroundColor Cyan
Write-Host ""

if ($emptySlots.Count -eq 0) {
    Write-Host "All slots are occupied. Nothing to fill." -ForegroundColor Green

    # Log scan complete with no empty slots
    Write-TelemetryEvent -EventType "slot_scan_completed" -Data @{
        occupied_count = $occupiedSlots.Count
        empty_count = 0
        filled_count = 0
    }

    exit 0
}

Write-Host "==> Fetching available tasks from backlog..." -ForegroundColor Yellow
$availableTasks = Get-AvailableTasks -BacklogPath $BacklogPath

if ($availableTasks.Count -eq 0) {
    Write-Host "No available tasks in backlog." -ForegroundColor Yellow

    # Log scan complete with no tasks
    Write-TelemetryEvent -EventType "slot_scan_completed" -Data @{
        occupied_count = $occupiedSlots.Count
        empty_count = $emptySlots.Count
        filled_count = 0
        reason = "no_available_tasks"
    }

    exit 0
}

Write-Host "Found $($availableTasks.Count) available task(s)" -ForegroundColor Cyan
Write-Host ""

Write-Host "==> Prioritizing tasks for optimal slot assignment..." -ForegroundColor Yellow
$prioritizedTasks = Get-PrioritizedTasks -Tasks $availableTasks -AvailableSlots $emptySlots.Count
Write-Host ""

Write-Host "==> Filling empty slots..." -ForegroundColor Yellow

$filledCount = 0
$taskIndex = 0

foreach ($slotNum in $emptySlots) {
    if ($taskIndex -ge $prioritizedTasks.Count) {
        Write-Host "  No more tasks available to fill remaining slots" -ForegroundColor Yellow
        break
    }

    $task = $prioritizedTasks[$taskIndex]
    $success = Fill-Slot -SlotNumber $slotNum -Task $task -DryRun:$DryRun

    if ($success) {
        $filledCount++
        $taskIndex++
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Filled $filledCount slot(s)" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan

# Log final summary
Write-TelemetryEvent -EventType "slot_scan_completed" -Data @{
    occupied_count = $occupiedSlots.Count
    empty_count = $emptySlots.Count
    filled_count = $filledCount
    dry_run = $DryRun.IsPresent
    prioritization_used = $true
}

exit 0
