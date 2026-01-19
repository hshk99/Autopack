# Check PR status for all [PENDING] phases and send auto-messages to cursors
# Usage: .\check_pr_status.ps1
# StreamDeck: check_pr_status.ps1 (no .bat wrapper needed)

param(
    [int]$WaveNumber = 0,
    [string]$WaveFile = "",
    [switch]$DryRun,
    [switch]$Interactive
)

Write-Host ""
Write-Host "============ PR STATUS CHECK ============" -ForegroundColor Cyan
Write-Host ""

# Auto-detect wave file if not provided
if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
    $waveFiles = @(Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)

    if ($waveFiles.Count -eq 0) {
        Write-Host "[ERROR] No Wave*_All_Phases.md file found" -ForegroundColor Red
        exit 1
    }

    $WaveFile = $waveFiles[0].FullName
    Write-Host "[AUTO-DETECT] Using: $($waveFiles[0].Name)"

    if ($waveFiles[0].Name -match "Wave(\d)_") {
        $WaveNumber = [int]$Matches[1]
    }
}

if (-not (Test-Path $WaveFile)) {
    Write-Host "[ERROR] Wave file not found: $WaveFile" -ForegroundColor Red
    exit 1
}

# Load all prompts
$prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile
$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" })

if ($pendingPrompts.Count -eq 0) {
    Write-Host "[INFO] No [PENDING] phases to check"
    Write-Host ""
    exit 0
}

Write-Host "Found $($pendingPrompts.Count) [PENDING] phase(s)"
Write-Host ""
Write-Host "Checking PR status..."
Write-Host ""

$passCount = 0
$failCount = 0
$runningCount = 0

# Get list of open cursor windows to map phases to slots
# Need WindowHelper to detect which cursor window is in which slot
if (-not ([System.Management.Automation.PSTypeName]'WindowHelper').Type) {
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowHelper {
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

    public struct RECT {
        public int Left, Top, Right, Bottom;
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

# Map pending phases to cursor slots
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")
$slotMap = @{}  # Maps phase ID to slot number

foreach ($window in $cursorWindows) {
    $title = [WindowHelper]::GetWindowTitle($window)
    $rect = [WindowHelper]::GetWindowRect($window)

    # Determine which slot this window is in based on coordinates
    # Slot 1: X=2560, Slot 2: X=3413, Slot 3: X=4266
    # Slot 4: X=2560, Slot 5: X=3413, Slot 6: X=4266
    # Slot 7: X=2560, Slot 8: X=3413, Slot 9: X=4266
    $slot = 0
    if ($rect.Left -ge 2560 -and $rect.Left -lt 3413) {
        $xCol = 1
    } elseif ($rect.Left -ge 3413 -and $rect.Left -lt 4266) {
        $xCol = 2
    } elseif ($rect.Left -ge 4266 -and $rect.Left -le 5120) {
        $xCol = 3
    } else {
        continue  # Not in grid
    }

    if ($rect.Top -ge 0 -and $rect.Top -lt 463) {
        $yRow = 1
    } elseif ($rect.Top -ge 463 -and $rect.Top -lt 926) {
        $yRow = 2
    } elseif ($rect.Top -ge 926 -and $rect.Top -le 1440) {
        $yRow = 3
    } else {
        continue  # Not in grid
    }

    $slot = ($yRow - 1) * 3 + $xCol

    # Extract phase ID from window title if present
    if ($title -match "Autopack_w\d+_(.+?)\s*[-]") {
        $phaseId = $Matches[1]
        $slotMap[$phaseId] = $slot
    }
}

# Check each pending prompt's PR status
foreach ($prompt in $pendingPrompts) {
    $phaseId = $prompt.ID
    $branchName = $prompt.Branch  # Use actual branch name from Wave file

    Write-Host "[$phaseId]" -ForegroundColor Cyan

    # Get slot number for this phase
    $slotNumber = $slotMap[$phaseId]
    $windowOpen = $null -ne $slotNumber

    if ($windowOpen) {
        Write-Host "  Slot: $slotNumber"
    } else {
        Write-Host "  Status: ℹ️ Phase not in any open cursor window (will still check PR)"
    }

    # Query GitHub PR status using gh CLI
    # Use correct fields: state (OPEN/MERGED/CLOSED), statusCheckRollup (CI status)
    # Need to check all states because a PR might already be merged
    $prJson = gh pr list --head $branchName --state all --json number,state,statusCheckRollup,title 2>/dev/null | ConvertFrom-Json

    if ($null -eq $prJson -or $prJson.Count -eq 0) {
        Write-Host "  Status: ⏳ PR NOT CREATED YET"
        Write-Host "  Action: Waiting for PR creation in cursor window"
        $runningCount++
    } else {
        $pr = $prJson
        if ($pr -is [array]) { $pr = $pr[0] }

        $prNumber = $pr.number
        $state = $pr.state
        $statusChecks = $pr.statusCheckRollup

        # Determine overall CI status from statusCheckRollup
        $ciStatus = "UNKNOWN"
        $hasFailure = $false
        $hasRunning = $false

        if ($null -ne $statusChecks -and $statusChecks.Count -gt 0) {
            foreach ($check in $statusChecks) {
                $conclusion = $check.conclusion
                $status = $check.status

                # Check for failures (conclusion: FAILURE)
                if ($conclusion -eq "FAILURE") {
                    $hasFailure = $true
                    break
                }

                # Check if still running (status: IN_PROGRESS)
                if ($status -eq "IN_PROGRESS") {
                    $hasRunning = $true
                }
            }

            if ($hasFailure) {
                $ciStatus = "FAIL"
            } elseif ($hasRunning) {
                $ciStatus = "RUNNING"
            } else {
                # All checks completed without failures
                $ciStatus = "PASS"
            }
        }

        # Check if PR is already merged
        if ($state -eq "MERGED") {
            Write-Host "  Status: MERGED (PR $($prNumber))" -ForegroundColor Green
            Write-Host "  Action: Auto-marking phase as [COMPLETED]..."

            if (-not $DryRun) {
                # Only send message if window is open
                if ($windowOpen) {
                    & "C:\dev\Autopack\scripts\send_message_to_cursor_slot.ps1" -SlotNumber $slotNumber -Message "PR merged - phase complete!" 2>/dev/null
                    Write-Host "  Message sent to slot $($slotNumber): 'PR merged - phase complete!'"
                }

                # Auto-mark as COMPLETED when PR is merged (regardless of window status)
                Write-Host "  Updating phase status to [COMPLETED]..."
                & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus "COMPLETED" 2>/dev/null
                Write-Host "  ✅ Phase marked [COMPLETED] - ready for Button 4 cleanup"
            }
            $passCount++
        } elseif ($ciStatus -eq "PASS") {
            Write-Host "  Status: CI PASSING (PR $($prNumber))" -ForegroundColor Green

            if ($windowOpen) {
                Write-Host "  Action: Auto-sending message to slot $($slotNumber)..."
                if (-not $DryRun) {
                    & "C:\dev\Autopack\scripts\send_message_to_cursor_slot.ps1" -SlotNumber $slotNumber -Message "proceed to merge" 2>/dev/null
                    Write-Host "  Message sent: 'proceed to merge'"
                }
            } else {
                Write-Host "  Action: Window not open, skipping message (window can proceed to merge manually)"
            }

            if (-not $DryRun) {
                # Auto-mark as COMPLETED when PR CI is passing
                Write-Host "  Updating phase status to [COMPLETED]..."
                & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Update -WaveFile $WaveFile -PhaseId $phaseId -NewStatus "COMPLETED" 2>/dev/null
                Write-Host "  ✅ Phase marked [COMPLETED] - ready for Button 4 cleanup"
            }
            $passCount++
        } elseif ($ciStatus -eq "FAIL") {
            Write-Host "  Status: CI FAILING (PR $($prNumber))" -ForegroundColor Red

            if ($windowOpen) {
                Write-Host "  Action: Auto-sending message to slot $($slotNumber)..."
                if (-not $DryRun) {
                    & "C:\dev\Autopack\scripts\send_message_to_cursor_slot.ps1" -SlotNumber $slotNumber -Message "CI check failed. fix the issue then re-run the test" 2>/dev/null
                    Write-Host "  Message sent: 'CI check failed. fix the issue then re-run the test'"
                }
            } else {
                Write-Host "  Action: Window not open, skipping message"
            }
            $failCount++
        } else {
            Write-Host "  Status: CI RUNNING (PR $($prNumber))" -ForegroundColor Yellow
            Write-Host '  Action: None. Wait for CI to complete.'
            $runningCount++
        }
    }

    Write-Host ""
}

Write-Host 'STATUS SUMMARY' -ForegroundColor Green
Write-Host ('PASSING: ' + $passCount + ' phases') -ForegroundColor Green
Write-Host ('FAILING: ' + $failCount + ' phases') -ForegroundColor Red
Write-Host ('RUNNING: ' + $runningCount + ' phases') -ForegroundColor Yellow

if ($failCount -gt 0) {
    Write-Host 'ACTION: Review failing PRs' -ForegroundColor Yellow
}
