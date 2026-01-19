# Send message to a specific Cursor window in the 3x3 grid
# Uses SetForegroundWindow to focus the window at the target slot, then sends keyboard events
# Usage: .\send_message_to_cursor_slot.ps1 -SlotNumber 1 -Message "test message"

param(
    [int]$SlotNumber = 0,
    [string]$Message = ""
)

if ($SlotNumber -lt 1 -or $SlotNumber -gt 9) {
    Write-Host "[ERROR] Invalid slot number: $SlotNumber (must be 1-9)" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($Message)) {
    Write-Host "[ERROR] Message cannot be empty" -ForegroundColor Red
    exit 1
}

# Add window and keyboard helper classes
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
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

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

if (-not ([System.Management.Automation.PSTypeName]'KeyboardHelper').Type) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;

public class KeyboardHelper {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);

    public const byte VK_CONTROL = 0x11;
    public const byte VK_V = 0x56;
    public const byte VK_RETURN = 0x0D;
    public const uint KEYEVENTF_KEYDOWN = 0x0000;
    public const uint KEYEVENTF_KEYUP = 0x0002;

    public static void PasteAndEnter() {
        // Ctrl+V to paste
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_V, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);
        System.Threading.Thread.Sleep(200);

        // Enter to send
        keybd_event(VK_RETURN, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0);
    }
}
"@
}

try {
    # Step 1: Find all Cursor windows
    $cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")
    if ($cursorWindows.Count -eq 0) {
        Write-Host "[ERROR] No Cursor windows found" -ForegroundColor Red
        exit 1
    }

    # Step 2: Map slot number to expected grid position
    # Slot 1-3: Row 1 (Y=0), Slot 4-6: Row 2 (Y=463), Slot 7-9: Row 3 (Y=926)
    # Slot 1,4,7: Col 1 (X=2560), Slot 2,5,8: Col 2 (X=3413), Slot 3,6,9: Col 3 (X=4266)
    $yRow = [Math]::Ceiling($SlotNumber / 3)
    $xCol = (($SlotNumber - 1) % 3) + 1

    $expectedYStart = ($yRow - 1) * 463
    $expectedYEnd = $expectedYStart + 463
    $expectedX = @{ 1 = 2560; 2 = 3413; 3 = 4266 }[$xCol]

    # Step 3: Find the window at the target slot position
    $targetWindow = $null
    $tolerance = 100

    foreach ($window in $cursorWindows) {
        $rect = [WindowHelper]::GetWindowRect($window)

        # Check if window is in the expected position for this slot
        if ($rect.Left -ge ($expectedX - $tolerance) -and $rect.Left -le ($expectedX + $tolerance) -and
            $rect.Top -ge ($expectedYStart - $tolerance) -and $rect.Top -le ($expectedYEnd + $tolerance)) {
            $targetWindow = $window
            break
        }
    }

    if ($null -eq $targetWindow) {
        Write-Host "[ERROR] No Cursor window found at slot $SlotNumber position (X~$expectedX, Y~$expectedYStart-$expectedYEnd)" -ForegroundColor Red
        exit 1
    }

    # Step 4: Focus the window
    [WindowHelper]::SetForegroundWindow($targetWindow) | Out-Null
    Start-Sleep -Milliseconds 500

    # Step 5: Set clipboard and paste
    $Message | Set-Clipboard
    Start-Sleep -Milliseconds 200

    # Step 6: Send Ctrl+V and Enter to the focused window
    [KeyboardHelper]::PasteAndEnter()
    Start-Sleep -Milliseconds 500

    Write-Host "[OK] Message sent to slot $SlotNumber" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "[ERROR] Failed to send message to slot $SlotNumber : $_" -ForegroundColor Red
    exit 1
}
