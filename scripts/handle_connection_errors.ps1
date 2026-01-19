# Handle connection errors in ANY Cursor windows
# Automatically detects and clicks "Resume" or "Try again" buttons on connection error dialogs
# Works with main Cursor window and all grid slot windows (#1-9)
# Monitors only when Cursor windows are actually open
# Usage: .\handle_connection_errors.ps1

# Configuration
$MONITOR_INTERVAL_MS = 1000      # Check every 1 second (more responsive)
$BUTTON_CLICK_DELAY_MS = 500     # Wait after clicking button
$CONTINUOUS_MONITOR = $true      # Run indefinitely until Ctrl+C

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Drawing;

public class WindowHelper {
    [DllImport("user32.dll")]
    public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern void SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint cButtons, uint dwExtraInfo);

    public struct RECT {
        public int Left, Top, Right, Bottom;
    }

    // Win32 Constants
    public const uint WM_LBUTTONDOWN = 0x0201;
    public const uint WM_LBUTTONUP = 0x0202;
    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    public static void MouseClick(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(50);
        mouse_event(MOUSEEVENTF_LEFTDOWN, (uint)x, (uint)y, 0, 0);
        System.Threading.Thread.Sleep(50);
        mouse_event(MOUSEEVENTF_LEFTUP, (uint)x, (uint)y, 0, 0);
    }
}
"@

Write-Host ""
Write-Host "========== CONNECTION ERROR HANDLER - CONTINUOUS ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status: MONITORING ACTIVE" -ForegroundColor Green
Write-Host "Monitoring ANY Cursor window for connection errors..."
Write-Host "Press Ctrl+C at any time to stop monitoring"
Write-Host ""
Write-Host "Monitors:" -ForegroundColor Yellow
Write-Host "  [+] Main Cursor window"
Write-Host "  [+] Grid slot windows (#1-9)"
Write-Host "  [+] Works while Cursor is open and running"
Write-Host "  [+] Only active when Cursor windows are open"
Write-Host "  [+] Automatically handles Resume then Try again"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Gray
Write-Host ""

# Tracking variables
$errorCount = 0
$resumedCount = 0
$retryCount = 0
$lastErrorTime = @{}
$sessionStartTime = Get-Date
$cursorWindowsFound = 0

# Set up Ctrl+C handler for graceful shutdown
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Gray
    Write-Host ""
    Write-Host "========== SESSION SUMMARY ==========" -ForegroundColor Green
    Write-Host ""
    $uptime = (Get-Date) - $sessionStartTime
    Write-Host "Session Duration: $($uptime.Hours)h $($uptime.Minutes)m $($uptime.Seconds)s"
    Write-Host "Cursor Windows Monitored: $cursorWindowsFound"
    Write-Host "Errors Detected: $errorCount"
    Write-Host "Resume Buttons Clicked: $resumedCount"
    Write-Host "Try Again Buttons Clicked: $retryCount"
    Write-Host "Total Actions: $($resumedCount + $retryCount)"
    Write-Host ""
    Write-Host "Monitor stopped. Goodbye!" -ForegroundColor Cyan
    Write-Host ""
}

function Get-CursorWindows {
    try {
        $cursorProcesses = @(Get-Process -Name "cursor" -ErrorAction SilentlyContinue)
        if ($cursorProcesses.Count -gt 0) {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

# Main monitoring loop
try {
    while ($CONTINUOUS_MONITOR) {
        # Check if ANY Cursor windows are open
        $cursorWindowsOpen = Get-CursorWindows

        if (-not $cursorWindowsOpen) {
            Start-Sleep -Milliseconds $MONITOR_INTERVAL_MS
            continue
        }

        # Cursor windows are open, check for connection errors
        try {
            [System.Reflection.Assembly]::LoadWithPartialName("UIAutomationClient") | Out-Null
            [System.Reflection.Assembly]::LoadWithPartialName("UIAutomationTypes") | Out-Null

            $automation = [System.Windows.Automation.AutomationElement]::RootElement

            # Check for RESUME button
            $buttonPattern = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Resume")
            $resumeButtons = $automation.FindAll([System.Windows.Automation.TreeScope]::Descendants, $buttonPattern)

            if ($resumeButtons.Count -gt 0) {
                $now = Get-Date
                $lastResume = $lastErrorTime["Resume"]

                if ($null -eq $lastResume -or ($now - $lastResume).TotalSeconds -gt 2) {
                    foreach ($button in $resumeButtons) {
                        try {
                            $clickPattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                            if ($clickPattern) {
                                $timestamp = Get-Date -Format "HH:mm:ss"
                                Write-Host "[$timestamp] [OK] Connection error detected - clicking Resume button" -ForegroundColor Green
                                $clickPattern.Invoke()
                                $resumedCount++
                                $errorCount++
                                $lastErrorTime["Resume"] = $now
                                Start-Sleep -Milliseconds $BUTTON_CLICK_DELAY_MS
                            }
                        } catch {
                            # Silently continue
                        }
                    }
                }
            }

            # Check for TRY AGAIN button
            $buttonPattern = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Try again")
            $retryButtons = $automation.FindAll([System.Windows.Automation.TreeScope]::Descendants, $buttonPattern)

            if ($retryButtons.Count -gt 0) {
                $now = Get-Date
                $lastRetry = $lastErrorTime["TryAgain"]

                if ($null -eq $lastRetry -or ($now - $lastRetry).TotalSeconds -gt 2) {
                    foreach ($button in $retryButtons) {
                        try {
                            $clickPattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                            if ($clickPattern) {
                                $timestamp = Get-Date -Format "HH:mm:ss"
                                Write-Host "[$timestamp] [OK] Connection error detected - clicking Try again button" -ForegroundColor Yellow
                                $clickPattern.Invoke()
                                $retryCount++
                                $errorCount++
                                $lastErrorTime["TryAgain"] = $now
                                Start-Sleep -Milliseconds $BUTTON_CLICK_DELAY_MS
                            }
                        } catch {
                            # Silently continue
                        }
                    }
                }
            }
        } catch {
            # UI Automation errors are typically transient
        }

        Start-Sleep -Milliseconds $MONITOR_INTERVAL_MS
    }
}
catch {
    Write-Host "Monitor error: $_" -ForegroundColor Red
}
finally {
    Write-Host ""
    Write-Host "Monitoring stopped"
    Write-Host ""
}
