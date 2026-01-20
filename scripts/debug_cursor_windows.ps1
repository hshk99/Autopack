# Debug script to check all Cursor windows
Write-Host ""
Write-Host "============ CURSOR WINDOW DEBUG ============" -ForegroundColor Cyan
Write-Host ""

# Define WindowHelper to enumerate windows
if (-not ([System.Management.Automation.PSTypeName]'WindowHelper').Type) {
    Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowHelper {
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

    public static List<IntPtr> GetWindowsByProcessName(string processName) {
        var windows = new List<IntPtr>();
        var processIds = new HashSet<uint>();

        foreach (var proc in System.Diagnostics.Process.GetProcessesByName(processName)) {
            processIds.Add((uint)proc.Id);
        }

        EnumWindows((hWnd, lParam) => {
            uint procId;
            GetWindowThreadProcessId(hWnd, out procId);

            if (processIds.Contains(procId)) {
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
}
"@
}

# Check all Cursor processes
$cursorProcs = Get-Process -Name 'cursor' -ErrorAction SilentlyContinue
Write-Host "Total Cursor processes: $($cursorProcs.Count)"
Write-Host ""

# Check which ones have visible windows
$windows = [WindowHelper]::GetWindowsByProcessName("Cursor")
Write-Host "Cursor processes with VISIBLE windows: $($windows.Count)"
Write-Host ""

if ($windows.Count -gt 0) {
    Write-Host "Windows found:"
    foreach ($hwnd in $windows) {
        $title = [WindowHelper]::GetWindowTitle($hwnd)
        Write-Host $title
    }
} else {
    Write-Host "[WARNING] No visible Cursor windows found"
}

Write-Host ""
Write-Host "Process details:"
foreach ($proc in $cursorProcs) {
    $procId = $proc.Id
    $title = $proc.MainWindowTitle
    $handles = $proc.Handles
    Write-Host "PID $procId - $title - Handles: $handles"
}
Write-Host ""
