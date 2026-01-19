# Test script to verify slot lookup works correctly
Write-Host "Testing slot lookup..."

if (-not ([System.Management.Automation.PSTypeName]'WindowHelper').Type) {
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowHelper {
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

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
            uint processId;
            GetWindowThreadProcessId(hWnd, out processId);
            if (processIds.Contains(processId) && IsWindowVisible(hWnd)) {
                windows.Add(hWnd);
            }
            return true;
        }, IntPtr.Zero);

        return windows;
    }

    public static string GetWindowTitle(IntPtr hWnd) {
        var length = GetWindowTextLength(hWnd);
        if (length == 0) return "";
        var sb = new StringBuilder(length + 1);
        GetWindowText(hWnd, sb, length + 1);
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

function Get-WindowSlotNumber {
    param([int]$WindowX, [int]$WindowY)
    $tolerance = 100
    $col = 0
    if ($WindowX -ge (2560 - $tolerance) -and $WindowX -le (2560 + $tolerance)) { $col = 1 }
    elseif ($WindowX -ge (3413 - $tolerance) -and $WindowX -le (3413 + $tolerance)) { $col = 2 }
    elseif ($WindowX -ge (4266 - $tolerance) -and $WindowX -le (4266 + $tolerance)) { $col = 3 }
    $row = 0
    if ($WindowY -ge (0 - $tolerance) -and $WindowY -le (0 + $tolerance)) { $row = 1 }
    elseif ($WindowY -ge (463 - $tolerance) -and $WindowY -le (463 + $tolerance)) { $row = 2 }
    elseif ($WindowY -ge (926 - $tolerance) -and $WindowY -le (926 + $tolerance)) { $row = 3 }
    if ($col -eq 0 -or $row -eq 0) { return 0 }
    return (($row - 1) * 3 + $col)
}

$windowSlotMap = @{}
$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")

Write-Host ""
Write-Host "Building window slot map:"
foreach ($window in $cursorWindows) {
    $title = [WindowHelper]::GetWindowTitle($window)
    $rect = [WindowHelper]::GetWindowRect($window)

    if ($title -match "Autopack_w\d+_([^\s]+)") {
        $phaseId = $Matches[1]
        $slot = Get-WindowSlotNumber -WindowX $rect.Left -WindowY $rect.Top
        if ($slot -gt 0) {
            $windowSlotMap[$phaseId] = $slot
            Write-Host "  Mapped: $phaseId -> Slot $slot"
        }
    }
}

Write-Host ""
Write-Host "Full windowSlotMap contents:"
$windowSlotMap.GetEnumerator() | ForEach-Object {
    Write-Host "  Key='$($_.Key)' Value=$($_.Value)"
}

Write-Host ""
Write-Host "Testing specific lookups:"
$testIds = @("feat003", "cost001", "cost003", "safety006")
foreach ($id in $testIds) {
    $slot = $windowSlotMap[$id]
    if ($null -eq $slot) {
        Write-Host "  $id : NULL (not found in map!)" -ForegroundColor Red
    } else {
        Write-Host "  $id : Slot $slot" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Hash table key comparison:"
$windowSlotMap.Keys | ForEach-Object {
    $key = $_
    Write-Host "  Key: '$key' (Length: $($key.Length))"
}
