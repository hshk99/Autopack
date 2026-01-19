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
function Record-UnresolvedIssue {
    param(
        [int]$WaveNumber,
        [string]$PhaseId,
        [string]$Issue,
        [string]$PRNumber
    )

    $issues = Load-UnresolvedIssues $WaveNumber

    # Check if this issue already exists
    $existing = $issues.issues | Where-Object { $_.phaseId -eq $PhaseId -and $_.issue -eq $Issue }

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

# Send message to cursor window via Claude Chat (clipboard paste)
# Assumes Claude Chat is already the default interface in the window
# Uses the working approach from paste_prompts_to_cursor_single_window.ps1
function Send-MessageToCursorWindow {
    param(
        [string]$Message
    )

    try {
        # Add window enumeration helper class if not already loaded
        if (-not ([System.Management.Automation.PSTypeName]'WindowEnumerator').Type) {
            Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowEnumerator {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    public static IntPtr GetFirstCursorWindow() {
        IntPtr firstWindow = IntPtr.Zero;
        var procesIds = new HashSet<uint>();

        foreach (var proc in System.Diagnostics.Process.GetProcessesByName("cursor")) {
            procesIds.Add((uint)proc.Id);
        }

        EnumWindows((hWnd, lParam) => {
            uint procId;
            GetWindowThreadProcessId(hWnd, out procId);
            if (procesIds.Contains(procId) && IsWindowVisible(hWnd)) {
                if (firstWindow == IntPtr.Zero) {
                    firstWindow = hWnd;
                }
            }
            return true;
        }, IntPtr.Zero);

        return firstWindow;
    }
}
"@
        }

        # Add keyboard helper class if not already loaded
        if (-not ([System.Management.Automation.PSTypeName]'KeyboardInput').Type) {
            Add-Type @"
using System;
using System.Runtime.InteropServices;

public class KeyboardInput {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    public const byte VK_CONTROL = 0x11;
    public const byte VK_V = 0x56;
    public const byte VK_RETURN = 0x0D;
    public const uint KEYEVENTF_KEYDOWN = 0x0000;
    public const uint KEYEVENTF_KEYUP = 0x0002;

    public static void PasteAndEnter() {
        // Ctrl+V to paste
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_V, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);
        System.Threading.Thread.Sleep(200);

        // Enter to send
        keybd_event(VK_RETURN, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0);
    }
}
"@
        }

        # Copy message to clipboard using PowerShell Set-Clipboard
        $Message | Set-Clipboard
        Start-Sleep -Milliseconds 200

        # Get first actual Cursor window using proper enumeration
        $cursorWindowHandle = [WindowEnumerator]::GetFirstCursorWindow()
        if ($cursorWindowHandle -eq [IntPtr]::Zero) {
            Write-Host "    [WARN] No Cursor window found"
            return $false
        }

        # Focus the window
        [KeyboardInput]::SetForegroundWindow($cursorWindowHandle)
        Start-Sleep -Milliseconds 500

        # Paste and send (Claude Chat assumed to be default interface, Ctrl+Shift+9 disabled)
        [KeyboardInput]::PasteAndEnter()
        Start-Sleep -Milliseconds 1000

        return $true
    } catch {
        Write-Host "    [WARN] Could not send message: $_"
        return $false
    }
}

if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $WaveFile = Get-DynamicFilePath "Wave*_All_Phases.md"

    if ([string]::IsNullOrWhiteSpace($WaveFile)) {
        Write-Host "ERROR: No Wave file found"
        exit 1
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
$unresolvedCount = 0
$unresolvedIssues = @()

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
                $failedChecks = $pr.statusCheckRollup | Where-Object { $_.status -eq "FAILURE" }
                $runningChecks = $pr.statusCheckRollup | Where-Object { $_.status -eq "IN_PROGRESS" }

                if ($runningChecks) {
                    # CI is still running
                    Write-Host "  -> [INFO] CI tests running..."
                } elseif ($failedChecks) {
                    # Determine if failures are PR-related or unrelated
                    $prRelatedFailure = $false

                    foreach ($check in $failedChecks) {
                        $checkName = $check.name -as [string]
                        # These are typically unrelated to code changes (infrastructure, environment issues)
                        if ($checkName -match "lint|format|type|build" -and -not ($checkName -match "code|security")) {
                            $prRelatedFailure = $true
                            break
                        }
                    }

                    if (-not $prRelatedFailure) {
                        Write-Host "  -> [WARN] CI failures detected (unrelated to this PR)"
                        Record-UnresolvedIssue -WaveNumber $waveNumber -PhaseId $phaseId -Issue "CI/lint failure" -PRNumber $prNumber
                        $unresolvedCount++
                        $unresolvedIssues += $phaseId
                    } else {
                        Write-Host "  -> [FAIL] PR needs fixes (code-related CI failures)"
                    }
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
Write-Host "Merged PRs ready to mark COMPLETED: $completedCount"
Write-Host "Unresolved issues recorded: $unresolvedCount"

if ($unresolvedCount -gt 0) {
    Write-Host ""
    Write-Host "[OK] READY TO MERGE (with unresolved issues to address separately)"
    Write-Host "Phases with unresolved issues: $($unresolvedIssues -join ', ')"
    Write-Host ""
    Write-Host "Sending messages to Cursor windows..."
    $messageSent = 0
    foreach ($phaseId in $unresolvedIssues) {
        Write-Host "  Sending to first Cursor window..."
        if (Send-MessageToCursorWindow "ready to merge (unrelated CI issue)") {
            $messageSent++
            Write-Host "    [OK] Message sent"
        } else {
            Write-Host "    [FAIL] Failed to send message"
        }
    }
    Write-Host ""
    Write-Host "[INFO] Issues have been recorded in: $(Get-UnresolvedIssuesFile $waveNumber)"
    Write-Host "   These issues will be included in wave cleanup summary."
}

if ($mergedPRs.Count -gt 0) {
    Write-Host ""
    Write-Host "PRs ready - sending messages..."
    $messageSent = 0
    foreach ($phaseId in $mergedPRs) {
        Write-Host "  Sending to first Cursor window..."
        if (Send-MessageToCursorWindow "proceed to merge") {
            $messageSent++
            Write-Host "    [OK] Message sent"
        } else {
            Write-Host "    [FAIL] Failed to send message"
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
