<#
.SYNOPSIS
    Triggers Autopack project generation phases with optional telemetry context.

.DESCRIPTION
    Orchestrates Phase 1 (discovery) and Phase 2 (wave planning) of the Autopack
    improvement workflow. When -UseTelemetryContext is enabled, aggregates historical
    telemetry data before Phase 1 to enable informed prioritization.

.PARAMETER UseTelemetryContext
    When enabled, runs telemetry_aggregator.py to generate TELEMETRY_SUMMARY.json
    and includes LEARNING_MEMORY.json paths in the prompt context for adaptive
    discovery and wave planning.

.PARAMETER TelemetryBasePath
    Base directory containing telemetry state files (nudge_state.json, ci_retry_state.json,
    slot_history.json). Defaults to ".autopack" in the current directory.

.PARAMETER LearningMemoryPath
    Path to the LEARNING_MEMORY.json file containing historical success/failure patterns.
    Defaults to ".autopack/LEARNING_MEMORY.json".

.PARAMETER OutputPath
    Path where TELEMETRY_SUMMARY.json will be written.
    Defaults to ".autopack/TELEMETRY_SUMMARY.json".

.PARAMETER Phase
    Which phase to trigger: "phase1", "phase2", or "all" (both phases).
    Defaults to "all".

.PARAMETER CarryoverContextPath
    Path where CARRYOVER_CONTEXT.json will be written when previous cycle data exists.
    Defaults to the user's Desktop folder.

.PARAMETER ImpsMasterPath
    Path to the AUTOPACK_IMPS_MASTER.json file containing previous cycle improvements.
    Defaults to the user's Desktop folder.

.PARAMETER DryRun
    When enabled, shows what would be done without executing telemetry aggregation.

.EXAMPLE
    .\trigger_project_generation.ps1 -UseTelemetryContext
    Runs both phases with telemetry context enabled.

.EXAMPLE
    .\trigger_project_generation.ps1 -Phase phase1 -UseTelemetryContext
    Runs only Phase 1 with telemetry context.

.EXAMPLE
    .\trigger_project_generation.ps1 -DryRun
    Shows what would be executed without running anything.

.NOTES
    IMP-GEN-001: Telemetry-Informed Task Generation
    Enables Phase 1 and Phase 2 to use historical telemetry for adaptive
    discovery prioritization and wave planning.
#>

param(
    [switch]$UseTelemetryContext,

    [string]$TelemetryBasePath = ".autopack",

    [string]$LearningMemoryPath = ".autopack/LEARNING_MEMORY.json",

    [string]$OutputPath = ".autopack/TELEMETRY_SUMMARY.json",

    [ValidateSet("phase1", "phase2", "all")]
    [string]$Phase = "all",

    [string]$CarryoverContextPath = "$env:USERPROFILE\OneDrive\Backup\Desktop\CARRYOVER_CONTEXT.json",

    [string]$ImpsMasterPath = "$env:USERPROFILE\OneDrive\Backup\Desktop\AUTOPACK_IMPS_MASTER.json",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Script configuration - determine project root
# If script is at project root, use current location
# If script is in a subdirectory, go up to find project root
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

# Resolve paths relative to project root
$TelemetryBasePath = Join-Path $ProjectRoot $TelemetryBasePath
$LearningMemoryPath = Join-Path $ProjectRoot $LearningMemoryPath
$OutputPath = Join-Path $ProjectRoot $OutputPath
$TelemetryAggregatorPath = Join-Path $ProjectRoot "scripts/utility/telemetry_aggregator.py"

function Write-Status {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "[Trigger] $Message" -ForegroundColor $Color
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[Warning] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[Error] $Message" -ForegroundColor Red
}

function Test-TelemetryFiles {
    <#
    .SYNOPSIS
        Validates that required telemetry files exist.
    #>
    $filesExist = @{
        TelemetryBasePath = Test-Path $TelemetryBasePath
        LearningMemoryPath = Test-Path $LearningMemoryPath
        TelemetryAggregator = Test-Path $TelemetryAggregatorPath
    }

    return $filesExist
}

function Invoke-TelemetryAggregation {
    <#
    .SYNOPSIS
        Runs the telemetry aggregator to generate TELEMETRY_SUMMARY.json.
    #>
    Write-Status "Running telemetry aggregation..."

    if ($DryRun) {
        Write-Status "[DryRun] Would execute: python `"$TelemetryAggregatorPath`" --base-path `"$TelemetryBasePath`" --output `"$OutputPath`"" -Color Yellow
        return $true
    }

    # Ensure output directory exists
    $outputDir = Split-Path -Parent $OutputPath
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }

    try {
        $result = & python $TelemetryAggregatorPath --base-path $TelemetryBasePath --output $OutputPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Telemetry aggregation returned non-zero exit code: $LASTEXITCODE"
            Write-Warning "Output: $result"
            return $false
        }
        Write-Status "Telemetry summary generated at: $OutputPath" -Color Green
        return $true
    }
    catch {
        Write-Warning "Failed to run telemetry aggregator: $_"
        return $false
    }
}

function Get-TelemetryContextPaths {
    <#
    .SYNOPSIS
        Returns the paths to telemetry context files for inclusion in prompts.
    #>
    $context = @{
        LearningMemoryPath = $null
        TelemetrySummaryPath = $null
        HasContext = $false
    }

    if (Test-Path $LearningMemoryPath) {
        $context.LearningMemoryPath = $LearningMemoryPath
    }

    if (Test-Path $OutputPath) {
        $context.TelemetrySummaryPath = $OutputPath
    }

    $context.HasContext = ($null -ne $context.LearningMemoryPath) -or ($null -ne $context.TelemetrySummaryPath)

    return $context
}

function Get-CarryoverContext {
    <#
    .SYNOPSIS
        Checks for existing cycle data and creates carryover context for Phase 1.
    .DESCRIPTION
        IMP-FEAT-001: Discovery Cycle Carryover
        When AUTOPACK_IMPS_MASTER.json exists from a previous cycle, extracts
        unimplemented improvements and creates CARRYOVER_CONTEXT.json for
        incorporation into the next Discovery cycle.
    #>
    $context = @{
        HasCarryover = $false
        CarryoverPath = $null
        ItemCount = 0
    }

    if (-not (Test-Path $ImpsMasterPath)) {
        Write-Status "No previous cycle data found at: $ImpsMasterPath" -Color Yellow
        return $context
    }

    try {
        $existingImps = Get-Content $ImpsMasterPath -Raw | ConvertFrom-Json

        # Check if unimplemented_imps array exists and has items
        if (-not $existingImps.unimplemented_imps -or $existingImps.unimplemented_imps.Count -eq 0) {
            Write-Status "No unimplemented improvements to carry over" -Color Yellow
            return $context
        }

        # Create carryover context with source cycle info
        $carryover = @{
            source_cycle = "Discovery_Cycle_$(Get-Date -Format 'yyyy-MM-dd')"
            created_at = (Get-Date -Format "o")
            unimplemented_imps = @()
        }

        # Process each unimplemented improvement, adding carryover_from field
        foreach ($imp in $existingImps.unimplemented_imps) {
            # Convert to hashtable for modification
            $impHash = @{}
            $imp.PSObject.Properties | ForEach-Object {
                $impHash[$_.Name] = $_.Value
            }
            $impHash["carryover_from"] = "previous_cycle"
            $carryover.unimplemented_imps += $impHash
        }

        if ($DryRun) {
            Write-Status "[DryRun] Would create carryover context with $($carryover.unimplemented_imps.Count) items at: $CarryoverContextPath" -Color Yellow
        }
        else {
            # Write carryover context to file
            $carryover | ConvertTo-Json -Depth 10 | Set-Content $CarryoverContextPath -Encoding UTF8
            Write-Status "Created carryover context with $($carryover.unimplemented_imps.Count) items" -Color Green
        }

        $context.HasCarryover = $true
        $context.CarryoverPath = $CarryoverContextPath
        $context.ItemCount = $carryover.unimplemented_imps.Count

        return $context
    }
    catch {
        Write-Warning "Failed to process carryover context: $_"
        return $context
    }
}

function Build-Phase1Prompt {
    <#
    .SYNOPSIS
        Constructs the Phase 1 discovery prompt with optional telemetry context.
    #>
    param(
        [hashtable]$TelemetryContext,
        [hashtable]$CarryoverContext = @{ HasCarryover = $false }
    )

    $prompt = "@phase1"

    if ($UseTelemetryContext -and $TelemetryContext.HasContext) {
        $contextLines = @()
        $contextLines += ""
        $contextLines += "## Telemetry Context (IMP-GEN-001)"
        $contextLines += ""

        if ($TelemetryContext.LearningMemoryPath) {
            $contextLines += "LEARNING_MEMORY: $($TelemetryContext.LearningMemoryPath)"
            $contextLines += "- Contains historical success_patterns and failure_patterns"
            $contextLines += "- Use to prioritize improvements with proven success rates"
            $contextLines += "- De-prioritize improvement types with high failure rates"
        }

        if ($TelemetryContext.TelemetrySummaryPath) {
            $contextLines += ""
            $contextLines += "TELEMETRY_SUMMARY: $($TelemetryContext.TelemetrySummaryPath)"
            $contextLines += "- Contains aggregated metrics from recent cycles"
            $contextLines += "- Includes completion_time_metrics per improvement category"
            $contextLines += "- Use to inform realistic wave sizing"
        }

        $prompt += "`n" + ($contextLines -join "`n")
    }

    # Add carryover context if available (IMP-FEAT-001)
    if ($CarryoverContext.HasCarryover) {
        $carryoverLines = @()
        $carryoverLines += ""
        $carryoverLines += "## Carryover Context (IMP-FEAT-001)"
        $carryoverLines += ""
        $carryoverLines += "CARRYOVER_CONTEXT: $($CarryoverContext.CarryoverPath)"
        $carryoverLines += "- Contains $($CarryoverContext.ItemCount) unimplemented improvements from previous cycle"
        $carryoverLines += "- Each item has 'carryover_from' field set to 'previous_cycle'"
        $carryoverLines += "- Prioritize carryover items that have been waiting longest"
        $carryoverLines += "- Preserve carryover_from field when incorporating into new cycle"
        $prompt += "`n" + ($carryoverLines -join "`n")
    }

    return $prompt
}

function Build-Phase2Prompt {
    <#
    .SYNOPSIS
        Constructs the Phase 2 wave planning prompt with optional telemetry context.
    #>
    param([hashtable]$TelemetryContext)

    $prompt = "@phase2"

    if ($UseTelemetryContext -and $TelemetryContext.HasContext) {
        $contextLines = @()
        $contextLines += ""
        $contextLines += "## Telemetry Context (IMP-GEN-001)"
        $contextLines += ""

        if ($TelemetryContext.LearningMemoryPath) {
            $contextLines += "LEARNING_MEMORY: $($TelemetryContext.LearningMemoryPath)"
            $contextLines += "- Check success_patterns for wave grouping insights"
            $contextLines += "- Adjust wave sizes based on historical completion rates"
            $contextLines += "- Consider improvement_outcomes for dependency ordering"
        }

        if ($TelemetryContext.TelemetrySummaryPath) {
            $contextLines += ""
            $contextLines += "TELEMETRY_SUMMARY: $($TelemetryContext.TelemetrySummaryPath)"
            $contextLines += "- Use completion_time_metrics to balance wave load"
            $contextLines += "- Consider escalation_frequency for risk assessment"
        }

        $prompt += "`n" + ($contextLines -join "`n")
    }

    return $prompt
}

function Invoke-Phase1 {
    <#
    .SYNOPSIS
        Triggers Phase 1 discovery with optional telemetry and carryover context.
    #>
    param(
        [hashtable]$TelemetryContext,
        [hashtable]$CarryoverContext = @{ HasCarryover = $false }
    )

    Write-Status "=== Phase 1: Discovery ===" -Color Magenta

    $prompt = Build-Phase1Prompt -TelemetryContext $TelemetryContext -CarryoverContext $CarryoverContext

    if ($DryRun) {
        Write-Status "[DryRun] Would send prompt:" -Color Yellow
        Write-Host $prompt
        return
    }

    Write-Status "Phase 1 prompt constructed with telemetry context: $($TelemetryContext.HasContext)"
    Write-Host ""
    Write-Host "--- Phase 1 Prompt ---" -ForegroundColor Gray
    Write-Host $prompt
    Write-Host "--- End Prompt ---" -ForegroundColor Gray
    Write-Host ""

    # Note: Actual Cursor invocation would happen here in a real implementation
    # For now, we output the prompt that should be sent to Cursor
    Write-Status "Phase 1 prompt ready for Cursor submission" -Color Green
}

function Invoke-Phase2 {
    <#
    .SYNOPSIS
        Triggers Phase 2 wave planning with optional telemetry context.
    #>
    param([hashtable]$TelemetryContext)

    Write-Status "=== Phase 2: Wave Planning ===" -Color Magenta

    $prompt = Build-Phase2Prompt -TelemetryContext $TelemetryContext

    if ($DryRun) {
        Write-Status "[DryRun] Would send prompt:" -Color Yellow
        Write-Host $prompt
        return
    }

    Write-Status "Phase 2 prompt constructed with telemetry context: $($TelemetryContext.HasContext)"
    Write-Host ""
    Write-Host "--- Phase 2 Prompt ---" -ForegroundColor Gray
    Write-Host $prompt
    Write-Host "--- End Prompt ---" -ForegroundColor Gray
    Write-Host ""

    # Note: Actual Cursor invocation would happen here in a real implementation
    Write-Status "Phase 2 prompt ready for Cursor submission" -Color Green
}

# Main execution
function Main {
    Write-Status "Autopack Project Generation Trigger" -Color Cyan
    Write-Status "Phase: $Phase | UseTelemetryContext: $UseTelemetryContext | DryRun: $DryRun"
    Write-Host ""

    # Validate environment
    $fileStatus = Test-TelemetryFiles
    if ($UseTelemetryContext) {
        if (-not $fileStatus.TelemetryAggregator) {
            Write-Warning "Telemetry aggregator not found at: $TelemetryAggregatorPath"
            Write-Warning "Continuing without telemetry aggregation..."
        }
    }

    # Run telemetry aggregation if enabled
    $telemetryContext = @{ HasContext = $false }
    if ($UseTelemetryContext) {
        Write-Status "Telemetry context enabled - aggregating historical data..."

        if ($fileStatus.TelemetryAggregator) {
            $aggregationSuccess = Invoke-TelemetryAggregation
            if (-not $aggregationSuccess) {
                Write-Warning "Telemetry aggregation failed - proceeding without fresh summary"
            }
        }

        $telemetryContext = Get-TelemetryContextPaths
        if ($telemetryContext.HasContext) {
            Write-Status "Telemetry context files found:" -Color Green
            if ($telemetryContext.LearningMemoryPath) {
                Write-Status "  - LEARNING_MEMORY: $($telemetryContext.LearningMemoryPath)"
            }
            if ($telemetryContext.TelemetrySummaryPath) {
                Write-Status "  - TELEMETRY_SUMMARY: $($telemetryContext.TelemetrySummaryPath)"
            }
        }
        else {
            Write-Warning "No telemetry context files found - proceeding without historical data"
        }
        Write-Host ""
    }

    # Check for carryover context from previous cycle (IMP-FEAT-001)
    $carryoverContext = @{ HasCarryover = $false }
    if ($Phase -eq "phase1" -or $Phase -eq "all") {
        Write-Status "Checking for previous cycle carryover data..."
        $carryoverContext = Get-CarryoverContext
        if ($carryoverContext.HasCarryover) {
            Write-Status "Carryover context prepared:" -Color Green
            Write-Status "  - Items to carry over: $($carryoverContext.ItemCount)"
            Write-Status "  - Context file: $($carryoverContext.CarryoverPath)"
        }
        Write-Host ""
    }

    # Execute requested phases
    switch ($Phase) {
        "phase1" {
            Invoke-Phase1 -TelemetryContext $telemetryContext -CarryoverContext $carryoverContext
        }
        "phase2" {
            Invoke-Phase2 -TelemetryContext $telemetryContext
        }
        "all" {
            Invoke-Phase1 -TelemetryContext $telemetryContext -CarryoverContext $carryoverContext
            Write-Host ""
            Invoke-Phase2 -TelemetryContext $telemetryContext
        }
    }

    Write-Host ""
    Write-Status "Generation trigger complete" -Color Green
}

# Run main
Main
