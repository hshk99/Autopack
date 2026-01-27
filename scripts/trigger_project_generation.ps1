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

.PARAMETER UseAutonomousDiscovery
    When enabled, runs autonomous_discovery.py to automatically identify improvement
    opportunities from failure patterns, optimization suggestions, and metrics anomalies.
    This enhances Phase 1 with data-driven IMP suggestions.

.PARAMETER UseAutonomousWavePlanning
    When enabled, runs autonomous_wave_planner.py to automatically group discovered IMPs
    into optimal waves based on dependencies and file conflicts, maximizing parallelization.
    This enhances Phase 2 with automated wave planning.

.PARAMETER UsePriorityEngine
    When enabled, runs the data-driven priority engine to rank improvements based on
    historical success rates, blocking patterns, and complexity estimates. This enables
    the memory->task_generation link in the self-improvement loop (IMP-TGN-001).

.PARAMETER PriorityEngineOutputPath
    Path where PRIORITY_RANKED_IMPS.json will be written when using the priority engine.
    Defaults to ".autopack/PRIORITY_RANKED_IMPS.json".

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

    [switch]$DryRun,

    [switch]$UseAutonomousDiscovery,

    [switch]$UseAutonomousWavePlanning,

    [switch]$UseDiscoveryContextInjection,

    [string]$DiscoveryContextOutputPath = "$env:USERPROFILE\OneDrive\Backup\Desktop\DISCOVERY_CONTEXT.json",

    [switch]$UseTelemetryFeedbackLoop,

    [string]$TelemetryFeedbackOutputPath = "$env:USERPROFILE\OneDrive\Backup\Desktop\TELEMETRY_FEEDBACK.json",

    [switch]$UsePriorityEngine,

    [string]$PriorityEngineOutputPath = ".autopack/PRIORITY_RANKED_IMPS.json"
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
$AutonomousDiscoveryOutputPath = Join-Path $ProjectRoot ".autopack/DISCOVERED_IMPS.json"
$AutonomousWavePlanOutputPath = Join-Path $ProjectRoot ".autopack/WAVE_PLAN.json"
$ContextInjectorPath = Join-Path $ProjectRoot "src/discovery/context_injector.py"
$PriorityEngineOutputPath = Join-Path $ProjectRoot $PriorityEngineOutputPath
$LearningDbPath = Join-Path $ProjectRoot ".autopack/learning_db.json"

function Write-Status {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "[Trigger] $Message" -ForegroundColor $Color
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

function Invoke-AutonomousDiscovery {
    <#
    .SYNOPSIS
        Runs the autonomous discovery module to identify improvement opportunities.
    .DESCRIPTION
        IMP-GEN-001: Autonomous Phase 1 Discovery
        Analyzes failure patterns, optimization suggestions, and metrics anomalies
        to automatically identify potential improvements.
    #>
    Write-Status "Running autonomous discovery..."

    if ($DryRun) {
        Write-Status "[DryRun] Would execute: python -c 'from generation.autonomous_discovery import AutonomousDiscovery; ...'" -Color Yellow
        return @{ HasDiscovery = $false; DiscoveryPath = $null; ImpCount = 0 }
    }

    try {
        $pythonScript = @"
import sys
sys.path.insert(0, 'src')
from generation.autonomous_discovery import AutonomousDiscovery
from memory.metrics_db import MetricsDatabase
from memory.failure_analyzer import FailureAnalyzer
from feedback.optimization_detector import OptimizationDetector

db = MetricsDatabase('data/metrics_history.db')
analyzer = FailureAnalyzer(db)
detector = OptimizationDetector(db)

discovery = AutonomousDiscovery(
    metrics_db=db,
    failure_analyzer=analyzer,
    optimization_detector=detector
)
imps = discovery.discover_all()
discovery.export_to_json('$($AutonomousDiscoveryOutputPath -replace '\\', '/')')
print(len(imps))
"@
        $result = $pythonScript | python 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Autonomous discovery returned non-zero exit code: $LASTEXITCODE"
            Write-Warning "Output: $result"
            return @{ HasDiscovery = $false; DiscoveryPath = $null; ImpCount = 0 }
        }

        $impCount = [int]$result
        Write-Status "Autonomous discovery found $impCount potential improvements" -Color Green
        Write-Status "Output: $AutonomousDiscoveryOutputPath" -Color Green

        # Log the autonomous discovery decision (IMP-LOG-001)
        Write-DecisionLog -DecisionType "autonomous_discovery" -Context @{
            imp_count = $impCount
            output_path = $AutonomousDiscoveryOutputPath
            sources = "failure_patterns,optimization_suggestions,metrics_anomalies"
        } -OptionsConsidered @("discover_from_failures", "discover_from_optimizations", "discover_from_anomalies", "discover_all") `
          -ChosenOption "discover_all" `
          -Reasoning "Ran comprehensive discovery from all sources, found $impCount improvements"

        return @{
            HasDiscovery = $true
            DiscoveryPath = $AutonomousDiscoveryOutputPath
            ImpCount = $impCount
        }
    }
    catch {
        Write-Warning "Failed to run autonomous discovery: $_"
        return @{ HasDiscovery = $false; DiscoveryPath = $null; ImpCount = 0 }
    }
}

function Invoke-AutonomousWavePlanning {
    <#
    .SYNOPSIS
        Runs the autonomous wave planner to group IMPs into optimal waves.
    .DESCRIPTION
        IMP-GEN-002: Autonomous Phase 2 Wave Planning
        Takes discovered IMPs and groups them into waves based on dependencies
        and file conflicts, maximizing parallelization potential.
    .PARAMETER DiscoveredImpsPath
        Path to the DISCOVERED_IMPS.json file from Phase 1 discovery.
    #>
    param(
        [string]$DiscoveredImpsPath
    )

    Write-Status "Running autonomous wave planning..."

    if ($DryRun) {
        Write-Status "[DryRun] Would execute: python -c 'from generation.autonomous_wave_planner import AutonomousWavePlanner; ...'" -Color Yellow
        return @{ HasWavePlan = $false; WavePlanPath = $null; WaveCount = 0; ImpCount = 0 }
    }

    if (-not (Test-Path $DiscoveredImpsPath)) {
        Write-Warning "Discovered IMPs file not found at: $DiscoveredImpsPath"
        Write-Warning "Run Phase 1 with -UseAutonomousDiscovery first"
        return @{ HasWavePlan = $false; WavePlanPath = $null; WaveCount = 0; ImpCount = 0 }
    }

    try {
        $pythonScript = @"
import sys
import json
sys.path.insert(0, 'src')
from generation.autonomous_wave_planner import AutonomousWavePlanner

# Load discovered IMPs
with open('$($DiscoveredImpsPath -replace '\\', '/')') as f:
    data = json.load(f)

imps = data.get('imps', [])
if not imps:
    print('0,0')
else:
    planner = AutonomousWavePlanner(imps)
    planner.export_wave_plan('$($AutonomousWavePlanOutputPath -replace '\\', '/')')
    plan = planner.plan_waves()
    print(f'{len(plan.waves)},{sum(len(ids) for ids in plan.waves.values())}')
"@
        $result = $pythonScript | python 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Autonomous wave planning returned non-zero exit code: $LASTEXITCODE"
            Write-Warning "Output: $result"
            return @{ HasWavePlan = $false; WavePlanPath = $null; WaveCount = 0; ImpCount = 0 }
        }

        $parts = $result.Split(',')
        $waveCount = [int]$parts[0]
        $impCount = [int]$parts[1]

        if ($waveCount -eq 0) {
            Write-Warning "No IMPs to plan waves for"
            return @{ HasWavePlan = $false; WavePlanPath = $null; WaveCount = 0; ImpCount = 0 }
        }

        Write-Status "Autonomous wave planning grouped $impCount IMPs into $waveCount waves" -Color Green
        Write-Status "Output: $AutonomousWavePlanOutputPath" -Color Green

        # Log the wave planning decision (IMP-LOG-001)
        Write-DecisionLog -DecisionType "wave_planning" -Context @{
            wave_count = $waveCount
            imp_count = $impCount
            output_path = $AutonomousWavePlanOutputPath
            discovered_imps_path = $DiscoveredImpsPath
        } -OptionsConsidered @("single_wave", "dependency_based_waves", "parallel_optimized_waves") `
          -ChosenOption "parallel_optimized_waves" `
          -Reasoning "Grouped $impCount IMPs into $waveCount waves optimized for maximum parallelization based on dependencies and file conflicts"

        return @{
            HasWavePlan = $true
            WavePlanPath = $AutonomousWavePlanOutputPath
            WaveCount = $waveCount
            ImpCount = $impCount
        }
    }
    catch {
        Write-Warning "Failed to run autonomous wave planning: $_"
        return @{ HasWavePlan = $false; WavePlanPath = $null; WaveCount = 0; ImpCount = 0 }
    }
}

function Invoke-PriorityEngine {
    <#
    .SYNOPSIS
        Runs the data-driven priority engine to rank improvements.
    .DESCRIPTION
        IMP-TGN-001: Data-Driven Task Prioritization
        Uses historical learning data to prioritize improvements based on:
        - Category success rates (past outcomes)
        - Blocking pattern detection
        - Complexity estimation
        This enables the memory->task_generation link in the self-improvement loop.
    .PARAMETER ImpsToRank
        Path to JSON file containing improvements to rank, or array of improvements.
    #>
    param(
        [string]$ImpsToRank = $null
    )

    Write-Status "Running data-driven priority engine..."

    if ($DryRun) {
        Write-Status "[DryRun] Would execute: python -c 'from autopack.task_generation.priority_engine import PriorityEngine; ...'" -Color Yellow
        return @{ HasPriorityRanking = $false; RankedImpsPath = $null; ImpCount = 0 }
    }

    try {
        $learningDbPath = $LearningDbPath -replace '\\', '/'
        $outputPath = $PriorityEngineOutputPath -replace '\\', '/'
        $impsMasterPath = $ImpsMasterPath -replace '\\', '/'

        $pythonScript = @"
import sys
import json
sys.path.insert(0, 'src')
from pathlib import Path
from autopack.task_generation.priority_engine import PriorityEngine
from autopack.memory.learning_db import LearningDatabase

# Initialize learning database
db_path = Path('$learningDbPath')
learning_db = LearningDatabase(db_path)

# Initialize priority engine
engine = PriorityEngine(learning_db)

# Load improvements to rank
imps_path = Path('$impsMasterPath')
if imps_path.exists():
    with open(imps_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    imps = data.get('unimplemented_imps', [])
else:
    imps = []

if not imps:
    print(json.dumps({'ranked': [], 'count': 0, 'summary': {}}))
else:
    # Rank improvements by data-driven priority
    ranked = engine.rank_improvements(imps, include_scores=True)
    summary = engine.get_priority_summary(imps)

    # Export to output file
    output_path = Path('$outputPath')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'ranked_improvements': ranked,
            'summary': summary,
            'source_file': '$impsMasterPath'
        }, f, indent=2)

    result = {
        'ranked': [imp.get('imp_id', imp.get('id', 'unknown')) for imp in ranked[:5]],
        'count': len(ranked),
        'summary': {
            'total': summary.get('total_improvements', 0),
            'high_risk': len(summary.get('high_risk_items', []))
        }
    }
    print(json.dumps(result))
"@
        $result = $pythonScript | python 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Priority engine returned non-zero exit code: $LASTEXITCODE"
            Write-Warning "Output: $result"
            return @{ HasPriorityRanking = $false; RankedImpsPath = $null; ImpCount = 0 }
        }

        $priorityResult = $result | ConvertFrom-Json

        if ($priorityResult.count -gt 0) {
            Write-Status "Priority engine ranked $($priorityResult.count) improvements" -Color Green
            Write-Status "Top 5 by priority: $($priorityResult.ranked -join ', ')" -Color Green
            if ($priorityResult.summary.high_risk -gt 0) {
                Write-Status "High-risk items detected: $($priorityResult.summary.high_risk)" -Color Yellow
            }
            Write-Status "Output: $PriorityEngineOutputPath" -Color Green

            # Log the priority ranking decision (IMP-LOG-001)
            Write-DecisionLog -DecisionType "priority_ranking" -Context @{
                total_improvements = $priorityResult.count
                high_risk_items = $priorityResult.summary.high_risk
                output_path = $PriorityEngineOutputPath
                top_ranked = $priorityResult.ranked -join ','
            } -OptionsConsidered @("static_priority", "category_based", "data_driven_priority") `
              -ChosenOption "data_driven_priority" `
              -Reasoning "Ranked $($priorityResult.count) improvements using historical success rates and blocking patterns"
        }
        else {
            Write-Status "No improvements to rank" -Color Yellow
        }

        return @{
            HasPriorityRanking = $priorityResult.count -gt 0
            RankedImpsPath = $PriorityEngineOutputPath
            ImpCount = $priorityResult.count
            TopRanked = $priorityResult.ranked
            HighRiskCount = $priorityResult.summary.high_risk
        }
    }
    catch {
        Write-Warning "Failed to run priority engine: $_"
        return @{ HasPriorityRanking = $false; RankedImpsPath = $null; ImpCount = 0 }
    }
}

function Invoke-DiscoveryContextInjection {
    <#
    .SYNOPSIS
        Runs the context injector to gather telemetry insights for discovery.
    .DESCRIPTION
        IMP-LOOP-001: Feedback Loop from Outcomes to Discovery
        Analyzes telemetry events and decision logs to extract recurring issues,
        successful patterns, and failed approaches. Injects this context into
        Phase 1 discovery to enable informed prioritization.
    #>
    Write-Status "Running discovery context injection..."

    if ($DryRun) {
        Write-Status "[DryRun] Would execute: python -c 'from src.discovery.context_injector import ContextInjector; ...'" -Color Yellow
        return @{ HasContext = $false; ContextPath = $null }
    }

    if (-not (Test-Path $ContextInjectorPath)) {
        Write-Warning "Context injector not found at: $ContextInjectorPath"
        return @{ HasContext = $false; ContextPath = $null }
    }

    try {
        $pythonScript = @"
import sys
sys.path.insert(0, 'src')
from discovery.context_injector import ContextInjector

injector = ContextInjector(
    telemetry_path='.autopack/telemetry_events.json',
    decisions_path='.autopack/decisions_log.json'
)
context = injector.gather_context(lookback_days=30)
injector.inject_into_phase1(context, r'$($DiscoveryContextOutputPath -replace '\\', '/')')
print('OK')
"@
        $result = $pythonScript | python 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Discovery context injection returned non-zero exit code: $LASTEXITCODE"
            Write-Warning "Output: $result"
            return @{ HasContext = $false; ContextPath = $null }
        }

        Write-Status "Discovery context injected successfully" -Color Green
        Write-Status "Output: $DiscoveryContextOutputPath" -Color Green

        # Log the context injection decision (IMP-LOG-001)
        Write-DecisionLog -DecisionType "context_injection" -Context @{
            output_path = $DiscoveryContextOutputPath
            lookback_days = 30
            sources = "telemetry_events,decisions_log"
        } -OptionsConsidered @("no_context", "telemetry_only", "decisions_only", "full_context") `
          -ChosenOption "full_context" `
          -Reasoning "Injected full context from telemetry and decisions for informed discovery"

        return @{
            HasContext = $true
            ContextPath = $DiscoveryContextOutputPath
        }
    }
    catch {
        Write-Warning "Failed to run discovery context injection: $_"
        return @{ HasContext = $false; ContextPath = $null }
    }
}

function Invoke-TelemetryFeedbackLoop {
    <#
    .SYNOPSIS
        Runs the telemetry-to-discovery feedback loop.
    .DESCRIPTION
        IMP-TEL-003: Telemetry-to-Discovery Feedback Loop
        Analyzes telemetry from the previous cycle to automatically identify
        recurring issues as improvement candidates. This closes the self-improvement
        loop by feeding operational telemetry back into discovery phases.
    #>
    Write-Status "Running telemetry-to-discovery feedback loop..."

    if ($DryRun) {
        Write-Status "[DryRun] Would execute: python -c 'from src.telemetry_analyzer import TelemetryAnalyzer; ...'" -Color Yellow
        return @{ HasFeedback = $false; FeedbackPath = $null; ImprovementsAdded = 0 }
    }

    try {
        $feedbackOutputPath = $TelemetryFeedbackOutputPath -replace '\\', '/'
        $telemetryBasePath = $TelemetryBasePath -replace '\\', '/'
        $impsMasterPath = $ImpsMasterPath -replace '\\', '/'

        $pythonScript = @"
import sys
import json
sys.path.insert(0, 'src')
from telemetry_analyzer import TelemetryAnalyzer

# Initialize analyzer with telemetry base path
analyzer = TelemetryAnalyzer('$telemetryBasePath')

# Generate discovery input from telemetry patterns
discovery_input = analyzer.generate_discovery_input()

# Export discovery input for Phase 1 consumption
export_success = analyzer.export_discovery_input('$feedbackOutputPath')

# Also generate improvements and append to master file
try:
    improvements_added = analyzer.generate_improvements_to_master('$impsMasterPath')
except Exception as e:
    improvements_added = 0

# Output results
result = {
    'has_feedback': bool(discovery_input),
    'feedback_path': '$feedbackOutputPath' if export_success else None,
    'improvements_added': improvements_added,
    'patterns_analyzed': discovery_input[0].get('total_patterns_analyzed', 0) if discovery_input else 0,
    'recurring_issues': len(discovery_input[0].get('recurring_issues', [])) if discovery_input else 0,
    'recommendations': len(discovery_input[0].get('recommendations', [])) if discovery_input else 0
}
print(json.dumps(result))
"@
        $result = $pythonScript | python 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Telemetry feedback loop returned non-zero exit code: $LASTEXITCODE"
            Write-Warning "Output: $result"
            return @{ HasFeedback = $false; FeedbackPath = $null; ImprovementsAdded = 0 }
        }

        $feedbackResult = $result | ConvertFrom-Json

        if ($feedbackResult.has_feedback) {
            Write-Status "Telemetry feedback loop completed:" -Color Green
            Write-Status "  - Patterns analyzed: $($feedbackResult.patterns_analyzed)"
            Write-Status "  - Recurring issues found: $($feedbackResult.recurring_issues)"
            Write-Status "  - Recommendations generated: $($feedbackResult.recommendations)"
            Write-Status "  - Improvements added to master: $($feedbackResult.improvements_added)"
            Write-Status "  - Feedback file: $($feedbackResult.feedback_path)"

            # Log the feedback loop decision (IMP-LOG-001)
            Write-DecisionLog -DecisionType "telemetry_feedback_loop" -Context @{
                patterns_analyzed = $feedbackResult.patterns_analyzed
                recurring_issues = $feedbackResult.recurring_issues
                recommendations = $feedbackResult.recommendations
                improvements_added = $feedbackResult.improvements_added
                feedback_path = $feedbackResult.feedback_path
            } -OptionsConsidered @("skip_feedback", "analyze_patterns_only", "analyze_and_generate_improvements") `
              -ChosenOption "analyze_and_generate_improvements" `
              -Reasoning "Analyzed $($feedbackResult.patterns_analyzed) patterns, found $($feedbackResult.recurring_issues) recurring issues, added $($feedbackResult.improvements_added) improvements to master"
        }
        else {
            Write-Status "No telemetry patterns detected for feedback loop" -Color Yellow
        }

        return @{
            HasFeedback = $feedbackResult.has_feedback
            FeedbackPath = $feedbackResult.feedback_path
            ImprovementsAdded = $feedbackResult.improvements_added
            PatternsAnalyzed = $feedbackResult.patterns_analyzed
            RecurringIssues = $feedbackResult.recurring_issues
            Recommendations = $feedbackResult.recommendations
        }
    }
    catch {
        Write-Warning "Failed to run telemetry feedback loop: $_"
        return @{ HasFeedback = $false; FeedbackPath = $null; ImprovementsAdded = 0 }
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
        [hashtable]$CarryoverContext = @{ HasCarryover = $false },
        [hashtable]$DiscoveryContext = @{ HasDiscovery = $false },
        [hashtable]$InjectedContext = @{ HasContext = $false },
        [hashtable]$FeedbackLoopContext = @{ HasFeedback = $false },
        [hashtable]$PriorityContext = @{ HasPriorityRanking = $false }
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

    # Add autonomous discovery context if available (IMP-GEN-001)
    if ($DiscoveryContext.HasDiscovery) {
        $discoveryLines = @()
        $discoveryLines += ""
        $discoveryLines += "## Autonomous Discovery Context (IMP-GEN-001)"
        $discoveryLines += ""
        $discoveryLines += "DISCOVERED_IMPS: $($DiscoveryContext.DiscoveryPath)"
        $discoveryLines += "- Contains $($DiscoveryContext.ImpCount) automatically identified improvements"
        $discoveryLines += "- Sourced from failure patterns, optimization suggestions, and metrics anomalies"
        $discoveryLines += "- Review and incorporate high-confidence items into the improvement list"
        $discoveryLines += "- Each item includes confidence score and discovery source"
        $prompt += "`n" + ($discoveryLines -join "`n")
    }

    # Add injected context from telemetry feedback loop (IMP-LOOP-001)
    if ($InjectedContext.HasContext) {
        $injectedLines = @()
        $injectedLines += ""
        $injectedLines += "## Feedback Loop Context (IMP-LOOP-001)"
        $injectedLines += ""
        $injectedLines += "DISCOVERY_CONTEXT: $($InjectedContext.ContextPath)"
        $injectedLines += "- Contains recurring issues, successful patterns, and failed approaches"
        $injectedLines += "- Prioritize fixing any recurring_issues listed"
        $injectedLines += "- Focus discovery on high_value_categories"
        $injectedLines += "- Avoid approaches listed in failed_approaches"
        $injectedLines += "- Follow the recommendations provided"
        $prompt += "`n" + ($injectedLines -join "`n")
    }

    # Add telemetry-to-discovery feedback loop context (IMP-TEL-003)
    if ($FeedbackLoopContext.HasFeedback) {
        $feedbackLines = @()
        $feedbackLines += ""
        $feedbackLines += "## Telemetry Feedback Loop Context (IMP-TEL-003)"
        $feedbackLines += ""
        $feedbackLines += "TELEMETRY_FEEDBACK: $($FeedbackLoopContext.FeedbackPath)"
        $feedbackLines += "- Generated from analysis of $($FeedbackLoopContext.PatternsAnalyzed) telemetry patterns"
        $feedbackLines += "- Contains $($FeedbackLoopContext.RecurringIssues) recurring issues requiring attention"
        $feedbackLines += "- Includes $($FeedbackLoopContext.Recommendations) prioritized recommendations"
        if ($FeedbackLoopContext.ImprovementsAdded -gt 0) {
            $feedbackLines += "- Added $($FeedbackLoopContext.ImprovementsAdded) auto-discovered improvements to master file"
        }
        $feedbackLines += "- Review high_value_categories to focus discovery efforts"
        $feedbackLines += "- Address recurring_issues with highest occurrence counts first"
        $feedbackLines += "- Follow recommendations based on pattern analysis"
        $prompt += "`n" + ($feedbackLines -join "`n")
    }

    # Add data-driven priority ranking context (IMP-TGN-001)
    if ($PriorityContext.HasPriorityRanking) {
        $priorityLines = @()
        $priorityLines += ""
        $priorityLines += "## Data-Driven Priority Context (IMP-TGN-001)"
        $priorityLines += ""
        $priorityLines += "PRIORITY_RANKED_IMPS: $($PriorityContext.RankedImpsPath)"
        $priorityLines += "- Contains $($PriorityContext.ImpCount) improvements ranked by historical success likelihood"
        $priorityLines += "- Ranking considers: category success rates, blocking patterns, complexity estimates"
        if ($PriorityContext.TopRanked) {
            $priorityLines += "- Top priorities: $($PriorityContext.TopRanked -join ', ')"
        }
        if ($PriorityContext.HighRiskCount -gt 0) {
            $priorityLines += "- WARNING: $($PriorityContext.HighRiskCount) items flagged as high-risk for blocking"
            $priorityLines += "- Review high_risk_items in the file for potential blockers"
        }
        $priorityLines += "- Use recommended_order to sequence wave assignments"
        $priorityLines += "- Consider deferring high-risk items to later waves"
        $prompt += "`n" + ($priorityLines -join "`n")
    }

    return $prompt
}

function Build-Phase2Prompt {
    <#
    .SYNOPSIS
        Constructs the Phase 2 wave planning prompt with optional telemetry context.
    #>
    param(
        [hashtable]$TelemetryContext,
        [hashtable]$WavePlanContext = @{ HasWavePlan = $false }
    )

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

    # Add autonomous wave planning context if available (IMP-GEN-002)
    if ($WavePlanContext.HasWavePlan) {
        $wavePlanLines = @()
        $wavePlanLines += ""
        $wavePlanLines += "## Autonomous Wave Plan Context (IMP-GEN-002)"
        $wavePlanLines += ""
        $wavePlanLines += "WAVE_PLAN: $($WavePlanContext.WavePlanPath)"
        $wavePlanLines += "- Contains $($WavePlanContext.ImpCount) IMPs grouped into $($WavePlanContext.WaveCount) waves"
        $wavePlanLines += "- Waves are optimized for maximum parallelization"
        $wavePlanLines += "- Dependencies and file conflicts have been validated"
        $wavePlanLines += "- Use this plan as the basis for worktree setup and task assignment"
        $wavePlanLines += "- Each wave includes phase IDs, branch names, and file lists"
        $prompt += "`n" + ($wavePlanLines -join "`n")
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
        [hashtable]$CarryoverContext = @{ HasCarryover = $false },
        [hashtable]$DiscoveryContext = @{ HasDiscovery = $false },
        [hashtable]$InjectedContext = @{ HasContext = $false },
        [hashtable]$FeedbackLoopContext = @{ HasFeedback = $false },
        [hashtable]$PriorityContext = @{ HasPriorityRanking = $false }
    )

    Write-Status "=== Phase 1: Discovery ===" -Color Magenta

    $prompt = Build-Phase1Prompt -TelemetryContext $TelemetryContext -CarryoverContext $CarryoverContext -DiscoveryContext $DiscoveryContext -InjectedContext $InjectedContext -FeedbackLoopContext $FeedbackLoopContext -PriorityContext $PriorityContext

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
    param(
        [hashtable]$TelemetryContext,
        [hashtable]$WavePlanContext = @{ HasWavePlan = $false }
    )

    Write-Status "=== Phase 2: Wave Planning ===" -Color Magenta

    $prompt = Build-Phase2Prompt -TelemetryContext $TelemetryContext -WavePlanContext $WavePlanContext

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
    Write-Status "Phase: $Phase | UseTelemetryContext: $UseTelemetryContext | UseDiscoveryContextInjection: $UseDiscoveryContextInjection | UseTelemetryFeedbackLoop: $UseTelemetryFeedbackLoop | UseAutonomousDiscovery: $UseAutonomousDiscovery | UseAutonomousWavePlanning: $UseAutonomousWavePlanning | UsePriorityEngine: $UsePriorityEngine | DryRun: $DryRun"
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

    # Run discovery context injection if enabled (IMP-LOOP-001)
    $injectedContext = @{ HasContext = $false; ContextPath = $null }
    if ($UseDiscoveryContextInjection -and ($Phase -eq "phase1" -or $Phase -eq "all")) {
        Write-Status "Discovery context injection enabled - gathering telemetry insights..."
        $injectedContext = Invoke-DiscoveryContextInjection
        if ($injectedContext.HasContext) {
            Write-Status "Discovery context injection completed:" -Color Green
            Write-Status "  - Context file: $($injectedContext.ContextPath)"
        }
        Write-Host ""
    }

    # Run telemetry-to-discovery feedback loop if enabled (IMP-TEL-003)
    $feedbackLoopContext = @{ HasFeedback = $false; FeedbackPath = $null; ImprovementsAdded = 0 }
    if ($UseTelemetryFeedbackLoop -and ($Phase -eq "phase1" -or $Phase -eq "all")) {
        Write-Status "Telemetry feedback loop enabled - analyzing previous cycle telemetry..."
        $feedbackLoopContext = Invoke-TelemetryFeedbackLoop
        if ($feedbackLoopContext.HasFeedback) {
            Write-Status "Telemetry feedback loop completed:" -Color Green
            Write-Status "  - Patterns analyzed: $($feedbackLoopContext.PatternsAnalyzed)"
            Write-Status "  - Recurring issues: $($feedbackLoopContext.RecurringIssues)"
            Write-Status "  - Recommendations: $($feedbackLoopContext.Recommendations)"
            if ($feedbackLoopContext.ImprovementsAdded -gt 0) {
                Write-Status "  - Improvements added to master: $($feedbackLoopContext.ImprovementsAdded)"
            }
        }
        Write-Host ""
    }

    # Run autonomous discovery if enabled (IMP-GEN-001)
    $discoveryContext = @{ HasDiscovery = $false; DiscoveryPath = $null; ImpCount = 0 }
    if ($UseAutonomousDiscovery -and ($Phase -eq "phase1" -or $Phase -eq "all")) {
        Write-Status "Autonomous discovery enabled - analyzing patterns..."
        $discoveryContext = Invoke-AutonomousDiscovery
        if ($discoveryContext.HasDiscovery) {
            Write-Status "Autonomous discovery completed:" -Color Green
            Write-Status "  - Improvements found: $($discoveryContext.ImpCount)"
            Write-Status "  - Output file: $($discoveryContext.DiscoveryPath)"
        }
        Write-Host ""
    }

    # Run data-driven priority engine if enabled (IMP-TGN-001)
    $priorityContext = @{ HasPriorityRanking = $false; RankedImpsPath = $null; ImpCount = 0 }
    if ($UsePriorityEngine -and ($Phase -eq "phase1" -or $Phase -eq "all")) {
        Write-Status "Data-driven priority engine enabled - ranking improvements..."
        $priorityContext = Invoke-PriorityEngine
        if ($priorityContext.HasPriorityRanking) {
            Write-Status "Priority ranking completed:" -Color Green
            Write-Status "  - Improvements ranked: $($priorityContext.ImpCount)"
            Write-Status "  - Output file: $($priorityContext.RankedImpsPath)"
            if ($priorityContext.TopRanked) {
                Write-Status "  - Top priorities: $($priorityContext.TopRanked -join ', ')"
            }
            if ($priorityContext.HighRiskCount -gt 0) {
                Write-Status "  - High-risk items: $($priorityContext.HighRiskCount)" -Color Yellow
            }
        }
        Write-Host ""
    }

    # Run autonomous wave planning if enabled (IMP-GEN-002)
    $wavePlanContext = @{ HasWavePlan = $false; WavePlanPath = $null; WaveCount = 0; ImpCount = 0 }
    if ($UseAutonomousWavePlanning -and ($Phase -eq "phase2" -or $Phase -eq "all")) {
        Write-Status "Autonomous wave planning enabled - grouping IMPs into waves..."
        $wavePlanContext = Invoke-AutonomousWavePlanning -DiscoveredImpsPath $AutonomousDiscoveryOutputPath
        if ($wavePlanContext.HasWavePlan) {
            Write-Status "Autonomous wave planning completed:" -Color Green
            Write-Status "  - Waves created: $($wavePlanContext.WaveCount)"
            Write-Status "  - IMPs grouped: $($wavePlanContext.ImpCount)"
            Write-Status "  - Output file: $($wavePlanContext.WavePlanPath)"
        }
        Write-Host ""
    }

    # Execute requested phases
    switch ($Phase) {
        "phase1" {
            Invoke-Phase1 -TelemetryContext $telemetryContext -CarryoverContext $carryoverContext -DiscoveryContext $discoveryContext -InjectedContext $injectedContext -FeedbackLoopContext $feedbackLoopContext -PriorityContext $priorityContext
        }
        "phase2" {
            Invoke-Phase2 -TelemetryContext $telemetryContext -WavePlanContext $wavePlanContext
        }
        "all" {
            Invoke-Phase1 -TelemetryContext $telemetryContext -CarryoverContext $carryoverContext -DiscoveryContext $discoveryContext -InjectedContext $injectedContext -FeedbackLoopContext $feedbackLoopContext -PriorityContext $priorityContext
            Write-Host ""
            Invoke-Phase2 -TelemetryContext $telemetryContext -WavePlanContext $wavePlanContext
        }
    }

    Write-Host ""
    Write-Status "Generation trigger complete" -Color Green
}

# Run main
Main
