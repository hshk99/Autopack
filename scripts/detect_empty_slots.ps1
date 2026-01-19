# Detect empty cursor window slots in the 3x3 grid
# Returns array of slot numbers (1-9) that are empty
# Uses WindowHelper API to identify windows in grid positions
# Usage: .\detect_empty_slots.ps1

# Grid coordinates (from STREAMDECK_REFERENCE.md, verified 2026-01-19)
# These are the window LEFT/TOP positions, not center points
# Window positions: X=2560/3413/4266, Y=0/463/926
# Window size: ~853x463 per slot
$gridCoordinates = @{
    1 = @{X=2560; Y=0;   Name="Slot 1 (Top-Left)"}
    2 = @{X=3413; Y=0;   Name="Slot 2 (Top-Center)"}
    3 = @{X=4266; Y=0;   Name="Slot 3 (Top-Right)"}
    4 = @{X=2560; Y=463; Name="Slot 4 (Mid-Left)"}
    5 = @{X=3413; Y=463; Name="Slot 5 (Mid-Center)"}
    6 = @{X=4266; Y=463; Name="Slot 6 (Mid-Right)"}
    7 = @{X=2560; Y=926; Name="Slot 7 (Bot-Left)"}
    8 = @{X=3413; Y=926; Name="Slot 8 (Bot-Center)"}
    9 = @{X=4266; Y=926; Name="Slot 9 (Bot-Right)"}
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

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

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

Write-Host ""
Write-Host "============ DETECTING EMPTY SLOTS ============" -ForegroundColor Cyan
Write-Host ""

# Get all Cursor windows
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")

Write-Host "Found $($cursorWindows.Count) Cursor windows open"
Write-Host ""

# Collect window titles and positions
$windowTitles = @{}
$windowRects = @{}

foreach ($window in $cursorWindows) {
    $title = [WindowHelper]::GetWindowTitle($window)
    $rect = [WindowHelper]::GetWindowRect($window)

    $windowTitles[$window.ToString()] = $title
    $windowRects[$window.ToString()] = $rect

    Write-Host "[WINDOW] $title"
    Write-Host "  Position: X=$($rect.Left), Y=$($rect.Top) | Size: $($rect.Right - $rect.Left)x$($rect.Bottom - $rect.Top)"
}

Write-Host ""
Write-Host "============ GRID ANALYSIS ============" -ForegroundColor Cyan
Write-Host ""

# Check each grid slot
$emptySlots = @()
$filledSlots = @()

foreach ($slotNum in 1..9) {
    $coord = $gridCoordinates[$slotNum]
    $expectedX = $coord.X
    $expectedY = $coord.Y

    # Check if any window occupies this slot (match by window LEFT/TOP position)
    $tolerance = 100  # pixels
    $isOccupied = $false

    foreach ($window in $cursorWindows) {
        $key = $window.ToString()
        $rect = $windowRects[$key]

        # Check if window position matches expected slot position
        if ($rect.Left -ge ($expectedX - $tolerance) -and $rect.Left -le ($expectedX + $tolerance) -and
            $rect.Top -ge ($expectedY - $tolerance) -and $rect.Top -le ($expectedY + $tolerance)) {
            $isOccupied = $true
            $title = $windowTitles[$key]
            Write-Host "[FILLED] $($coord.Name) - $title" -ForegroundColor Green
            $filledSlots += $slotNum
            break
        }
    }

    if (-not $isOccupied) {
        Write-Host "[EMPTY] $($coord.Name)" -ForegroundColor Yellow
        $emptySlots += $slotNum
    }
}

Write-Host ""
Write-Host "============ SUMMARY ============" -ForegroundColor Cyan
Write-Host "Filled slots: $($filledSlots -join ', ')"
Write-Host "Empty slots: $($emptySlots -join ', ')"
Write-Host "Available for fill: $($emptySlots.Count)"
Write-Host ""

# Return empty slots for pipeline use
$emptySlots
