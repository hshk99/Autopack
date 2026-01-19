# Diagnostic version to test clipboard pasting step by step

param(
    [string]$PromptsFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\Wave_Prompts.md"
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   PASTE PROMPTS DIAGNOSTIC TEST       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Read the first prompt
$content = Get-Content $PromptsFile -Raw -Encoding UTF8
$promptMatches = [regex]::Matches($content, '## (Cursor\d+[^`n]*)\n([\s\S]*?)(?=## Cursor|---|\Z)')

if ($promptMatches.Count -eq 0) {
    Write-Host "[ERROR] No prompts found in file" -ForegroundColor Red
    exit 1
}

$match = $promptMatches[0]
$title = $match.Groups[1].Value.Trim()
$prompt = $match.Groups[2].Value.Trim()

Write-Host "First prompt found:" -ForegroundColor Yellow
Write-Host "  Title: $title" -ForegroundColor Gray
Write-Host "  Length: $($prompt.Length) characters" -ForegroundColor Gray
Write-Host "  First 100 chars: $($prompt.Substring(0, [Math]::Min(100, $prompt.Length)))" -ForegroundColor Gray
Write-Host ""

Write-Host "Step 1: Setting clipboard..." -ForegroundColor Yellow
$prompt | Set-Clipboard
Write-Host "  [OK] Text set to clipboard" -ForegroundColor Green
Write-Host ""

Write-Host "Step 2: Verify clipboard content..." -ForegroundColor Yellow
$clipboardText = Get-Clipboard -Raw
Write-Host "  Clipboard length: $($clipboardText.Length) characters" -ForegroundColor Gray
Write-Host "  First 100 chars: $($clipboardText.Substring(0, [Math]::Min(100, $clipboardText.Length)))" -ForegroundColor Gray

if ($clipboardText.Length -eq $prompt.Length) {
    Write-Host "  [OK] Clipboard contains full text" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Clipboard text differs from prompt!" -ForegroundColor Yellow
    Write-Host "    Prompt: $($prompt.Length) chars" -ForegroundColor Gray
    Write-Host "    Clipboard: $($clipboardText.Length) chars" -ForegroundColor Gray
}
Write-Host ""

Write-Host "Step 3: Keyboard test (no actual pasting)" -ForegroundColor Yellow
Write-Host "  This will NOT paste to a window" -ForegroundColor Gray
Write-Host "  Just testing the keyboard helper..." -ForegroundColor Gray

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

Write-Host "  [OK] Keyboard helper loaded" -ForegroundColor Green
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Clipboard status:" -ForegroundColor Yellow

if ($clipboardText.Length -eq $prompt.Length) {
    Write-Host "  [GOOD] Full prompt is in clipboard ($($prompt.Length) chars)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next: Manually click on a chat window and test pasting" -ForegroundColor Yellow
    Write-Host "  1. Click on chat input box" -ForegroundColor Gray
    Write-Host "  2. Press Ctrl+V to paste" -ForegroundColor Gray
    Write-Host "  3. You should see the full prompt text" -ForegroundColor Gray
} else {
    Write-Host "  [BAD] Clipboard content mismatch!" -ForegroundColor Red
    Write-Host "    Expected: $($prompt.Length) chars" -ForegroundColor Gray
    Write-Host "    Got: $($clipboardText.Length) chars" -ForegroundColor Gray
}

Write-Host ""
