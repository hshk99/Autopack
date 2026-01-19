# Diagnostic script to find actual button text in Cursor connection error dialogs
# Usage: .\diagnose_connection_errors.ps1
# Focuses on finding error dialog buttons in Cursor windows

Write-Host ""
Write-Host "========== CONNECTION ERROR DIAGNOSTICS ==========" -ForegroundColor Cyan
Write-Host ""
Write-Host "Scanning for UI elements in all windows..."
Write-Host "Press Ctrl+C to stop"
Write-Host ""

try {
    [System.Reflection.Assembly]::LoadWithPartialName("UIAutomationClient") | Out-Null
    [System.Reflection.Assembly]::LoadWithPartialName("UIAutomationTypes") | Out-Null

    Write-Host "UI Automation loaded successfully" -ForegroundColor Green
    Write-Host ""

    $scanCount = 0
    $foundElements = @{}

    # Get root element
    $rootElement = [System.Windows.Automation.AutomationElement]::RootElement

    if ($null -eq $rootElement) {
        Write-Host "ERROR: Could not get root automation element" -ForegroundColor Red
        exit 1
    }

    Write-Host "Root element obtained, starting scan..." -ForegroundColor Green
    Write-Host ""

    while ($true) {
        $scanCount++
        Write-Host "[Scan #$scanCount] $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Yellow

        try {
            # Find all buttons in entire UI tree
            $buttonPattern = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Button
            )

            $allButtons = $rootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants, $buttonPattern)

            if ($allButtons -and $allButtons.Count -gt 0) {
                Write-Host "  Found $($allButtons.Count) buttons total" -ForegroundColor Yellow

                $buttonTexts = @()
                $newElements = $false

                foreach ($button in $allButtons) {
                    try {
                        $buttonName = $button.Current.Name
                        if ($buttonName -and $buttonName.Length -gt 0) {
                            $buttonTexts += $buttonName

                            # Track new buttons
                            if (-not $foundElements.ContainsKey($buttonName)) {
                                $foundElements[$buttonName] = $true
                                $newElements = $true
                            }
                        }
                    } catch {
                        # Continue
                    }
                }

                # Show new buttons found
                if ($newElements) {
                    Write-Host "  [NEW] Buttons found:" -ForegroundColor Green
                    $buttonTexts | Where-Object { $foundElements[$_] } | Sort-Object -Unique | ForEach-Object {
                        Write-Host "    - '$_'"
                    }
                    Write-Host ""
                }

                # Highlight error-related buttons
                $errorButtons = $buttonTexts | Where-Object { $_ -match "Resume|Try again|Retry|Cancel|Close|OK|Error|Warning|Connection|Reconnect" }
                if ($errorButtons) {
                    Write-Host "  [+] POTENTIAL ERROR BUTTONS:" -ForegroundColor Green
                    $errorButtons | Sort-Object -Unique | ForEach-Object {
                        Write-Host "      >>> '$_'" -ForegroundColor Green
                    }
                    Write-Host ""
                }
            } else {
                Write-Host "  No buttons found" -ForegroundColor Gray
            }
        } catch {
            Write-Host "  Error during scan: $_" -ForegroundColor Red
        }

        Start-Sleep -Milliseconds 2000
    }
}
catch {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host ""
}
finally {
    Write-Host ""
    Write-Host "Diagnostics stopped"
    Write-Host ""
}
