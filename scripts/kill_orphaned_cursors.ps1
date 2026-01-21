# Kill ONLY orphaned Cursor processes (those with no window title)
# SAFE: Keeps your main Cursor window (the one with a title)
# Usage: .\kill_orphaned_cursors.ps1

Write-Host ""
Write-Host "============ KILL ORPHANED CURSOR PROCESSES ============" -ForegroundColor Cyan
Write-Host ""

# Define WindowHelper to get window titles
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

    public static List<IntPtr> GetAllCursorWindows() {
        var windows = new List<IntPtr>();
        var processIds = new HashSet<uint>();

        foreach (var proc in System.Diagnostics.Process.GetProcessesByName("cursor")) {
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

# Get all Cursor processes
$allProcs = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
Write-Host "Total Cursor processes: $($allProcs.Count)"

# Get processes with visible windows (have a title)
$windowedProcs = @()
$windows = [WindowHelper]::GetAllCursorWindows()
foreach ($window in $windows) {
    $procId = 0
    [WindowHelper]::GetWindowThreadProcessId($window, [ref]$procId) | Out-Null
    if ($procId -gt 0) {
        $windowedProcs += $procId
    }
}

Write-Host "Processes with windows: $($windowedProcs.Count)"
Write-Host "Orphaned processes (no window): $($allProcs.Count - $windowedProcs.Count)"
Write-Host ""

# Find orphaned processes
$orphaned = @()
foreach ($proc in $allProcs) {
    if ($windowedProcs -notcontains $proc.Id) {
        $orphaned += $proc
    }
}

if ($orphaned.Count -eq 0) {
    Write-Host "[OK] No orphaned Cursor processes found"
    exit 0
}

Write-Host "Orphaned processes to kill:" -ForegroundColor Yellow
foreach ($proc in $orphaned) {
    Write-Host "  PID: $($proc.Id) | Started: $($proc.StartTime)"
}
Write-Host ""

Write-Host "[ACTION] Killing $($orphaned.Count) orphaned process(es)..."
$killed = 0
foreach ($proc in $orphaned) {
    try {
        Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        Write-Host "[OK] Killed PID $($proc.Id)"
        $killed++
    } catch {
        Write-Host "[FAIL] Could not kill PID $($proc.Id): $_" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "============ CLEANUP COMPLETE ============" -ForegroundColor Green
Write-Host "Killed: $killed"
Write-Host "Your main window (with title) is safe"
Write-Host ""
