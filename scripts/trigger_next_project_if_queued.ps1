<#
.SYNOPSIS
    Triggers the next queued project and captures discovery cycle metrics on completion.

.DESCRIPTION
    IMP-MEM-002: Discovery Cycle Metrics Capture
    Manages the project queue stored in PROJECT_QUEUE.json and captures cycle quality
    metrics when projects complete. This data feeds the historical learning database
    for pattern analysis and cross-cycle learning.

    Metrics captured:
    - phases_completed: Number of phases that completed successfully
    - phases_blocked: Number of phases that were blocked
    - total_nudges: Total nudges (reminders/prompts) during the cycle
    - total_escalations: Total escalations (interventions) during the cycle
    - duration_hours: Total duration of the cycle in hours
    - completion_rate: Ratio of completed phases (0.0-1.0)

.PARAMETER Action
    Action to perform: "next" (trigger next project), "complete" (mark current complete),
    "status" (show queue status), "list" (list all projects).
    Defaults to "status".

.PARAMETER ProjectId
    Project ID to operate on (required for "complete" action).

.PARAMETER PhasesCompleted
    Number of phases completed (for "complete" action).

.PARAMETER PhasesBlocked
    Number of phases blocked (for "complete" action).

.PARAMETER TotalNudges
    Total nudges during the cycle (for "complete" action).

.PARAMETER TotalEscalations
    Total escalations during the cycle (for "complete" action).

.PARAMETER StartTime
    ISO timestamp when the project started (for duration calculation).

.PARAMETER QueuePath
    Path to PROJECT_QUEUE.json. Defaults to ".autopack/PROJECT_QUEUE.json".

.PARAMETER LearningDbPath
    Path to the learning database. Defaults to ".autopack/learning_db.json".

.PARAMETER DryRun
    When enabled, shows what would be done without making changes.

.EXAMPLE
    .\trigger_next_project_if_queued.ps1 -Action status
    Shows the current queue status.

.EXAMPLE
    .\trigger_next_project_if_queued.ps1 -Action next
    Triggers the next queued project.

.EXAMPLE
    .\trigger_next_project_if_queued.ps1 -Action complete -ProjectId "proj-001" -PhasesCompleted 5 -PhasesBlocked 1 -TotalNudges 12 -TotalEscalations 2
    Marks a project as complete with cycle metrics.

.NOTES
    IMP-MEM-002: Discovery Cycle Metrics Capture
    This script bridges the execution->memory link by capturing cycle quality
    metrics that feed into the historical learning database for pattern analysis.
#>

param(
    [ValidateSet("next", "complete", "status", "list", "add")]
    [string]$Action = "status",

    [string]$ProjectId,

    [int]$PhasesCompleted = 0,

    [int]$PhasesBlocked = 0,

    [int]$TotalNudges = 0,

    [int]$TotalEscalations = 0,

    [string]$StartTime,

    [string]$QueuePath = ".autopack/PROJECT_QUEUE.json",

    [string]$LearningDbPath = ".autopack/learning_db.json",

    [string]$ProjectName,

    [string]$ProjectDescription,

    [switch]$DryRun
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

# Check if we're at project root
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

# Resolve paths relative to project root
$QueuePath = Join-Path $ProjectRoot $QueuePath
$LearningDbPath = Join-Path $ProjectRoot $LearningDbPath

function Write-Status {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "[ProjectQueue] $Message" -ForegroundColor $Color
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[Warning] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[Error] $Message" -ForegroundColor Red
}

function Get-EmptyQueueSchema {
    <#
    .SYNOPSIS
        Creates an empty PROJECT_QUEUE.json schema.
    #>
    return @{
        schema_version = 1
        created_at = (Get-Date -Format "o")
        updated_at = (Get-Date -Format "o")
        current_project = $null
        queued_projects = @()
        completed_projects = @()
    }
}

function Read-ProjectQueue {
    <#
    .SYNOPSIS
        Reads the project queue from PROJECT_QUEUE.json.
    #>
    if (-not (Test-Path $QueuePath)) {
        Write-Status "Queue file not found, creating empty queue at: $QueuePath" -Color Yellow
        $queue = Get-EmptyQueueSchema
        Save-ProjectQueue -Queue $queue
        return $queue
    }

    try {
        $content = Get-Content $QueuePath -Raw -Encoding UTF8
        $queue = $content | ConvertFrom-Json
        return $queue
    }
    catch {
        Write-Error "Failed to read queue file: $_"
        return Get-EmptyQueueSchema
    }
}

function Save-ProjectQueue {
    <#
    .SYNOPSIS
        Saves the project queue to PROJECT_QUEUE.json.
    #>
    param([Parameter(Mandatory=$true)]$Queue)

    if ($DryRun) {
        Write-Status "[DryRun] Would save queue to: $QueuePath" -Color Yellow
        return $true
    }

    try {
        # Ensure parent directory exists
        $queueDir = Split-Path -Parent $QueuePath
        if (-not (Test-Path $queueDir)) {
            New-Item -ItemType Directory -Path $queueDir -Force | Out-Null
        }

        $Queue.updated_at = (Get-Date -Format "o")
        $Queue | ConvertTo-Json -Depth 10 | Set-Content $QueuePath -Encoding UTF8
        return $true
    }
    catch {
        Write-Error "Failed to save queue file: $_"
        return $false
    }
}

function Calculate-CycleMetrics {
    <#
    .SYNOPSIS
        Calculates cycle metrics including duration and completion rate.
    #>
    param(
        [int]$PhasesCompleted,
        [int]$PhasesBlocked,
        [int]$TotalNudges,
        [int]$TotalEscalations,
        [string]$StartTimeStr
    )

    $totalPhases = $PhasesCompleted + $PhasesBlocked
    $completionRate = if ($totalPhases -gt 0) { [math]::Round($PhasesCompleted / $totalPhases, 2) } else { 0.0 }

    $durationHours = 0.0
    if ($StartTimeStr) {
        try {
            $startTime = [datetime]::Parse($StartTimeStr)
            $duration = (Get-Date) - $startTime
            $durationHours = [math]::Round($duration.TotalHours, 2)
        }
        catch {
            Write-Warning "Could not parse start time: $StartTimeStr"
        }
    }

    return @{
        phases_completed = $PhasesCompleted
        phases_blocked = $PhasesBlocked
        total_nudges = $TotalNudges
        total_escalations = $TotalEscalations
        duration_hours = $durationHours
        completion_rate = $completionRate
    }
}

function Record-ToLearningDatabase {
    <#
    .SYNOPSIS
        Records cycle metrics to the historical learning database.
    .DESCRIPTION
        Calls the LearningDatabase.record_cycle_outcome() method via Python
        to persist cycle metrics for pattern analysis.
    #>
    param(
        [string]$CycleId,
        [hashtable]$Metrics
    )

    if ($DryRun) {
        Write-Status "[DryRun] Would record to learning database: $CycleId" -Color Yellow
        return $true
    }

    try {
        $metricsJson = $Metrics | ConvertTo-Json -Compress
        $learningDbPathEscaped = $LearningDbPath -replace '\\', '/'

        $pythonScript = @"
import sys
import json
sys.path.insert(0, 'src')
from pathlib import Path
from autopack.memory.learning_db import LearningDatabase

cycle_id = '$CycleId'
metrics = json.loads('$($metricsJson -replace "'", "''")')
db_path = Path('$learningDbPathEscaped')

db = LearningDatabase(db_path)
success = db.record_cycle_outcome(cycle_id, metrics)
print('OK' if success else 'FAILED')
"@

        $env:PYTHONPATH = "src"
        $result = $pythonScript | python 2>&1

        if ($result -eq "OK") {
            Write-Status "Recorded cycle metrics to learning database" -Color Green
            return $true
        }
        else {
            Write-Warning "Failed to record to learning database: $result"
            return $false
        }
    }
    catch {
        Write-Warning "Error recording to learning database: $_"
        return $false
    }
}

function Show-QueueStatus {
    <#
    .SYNOPSIS
        Displays the current queue status.
    #>
    $queue = Read-ProjectQueue

    Write-Status "=== Project Queue Status ===" -Color Magenta
    Write-Host ""

    if ($queue.current_project) {
        Write-Status "Current Project:" -Color Green
        Write-Host "  ID: $($queue.current_project.id)"
        Write-Host "  Name: $($queue.current_project.name)"
        Write-Host "  Started: $($queue.current_project.started_at)"
    }
    else {
        Write-Status "No project currently in progress" -Color Yellow
    }

    Write-Host ""
    Write-Status "Queued Projects: $($queue.queued_projects.Count)" -Color Cyan
    foreach ($proj in $queue.queued_projects) {
        Write-Host "  - [$($proj.id)] $($proj.name)"
    }

    Write-Host ""
    Write-Status "Completed Projects: $($queue.completed_projects.Count)" -Color Cyan

    # Show last 5 completed with metrics
    $recentCompleted = $queue.completed_projects | Select-Object -Last 5
    foreach ($proj in $recentCompleted) {
        $metrics = $proj.metrics
        if ($metrics) {
            Write-Host "  - [$($proj.id)] $($proj.name) (completion: $([math]::Round($metrics.completion_rate * 100, 0))%)"
        }
        else {
            Write-Host "  - [$($proj.id)] $($proj.name)"
        }
    }
}

function Get-NextProject {
    <#
    .SYNOPSIS
        Triggers the next queued project.
    #>
    $queue = Read-ProjectQueue

    if ($queue.current_project) {
        Write-Warning "A project is already in progress: $($queue.current_project.id)"
        Write-Warning "Complete it first with: -Action complete -ProjectId $($queue.current_project.id)"
        return
    }

    if ($queue.queued_projects.Count -eq 0) {
        Write-Status "No projects in queue" -Color Yellow
        return
    }

    # Pop the first project from the queue
    $nextProject = $queue.queued_projects[0]
    $queue.queued_projects = @($queue.queued_projects | Select-Object -Skip 1)

    # Set as current project with start time
    $nextProject | Add-Member -NotePropertyName "started_at" -NotePropertyValue (Get-Date -Format "o") -Force
    $queue.current_project = $nextProject

    if ($DryRun) {
        Write-Status "[DryRun] Would start project: $($nextProject.id) - $($nextProject.name)" -Color Yellow
    }
    else {
        Save-ProjectQueue -Queue $queue
        Write-Status "Started project: $($nextProject.id) - $($nextProject.name)" -Color Green
        Write-Status "Started at: $($nextProject.started_at)"
    }

    return $nextProject
}

function Complete-Project {
    <#
    .SYNOPSIS
        Marks a project as complete and captures cycle metrics.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$ProjectId
    )

    $queue = Read-ProjectQueue

    # Check if this is the current project
    if (-not $queue.current_project -or $queue.current_project.id -ne $ProjectId) {
        Write-Error "Project '$ProjectId' is not the current project"
        if ($queue.current_project) {
            Write-Status "Current project is: $($queue.current_project.id)"
        }
        return
    }

    $project = $queue.current_project

    # Calculate metrics
    $startTimeStr = if ($project.started_at) { $project.started_at } else { $StartTime }
    $metrics = Calculate-CycleMetrics -PhasesCompleted $PhasesCompleted -PhasesBlocked $PhasesBlocked `
        -TotalNudges $TotalNudges -TotalEscalations $TotalEscalations -StartTimeStr $startTimeStr

    Write-Status "=== Cycle Metrics ===" -Color Magenta
    Write-Host "  Phases Completed: $($metrics.phases_completed)"
    Write-Host "  Phases Blocked: $($metrics.phases_blocked)"
    Write-Host "  Total Nudges: $($metrics.total_nudges)"
    Write-Host "  Total Escalations: $($metrics.total_escalations)"
    Write-Host "  Duration (hours): $($metrics.duration_hours)"
    Write-Host "  Completion Rate: $([math]::Round($metrics.completion_rate * 100, 0))%"

    # Add metrics and completion time to project
    $project | Add-Member -NotePropertyName "completed_at" -NotePropertyValue (Get-Date -Format "o") -Force
    $project | Add-Member -NotePropertyName "metrics" -NotePropertyValue $metrics -Force

    # Move to completed projects
    $queue.completed_projects += $project
    $queue.current_project = $null

    if ($DryRun) {
        Write-Status "[DryRun] Would complete project: $ProjectId" -Color Yellow
    }
    else {
        Save-ProjectQueue -Queue $queue
        Write-Status "Completed project: $ProjectId" -Color Green

        # Record to learning database
        $cycleId = "cycle_$ProjectId_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Record-ToLearningDatabase -CycleId $cycleId -Metrics $metrics
    }

    # Check if there's a next project to trigger
    if ($queue.queued_projects.Count -gt 0) {
        Write-Host ""
        Write-Status "Next project in queue: $($queue.queued_projects[0].id) - $($queue.queued_projects[0].name)" -Color Cyan
        Write-Status "Run with '-Action next' to start it"
    }
}

function Add-Project {
    <#
    .SYNOPSIS
        Adds a new project to the queue.
    #>
    param(
        [string]$Name,
        [string]$Description
    )

    if (-not $Name) {
        Write-Error "Project name is required (-ProjectName)"
        return
    }

    $queue = Read-ProjectQueue

    # Generate project ID
    $projectNumber = $queue.completed_projects.Count + $queue.queued_projects.Count + 1
    if ($queue.current_project) { $projectNumber++ }
    $projectId = "proj-$('{0:D3}' -f $projectNumber)"

    $newProject = @{
        id = $projectId
        name = $Name
        description = if ($Description) { $Description } else { "" }
        created_at = (Get-Date -Format "o")
    }

    $queue.queued_projects += $newProject

    if ($DryRun) {
        Write-Status "[DryRun] Would add project: $projectId - $Name" -Color Yellow
    }
    else {
        Save-ProjectQueue -Queue $queue
        Write-Status "Added project to queue: $projectId - $Name" -Color Green
    }
}

function List-Projects {
    <#
    .SYNOPSIS
        Lists all projects with their metrics.
    #>
    $queue = Read-ProjectQueue

    Write-Status "=== All Projects ===" -Color Magenta
    Write-Host ""

    Write-Host "--- Current ---" -ForegroundColor Yellow
    if ($queue.current_project) {
        Write-Host "  [$($queue.current_project.id)] $($queue.current_project.name)"
        Write-Host "    Started: $($queue.current_project.started_at)"
    }
    else {
        Write-Host "  (none)"
    }

    Write-Host ""
    Write-Host "--- Queued ($($queue.queued_projects.Count)) ---" -ForegroundColor Cyan
    foreach ($proj in $queue.queued_projects) {
        Write-Host "  [$($proj.id)] $($proj.name)"
    }

    Write-Host ""
    Write-Host "--- Completed ($($queue.completed_projects.Count)) ---" -ForegroundColor Green
    foreach ($proj in $queue.completed_projects) {
        $m = $proj.metrics
        if ($m) {
            $completionPct = [math]::Round($m.completion_rate * 100, 0)
            Write-Host "  [$($proj.id)] $($proj.name)"
            Write-Host "    Completed: $($proj.completed_at)"
            Write-Host "    Metrics: phases=$($m.phases_completed)/$($m.phases_completed + $m.phases_blocked), nudges=$($m.total_nudges), escalations=$($m.total_escalations), duration=$($m.duration_hours)h, completion=$completionPct%"
        }
        else {
            Write-Host "  [$($proj.id)] $($proj.name) (no metrics)"
        }
    }
}

# Main execution
function Main {
    Write-Status "Project Queue Manager (IMP-MEM-002)" -Color Cyan
    Write-Status "Action: $Action | DryRun: $DryRun"
    Write-Host ""

    switch ($Action) {
        "status" {
            Show-QueueStatus
        }
        "next" {
            Get-NextProject
        }
        "complete" {
            if (-not $ProjectId) {
                Write-Error "ProjectId is required for 'complete' action"
                return
            }
            Complete-Project -ProjectId $ProjectId
        }
        "add" {
            Add-Project -Name $ProjectName -Description $ProjectDescription
        }
        "list" {
            List-Projects
        }
    }

    Write-Host ""
    Write-Status "Done" -Color Green
}

# Run main
Main
