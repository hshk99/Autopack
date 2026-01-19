# Connection Error Handler - Direct Coordinate Clicking
# When triggered (manually or by external tool), clicks Resume button at specified slot
# This is the simplest, most reliable approach

# Resume button coordinates for each grid slot
$RESUME_BUTTON_COORDS = @{
    1 = @{ X = 3121; Y = 337 }   # Slot 1
    2 = @{ X = 3979; Y = 337 }   # Slot 2
    3 = @{ X = 4833; Y = 337 }   # Slot 3
    4 = @{ X = 3121; Y = 801 }   # Slot 4
    5 = @{ X = 3979; Y = 801 }   # Slot 5
    6 = @{ X = 4833; Y = 801 }   # Slot 6
    7 = @{ X = 3121; Y = 1264 }  # Slot 7
    8 = @{ X = 3979; Y = 1264 }  # Slot 8
    9 = @{ X = 4833; Y = 1264 }  # Slot 9
}

Write-Host ""
Write-Host "========== CONNECTION ERROR HANDLER (DIRECT CLICK) ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "This handler clicks Resume button when you specify the grid slot"
Write-Host ""
Write-Host "Usage:"
Write-Host "  click-error 1    <- Clicks Resume in slot 1"
Write-Host "  click-error 2    <- Clicks Resume in slot 2"
Write-Host "  ... etc ..."
Write-Host ""
Write-Host "Or run continuously and monitor for Cursor errors:"
Write-Host "  Press Ctrl+C to stop"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Gray
Write-Host ""

# Function to click Resume button at coordinates
function Click-ResumeButton {
    param([int]$Slot)

    try {
        $coords = $RESUME_BUTTON_COORDS[$Slot]

        # Add mouse clicking capability
        Add-Type @"
using System;
using System.Runtime.InteropServices;

public class MouseClicker {
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint cButtons, uint dwExtraInfo);

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;

    public static void Click(int x, int y) {
        SetCursorPos(x, y);
        System.Threading.Thread.Sleep(100);
        mouse_event(MOUSEEVENTF_LEFTDOWN, (uint)x, (uint)y, 0, 0);
        System.Threading.Thread.Sleep(50);
        mouse_event(MOUSEEVENTF_LEFTUP, (uint)x, (uint)y, 0, 0);
    }
}
"@ -ErrorAction SilentlyContinue

        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Clicking Resume button in SLOT $Slot at ($($coords.X), $($coords.Y))" -ForegroundColor Green
        [MouseClicker]::Click($coords.X, $coords.Y)
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Click sent successfully" -ForegroundColor Green

        return $true
    } catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Error clicking button: $_" -ForegroundColor Red
        return $false
    }
}

# If arguments provided, click that slot
if ($args.Count -gt 0) {
    $slot = [int]$args[0]
    if ($slot -ge 1 -and $slot -le 9) {
        Click-ResumeButton -Slot $slot
        exit 0
    } else {
        Write-Host "Invalid slot: $slot. Must be 1-9" -ForegroundColor Red
        exit 1
    }
}

# Otherwise run interactive mode
Write-Host "Interactive mode - Enter slot number (1-9) to click, or 'q' to quit:"
Write-Host ""

while ($true) {
    Write-Host -NoNewline "Slot [1-9] or (q)uit? > " -ForegroundColor Yellow
    $input = Read-Host

    if ($input -eq "q") {
        break
    }

    if ([int]::TryParse($input, [ref]$slot)) {
        if ($slot -ge 1 -and $slot -le 9) {
            Click-ResumeButton -Slot $slot
            Write-Host ""
        } else {
            Write-Host "Invalid slot. Must be 1-9" -ForegroundColor Red
            Write-Host ""
        }
    } else {
        Write-Host "Invalid input" -ForegroundColor Red
        Write-Host ""
    }
}

Write-Host ""
Write-Host "Handler stopped" -ForegroundColor Gray
