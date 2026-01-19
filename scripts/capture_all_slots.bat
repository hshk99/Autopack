@echo off
REM Capture all 9 grid slots simultaneously for Phase 2 analysis
REM Creates screenshots of all slots showing error dialog(s)
REM Useful for analyzing error patterns across all windows

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\capture_all_slots.ps1"

exit /b 0
