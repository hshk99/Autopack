# Reset baselines for handler

Write-Host ""
Write-Host "========== BASELINE RESET ==========" -ForegroundColor Cyan
Write-Host ""

# Delete old baselines
Write-Host "Deleting old baselines..." -ForegroundColor Yellow
Remove-Item -Path "C:\dev\Autopack\error_baselines" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Done!" -ForegroundColor Green
Write-Host ""
Write-Host ""
Write-Host "========== CRITICAL INSTRUCTIONS ==========" -ForegroundColor Red
Write-Host ""
Write-Host "BASELINE MUST BE CAPTURED IN CLEAN STATE!"
Write-Host ""
Write-Host "Before running the handler, you MUST ensure:"
Write-Host ""
Write-Host "1. ALL 9 Cursor windows show NORMAL editor (no errors)"
Write-Host "   - Check each window"
Write-Host "   - No 'Connection Error' pop-ups visible"
Write-Host "   - All slots show clean, working editor"
Write-Host ""
Write-Host "2. If ANY errors are visible:"
Write-Host "   - Run Phase 1 to recover:"
Write-Host "     C:\dev\Autopack\scripts\handle_connection_errors.bat"
Write-Host "   - Type the slot number with error"
Write-Host "   - Wait for Resume to be clicked"
Write-Host "   - Repeat for all error slots"
Write-Host ""
Write-Host "3. Once ALL slots are clean:"
Write-Host "   - Run the handler to capture fresh baselines:"
Write-Host "     C:\dev\Autopack\scripts\handle_connection_errors_automated.bat"
Write-Host ""
Write-Host "=========================================="
Write-Host ""
Write-Host "Why this matters:" -ForegroundColor Yellow
Write-Host "  If baseline is captured WITH errors, then:"
Write-Host "    • Handler compares: (current state) vs (error state)"
Write-Host "    • Normal operation appears as CHANGES"
Write-Host "    • All slots show constant false detections"
Write-Host ""
Write-Host "  If baseline is captured WITHOUT errors, then:"
Write-Host "    • Handler compares: (current state) vs (clean state)"
Write-Host "    • Error APPEARANCE triggers detection"
Write-Host "    • Only real errors detected correctly"
Write-Host ""
Write-Host "=========================================="
Write-Host ""
