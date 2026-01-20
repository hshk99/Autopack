# Paste prompt to a specific Cursor window in the grid and update phase status
# Usage: .\paste_prompts_to_cursor_single_window.ps1 -SlotNumber 1 -PhaseId "sec001" -WaveFile "Prompts_All_Waves.md"

param(
    [int]$SlotNumber = 1,
    [string]$PhaseId = "",
    [string]$WaveFile = ""
)

if ([string]::IsNullOrWhiteSpace($PhaseId)) {
    Write-Host "[ERROR] PhaseId required" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    Write-Host "[ERROR] WaveFile required" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $WaveFile)) {
    Write-Host "[ERROR] Wave file not found: $WaveFile" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============ PASTE PROMPT ============" -ForegroundColor Cyan
Write-Host "Slot: $SlotNumber"
Write-Host "Phase: $PhaseId"
Write-Host ""

# Read the wave file to get the prompt
$waveContent = Get-Content $WaveFile -Raw

# Pattern handles multiple formats:
# - New format: ## Phase: <id> [STATUS] -> **Wave**: -> **IMP**: -> **Title**: -> **Path**: -> **Branch**: -> <prompt>
# - Old format: ## Phase: <id> [STATUS] -> **Title**: -> **Path**: -> **Branch**: -> <prompt>
# The prompt content is everything from the blank line after metadata until the next "---"

# Updated regex: Skip optional **Wave**: and **IMP**: fields before **Title**:
$phasePattern = "## Phase: $PhaseId \[.*?\](?:.*?\*\*Wave\*\*:.*?(?:\r?\n))?(?:.*?\*\*IMP\*\*:.*?(?:\r?\n))?.*?\*\*Title\*\*: (.*?)(?:\r?\n).*?\*\*Path\*\*: (.*?)(?:\r?\n)(?:\*\*Branch\*\*: (.*?)(?:\r?\n))?(?:\r?\n)+(.*?)(?=\r?\n---|\Z)"
$match = [regex]::Match($waveContent, $phasePattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)

if (-not $match.Success) {
    Write-Host "[ERROR] Phase $PhaseId not found in wave file" -ForegroundColor Red
    exit 1
}

$phaseTitle = $match.Groups[1].Value.Trim()
$phasePath = $match.Groups[2].Value.Trim()
$phaseBranch = $match.Groups[3].Value.Trim()
$phasePrompt = $match.Groups[4].Value.Trim()

Write-Host "[INFO] Title: $phaseTitle"
Write-Host "[INFO] Path: $phasePath"
if ($phaseBranch) {
    Write-Host "[INFO] Branch: $phaseBranch"
}
Write-Host "[INFO] Prompt length: $($phasePrompt.Length) chars"
Write-Host ""

# ============ Define Window and Keyboard Helpers ============
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

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, int dwExtraInfo);

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    public const uint MOUSEEVENTF_ABSOLUTE = 0x8000;

    public static void ClickCenter(IntPtr hWnd) {
        RECT rect;
        GetWindowRect(hWnd, out rect);
        int centerX = (rect.Left + rect.Right) / 2;
        int centerY = (rect.Top + rect.Bottom) / 2;

        // Move to center and click
        mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN, (uint)centerX, (uint)centerY, 0, 0);
        System.Threading.Thread.Sleep(100);
        mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP, (uint)centerX, (uint)centerY, 0, 0);
    }
}
"@
}

# Load Windows Forms for SendKeys (works better with Electron/web apps)
Add-Type -AssemblyName System.Windows.Forms

if (-not ([System.Management.Automation.PSTypeName]'KeyboardHelper').Type) {
Add-Type @"
using System;
using System.Runtime.InteropServices;

public class KeyboardHelper {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);

    public const byte VK_CONTROL = 0x11;
    public const byte VK_SHIFT = 0x10;
    public const byte VK_9 = 0x39;
    public const byte VK_V = 0x56;
    public const byte VK_RETURN = 0x0D;
    public const byte VK_M = 0x4D;
    public const byte VK_O = 0x4F;
    public const uint KEYEVENTF_KEYDOWN = 0x0000;
    public const uint KEYEVENTF_KEYUP = 0x0002;

    // Keep old method as fallback
    public static void PasteAndEnterLegacy() {
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

    public static void OpenProjectFolder() {
        // Ctrl+M to open menu, then O for project folder
        System.Threading.Thread.Sleep(500);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_M, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_M, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);
        System.Threading.Thread.Sleep(300);

        keybd_event(VK_O, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_O, 0, KEYEVENTF_KEYUP, 0);
    }

    // SendKeys method for Ctrl+Shift+9 (works better with web UIs)
    public static void SendCtrlShift9() {
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_9, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_9, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);
    }
}
"@
}

# ============ Step 1: Focus the Cursor window at the specified slot ============
Write-Host "[ACTION] Focusing Cursor window at slot $SlotNumber..."

$cursorWindows = [WindowHelper]::GetWindowsByProcessName("cursor")
if ($cursorWindows.Count -eq 0) {
    Write-Host "[ERROR] No Cursor windows found" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Found $($cursorWindows.Count) Cursor window(s)"

# Map slot number to expected coordinates
# Slot 1-3: Row 1 (Y=0), Slot 4-6: Row 2 (Y=463), Slot 7-9: Row 3 (Y=926)
# Slot 1,4,7: Col 1 (X=2560), Slot 2,5,8: Col 2 (X=3413), Slot 3,6,9: Col 3 (X=4266)
$yRow = [Math]::Ceiling($SlotNumber / 3)
$xCol = (($SlotNumber - 1) % 3) + 1

$expectedYStart = ($yRow - 1) * 463
$expectedYEnd = $expectedYStart + 463

$expectedX = @{ 1 = 2560; 2 = 3413; 3 = 4266 }[$xCol]

Write-Host "[INFO] Looking for window at slot $SlotNumber (Row $yRow, Col $xCol)"
Write-Host "[INFO] Expected position: X~$expectedX, Y~$expectedYStart-$expectedYEnd"

# Find window at target position
$targetWindow = $null
$tolerance = 100

foreach ($window in $cursorWindows) {
    $rect = [WindowHelper]::GetWindowRect($window)
    $title = [WindowHelper]::GetWindowTitle($window)

    # Check if window is in the expected position
    if ($rect.Left -ge ($expectedX - $tolerance) -and $rect.Left -le ($expectedX + $tolerance) -and
        $rect.Top -ge ($expectedYStart - $tolerance) -and $rect.Top -le ($expectedYEnd + $tolerance)) {
        $targetWindow = $window
        Write-Host "[FOUND] Window at correct position: $title"
        break
    }
}

if ($null -eq $targetWindow) {
    Write-Host "[WARNING] Could not find window at exact position for slot $SlotNumber" -ForegroundColor Yellow
    Write-Host "[INFO] Using first available window as fallback"
    $targetWindow = $cursorWindows[0]
    $title = [WindowHelper]::GetWindowTitle($targetWindow)
    Write-Host "[FOUND] Using window: $title"
}

# Set foreground window
Write-Host "[ACTION] Setting window to foreground..."
[WindowHelper]::SetForegroundWindow($targetWindow) | Out-Null
Start-Sleep -Milliseconds 5000

# ============ Step 2: Open Claude Chat (Ctrl+Shift+9) ============
Write-Host "[ACTION] Opening Claude Chat with Ctrl+Shift+9..."

# Use SendKeys for better compatibility with Electron/web apps
[System.Windows.Forms.SendKeys]::SendWait("^+9")

Write-Host "[OK] Claude Chat shortcut sent (via SendKeys)"
Write-Host "[INFO] Waiting for Claude Chat panel to open..."
Start-Sleep -Milliseconds 2500

# ============ Step 3: Set clipboard and paste prompt to Chat ============
Write-Host "[ACTION] Pasting prompt to Claude Chat..."

# Copy prompt to clipboard
$phasePrompt | Set-Clipboard
Write-Host "[INFO] Clipboard set with prompt ($($phasePrompt.Length) chars)"
Start-Sleep -Milliseconds 500

# Use SendKeys for paste - works better with web-based UIs in Electron apps
# ^v = Ctrl+V, {ENTER} = Enter key
Write-Host "[INFO] Sending Ctrl+V via SendKeys..."
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 500

Write-Host "[INFO] Sending Enter via SendKeys..."
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")

Write-Host "[OK] Prompt pasted to Claude Chat and sent (via SendKeys)"
Start-Sleep -Milliseconds 500

Write-Host ""

# Update the phase status from READY to PENDING in the wave file
Write-Host "[ACTION] Updating phase status to PENDING..."

# Read current file
$fileContent = Get-Content $WaveFile -Raw

# Try to replace READY or UNRESOLVED → PENDING
$updatedContent = $fileContent -replace "## Phase: $PhaseId \[READY\]", "## Phase: $PhaseId [PENDING]"
$updatedContent = $updatedContent -replace "## Phase: $PhaseId \[UNRESOLVED\]", "## Phase: $PhaseId [PENDING]"

if ($updatedContent -ne $fileContent) {
    # Content changed, write it back
    Set-Content $WaveFile $updatedContent -Encoding UTF8
    if ($fileContent -match "## Phase: $PhaseId \[UNRESOLVED\]") {
        Write-Host "[OK] Status updated: UNRESOLVED → PENDING"
    } else {
        Write-Host "[OK] Status updated: READY → PENDING"
    }
} else {
    # Check if already in another state
    if ($fileContent -match "## Phase: $PhaseId \[(PENDING|COMPLETED)\]") {
        Write-Host "[INFO] Phase already in $($Matches[1]) state"
    } else {
        Write-Host "[WARNING] Could not find phase status line for $PhaseId"
    }
}

Write-Host ""
Write-Host "[DONE] Prompt prepared for slot $SlotNumber"
