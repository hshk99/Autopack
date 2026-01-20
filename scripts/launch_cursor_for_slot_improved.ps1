# Launch a new Cursor window and position it to a specific grid slot
# IMPROVED VERSION: Handles hidden windows, proper initialization, and visibility
# Key improvements:
#   - Detects new processes OR new windows (handles Cursor's reuse of main process)
#   - Forces window visibility before positioning
#   - Waits for proper Cursor initialization
#   - Brings window to foreground to ensure it's visible
# Usage: .\launch_cursor_for_slot_improved.ps1 -SlotNumber 1 -ProjectPath "C:\dev\Autopack"

param(
    [int]$SlotNumber = 1,
    [string]$ProjectPath = "",
    [int]$MaxWaitSeconds = 20
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
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    public static List<IntPtr> GetAllCursorWindowHandles() {
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
                    // Filter out system UI windows
                    if (!string.IsNullOrWhiteSpace(title) && title.Length > 1 &&
                        !title.Contains("Default IME") && !title.Contains("MSCTFIME")) {
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

    public static void EnsureWindowVisible(IntPtr hWnd) {
        // If minimized, restore it
        if (IsIconic(hWnd)) {
            ShowWindow(hWnd, 9);  // SW_RESTORE
        }

        // Ensure it's visible
        if (!IsWindowVisible(hWnd)) {
            ShowWindow(hWnd, 5);  // SW_SHOW
        }
    }
}
"@
}

# Grid slot coordinates for 5120x1440 monitor
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

Write-Host ""
Write-Host "============ LAUNCH CURSOR FOR SLOT (IMPROVED) ============" -ForegroundColor Cyan
Write-Host "Target Slot: $SlotNumber"
Write-Host ""

# Record existing windows BEFORE launch
$beforeWindows = [WindowHelper]::GetAllCursorWindowHandles()
$beforeHandles = @($beforeWindows | ForEach-Object { $_.GetHashCode() })
Write-Host "[INFO] Existing Cursor windows before launch: $($beforeWindows.Count)"
Write-Host ""

# Record existing processes BEFORE launch
$beforeProcs = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
$beforeProcIds = @($beforeProcs | ForEach-Object { $_.Id })

# Launch Cursor
Write-Host "[ACTION] Launching Cursor..."
try {
    $cursorExe = "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe"
    if (-not (Test-Path $cursorExe)) {
        $cursorExe = "cursor"
    }
    Write-Host "[INFO] Executable: $cursorExe"

    if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
        Write-Host "[INFO] Launching without project"
        Start-Process -FilePath $cursorExe -ArgumentList "--new-window" -ErrorAction Stop
    } else {
        Write-Host "[INFO] Opening project: $ProjectPath"
        Start-Process -FilePath $cursorExe -ArgumentList "--new-window", $ProjectPath -ErrorAction Stop
    }

    Write-Host "[OK] Launch command executed"
} catch {
    Write-Host "[ERROR] Failed to launch Cursor: $_" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Waiting for new window to appear and initialize..."
Write-Host ""

# Wait for new window to appear
$newWindow = $null
$elapsedSeconds = 0
$checkInterval = 400  # milliseconds

while ($elapsedSeconds -lt $MaxWaitSeconds) {
    Start-Sleep -Milliseconds $checkInterval
    $currentWindows = [WindowHelper]::GetAllCursorWindowHandles()

    # Find NEW window(s) - one that's NOT in the existing list
    foreach ($window in $currentWindows) {
        $handle = $window.GetHashCode()
        if ($beforeHandles -notcontains $handle) {
            $newWindow = $window
            $title = [WindowHelper]::GetWindowTitle($newWindow)
            Write-Host "[FOUND] New window detected: $title"
            break
        }
    }

    if ($null -ne $newWindow) {
        break
    }

    $elapsedSeconds += ($checkInterval / 1000)
}

if ($null -eq $newWindow) {
    Write-Host "[WARNING] No new window detected in enumeration" -ForegroundColor Yellow
    Write-Host "[INFO] Cursor may be reusing main process - checking for process change..."

    # Check if a new process was created
    $currentProcs = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
    $currentProcIds = @($currentProcs | ForEach-Object { $_.Id })

    # Find new process
    $newProc = $null
    foreach ($proc in $currentProcs) {
        if ($beforeProcIds -notcontains $proc.Id) {
            $newProc = $proc
            Write-Host "[FOUND] New process: PID $($newProc.Id)"
            break
        }
    }

    # If no new process, try to find any window from existing processes
    if ($null -eq $newProc) {
        Write-Host "[INFO] No new process detected - Cursor reusing main process"
        Write-Host "[ACTION] Looking for any Cursor window to reposition..."

        $allWindows = [WindowHelper]::GetAllCursorWindowHandles()
        if ($allWindows.Count -gt 0) {
            # Use the most recent window
            $newWindow = $allWindows[-1]
            $title = [WindowHelper]::GetWindowTitle($newWindow)
            Write-Host "[OK] Using window: $title"
        }
    }
}

if ($null -eq $newWindow) {
    Write-Host ""
    Write-Host "[ERROR] Could not find any Cursor window to position" -ForegroundColor Red
    Write-Host "[DEBUG] Available windows:"
    [WindowHelper]::GetAllCursorWindowHandles() | ForEach-Object {
        $title = [WindowHelper]::GetWindowTitle($_)
        Write-Host "  - $title"
    }
    exit 1
}

Write-Host "[OK] Window ready for positioning"
Write-Host ""

# Ensure window is visible BEFORE moving
Write-Host "[ACTION] Ensuring window is visible..."
[WindowHelper]::EnsureWindowVisible($newWindow)
Write-Host "[OK] Window visibility ensured"
Write-Host ""

# Give Cursor time to fully initialize the UI
Write-Host "[INFO] Waiting for UI initialization..."
Start-Sleep -Seconds 2

# Position window to slot
$slot = $gridSlots[$SlotNumber]
Write-Host "[ACTION] Moving window to slot $SlotNumber..."
Write-Host "  Position: X=$($slot.X), Y=$($slot.Y)"
Write-Host "  Size: $($slot.W)x$($slot.H)"

$result = [WindowHelper]::MoveWindow($newWindow, $slot.X, $slot.Y, $slot.W, $slot.H, $true)

if ($result) {
    Write-Host "[OK] Window positioned successfully"
} else {
    Write-Host "[WARNING] MoveWindow returned false (window may still have moved)"
}

# Bring to foreground to ensure visibility
Write-Host "[ACTION] Bringing window to foreground..."
[WindowHelper]::SetForegroundWindow($newWindow) | Out-Null
Start-Sleep -Milliseconds 500

Write-Host "[OK] Window brought to foreground"
Write-Host ""

Write-Host "============ LAUNCH COMPLETE ============" -ForegroundColor Green
Write-Host "[DONE] New Cursor window launched and positioned to slot $SlotNumber"
if (-not [string]::IsNullOrWhiteSpace($ProjectPath)) {
    Write-Host "[INFO] Project: $ProjectPath"
}
Write-Host ""
