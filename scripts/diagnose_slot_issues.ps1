# Diagnostic script to understand why slots 3 and 5 didn't receive messages
# This script simulates what check_pr_status.ps1 does and shows the mapping

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "SLOT ISSUE DIAGNOSTIC" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Define WindowHelper
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

# Helper function to map window positions to grid slots (exact copy from check_pr_status.ps1)
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

    if ($col -eq 0 -or $row -eq 0) {
        return 0
    }

    $slot = ($row - 1) * 3 + $col
    return $slot
}

Write-Host "STEP 1: Enumerate Cursor Windows" -ForegroundColor Yellow
Write-Host ""

$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")
Write-Host "Found $($cursorWindows.Count) Cursor windows"
Write-Host ""

$windowSlotMap = @{}

foreach ($window in $cursorWindows) {
    $title = [WindowHelper]::GetWindowTitle($window)
    $rect = [WindowHelper]::GetWindowRect($window)

    # Show all windows
    Write-Host "Window: $title"
    Write-Host "  Position: X=$($rect.Left), Y=$($rect.Top)"

    # Extract phase ID from window title
    if ($title -match "Autopack_w\d+_([^\s]+)") {
        $phaseId = $Matches[1]
        $slot = Get-WindowSlotNumber -WindowX $rect.Left -WindowY $rect.Top

        Write-Host "  Phase ID: $phaseId"
        Write-Host "  Calculated Slot: $slot"

        if ($slot -gt 0) {
            $windowSlotMap[$phaseId] = $slot
            Write-Host "  -> MAPPED: $phaseId -> Slot $slot" -ForegroundColor Green
        } else {
            Write-Host "  -> NOT IN GRID (slot=0)" -ForegroundColor Red
        }
    } else {
        Write-Host "  -> No phase ID in title" -ForegroundColor Yellow
    }
    Write-Host ""
}

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "WINDOW SLOT MAP SUMMARY" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Show the final mapping
foreach ($slot in 1..9) {
    $phase = $windowSlotMap.GetEnumerator() | Where-Object { $_.Value -eq $slot } | Select-Object -First 1
    if ($phase) {
        Write-Host "Slot $slot : $($phase.Key)" -ForegroundColor Green
    } else {
        Write-Host "Slot $slot : (empty)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "STEP 2: Check PENDING Phases" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Load wave file
$backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
$waveFiles = Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
$WaveFile = $waveFiles[0].FullName
Write-Host "Wave file: $WaveFile"
Write-Host ""

$prompts = @(& "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile 2>&1 | Where-Object { $_ -ne $null -and -not ($_ -is [string]) })
$pendingPrompts = @($prompts | Where-Object { $_.Status -eq "PENDING" })

Write-Host "PENDING phases ($($pendingPrompts.Count)):" -ForegroundColor Yellow
foreach ($p in $pendingPrompts) {
    $slot = $windowSlotMap[$p.ID]
    $slotInfo = if ($slot) { "-> Slot $slot" } else { "-> NO SLOT MAPPED" }
    Write-Host "  $($p.ID) : $($p.Branch) $slotInfo"
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "STEP 3: Check Which Slots Would NOT Get Messages" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Simulate check_pr_status logic - only first 9 pending prompts are checked
$first9Pending = $pendingPrompts | Select-Object -First 9
Write-Host "First 9 PENDING phases (these are what check_pr_status checks):" -ForegroundColor Yellow
foreach ($p in $first9Pending) {
    $slot = $windowSlotMap[$p.ID]
    if ($null -ne $slot -and $slot -gt 0) {
        Write-Host "  $($p.ID) -> Slot $slot (WOULD GET MESSAGE)" -ForegroundColor Green
    } else {
        Write-Host "  $($p.ID) -> NO SLOT (WOULD NOT GET MESSAGE)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "CONCLUSION" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Check if feat003 and cost001 are in the mapping
$slot3Phase = $windowSlotMap.GetEnumerator() | Where-Object { $_.Value -eq 3 } | Select-Object -First 1
$slot5Phase = $windowSlotMap.GetEnumerator() | Where-Object { $_.Value -eq 5 } | Select-Object -First 1

if ($slot3Phase) {
    $inPending = $first9Pending | Where-Object { $_.ID -eq $slot3Phase.Key }
    if ($inPending) {
        Write-Host "Slot 3 ($($slot3Phase.Key)): IN first 9 PENDING list - SHOULD receive message" -ForegroundColor Green
    } else {
        Write-Host "Slot 3 ($($slot3Phase.Key)): NOT in first 9 PENDING list - will NOT receive message" -ForegroundColor Red
    }
} else {
    Write-Host "Slot 3: No window mapped to this slot" -ForegroundColor Red
}

if ($slot5Phase) {
    $inPending = $first9Pending | Where-Object { $_.ID -eq $slot5Phase.Key }
    if ($inPending) {
        Write-Host "Slot 5 ($($slot5Phase.Key)): IN first 9 PENDING list - SHOULD receive message" -ForegroundColor Green
    } else {
        Write-Host "Slot 5 ($($slot5Phase.Key)): NOT in first 9 PENDING list - will NOT receive message" -ForegroundColor Red
    }
} else {
    Write-Host "Slot 5: No window mapped to this slot" -ForegroundColor Red
}

Write-Host ""
