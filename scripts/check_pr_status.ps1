# Check PR status for all PENDING phases and mark completed ones
# Also tracks unresolved issues (CI/lint failures unrelated to current PR)
param(
    [string]$WaveFile = ""
)

$backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"

# Helper function to find dynamically generated files
function Get-DynamicFilePath {
    param([string]$Pattern)
    $files = @(Get-ChildItem -Path $backupDir -Filter $Pattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($files.Count -gt 0) {
        return $files[0].FullName
    }
    return $null
}

# Extract wave number from wave file
function Get-WaveNumber {
    param([string]$FilePath)
    if ($FilePath -match "Wave(\d)") {
        return [int]$Matches[1]
    }
    return 1
}

# Get or create unresolved issues tracking file
function Get-UnresolvedIssuesFile {
    param([int]$WaveNumber)
    $fileName = "Wave${WaveNumber}_Unresolved_Issues.json"
    return Join-Path $backupDir $fileName
}

# Load existing unresolved issues or create new tracking
# New format groups issues by failure type category
function Load-UnresolvedIssues {
    param([int]$WaveNumber)
    $filePath = Get-UnresolvedIssuesFile $WaveNumber

    if (Test-Path $filePath) {
        try {
            $data = Get-Content $filePath -Raw | ConvertFrom-Json
            # Check if it's old format (has 'issues' with phaseId) or new format (has 'failureGroups')
            if ($null -ne $data.failureGroups) {
                return $data  # New format
            } elseif ($null -ne $data.issues) {
                # Migrate old format to new format
                return Migrate-OldFormatToNew $data
            }
        } catch {
            return @{ failureGroups = @(); lastUpdated = Get-Date -Format 'yyyy-MM-dd HH:mm:ss' }
        }
    }

    return @{ failureGroups = @(); lastUpdated = Get-Date -Format 'yyyy-MM-dd HH:mm:ss' }
}

# Migrate old format (per-phase) to new format (grouped by failure type)
function Migrate-OldFormatToNew {
    param([object]$OldData)

    $newData = @{
        failureGroups = @()
        lastUpdated = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    }

    if ($null -eq $OldData.issues -or $OldData.issues.Count -eq 0) {
        return $newData
    }

    # Group old issues by their failure type category
    $grouped = @{}
    foreach ($issue in $OldData.issues) {
        $category = Get-FailureCategory $issue.issue
        if (-not $grouped.ContainsKey($category)) {
            $grouped[$category] = @{
                failureType = $category
                description = $issue.issue
                affectedPhases = @()
            }
        }
        $grouped[$category].affectedPhases += @{
            phaseId = $issue.phaseId
            prNumber = $issue.prNumber
            recorded = $issue.recorded
        }
    }

    $newData.failureGroups = @($grouped.Values)
    return $newData
}

# Categorize failure type from the issue description
# Returns a normalized category name for grouping
function Get-FailureCategory {
    param([string]$IssueDescription)

    $desc = $IssueDescription.ToLower()

    # Check for Core Tests failure (critical - needs its own fix)
    if ($desc -match "core tests") {
        return "core-tests"
    }

    # Check for CodeQL (security scanning)
    if ($desc -match "codeql") {
        return "codeql"
    }

    # Check for lint/verify-structure (common systemic issues)
    if ($desc -match "lint" -and $desc -match "verify-structure") {
        return "lint-verify-structure"
    }
    if ($desc -match "verify-structure") {
        return "verify-structure"
    }
    if ($desc -match "lint") {
        return "lint"
    }

    # Default: use the full description as category (unique issue)
    return "other"
}

# Save unresolved issues to file
function Save-UnresolvedIssues {
    param([int]$WaveNumber, [object]$IssuesData)
    $filePath = Get-UnresolvedIssuesFile $WaveNumber
    $IssuesData.lastUpdated = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $IssuesData | ConvertTo-Json -Depth 10 | Set-Content $filePath -Encoding UTF8
}

# Record an unresolved issue (grouped by failure type)
# Groups similar failures together instead of creating separate entries per phase
function Record-UnresolvedIssue {
    param(
        [int]$WaveNumber,
        [string]$PhaseId,
        [string]$Issue,
        [string]$PRNumber
    )

    $data = Load-UnresolvedIssues $WaveNumber
    $category = Get-FailureCategory $Issue

    # Check if this phaseId already exists in ANY group (prevents duplicates)
    foreach ($group in $data.failureGroups) {
        $existingPhase = $group.affectedPhases | Where-Object { $_.phaseId -eq $PhaseId }
        if ($existingPhase) {
            return $false  # Phase already recorded
        }
    }

    # Find existing group for this failure category
    $existingGroup = $data.failureGroups | Where-Object { $_.failureType -eq $category }

    if ($existingGroup) {
        # Add phase to existing group
        $existingGroup.affectedPhases += @{
            phaseId = $PhaseId
            prNumber = $PRNumber
            recorded = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        }
    } else {
        # Create new group for this failure type
        $newGroup = @{
            failureType = $category
            description = $Issue
            affectedPhases = @(
                @{
                    phaseId = $PhaseId
                    prNumber = $PRNumber
                    recorded = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
                }
            )
        }
        $data.failureGroups += $newGroup
    }

    Save-UnresolvedIssues $WaveNumber $data
    return $true
}

# Send message to cursor window at specific grid slot
# Maps phase to window slot and sends message to correct grid position
function Send-MessageToCursorWindowSlot {
    param(
        [string]$Message,
        [int]$SlotNumber
    )

    # Delegate to send_message_to_cursor_slot.ps1 which handles slot-specific messaging
    try {
        & "C:\dev\Autopack\scripts\send_message_to_cursor_slot.ps1" -SlotNumber $SlotNumber -Message $Message 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        Write-Host "    [WARN] Could not send message to slot $SlotNumber : $_"
        return $false
    }
}

# Helper function to map window positions to grid slots
function Get-WindowSlotNumber {
    param([int]$WindowX, [int]$WindowY)

    # Grid coordinates (from STREAMDECK_REFERENCE.md, verified 2026-01-19):
    # Window LEFT positions: X=2560, 3413, 4266
    # Window TOP positions:  Y=0, 463, 926
    # Window size: ~853x463

    $tolerance = 100  # Tolerance for window position matching

    # Determine column based on window LEFT position
    $col = 0
    if ($WindowX -ge (2560 - $tolerance) -and $WindowX -le (2560 + $tolerance)) { $col = 1 }
    elseif ($WindowX -ge (3413 - $tolerance) -and $WindowX -le (3413 + $tolerance)) { $col = 2 }
    elseif ($WindowX -ge (4266 - $tolerance) -and $WindowX -le (4266 + $tolerance)) { $col = 3 }

    # Determine row based on window TOP position
    $row = 0
    if ($WindowY -ge (0 - $tolerance) -and $WindowY -le (0 + $tolerance)) { $row = 1 }
    elseif ($WindowY -ge (463 - $tolerance) -and $WindowY -le (463 + $tolerance)) { $row = 2 }
    elseif ($WindowY -ge (926 - $tolerance) -and $WindowY -le (926 + $tolerance)) { $row = 3 }

    if ($col -eq 0 -or $row -eq 0) {
        return 0  # Not in grid
    }

    # Convert row/col to slot number (1-9)
    $slot = ($row - 1) * 3 + $col
    return $slot
}

# Start OCR handler in background if not already running
# Returns $true if handler was started or is already running
function Start-OCRHandler {
    $scriptDir = "C:\dev\Autopack\scripts"
    $ocrScript = Join-Path $scriptDir "handle_connection_errors_ocr.py"

    # Check if OCR handler is already running
    $existingProcess = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        try {
            $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
            $cmdLine -match "handle_connection_errors_ocr"
        } catch {
            $false
        }
    }

    if ($existingProcess) {
        Write-Host "[INFO] OCR handler already running (PID: $($existingProcess.Id))"
        return $true
    }

    # Start OCR handler in background
    if (Test-Path $ocrScript) {
        Write-Host "[ACTION] Starting OCR handler in background..."
        try {
            $process = Start-Process -FilePath "python" -ArgumentList "`"$ocrScript`"" -WindowStyle Minimized -PassThru
            Write-Host "[OK] OCR handler started (PID: $($process.Id))"

            # Give it a moment to initialize
            Start-Sleep -Seconds 2
            return $true
        } catch {
            Write-Host "[WARN] Failed to start OCR handler: $_"
            return $false
        }
    } else {
        Write-Host "[WARN] OCR handler script not found: $ocrScript"
        return $false
    }
}

if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $promptsFile = Join-Path $backupDir "Prompts_All_Waves.md"

    if (Test-Path $promptsFile) {
        $WaveFile = $promptsFile
    } else {
        # Fallback to old Wave*_All_Phases.md format for backwards compatibility
        $WaveFile = Get-DynamicFilePath "Wave*_All_Phases.md"

        if ([string]::IsNullOrWhiteSpace($WaveFile)) {
            Write-Host "ERROR: No Prompts_All_Waves.md or Wave*_All_Phases.md file found"
            exit 1
        }
    }
}

$waveNumber = Get-WaveNumber $WaveFile

Write-Host "PR STATUS CHECK"
Write-Host "==============="
Write-Host ""

# Start OCR handler early - it runs continuously and adapts to windows appearing/disappearing
# No need to wait for auto_fill to finish - OCR handler dynamically detects active slots
Start-OCRHandler | Out-Null

# Load all prompts - manage_prompt_state returns phase objects
$prompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })
$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" } 2>/dev/null)

Write-Host "Found $($pendingPrompts.Count) PENDING phases"
Write-Host ""

$completedCount = 0
$mergedPRs = @()
$ciFailedCount = 0
$ciFailedPhases = @()
$readyToMergeCount = 0
$readyToMergePhases = @()  # Phases with CI passing, ready for merge

# Build window slot mapping for sending messages to correct grid positions
$windowSlotMap = @{}  # Maps phaseId to slot number

# Get all Cursor windows and map them to grid slots
if (-not ([System.Management.Automation.PSTypeName]'WindowHelper').Type) {
    Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowHelper {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static List<IntPtr> GetWindowsByProcessName(string processName) {
        var windows = new List<IntPtr>();
        var processIds = new HashSet<uint>();

        foreach (var proc in System.Diagnostics.Process.GetProcessesByName(processName)) {
            processIds.Add((uint)proc.Id);
        }

        EnumWindows((hWnd, lParam) => {
            uint processId;
            GetWindowThreadProcessId(hWnd, out processId);
            if (processIds.Contains(processId) && IsWindowVisible(hWnd)) {
                windows.Add(hWnd);
            }
            return true;
        }, IntPtr.Zero);

        return windows;
    }

    public static string GetWindowTitle(IntPtr hWnd) {
        var length = GetWindowTextLength(hWnd);
        if (length == 0) return "";
        var sb = new StringBuilder(length + 1);
        GetWindowText(hWnd, sb, length + 1);
        return sb.ToString();
    }

    public static RECT GetWindowRect(IntPtr hWnd) {
        RECT rect;
        GetWindowRect(hWnd, out rect);
        return rect;
    }
}
"@
}

# Enumerate Cursor windows and map to slots
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")
foreach ($window in $cursorWindows) {
    $title = [WindowHelper]::GetWindowTitle($window)
    $rect = [WindowHelper]::GetWindowRect($window)

    # Extract phase ID from window title (format: "Autopack_w<wave>_<phaseId> ..." or just folder name)
    # Try multiple patterns to match different Cursor title formats
    $phaseId = $null

    # Pattern 1: Standard worktree format "Autopack_w<wave>_<phaseId>"
    if ($title -match "Autopack_w\d+_([^\s\\-]+(?:-[^\s\\]+)*)") {
        $phaseId = $Matches[1]
    }
    # Pattern 2: Just the folder name (sometimes Cursor shows short form)
    elseif ($title -match "\\Autopack_w\d+_([^\s\\]+)") {
        $phaseId = $Matches[1]
    }
    # Pattern 3: Fix branches use "fix-" prefix
    elseif ($title -match "(fix-[a-z-]+)") {
        $phaseId = $Matches[1]
    }

    if ($null -ne $phaseId) {
        # Determine grid slot from window coordinates
        $slot = Get-WindowSlotNumber -WindowX $rect.Left -WindowY $rect.Top
        if ($slot -gt 0) {
            $windowSlotMap[$phaseId] = $slot
        }
    }
}

# Check for COMPLETED phases that still have open windows (cleanup from previous runs)
$completedPrompts = @($prompts | Where-Object { $_.Status -eq "COMPLETED" } 2>/dev/null)
$staleWindowsClosed = 0
foreach ($prompt in $completedPrompts) {
    $phaseId = $prompt.ID
    $slot = $windowSlotMap[$phaseId]
    if ($null -ne $slot -and $slot -gt 0) {
        Write-Host "[CLEANUP] Phase $phaseId is COMPLETED but still has window at slot $slot - closing..."
        try {
            & "C:\dev\Autopack\scripts\close_cursor_window_slot.ps1" -SlotNumber $slot 2>&1 | Out-Null
            Write-Host "  [OK] Stale window closed for $phaseId"
            $staleWindowsClosed++
        } catch {
            Write-Host "  [WARN] Could not close window: $_"
        }
    }
}
if ($staleWindowsClosed -gt 0) {
    Write-Host "[INFO] Closed $staleWindowsClosed stale window(s) for completed phases"
    Write-Host ""
}

# Check first 9 phases (sec001-006, safety001-003)
foreach ($prompt in $pendingPrompts | Select-Object -First 9) {
    $phaseId = $prompt.ID
    $branchName = $prompt.Branch

    Write-Host "$phaseId..."

    # Query GitHub
    $prJson = gh pr list --head $branchName --state all --json number,state,statusCheckRollup 2>/dev/null | ConvertFrom-Json

    if ($null -ne $prJson -and $prJson.Count -gt 0) {
        $pr = if ($prJson -is [array]) { $prJson[0] } else { $prJson }
        $state = $pr.state
        $prNumber = $pr.number

        if ($state -eq "MERGED") {
            Write-Host "  -> MERGED PR #$prNumber (marking complete)"
            $mergedPRs += $phaseId
            $completedCount++
        } elseif ($state -eq "OPEN") {
            Write-Host "  -> OPEN PR #$prNumber"

            # Check for CI status
            $hasChecks = $null -ne $pr.statusCheckRollup -and $pr.statusCheckRollup -is [array]

            if ($hasChecks) {
                # Analyze status checks
                # Note: GitHub API uses 'conclusion' for result (SUCCESS/FAILURE) and 'status' for state (COMPLETED/IN_PROGRESS)
                $failedChecks = @($pr.statusCheckRollup | Where-Object { $_.conclusion -eq "FAILURE" })
                $runningChecks = @($pr.statusCheckRollup | Where-Object { $_.status -eq "IN_PROGRESS" })

                # Separate critical failures from unrelated failures
                # Critical: "Core Tests (Must Pass)" - these MUST pass for merge
                # Unrelated: "lint", "verify-structure" - pre-existing issues, don't block merge
                $unrelatedCheckNames = @("lint", "verify-structure")
                $criticalFailures = @($failedChecks | Where-Object { $_.name -notin $unrelatedCheckNames })
                $unrelatedFailures = @($failedChecks | Where-Object { $_.name -in $unrelatedCheckNames })

                if ($runningChecks.Count -gt 0) {
                    # CI is still running
                    Write-Host "  -> [INFO] CI tests running..."
                } elseif ($criticalFailures.Count -gt 0) {
                    # Critical CI failures (Core Tests failed) - MUST FIX on the SAME branch
                    # Do NOT record as unresolved issue - the fix goes to the original PR
                    $criticalNames = ($criticalFailures | ForEach-Object { $_.name }) -join ", "
                    Write-Host "  -> [FAIL] Critical CI failed: $criticalNames" -ForegroundColor Red
                    Write-Host "  -> [INFO] Fix should be pushed to the SAME branch/PR (not a new PR)"
                    $ciFailedCount++
                    $ciFailedPhases += $phaseId
                    # NOTE: Core Tests failures are NOT recorded as unresolved issues
                    # They stay PENDING and the Cursor window gets a message to fix on the same branch
                } elseif ($unrelatedFailures.Count -gt 0) {
                    # Only unrelated failures (lint, verify-structure) - these don't block merge
                    $unrelatedNames = ($unrelatedFailures | ForEach-Object { $_.name }) -join ", "
                    Write-Host "  -> [INFO] Unrelated CI failures (skipping): $unrelatedNames" -ForegroundColor Yellow
                    Write-Host "  -> [OK] Core Tests PASSED - ready to merge"
                    Write-Host "  -> [INFO] PR still OPEN - waiting for merge (not marking completed)"

                    # Record unrelated failures for tracking
                    $recorded = Record-UnresolvedIssue -WaveNumber $waveNumber -PhaseId $phaseId -Issue "Unrelated CI: $unrelatedNames" -PRNumber $prNumber
                    if ($recorded) {
                        Write-Host "  -> [INFO] Recorded unrelated issue for tracking"
                    }
                    # Track as ready to merge (will send message to Cursor window)
                    $readyToMergeCount++
                    $readyToMergePhases += @{ phaseId = $phaseId; prNumber = $prNumber }
                    # DO NOT mark as completed - PR is still OPEN, not MERGED
                } else {
                    # All CI checks passed but PR still OPEN
                    Write-Host "  -> [OK] CI PASSING - ready to merge"
                    Write-Host "  -> [INFO] PR still OPEN - waiting for merge (not marking completed)"
                    # Track as ready to merge (will send message to Cursor window)
                    $readyToMergeCount++
                    $readyToMergePhases += @{ phaseId = $phaseId; prNumber = $prNumber }
                    # DO NOT mark as completed - PR is still OPEN, not MERGED
                }
            } else {
                # No checks present yet
                Write-Host "  -> [INFO] No CI checks found yet"
            }
        } else {
            Write-Host "  -> PR state: $state"
        }
    } else {
        Write-Host "  -> No PR found"
    }
}

Write-Host ""
Write-Host "RESULTS:"
Write-Host "========="
Write-Host "PRs MERGED (marking completed): $completedCount"
Write-Host "PRs with CI failures: $ciFailedCount"
Write-Host "PRs ready to merge: $readyToMergeCount"

if ($ciFailedCount -gt 0) {
    Write-Host ""
    Write-Host "[ACTION] Sending CI failure messages to Cursor windows..."
    $messageSent = 0
    foreach ($phaseId in $ciFailedPhases) {
        $slot = $windowSlotMap[$phaseId]
        if ($null -ne $slot -and $slot -gt 0) {
            Write-Host "  Sending to slot $slot ($phaseId)..."
            if (Send-MessageToCursorWindowSlot "CI run has failed. Please fix and re-run" $slot) {
                $messageSent++
                Write-Host "    [OK] Message sent"
            } else {
                Write-Host "    [FAIL] Failed to send message to slot $slot"
            }
        } else {
            Write-Host "  [WARN] Phase $phaseId not found in grid, skipping message"
        }
    }
    Write-Host ""
    Write-Host "[INFO] $messageSent CI failure messages sent"
}

if ($readyToMergePhases.Count -gt 0) {
    Write-Host ""
    Write-Host "[ACTION] Sending 'ready to merge' messages to Cursor windows..."
    $messageSent = 0
    foreach ($phase in $readyToMergePhases) {
        $phaseId = $phase.phaseId
        $prNumber = $phase.prNumber
        $slot = $windowSlotMap[$phaseId]
        if ($null -ne $slot -and $slot -gt 0) {
            Write-Host "  Sending to slot $slot ($phaseId, PR #$prNumber)..."
            $mergeMsg = "CI passed! Your PR #$prNumber is ready to merge. Run: gh pr merge $prNumber --squash --delete-branch"
            if (Send-MessageToCursorWindowSlot $mergeMsg $slot) {
                $messageSent++
                Write-Host "    [OK] Message sent"
            } else {
                Write-Host "    [FAIL] Failed to send message to slot $slot"
            }
        } else {
            Write-Host "  [WARN] Phase $phaseId not found in grid, skipping message"
        }
    }
    Write-Host ""
    Write-Host "[INFO] $messageSent ready-to-merge messages sent"
}

if ($mergedPRs.Count -gt 0) {
    # PRs already merged - mark as completed, close windows, trigger cleanup
    Write-Host ""
    Write-Host "[INFO] Found $($mergedPRs.Count) already-merged PR(s) - processing..."

    Write-Host ""
    Write-Host "Marking phases as COMPLETED..."

    foreach ($phaseId in $mergedPRs) {
        & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus "COMPLETED" 2>&1 | Where-Object { $_ -match "OK|ERROR" }

        # Close the Cursor window for this phase
        $slot = $windowSlotMap[$phaseId]
        if ($null -ne $slot -and $slot -gt 0) {
            Write-Host "  Closing Cursor window at slot $slot ($phaseId)..."
            try {
                & "C:\dev\Autopack\scripts\close_cursor_window_slot.ps1" -SlotNumber $slot 2>&1 | Out-Null
                Write-Host "    [OK] Window closed"
            } catch {
                Write-Host "    [WARN] Could not close window: $_"
            }
        } else {
            Write-Host "  [WARN] No slot found for $phaseId - window cannot be closed automatically"
        }
    }

    # Run cleanup once for all completed phases
    Write-Host ""
    Write-Host "[ACTION] Running cleanup for completed phases..."
    try {
        & "C:\dev\Autopack\scripts\cleanup_wave_prompts.ps1" -WaveFile $WaveFile 2>&1 | ForEach-Object {
            if ($_ -match "^\[OK\]|^\[INFO\]|^Remaining") {
                Write-Host "  $_"
            }
        }
        Write-Host "[OK] Cleanup completed"
    } catch {
        Write-Host "[WARN] Cleanup error: $_"
    }

    # Trigger auto-fill to refill empty slots
    Write-Host ""
    Write-Host "[ACTION] Triggering auto-fill for empty slots..."
    Start-Sleep -Seconds 2
    try {
        & "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1" -WaveFile $WaveFile -SkipPRMonitoring 2>&1 | ForEach-Object {
            if ($_ -match "^\[|^STEP|^Fill|^Slots|^Wave") {
                Write-Host "  $_"
            }
        }
        Write-Host "[OK] Auto-fill triggered"
    } catch {
        Write-Host "[WARN] Auto-fill error: $_"
    }

    # Update AUTOPACK_IMPS_MASTER.json if it exists
    $masterFile = Get-DynamicFilePath "AUTOPACK_IMPS_MASTER.json"
    if ($null -ne $masterFile -and (Test-Path $masterFile)) {
        Write-Host ""
        Write-Host "Updating AUTOPACK_IMPS_MASTER.json..."
        try {
            $masterJson = Get-Content $masterFile -Raw | ConvertFrom-Json
            if ($null -ne $masterJson.improvements) {
                $masterJson.improvements = @($masterJson.improvements | Where-Object { $_.id -notin $mergedPRs })
                $masterJson | ConvertTo-Json -Depth 10 | Set-Content $masterFile -Encoding UTF8
                Write-Host "  [OK] Removed $($mergedPRs.Count) completed phases from improvements"
            }
        } catch {
            Write-Host "  [WARN] Could not update AUTOPACK_IMPS_MASTER.json: $_"
        }
    }

    # Update AUTOPACK_WAVE_PLAN.json if it exists
    $planFile = Get-DynamicFilePath "AUTOPACK_WAVE_PLAN.json"
    if ($null -ne $planFile -and (Test-Path $planFile)) {
        Write-Host "Updating AUTOPACK_WAVE_PLAN.json..."
        try {
            $planJson = Get-Content $planFile -Raw | ConvertFrom-Json
            $waveNumber = 1
            if ($WaveFile -match "Wave(\d)") {
                $waveNumber = [int]$Matches[1]
            }
            $waveKey = "wave_$waveNumber"

            if ($planJson.PSObject.Properties[$waveKey]) {
                if ($null -ne $planJson.PSObject.Properties[$waveKey].Value.phases) {
                    $planJson.PSObject.Properties[$waveKey].Value.phases = @(
                        $planJson.PSObject.Properties[$waveKey].Value.phases |
                        Where-Object { $_.id -notin $mergedPRs }
                    )
                    $planJson | ConvertTo-Json -Depth 10 | Set-Content $planFile -Encoding UTF8
                    Write-Host "  [OK] Removed $($mergedPRs.Count) completed phases from Wave $waveNumber plan"
                }
            }
        } catch {
            Write-Host "  [WARN] Could not update AUTOPACK_WAVE_PLAN.json: $_"
        }
    }
}

# ============ UPDATE HEADER COUNTS ============
# Always update header to reflect current phase counts
Write-Host ""
Write-Host "Updating header counts..."

$content = Get-Content $WaveFile -Raw

# Count current statuses
$readyCount = ([regex]::Matches($content, '\[READY\]')).Count
$unresolvedCount = ([regex]::Matches($content, '\[UNRESOLVED\]')).Count
$pendingCount = ([regex]::Matches($content, '\[PENDING\]')).Count
$completedCount = ([regex]::Matches($content, '\[COMPLETED\]')).Count

# Update header - try multiple formats
# Format 1 (current pipe-separated): "READY: 70 | PENDING: 0 | COMPLETED: 0 | UNIMPLEMENTED: 0"
$headerPattern1 = 'READY: \d+ \| PENDING: \d+ \| COMPLETED: \d+ \| UNIMPLEMENTED: \d+'
$headerReplacement1 = "READY: $readyCount | PENDING: $pendingCount | COMPLETED: $completedCount | UNIMPLEMENTED: $unresolvedCount"
$content = $content -replace $headerPattern1, $headerReplacement1

# Format 2 (old comma-separated): "READY: N, PENDING: N, COMPLETED: N, UNRESOLVED: N"
$headerPattern2 = 'READY: \d+, PENDING: \d+, COMPLETED: \d+, UNRESOLVED: \d+'
$headerReplacement2 = "READY: $readyCount, PENDING: $pendingCount, COMPLETED: $completedCount, UNRESOLVED: $unresolvedCount"
$content = $content -replace $headerPattern2, $headerReplacement2

# Format 3 (alternate with UNRESOLVED in different position)
$headerPattern3 = 'READY: \d+, UNRESOLVED: \d+, PENDING: \d+, COMPLETED: \d+'
$headerReplacement3 = "READY: $readyCount, UNRESOLVED: $unresolvedCount, PENDING: $pendingCount, COMPLETED: $completedCount"
$content = $content -replace $headerPattern3, $headerReplacement3

Set-Content $WaveFile $content -Encoding UTF8

Write-Host "[OK] Header updated: $readyCount READY | $unresolvedCount UNRESOLVED | $pendingCount PENDING | $completedCount COMPLETED"
Write-Host ""

# ============ MERGE MONITORING LOOP ============
# If there are PRs ready to merge, poll every 30 seconds until they merge
# Then close the Cursor window and trigger auto-fill

if ($readyToMergePhases.Count -gt 0) {
    Write-Host "=============================================="
    Write-Host "MERGE MONITORING MODE"
    Write-Host "=============================================="
    Write-Host ""
    Write-Host "Monitoring $($readyToMergePhases.Count) PR(s) for merge completion..."
    Write-Host "Checking every 30 seconds. Press Ctrl+C to stop."
    Write-Host ""

    $pendingMerges = [System.Collections.ArrayList]@($readyToMergePhases)
    $pollInterval = 30  # seconds

    while ($pendingMerges.Count -gt 0) {
        Start-Sleep -Seconds $pollInterval

        $timestamp = Get-Date -Format "HH:mm:ss"
        Write-Host "[$timestamp] Checking $($pendingMerges.Count) pending PR(s)..."

        $mergedThisRound = @()

        foreach ($phase in $pendingMerges) {
            $phaseId = $phase.phaseId
            $prNumber = $phase.prNumber

            # Check PR state via GitHub API
            try {
                $prState = gh pr view $prNumber --json state --jq '.state' 2>$null

                if ($prState -eq "MERGED") {
                    Write-Host "  [MERGED] PR #$prNumber ($phaseId)"
                    $mergedThisRound += $phase

                    # Get the slot for this phase
                    $slot = $windowSlotMap[$phaseId]

                    # Mark phase as COMPLETED
                    Write-Host "    Marking $phaseId as COMPLETED..."
                    & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus "COMPLETED" 2>&1 | Out-Null

                    # Close the Cursor window for this slot
                    if ($null -ne $slot -and $slot -gt 0) {
                        Write-Host "    Closing Cursor window at slot $slot..."
                        try {
                            & "C:\dev\Autopack\scripts\close_cursor_window_slot.ps1" -SlotNumber $slot 2>&1 | Out-Null
                            Write-Host "    [OK] Window closed"
                        } catch {
                            Write-Host "    [WARN] Could not close window: $_"
                        }
                    }

                    # Trigger cleanup for this completed phase
                    Write-Host "    Running cleanup for completed phase..."
                    try {
                        & "C:\dev\Autopack\scripts\cleanup_wave_prompts.ps1" -WaveFile $WaveFile 2>&1 | ForEach-Object {
                            if ($_ -match "^\[OK\]|^\[INFO\]|^Remaining") {
                                Write-Host "      $_"
                            }
                        }
                        Write-Host "    [OK] Cleanup completed"
                    } catch {
                        Write-Host "    [WARN] Cleanup error: $_"
                    }
                } elseif ($prState -eq "CLOSED") {
                    Write-Host "  [CLOSED] PR #$prNumber ($phaseId) - removed from monitoring"
                    $mergedThisRound += $phase
                } else {
                    Write-Host "  [OPEN] PR #$prNumber ($phaseId) - still waiting..."
                }
            } catch {
                Write-Host "  [ERROR] Could not check PR #$prNumber : $_"
            }
        }

        # Remove merged PRs from pending list
        foreach ($merged in $mergedThisRound) {
            $pendingMerges.Remove($merged) | Out-Null
        }

        # If any PRs merged this round, trigger auto-fill
        if ($mergedThisRound.Count -gt 0) {
            Write-Host ""
            Write-Host "[ACTION] $($mergedThisRound.Count) PR(s) merged - triggering auto-fill..."

            # Small delay to let windows close properly
            Start-Sleep -Seconds 2

            try {
                & "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1" -WaveFile $WaveFile -SkipPRMonitoring 2>&1 | ForEach-Object {
                    if ($_ -match "^\[|^STEP|^Fill|^Slots|^Wave") {
                        Write-Host "    $_"
                    }
                }
                Write-Host "    [OK] Auto-fill triggered"
            } catch {
                Write-Host "    [WARN] Auto-fill error: $_"
            }

            Write-Host ""
        }

        if ($pendingMerges.Count -gt 0) {
            Write-Host "  Waiting $pollInterval seconds before next check..."
        }
    }

    Write-Host ""
    Write-Host "=============================================="
    Write-Host "All monitored PRs have been merged!"
    Write-Host "=============================================="
    Write-Host ""

    # ============ CHECK WAVE COMPLETION ============
    # After all monitored PRs merged, check if the CURRENT wave is complete
    Write-Host "[INFO] Checking wave completion status..."

    # Reload prompts to get current state (now includes Wave field)
    $currentPrompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })

    # Determine current wave from phases with active statuses
    $activeWaves = @($currentPrompts | Where-Object { $_.Status -in @("READY", "UNRESOLVED", "PENDING") } | ForEach-Object { $_.Wave } | Sort-Object -Unique)

    if ($activeWaves.Count -eq 0) {
        Write-Host ""
        Write-Host "=============================================="
        Write-Host "ALL WAVES COMPLETE!"
        Write-Host "=============================================="
        Write-Host ""
        Write-Host "[INFO] All 70 phases across all waves have been completed!"
        Write-Host "[INFO] Workflow finished successfully."
    } else {
        $currentWave = $activeWaves[0]  # Lowest wave with active phases

        # Check current wave status
        $currentWavePrompts = @($currentPrompts | Where-Object { $_.Wave -eq $currentWave })
        $waveReadyRemaining = @($currentWavePrompts | Where-Object { $_.Status -eq "READY" }).Count
        $wavePendingRemaining = @($currentWavePrompts | Where-Object { $_.Status -eq "PENDING" }).Count
        $waveUnresolvedRemaining = @($currentWavePrompts | Where-Object { $_.Status -eq "UNRESOLVED" }).Count

        Write-Host "[INFO] Wave $currentWave status: $waveReadyRemaining READY | $wavePendingRemaining PENDING | $waveUnresolvedRemaining UNRESOLVED"

        if ($waveReadyRemaining -eq 0 -and $wavePendingRemaining -eq 0 -and $waveUnresolvedRemaining -eq 0) {
            Write-Host ""
            Write-Host "=============================================="
            Write-Host "WAVE $currentWave COMPLETE!"
            Write-Host "=============================================="
            Write-Host ""

            # Check if there's a next wave
            if ($activeWaves.Count -gt 1) {
                $nextWave = $activeWaves[1]
                Write-Host "[INFO] Wave $currentWave finished. Starting Wave $nextWave..."
                Write-Host ""

                Write-Host "[ACTION] Starting Wave $nextWave with auto-fill..."

                # Small delay before auto-fill
                Start-Sleep -Seconds 2

                try {
                    & "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1" -WaveFile $WaveFile -SkipPRMonitoring 2>&1 | ForEach-Object {
                        if ($_ -match "^\[|^STEP|^Fill|^Slots|^Wave") {
                            Write-Host "    $_"
                        }
                    }
                    Write-Host "    [OK] Wave $nextWave started"

                    # Continue monitoring by recursively calling this script
                    Write-Host ""
                    Write-Host "[AUTO] Continuing PR monitoring for Wave $nextWave..."
                    & "C:\dev\Autopack\scripts\check_pr_status.ps1" -WaveFile $WaveFile
                } catch {
                    Write-Host "    [WARN] Auto-fill error: $_"
                }
            } else {
                Write-Host "[INFO] All waves complete! Workflow finished."
            }
        } elseif ($waveReadyRemaining -gt 0 -or $waveUnresolvedRemaining -gt 0) {
            Write-Host "[INFO] Wave $currentWave still has phases to process"
            Write-Host "[ACTION] Triggering auto-fill for remaining Wave $currentWave phases..."

            # Small delay before auto-fill
            Start-Sleep -Seconds 2

            try {
                & "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1" -WaveFile $WaveFile -SkipPRMonitoring 2>&1 | ForEach-Object {
                    if ($_ -match "^\[|^STEP|^Fill|^Slots|^Wave") {
                        Write-Host "    $_"
                    }
                }
                Write-Host "    [OK] Next batch started"

                # Continue monitoring by recursively calling this script
                Write-Host ""
                Write-Host "[AUTO] Continuing PR monitoring for current wave..."
                & "C:\dev\Autopack\scripts\check_pr_status.ps1" -WaveFile $WaveFile
            } catch {
                Write-Host "    [WARN] Auto-fill error: $_"
            }
        }
    }
} elseif ($pendingPrompts.Count -gt 0) {
    # ============ FALLBACK: PENDING MONITORING LOOP ============
    # No PRs ready to merge yet, but there are PENDING phases
    # Poll every 60 seconds until PRs become ready or merge
    Write-Host ""
    Write-Host "=============================================="
    Write-Host "PENDING MONITORING MODE"
    Write-Host "=============================================="
    Write-Host ""
    Write-Host "[INFO] $($pendingPrompts.Count) PENDING phase(s) still in progress"
    Write-Host "[INFO] CI may still be running or PRs awaiting review"
    Write-Host "[INFO] Polling every 60 seconds until PRs are ready to merge or merged..."
    Write-Host ""

    $pollInterval = 60  # seconds (longer interval since CI takes time)

    while ($true) {
        Start-Sleep -Seconds $pollInterval

        $timestamp = Get-Date -Format "HH:mm:ss"
        Write-Host "[$timestamp] Re-checking PR status..."

        # Recursively call this script to re-check all PRs
        # The recursive call will handle any state changes
        & "C:\dev\Autopack\scripts\check_pr_status.ps1" -WaveFile $WaveFile

        # If we get here, the recursive call has completed
        # This means either all work is done or something changed
        # Exit to prevent infinite nesting
        break
    }
}
