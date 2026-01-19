# Test if WindowEnumerator can find Cursor windows

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

    public static List<IntPtr> GetAllCursorWindows() {
        var windows = new List<IntPtr>();
        var procesIds = new HashSet<uint>();

        foreach (var proc in System.Diagnostics.Process.GetProcessesByName("cursor")) {
            procesIds.Add((uint)proc.Id);
        }

        EnumWindows((hWnd, lParam) => {
            uint procId;
            GetWindowThreadProcessId(hWnd, out procId);
            if (procesIds.Contains(procId) && IsWindowVisible(hWnd)) {
                windows.Add(hWnd);
            }
            return true;
        }, IntPtr.Zero);

        return windows;
    }
}
"@
}

Write-Host "Testing Window Enumeration"
Write-Host "============================="
Write-Host ""

$cursor_processes = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
Write-Host "Found $($cursor_processes.Count) Cursor processes"
Write-Host ""

$window = [WindowEnumerator]::GetFirstCursorWindow()
if ($window -eq [IntPtr]::Zero) {
    Write-Host "[ERROR] No Cursor window found via EnumWindows"
} else {
    Write-Host "[OK] Found first Cursor window: $window"
}

Write-Host ""

$all_windows = [WindowEnumerator]::GetAllCursorWindows()
Write-Host "Found $($all_windows.Count) visible Cursor windows"
foreach ($w in $all_windows) {
    Write-Host "  - Window handle: $w"
}
