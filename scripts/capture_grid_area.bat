@echo off
REM Capture grid area screenshot (all 9 slots in one image)
REM Shows which slot has connection error

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\capture_grid_area.ps1"

exit /b 0
