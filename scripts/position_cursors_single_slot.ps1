# Position a single Cursor window to a specific slot in the 3x3 grid
# Usage: .\position_cursors_single_slot.ps1 -SlotNumber 1 -WindowTitle "Autopack_w1_sec001"
# Refactored from position_cursors.ps1 for single-window use

param(
    [int]$SlotNumber = 1,  # 1-9
    [string]$WindowTitle = "",  # If empty, positions the most recent Cursor window
    [switch]$Interactive
)

if ($SlotNumber -lt 1 -or $SlotNumber -gt 9) {
    Write-Host "[ERROR] SlotNumber must be 1-9" -ForegroundColor Red
    exit 1
}

if (-not ([System.Management.Automation.PSTypeName]'WindowHelper').Type) {
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowHelper {
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

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
            uint procId;
            GetWindowThreadProcessId(hWnd, out procId);

            if (processIds.Contains(procId) && IsWindowVisible(hWnd)) {
                int length = GetWindowTextLength(hWnd);
                if (length > 0) {
                    StringBuilder sb = new StringBuilder(length + 1);
                    GetWindowText(hWnd, sb, sb.Capacity);
                    string title = sb.ToString();
                    if (!string.IsNullOrWhiteSpace(title) && title.Length > 1) {
                        windows.Add(hWnd);
                    }
                }
            }
            return true;
        }, IntPtr.Zero);

        return windows;
    }

    public static string GetWindowTitle(IntPtr hWnd) {
        int length = GetWindowTextLength(hWnd);
        if (length == 0) return "";
        StringBuilder sb = new StringBuilder(length + 1);
        GetWindowText(hWnd, sb, sb.Capacity);
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

# Grid slot coordinates for 5120x1440 ultra-wide monitor (right half only)
# Right half: X starts at 2560, width 2560, height 1440
# 3x3 grid: ~853 x 420 pixels per cell (reduced height to account for taskbar)
# Bottom row (slots 7-9) positioned at Y=900 to leave room for taskbar (60px at bottom)
$gridSlots = @{
    1 = @{X=2560; Y=0; W=853; H=463}      # Top-Left
    2 = @{X=3413; Y=0; W=853; H=463}      # Top-Center
    3 = @{X=4266; Y=0; W=854; H=463}      # Top-Right
    4 = @{X=2560; Y=463; W=853; H=463}    # Mid-Left
    5 = @{X=3413; Y=463; W=853; H=463}    # Mid-Center
    6 = @{X=4266; Y=463; W=854; H=463}    # Mid-Right
    7 = @{X=2560; Y=926; W=853; H=464}    # Bot-Left
    8 = @{X=3413; Y=926; W=853; H=464}    # Bot-Center
    9 = @{X=4266; Y=926; W=854; H=464}    # Bot-Right
}

Write-Host ""
Write-Host "============ POSITION SINGLE WINDOW ============" -ForegroundColor Cyan
Write-Host "Target Slot: $SlotNumber"
Write-Host ""

# Get all Cursor windows
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")

if ($cursorWindows.Count -eq 0) {
    Write-Host "[WARNING] No Cursor windows found - skipping positioning" -ForegroundColor Yellow
    exit 0
}

# Find target window
$targetWindow = $null

if ([string]::IsNullOrWhiteSpace($WindowTitle)) {
    # Use the most recently active window (last in list)
    $targetWindow = $cursorWindows[-1]
    $title = [WindowHelper]::GetWindowTitle($targetWindow)
    Write-Host "[AUTO-SELECT] Using most recent window: $title"
} else {
    # Find window by title
    foreach ($window in $cursorWindows) {
        $title = [WindowHelper]::GetWindowTitle($window)
        if ($title -like "*$WindowTitle*") {
            $targetWindow = $window
            Write-Host "[FOUND] $title"
            break
        }
    }

    if ($null -eq $targetWindow) {
        Write-Host "[ERROR] Window '$WindowTitle' not found" -ForegroundColor Red
        exit 1
    }
}

# Get slot coordinates
$slot = $gridSlots[$SlotNumber]
$x = $slot.X
$y = $slot.Y
$w = $slot.W
$h = $slot.H

Write-Host "Position: X=$x, Y=$y | Size: ${w}x$h"
Write-Host ""

# Restore if minimized
if ([WindowHelper]::IsIconic($targetWindow)) {
    Write-Host "[INFO] Restoring minimized window..."
    [WindowHelper]::ShowWindow($targetWindow, 9)
    Start-Sleep -Milliseconds 200
}

# Move window to slot
Write-Host "[ACTION] Moving window to slot $SlotNumber..."
$result = [WindowHelper]::MoveWindow($targetWindow, $x, $y, $w, $h, $true)

if ($result) {
    Write-Host "[OK] Window positioned successfully"
} else {
    Write-Host "[WARNING] MoveWindow returned false (window may still have moved)"
}

Write-Host ""

if ($Interactive) {
    Write-Host "Verify window position. Press Enter to continue..." -ForegroundColor Yellow
    Read-Host
}

Write-Host "[DONE] Slot $SlotNumber is ready"
