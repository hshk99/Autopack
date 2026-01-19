# Diagnostic script to show where Cursor windows are positioned
# Usage: .\diagnose_windows.ps1

Write-Host ""
Write-Host "========== CURSOR WINDOW DIAGNOSTIC ==========" -ForegroundColor Cyan
Write-Host ""

if (-not ([System.Management.Automation.PSTypeName]'WindowHelper').Type) {
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowHelper {
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

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

$windows = [WindowHelper]::GetWindowsByProcessName("cursor")
Write-Host "Total Cursor windows: $($windows.Count)"
Write-Host ""

$gridSlots = @{
    1 = @{X=2560; Y=0; W=853; H=463}
    2 = @{X=3413; Y=0; W=853; H=463}
    3 = @{X=4266; Y=0; W=854; H=463}
    4 = @{X=2560; Y=463; W=853; H=463}
    5 = @{X=3413; Y=463; W=853; H=463}
    6 = @{X=4266; Y=463; W=854; H=463}
    7 = @{X=2560; Y=926; W=853; H=464}
    8 = @{X=3413; Y=926; W=853; H=464}
    9 = @{X=4266; Y=926; W=854; H=464}
}

for ($i = 0; $i -lt $windows.Count; $i++) {
    $w = $windows[$i]
    $title = [WindowHelper]::GetWindowTitle($w)
    $rect = [WindowHelper]::GetWindowRect($w)
    $x = $rect.Left
    $y = $rect.Top
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top

    Write-Host "Window $($i+1): $title"
    Write-Host "  Position: X=$x Y=$y | Size: ${width}x$height"

    # Check which slot this window is in
    $slotMatch = $false
    for ($s = 1; $s -le 9; $s++) {
        $slot = $gridSlots[$s]
        if ($x -ge $slot.X -and $x -lt ($slot.X + $slot.W) -and $y -ge $slot.Y -and $y -lt ($slot.Y + $slot.H)) {
            Write-Host "  ✅ In Slot $s"
            $slotMatch = $true
            break
        }
    }

    if (-not $slotMatch) {
        Write-Host "  ❌ NOT in any grid slot!"
    }

    Write-Host ""
}

Write-Host "========== GRID REFERENCE ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Expected Grid Layout (5120x1440) - NO GAPS, NO TASKBAR CUTOFF:"
Write-Host "Row 1 (Y:0-463):        Slots 1,2,3 (Top-Left, Top-Mid, Top-Right)"
Write-Host "Row 2 (Y:463-926):      Slots 4,5,6 (Mid-Left, Mid-Mid, Mid-Right)"
Write-Host "Row 3 (Y:926-1390):     Slots 7,8,9 (Bot-Left, Bot-Mid, Bot-Right) - avoids 50px taskbar"
Write-Host ""
Write-Host "X ranges: 2560-3413 (Slot 1,4,7) | 3413-4266 (Slot 2,5,8) | 4266-5120 (Slot 3,6,9)"
Write-Host ""
