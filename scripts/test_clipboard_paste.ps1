# Test clipboard and paste functionality
# This script tests pasting a small test string to verify the mechanism works

param(
    [int]$DelayMs = 400
)

Add-Type @"
using System;
using System.Runtime.InteropServices;

public class MouseHelper {
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, int dwExtraInfo);

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;

    public static void Click(int x, int y) {
        SetCursorPos(x, y);
        mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0);
        mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0);
    }
}

public class KeyboardHelper {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);

    public const byte VK_CONTROL = 0x11;
    public const byte VK_V = 0x56;
    public const byte VK_RETURN = 0x0D;
    public const uint KEYEVENTF_KEYDOWN = 0x0000;
    public const uint KEYEVENTF_KEYUP = 0x0002;

    public static void PasteAndEnter() {
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_V, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);

        System.Threading.Thread.Sleep(200);

        keybd_event(VK_RETURN, 0, KEYEVENTF_KEYDOWN, 0);
        keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0);
    }
}
"@

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   CLIPBOARD PASTE TEST                " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Test 1: Small text (10 chars)" -ForegroundColor Yellow
$testText1 = "Hello Test"
"$testText1" | Set-Clipboard
Write-Host "  Copied to clipboard: $testText1" -ForegroundColor Green
Write-Host "  Clicking at X=2977, Y=144 in 2 seconds..." -ForegroundColor Gray
Start-Sleep -Seconds 2

[MouseHelper]::Click(2977, 144)
Write-Host "  Clicked. Waiting 500ms..." -ForegroundColor Gray
Start-Sleep -Milliseconds 500

Write-Host "  Pasting and pressing Enter..." -ForegroundColor Gray
[KeyboardHelper]::PasteAndEnter()
Write-Host "  Done! Text should appear in window." -ForegroundColor Green

Write-Host ""
Write-Host "Test 2: Medium text (100 chars)" -ForegroundColor Yellow
$testText2 = "I'm working on automation. This is a test message with more characters to see if the clipboard can handle longer text properly without truncation issues."
$testText2 | Set-Clipboard
Write-Host "  Copied to clipboard: $($testText2.Substring(0, 50))..." -ForegroundColor Green
Write-Host "  Clicking at X=3812, Y=144 in 2 seconds..." -ForegroundColor Gray
Start-Sleep -Seconds 2

[MouseHelper]::Click(3812, 144)
Write-Host "  Clicked. Waiting 500ms..." -ForegroundColor Gray
Start-Sleep -Milliseconds 500

Write-Host "  Pasting and pressing Enter..." -ForegroundColor Gray
[KeyboardHelper]::PasteAndEnter()
Write-Host "  Done! Full text should appear in window." -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TEST COMPLETE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If both messages appeared in the windows:" -ForegroundColor Yellow
Write-Host "  - Small message in top-left" -ForegroundColor Gray
Write-Host "  - Medium message in top-center" -ForegroundColor Gray
Write-Host "Then the clipboard and paste mechanism is working correctly!" -ForegroundColor Green
Write-Host ""
Write-Host "If only first 1-2 characters appeared:" -ForegroundColor Yellow
Write-Host "  - There may be a timing issue" -ForegroundColor Gray
Write-Host "  - Try running again with longer delays" -ForegroundColor Gray
Write-Host ""
