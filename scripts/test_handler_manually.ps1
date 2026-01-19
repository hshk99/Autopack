# Manual test of handler detection
# This simulates what happens when an error appears

Write-Host ""
Write-Host "========== MANUAL HANDLER TEST ==========" -ForegroundColor Cyan
Write-Host ""

$BASELINE_DIR = "C:\dev\Autopack\error_baselines"

Write-Host "OPTIONS:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Analyze current pixel changes in all slots"
Write-Host "2. Run handler for 30 seconds and observe"
Write-Host "3. Check baseline files exist"
Write-Host "4. Manually test detection logic with sample values"
Write-Host ""

$choice = Read-Host "Choose option (1-4)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Analyzing pixel changes in all slots..." -ForegroundColor Yellow
        Write-Host ""

        & "C:\dev\Autopack\scripts\analyze_error_detection.ps1"
    }

    "2" {
        Write-Host ""
        Write-Host "Starting handler for 30 seconds..." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Watch for any errors detected in the output below:"
        Write-Host ""

        $job = Start-Job -FilePath "C:\dev\Autopack\scripts\handle_connection_errors_automated.ps1"
        Start-Sleep -Seconds 30
        Stop-Job -Job $job
        Receive-Job -Job $job
        Remove-Job -Job $job

        Write-Host ""
        Write-Host "Handler test complete." -ForegroundColor Green
    }

    "3" {
        Write-Host ""
        Write-Host "Checking baseline files..." -ForegroundColor Yellow
        Write-Host ""

        if (Test-Path $BASELINE_DIR) {
            $files = Get-ChildItem "$BASELINE_DIR\baseline_*.png"
            if ($files.Count -eq 9) {
                Write-Host "✓ All 9 baseline files exist:" -ForegroundColor Green
                foreach ($file in $files | Sort-Object Name) {
                    $sizeMB = [Math]::Round($file.Length / 1MB, 2)
                    Write-Host "  $($file.Name) - $sizeMB MB"
                }
                Write-Host ""
                Write-Host "✓ Baselines are ready for detection" -ForegroundColor Green
            } else {
                Write-Host "✗ Only $($files.Count) baseline files found (need 9)" -ForegroundColor Red
            }
        } else {
            Write-Host "✗ Baseline directory not found" -ForegroundColor Red
        }
    }

    "4" {
        Write-Host ""
        Write-Host "Testing detection logic with sample scenarios..." -ForegroundColor Yellow
        Write-Host ""

        & "C:\dev\Autopack\scripts\test_phase2_logic.ps1"
    }

    default {
        Write-Host "Invalid choice" -ForegroundColor Red
    }
}

Write-Host ""
