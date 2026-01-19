# Launch a new Cursor window and position it to a specific grid slot
# Usage: .\launch_cursor_for_slot.ps1 -SlotNumber 1 -ProjectPath "C:\dev\Autopack_w1_sec001"
# Launches Cursor with the project directory, then positions the new window to the slot
# KEY: This script only LAUNCHES the window and POSITIONS it. It does NOT move existing windows.

param(
    [int]$SlotNumber = 1,  # 1-9
    [string]$ProjectPath = "",  # Path to project directory to open (optional)
    [int]$MaxWaitSeconds = 10  # Max time to wait for window to appear
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

# Grid slot coordinates for 5120x1440 ultra-wide monitor (right half only)
# CRITICAL: Bottom row positioned to avoid taskbar cutoff
# Monitor: 5120x1440 total, 50px taskbar at bottom
# Available height: 1390px (1440 - 50 taskbar)
# 3x3 grid: 463px per row (except row 3: 464px)
# NO GAPS - edge-to-edge layout
$gridSlots = @{
    1 = @{X=2560; Y=0; W=853; H=463}      # Top-Left
    2 = @{X=3413; Y=0; W=853; H=463}      # Top-Center
    3 = @{X=4266; Y=0; W=854; H=463}      # Top-Right
    4 = @{X=2560; Y=463; W=853; H=463}    # Mid-Left
    5 = @{X=3413; Y=463; W=853; H=463}    # Mid-Center
    6 = @{X=4266; Y=463; W=854; H=463}    # Mid-Right
    7 = @{X=2560; Y=926; W=853; H=464}    # Bot-Left (includes extra 1px)
    8 = @{X=3413; Y=926; W=853; H=464}    # Bot-Center
    9 = @{X=4266; Y=926; W=854; H=464}    # Bot-Right
}

Write-Host ""
Write-Host "============ LAUNCH CURSOR FOR SLOT ============" -ForegroundColor Cyan
Write-Host "Target Slot: $SlotNumber"
Write-Host ""

# CRITICAL: Get window handles BEFORE launch to identify new windows later
$existingWindows = [WindowHelper]::GetWindowsByProcessName("cursor")
$existingWindowHandles = @($existingWindows | ForEach-Object { $_.GetHashCode() })
Write-Host "[INFO] Current Cursor windows: $($existingWindows.Count)"
Write-Host "[CRITICAL] Existing window IDs (will NOT touch these): $($existingWindowHandles -join ', ')"

# Launch Cursor application
Write-Host "[ACTION] Launching Cursor..."
try {
    if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
        # Force new window with -n flag
        Start-Process -FilePath "cursor" -ArgumentList "-n" -ErrorAction Stop
    } else {
        Write-Host "[INFO] Opening project: $ProjectPath"
        # Force new window with -n flag, then specify path
        Start-Process -FilePath "cursor" -ArgumentList "-n", $ProjectPath -ErrorAction Stop
    }
} catch {
    Write-Host "[ERROR] Failed to launch Cursor: $_" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Waiting for new window to appear..."

# Wait for new window to appear (with timeout)
$newWindow = $null
$elapsedSeconds = 0
$checkInterval = 200  # milliseconds

while ($elapsedSeconds -lt $MaxWaitSeconds) {
    Start-Sleep -Milliseconds $checkInterval
    $currentWindows = [WindowHelper]::GetWindowsByProcessName("cursor")

    # Find the NEW window(s) - one that's NOT in the existing list
    foreach ($window in $currentWindows) {
        $windowId = $window.GetHashCode()
        if ($existingWindowHandles -notcontains $windowId) {
            $newWindow = $window
            $title = [WindowHelper]::GetWindowTitle($newWindow)
            Write-Host "[FOUND] New window: $title"
            break
        }
    }

    if ($null -ne $newWindow) {
        break
    }

    $elapsedSeconds += ($checkInterval / 1000)
}

if ($null -eq $newWindow) {
    Write-Host "[WARNING] Timeout waiting for Cursor window to appear" -ForegroundColor Yellow
    Write-Host "[INFO] Cursor may be starting in background - giving extra time..."

    # Give it more time and try once more
    Start-Sleep -Seconds 2
    $currentWindows = [WindowHelper]::GetWindowsByProcessName("cursor")

    foreach ($window in $currentWindows) {
        $windowId = $window.GetHashCode()
        if ($existingWindowHandles -notcontains $windowId) {
            $newWindow = $window
            $title = [WindowHelper]::GetWindowTitle($newWindow)
            Write-Host "[FOUND] New window after delay: $title"
            break
        }
    }

    if ($null -eq $newWindow) {
        Write-Host "[ERROR] Still no new window found" -ForegroundColor Red
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

# Give window time to fully initialize and load the project
# This is critical: Cursor needs time to:
# 1. Launch the process
# 2. Load the specified project directory
# 3. Initialize the UI
# Extended delay to ensure Cursor finishes loading before we position the window
Start-Sleep -Milliseconds 5000

# Restore if minimized
if ([WindowHelper]::IsIconic($newWindow)) {
    Write-Host "[INFO] Restoring window..."
    [WindowHelper]::ShowWindow($newWindow, 9)
    Start-Sleep -Milliseconds 200
}

# Move window to slot
Write-Host "[ACTION] Moving new window to slot $SlotNumber..."
$result = [WindowHelper]::MoveWindow($newWindow, $x, $y, $w, $h, $true)

if ($result) {
    Write-Host "[OK] Window positioned successfully"
} else {
    Write-Host "[WARNING] MoveWindow returned false (window may still have moved)"
}

# Bring to foreground
[WindowHelper]::SetForegroundWindow($newWindow) | Out-Null

# Wait a bit more after positioning to allow project to load
Start-Sleep -Milliseconds 1000

Write-Host ""
Write-Host "[DONE] New Cursor window launched and positioned to slot $SlotNumber"
Write-Host "[INFO] Window will open project: $(if ([string]::IsNullOrWhiteSpace($ProjectPath)) { 'default' } else { $ProjectPath })"
