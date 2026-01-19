# Send message to a specific Cursor window in the 3x3 grid
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

# Grid coordinates for chat input boxes (from STREAMDECK_COMPLETE_SETUP.md)
# These are the positions where the chat input field is located for each slot
$chatCoordinates = @(
    @{ Slot = 1; X = 3121; Y = 337 },   # Top-left
    @{ Slot = 2; X = 3979; Y = 337 },   # Top-center
    @{ Slot = 3; X = 4833; Y = 337 },   # Top-right
    @{ Slot = 4; X = 3121; Y = 801 },   # Mid-left
    @{ Slot = 5; X = 3979; Y = 801 },   # Mid-center
    @{ Slot = 6; X = 4833; Y = 801 },   # Mid-right
    @{ Slot = 7; X = 3121; Y = 1264 },  # Bot-left
    @{ Slot = 8; X = 3979; Y = 1264 },  # Bot-center
    @{ Slot = 9; X = 4833; Y = 1264 }   # Bot-right
)

# Find coordinates for this slot
$coords = $chatCoordinates | Where-Object { $_.Slot -eq $SlotNumber }
if ($null -eq $coords) {
    Write-Host "[ERROR] Could not find coordinates for slot $SlotNumber" -ForegroundColor Red
    exit 1
}

$targetX = $coords.X
$targetY = $coords.Y

# Set up clipboard with message
$Message | Set-Clipboard
Start-Sleep -Milliseconds 200

# Add keyboard helper class for sending keys
if (-not ([System.Management.Automation.PSTypeName]'KeyboardInput').Type) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;

public class KeyboardInput {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint cButtons, uint dwExtraInfo);

    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);

    public const byte VK_CONTROL = 0x11;
    public const byte VK_V = 0x56;
    public const byte VK_RETURN = 0x0D;
    public const uint KEYEVENTF_KEYDOWN = 0x0000;
    public const uint KEYEVENTF_KEYUP = 0x0002;

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    public const uint MOUSEEVENTF_ABSOLUTE = 0x8000;

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

    public static void ClickPosition(int x, int y) {
        // Move cursor to position and click
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(100);
        mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN, (uint)x, (uint)y, 0, 0);
        System.Threading.Thread.Sleep(50);
        mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP, (uint)x, (uint)y, 0, 0);
    }
}
"@
}

try {
    # Click on the chat input box at the target coordinates to focus it
    [KeyboardInput]::ClickPosition($targetX, $targetY)
    Start-Sleep -Milliseconds 300

    # Paste and send the message
    [KeyboardInput]::PasteAndEnter()
    Start-Sleep -Milliseconds 500

    Write-Host "[OK] Message sent to slot $SlotNumber" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "[ERROR] Failed to send message to slot $SlotNumber : $_" -ForegroundColor Red
    exit 1
}
