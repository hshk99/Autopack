# Full debug version of check_pr_status to find why slots 3 and 5 don't get messages
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "DEBUG: Full PR Check with Slot Mapping" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

$backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"

function Get-DynamicFilePath {
    param([string]$Pattern)
    $files = @(Get-ChildItem -Path $backupDir -Filter $Pattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($files.Count -gt 0) { return $files[0].FullName }
    return $null
}

function Get-WindowSlotNumber {
    param([int]$WindowX, [int]$WindowY)
    $tolerance = 100
    $col = 0
    if ($WindowX -ge (2560 - $tolerance) -and $WindowX -le (2560 + $tolerance)) { $col = 1 }
    elseif ($WindowX -ge (3413 - $tolerance) -and $WindowX -le (3413 + $tolerance)) { $col = 2 }
    elseif ($WindowX -ge (4266 - $tolerance) -and $WindowX -le (4266 + $tolerance)) { $col = 3 }
    $row = 0
    if ($WindowY -ge (0 - $tolerance) -and $WindowY -le (0 + $tolerance)) { $row = 1 }
    elseif ($WindowY -ge (463 - $tolerance) -and $WindowY -le (463 + $tolerance)) { $row = 2 }
    elseif ($WindowY -ge (926 - $tolerance) -and $WindowY -le (926 + $tolerance)) { $row = 3 }
    if ($col -eq 0 -or $row -eq 0) { return 0 }
    return (($row - 1) * 3 + $col)
}

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

$WaveFile = Get-DynamicFilePath "Wave*_All_Phases.md"
Write-Host "Wave file: $WaveFile"
Write-Host ""

# Load prompts
$prompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })
$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" })

Write-Host "PENDING phases: $($pendingPrompts.Count)"
Write-Host ""

# Build window slot map
Write-Host "STEP 1: Building Window Slot Map" -ForegroundColor Yellow
Write-Host ""

$windowSlotMap = @{}
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")
Write-Host "Found $($cursorWindows.Count) Cursor windows"
Write-Host ""

foreach ($window in $cursorWindows) {
    $title = [WindowHelper]::GetWindowTitle($window)
    $rect = [WindowHelper]::GetWindowRect($window)

    if ($title -match "Autopack_w\d+_([^\s]+)") {
        $phaseId = $Matches[1]
        $slot = Get-WindowSlotNumber -WindowX $rect.Left -WindowY $rect.Top

        Write-Host "Window: '$title'"
        Write-Host "  Extracted phaseId: '$phaseId'"
        Write-Host "  Position: X=$($rect.Left), Y=$($rect.Top)"
        Write-Host "  Calculated slot: $slot"

        if ($slot -gt 0) {
            $windowSlotMap[$phaseId] = $slot
            Write-Host "  -> MAPPED to slot $slot" -ForegroundColor Green
        } else {
            Write-Host "  -> NOT IN GRID" -ForegroundColor Red
        }
        Write-Host ""
    }
}

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "WINDOW SLOT MAP (final):" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
foreach ($entry in $windowSlotMap.GetEnumerator()) {
    Write-Host "  '$($entry.Key)' -> Slot $($entry.Value)"
}
Write-Host ""

# Check PRs and build CI failed list
Write-Host "STEP 2: Checking PRs" -ForegroundColor Yellow
Write-Host ""

$ciFailedPhases = @()

foreach ($prompt in $pendingPrompts | Select-Object -First 9) {
    $phaseId = $prompt.ID
    $branchName = $prompt.Branch

    Write-Host "$phaseId (branch: $branchName)..."

    $prJson = gh pr list --head $branchName --state all --json number,state,statusCheckRollup 2>$null | ConvertFrom-Json

    if ($null -ne $prJson -and $prJson.Count -gt 0) {
        $pr = if ($prJson -is [array]) { $prJson[0] } else { $prJson }
        $state = $pr.state
        $prNumber = $pr.number

        if ($state -eq "OPEN") {
            $hasChecks = $null -ne $pr.statusCheckRollup -and $pr.statusCheckRollup -is [array]
            if ($hasChecks) {
                $failedChecks = @($pr.statusCheckRollup | Where-Object { $_.conclusion -eq "FAILURE" })
                $runningChecks = @($pr.statusCheckRollup | Where-Object { $_.status -eq "IN_PROGRESS" })

                if ($runningChecks.Count -gt 0) {
                    Write-Host "  -> PR #${prNumber} CI running"
                } elseif ($failedChecks.Count -gt 0) {
                    Write-Host "  -> PR #${prNumber} CI FAILED" -ForegroundColor Red
                    $ciFailedPhases += $phaseId
                    Write-Host "  -> Added '$phaseId' to ciFailedPhases" -ForegroundColor Yellow
                } else {
                    Write-Host "  -> PR #${prNumber} CI PASSING"
                }
            }
        }
    } else {
        Write-Host "  -> No PR found"
    }
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "CI FAILED PHASES:" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
foreach ($phaseId in $ciFailedPhases) {
    Write-Host "  '$phaseId'"
}
Write-Host ""

Write-Host "STEP 3: Sending Messages" -ForegroundColor Yellow
Write-Host ""

foreach ($phaseId in $ciFailedPhases) {
    Write-Host "Processing phase: '$phaseId'"

    # Check if key exists in map
    $keyExists = $windowSlotMap.ContainsKey($phaseId)
    Write-Host "  Key '$phaseId' exists in windowSlotMap: $keyExists"

    if ($keyExists) {
        $slot = $windowSlotMap[$phaseId]
        Write-Host "  Slot value: $slot"
        Write-Host "  Slot is not null: $($null -ne $slot)"
        Write-Host "  Slot > 0: $($slot -gt 0)"

        if ($null -ne $slot -and $slot -gt 0) {
            Write-Host "  -> WOULD SEND MESSAGE to slot $slot" -ForegroundColor Green
        } else {
            Write-Host "  -> WOULD SKIP (slot is null or 0)" -ForegroundColor Red
        }
    } else {
        Write-Host "  -> WOULD SKIP (key not found in map)" -ForegroundColor Red

        # Debug: show all keys in map
        Write-Host "  All keys in windowSlotMap:"
        foreach ($key in $windowSlotMap.Keys) {
            $match = if ($key -eq $phaseId) { " <-- SHOULD MATCH!" } else { "" }
            Write-Host "    '$key' (length: $($key.Length))$match"
        }
        Write-Host "  Looking for: '$phaseId' (length: $($phaseId.Length))"
    }
    Write-Host ""
}
