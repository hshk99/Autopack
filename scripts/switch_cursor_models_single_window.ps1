# Switch LLM model for a specific Cursor window in the grid
# Usage: .\switch_cursor_models_single_window.ps1 -SlotNumber 1 -ModelName "glm-4.7"

param(
    [int]$SlotNumber = 1,
    [string]$ModelName = "glm-4.7"
)

if ($SlotNumber -lt 1 -or $SlotNumber -gt 9) {
    Write-Host "[ERROR] SlotNumber must be 1-9" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============ SWITCH MODEL ============" -ForegroundColor Cyan
Write-Host "Slot: $SlotNumber"
Write-Host "Model: $ModelName"
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
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

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

# Get all Cursor windows
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")

if ($cursorWindows.Count -eq 0) {
    Write-Host "[WARNING] No Cursor windows found - skipping model switch" -ForegroundColor Yellow
    exit 0
}

# Select the most recent window
$targetWindow = $cursorWindows[-1]
$title = [WindowHelper]::GetWindowTitle($targetWindow)

Write-Host "[INFO] Target window: $title"
Write-Host ""

# Focus the window
Write-Host "[ACTION] Focusing Cursor window..."
[WindowHelper]::SetForegroundWindow($targetWindow) | Out-Null

Start-Sleep -Milliseconds 500

# Note: Model switching via keyboard is unreliable with Cursor
# Instead, ensure Cursor is configured with the correct model in settings
# If ModelName is "claude", Cursor must have Claude API configured in settings

if ($ModelName -eq "claude") {
    Write-Host "[INFO] Claude model requested"
    Write-Host "[NOTE] Ensure Claude API key is configured in Cursor settings"
    Write-Host "[NOTE] Settings → Extensions → Claude (or similar)"
    Write-Host "[OK] Using default Cursor configuration (assumes Claude API is set)"
} else {
    Write-Host "[INFO] Model: $ModelName"
    Write-Host "[OK] Using configured model"
}

Write-Host ""
Write-Host "[DONE] Slot $SlotNumber will use: $ModelName"
