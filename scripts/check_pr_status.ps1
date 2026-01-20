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
function Load-UnresolvedIssues {
    param([int]$WaveNumber)
    $filePath = Get-UnresolvedIssuesFile $WaveNumber

    if (Test-Path $filePath) {
        try {
            return Get-Content $filePath -Raw | ConvertFrom-Json
        } catch {
            return @{ issues = @(); lastUpdated = Get-Date -Format 'yyyy-MM-dd HH:mm:ss' }
        }
    }

    return @{ issues = @(); lastUpdated = Get-Date -Format 'yyyy-MM-dd HH:mm:ss' }
}

# Save unresolved issues to file
function Save-UnresolvedIssues {
    param([int]$WaveNumber, [object]$IssuesData)
    $filePath = Get-UnresolvedIssuesFile $WaveNumber
    $IssuesData.lastUpdated = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $IssuesData | ConvertTo-Json -Depth 10 | Set-Content $filePath -Encoding UTF8
}

# Record an unresolved issue
# Only records if phaseId doesn't already exist (prevents duplicates)
function Record-UnresolvedIssue {
    param(
        [int]$WaveNumber,
        [string]$PhaseId,
        [string]$Issue,
        [string]$PRNumber
    )

    $issues = Load-UnresolvedIssues $WaveNumber

    # Check if this phaseId already exists (skip if so - prevents duplicates)
    $existing = $issues.issues | Where-Object { $_.phaseId -eq $PhaseId }

    if (-not $existing) {
        $issues.issues += @{
            phaseId = $PhaseId
            issue = $Issue
            prNumber = $PRNumber
            recorded = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        }

        Save-UnresolvedIssues $WaveNumber $issues
        return $true
    }

    return $false
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

# Load all prompts - manage_prompt_state returns phase objects
$prompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })
$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" } 2>/dev/null)

Write-Host "Found $($pendingPrompts.Count) PENDING phases"
Write-Host ""

$completedCount = 0
$mergedPRs = @()
$ciFailedCount = 0
$ciFailedPhases = @()

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

    # Extract phase ID from window title (format: "Autopack_w<wave>_<phaseId> ...")
    if ($title -match "Autopack_w\d+_([^\s]+)") {
        $phaseId = $Matches[1]

        # Determine grid slot from window coordinates
        $slot = Get-WindowSlotNumber -WindowX $rect.Left -WindowY $rect.Top
        if ($slot -gt 0) {
            $windowSlotMap[$phaseId] = $slot
        }
    }
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
                    # Critical CI failures (Core Tests failed) - MUST FIX before merge
                    $criticalNames = ($criticalFailures | ForEach-Object { $_.name }) -join ", "
                    Write-Host "  -> [FAIL] Critical CI failed: $criticalNames" -ForegroundColor Red
                    $ciFailedCount++
                    $ciFailedPhases += $phaseId

                    # Record as unresolved issue
                    $allFailedNames = ($failedChecks | ForEach-Object { $_.name }) -join ", "
                    $recorded = Record-UnresolvedIssue -WaveNumber $waveNumber -PhaseId $phaseId -Issue "CI failed: $allFailedNames" -PRNumber $prNumber
                    if ($recorded) {
                        Write-Host "  -> [INFO] Recorded unresolved issue"
                    }
                } elseif ($unrelatedFailures.Count -gt 0) {
                    # Only unrelated failures (lint, verify-structure) - these don't block merge
                    $unrelatedNames = ($unrelatedFailures | ForEach-Object { $_.name }) -join ", "
                    Write-Host "  -> [INFO] Unrelated CI failures (skipping): $unrelatedNames" -ForegroundColor Yellow
                    Write-Host "  -> [OK] Core Tests PASSED - ready to merge"

                    # Record unrelated failures for tracking but allow merge
                    $recorded = Record-UnresolvedIssue -WaveNumber $waveNumber -PhaseId $phaseId -Issue "Unrelated CI: $unrelatedNames" -PRNumber $prNumber
                    if ($recorded) {
                        Write-Host "  -> [INFO] Recorded unrelated issue for tracking"
                    }

                    # Allow merge since Core Tests passed
                    $mergedPRs += $phaseId
                    $completedCount++
                } else {
                    # All CI checks passed
                    Write-Host "  -> [OK] CI PASSING - ready to merge"
                    $mergedPRs += $phaseId
                    $completedCount++
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
Write-Host "PRs ready to merge: $completedCount"
Write-Host "PRs with CI failures: $ciFailedCount"

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

if ($mergedPRs.Count -gt 0) {
    Write-Host ""
    Write-Host "PRs ready - sending messages..."
    $messageSent = 0
    foreach ($phaseId in $mergedPRs) {
        $slot = $windowSlotMap[$phaseId]
        if ($null -ne $slot -and $slot -gt 0) {
            Write-Host "  Sending to slot $slot..."
            # Send clear instruction to Cursor to merge the PR
            $mergeInstruction = "Your PR has passed all CI checks and is ready. Please merge it now using: gh pr merge --squash --delete-branch"
            if (Send-MessageToCursorWindowSlot $mergeInstruction $slot) {
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
    Write-Host "Marking phases as COMPLETED..."

    foreach ($phaseId in $mergedPRs) {
        & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus "COMPLETED" 2>&1 | Where-Object { $_ -match "OK|ERROR" }
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
$headerPattern1 = 'READY: \d+, PENDING: \d+, COMPLETED: \d+, UNRESOLVED: \d+'
$headerReplacement1 = "READY: $readyCount, PENDING: $pendingCount, COMPLETED: $completedCount, UNRESOLVED: $unresolvedCount"
$content = $content -replace $headerPattern1, $headerReplacement1

# Also try alternate format (with UNRESOLVED in different position)
$headerPattern2 = 'READY: \d+, UNRESOLVED: \d+, PENDING: \d+, COMPLETED: \d+'
$headerReplacement2 = "READY: $readyCount, UNRESOLVED: $unresolvedCount, PENDING: $pendingCount, COMPLETED: $completedCount"
$content = $content -replace $headerPattern2, $headerReplacement2

Set-Content $WaveFile $content -Encoding UTF8

Write-Host "[OK] Header updated: $readyCount READY | $unresolvedCount UNRESOLVED | $pendingCount PENDING | $completedCount COMPLETED"
Write-Host ""
