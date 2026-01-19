# Find Cursor windows and their properties
# This helps understand how Cursor windows appear to UI Automation

Write-Host ""
Write-Host "========== CURSOR WINDOW DETECTION ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Finding all Cursor windows..." -ForegroundColor Yellow
Write-Host ""

try {
    [System.Reflection.Assembly]::LoadWithPartialName("UIAutomationClient") | Out-Null
    [System.Reflection.Assembly]::LoadWithPartialName("UIAutomationTypes") | Out-Null

    $rootElement = [System.Windows.Automation.AutomationElement]::RootElement

    # Find windows by looking for various Cursor-related properties
    Write-Host "Method 1: Looking for windows with 'Cursor' in automation properties..." -ForegroundColor Yellow
    Write-Host ""

    # Find all window elements
    $windowPattern = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Window
    )

    $allWindows = $rootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $windowPattern)

    Write-Host "Total windows found: $($allWindows.Count)" -ForegroundColor Yellow
    Write-Host ""

    $cursorWindowCount = 0
    foreach ($window in $allWindows) {
        try {
            $windowName = $window.Current.Name
            $className = $window.Current.ClassName

            # Check if this is a Cursor window
            if ($windowName -match "Cursor|cursor" -or $className -match "Cursor|cursor") {
                $cursorWindowCount++
                Write-Host "[Cursor Window Found]" -ForegroundColor Green
                Write-Host "  Name: '$windowName'"
                Write-Host "  ClassName: '$className'"
                Write-Host ""

                # List all controls in this window
                $controlPattern = New-Object System.Windows.Automation.PropertyCondition(
                    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                    [System.Windows.Automation.ControlType]::Button
                )

                $windowButtons = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $controlPattern)

                if ($windowButtons -and $windowButtons.Count -gt 0) {
                    Write-Host "  Buttons in this window ($($windowButtons.Count)):" -ForegroundColor Green
                    foreach ($btn in $windowButtons) {
                        Write-Host "    - '$($btn.Current.Name)'"
                    }
                } else {
                    Write-Host "  No buttons found in this window" -ForegroundColor Gray
                }

                Write-Host ""
            }
        } catch {
            # Continue
        }
    }

    if ($cursorWindowCount -eq 0) {
        Write-Host "No Cursor windows found by name matching." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "All windows found:" -ForegroundColor Yellow
        foreach ($window in $allWindows | Select-Object -First 20) {
            try {
                $windowName = $window.Current.Name
                if ($windowName -and $windowName.Length -gt 0) {
                    Write-Host "  - '$windowName'"
                }
            } catch {
                # Continue
            }
        }
    }

    Write-Host ""
    Write-Host "Method 2: Checking for processes..." -ForegroundColor Yellow
    Write-Host ""

    try {
        $cursorProcess = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
        if ($cursorProcess) {
            Write-Host "[Cursor Process Found]" -ForegroundColor Green
            Write-Host "  Process Name: $($cursorProcess.ProcessName)"
            Write-Host "  Process Count: $($cursorProcess.Count)"
            Write-Host "  Main Window Title: $($cursorProcess[0].MainWindowTitle)"
            Write-Host "  Main Window Handle: 0x$($cursorProcess[0].MainWindowHandle.ToString('X'))"
        } else {
            Write-Host "[No Cursor Process Found]" -ForegroundColor Red
        }
    } catch {
        Write-Host "Error checking processes: $_" -ForegroundColor Red
    }

} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Gray
Write-Host ""
