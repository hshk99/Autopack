# SAFE cleanup of background Cursor windows opened by auto_fill
# IMPORTANT: This ONLY closes Cursor windows - NOT VSCode or Claude Code
# IMPORTANT: Keeps your main window intact
# Usage: .\safe_cleanup_background_cursors.ps1
# Usage: .\safe_cleanup_background_cursors.ps1 -DryRun  # Show what would be closed

param(
    [switch]$DryRun,
    [int]$MinutesOld = 0  # 0 = close all Cursor windows except oldest
)

Write-Host ""
Write-Host "============ SAFE CURSOR CLEANUP ============" -ForegroundColor Cyan
Write-Host ""

# Define WindowHelper if not already loaded
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
}
"@
}

# Get all visible Cursor windows
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("Cursor")

if ($cursorWindows.Count -eq 0) {
    Write-Host "[INFO] No visible Cursor windows found"
    Write-Host ""
    exit 0
}

Write-Host "[INFO] Found $($cursorWindows.Count) visible Cursor window(s)"
Write-Host ""

# Get process info for each window
$windowsWithProcs = @()
foreach ($hwnd in $cursorWindows) {
    $title = [WindowHelper]::GetWindowTitle($hwnd)

    # Get the process
    $procId = 0
    $proc = $null
    [WindowHelper]::GetWindowThreadProcessId($hwnd, [ref]$procId) | Out-Null

    if ($procId -gt 0) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                $windowsWithProcs += @{
                    Handle = $hwnd
                    Title = $title
                    ProcessId = $procId
                    ProcessName = $proc.ProcessName
                    StartTime = $proc.StartTime
                }
            }
        } catch {
            # Skip if process already terminated
        }
    }
}

if ($windowsWithProcs.Count -eq 0) {
    Write-Host "[INFO] No accessible Cursor processes found"
    Write-Host ""
    exit 0
}

# Sort by start time - we want to keep the OLDEST window (your main one)
$windowsWithProcs = @($windowsWithProcs | Sort-Object -Property StartTime)

Write-Host "Cursor windows by start time (oldest first):"
for ($i = 0; $i -lt $windowsWithProcs.Count; $i++) {
    $window = $windowsWithProcs[$i]
    $age = (Get-Date) - $window.StartTime
    $ageStr = "{0}d {1}h {2}m" -f $age.Days, $age.Hours, $age.Minutes
    $marker = if ($i -eq 0) { "[KEEP] OLDEST - Likely your main window" } else { "[CLOSE] Background window" }
    Write-Host "  $i. $($window.Title)"
    Write-Host "     Started: $($window.StartTime.ToString('yyyy-MM-dd HH:mm:ss')) (Age: $ageStr)"
    Write-Host "     PID: $($window.ProcessId)  $marker"
    Write-Host ""
}

# Close all but the oldest (which is your main window)
$toClose = @($windowsWithProcs | Select-Object -Skip 1)

if ($toClose.Count -eq 0) {
    Write-Host "[INFO] Only 1 Cursor window found - keeping it as main window"
    Write-Host ""
    exit 0
}

Write-Host "[ACTION] Closing $($toClose.Count) background Cursor window(s)..."
Write-Host ""

$closedCount = 0
foreach ($window in $toClose) {
    if ($DryRun) {
        Write-Host "[DRY-RUN] Would close: $($window.Title) (PID: $($window.ProcessId))" -ForegroundColor Yellow
    } else {
        try {
            # Close the process
            Stop-Process -Id $window.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] Closed: $($window.Title) (PID: $($window.ProcessId))" -ForegroundColor Green
            $closedCount++
        } catch {
            Write-Host "[WARN] Failed to close $($window.Title): $_" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "============ CLEANUP COMPLETE ============" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "[DRY-RUN] Would have closed: $($toClose.Count) window(s)"
} else {
    Write-Host "[OK] Closed: $closedCount window(s)"
    Write-Host "[INFO] Your main Cursor window should still be running"
}
Write-Host ""
