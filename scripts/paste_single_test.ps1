# Single cursor paste test - for debugging
# This will paste ONLY to the first grid position (top-left)

param(
    [string]$PromptsFile = "C:\Users\hshk9\OneDrive\Backup\Desktop\Wave_Prompts.md",
    [int]$DelayMs = 500
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
"@

Add-Type -AssemblyName System.Windows.Forms

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SINGLE CURSOR PASTE TEST           " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Read prompts
$content = Get-Content $PromptsFile -Raw -Encoding UTF8
$promptMatches = [regex]::Matches($content, '## (Cursor\d+[^`n]*)\n([\s\S]*?)(?=## Cursor|---|\Z)')

if ($promptMatches.Count -eq 0) {
    Write-Host "[ERROR] No prompts found" -ForegroundColor Red
    exit 1
}

$match = $promptMatches[0]
$title = $match.Groups[1].Value.Trim()
$prompt = $match.Groups[2].Value.Trim()

if ($title -match 'Cursor(\d+)\s*-\s*([^\s-]+(?:-[^\s-]+)*)\s*-') {
    $actualCursorNum = [int]$Matches[1]
    $branchName = $Matches[2]
} else {
    Write-Host "[ERROR] Could not parse title: $title" -ForegroundColor Red
    exit 1
}

Write-Host "PREPARING TO PASTE:" -ForegroundColor Yellow
Write-Host "  Cursor: $actualCursorNum" -ForegroundColor Gray
Write-Host "  Branch: $branchName" -ForegroundColor Gray
Write-Host "  Prompt: $($prompt.Substring(0, 60))..." -ForegroundColor Gray
Write-Host "  Length: $($prompt.Length) characters" -ForegroundColor Gray
Write-Host ""

Write-Host "STEP 1: Setting clipboard" -ForegroundColor Yellow
$prompt | Set-Clipboard
Write-Host "  [OK] Clipboard set with $($prompt.Length) characters" -ForegroundColor Green
Write-Host ""

Write-Host "STEP 2: Preparing to click at X=2977, Y=144 (top-left)" -ForegroundColor Yellow
Write-Host "  IMPORTANT: Make sure Cursor window #1 is visible and has chat panel open!" -ForegroundColor Red
Write-Host ""
Write-Host "STEP 3: Waiting 3 seconds before click..." -ForegroundColor Yellow
for ($i = 3; $i -gt 0; $i--) {
    Write-Host "  $i..." -NoNewline -ForegroundColor Gray
    Start-Sleep -Seconds 1
}
Write-Host ""
Write-Host ""

Write-Host "CLICKING NOW!" -ForegroundColor Cyan
[MouseHelper]::Click(2977, 144)
Write-Host "  [OK] Clicked" -ForegroundColor Green
Start-Sleep -Milliseconds 800

Write-Host ""
Write-Host "PASTING WITH CTRL+V..." -ForegroundColor Cyan
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 300

Write-Host "PRESSING ENTER..." -ForegroundColor Cyan
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Milliseconds 500

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TEST COMPLETE!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "What you should see:" -ForegroundColor Yellow
Write-Host "  - Cursor window #1 should have the full prompt pasted" -ForegroundColor Gray
Write-Host "  - Prompt should start with: 'I'm working in git worktree...'" -ForegroundColor Gray
Write-Host ""
Write-Host "If you only see 'I ' or a few characters:" -ForegroundColor Red
Write-Host "  - The click may not be focusing the input field" -ForegroundColor Gray
Write-Host "  - Try clicking on the chat input manually first" -ForegroundColor Gray
Write-Host "  - Then run this test again" -ForegroundColor Gray
Write-Host ""
