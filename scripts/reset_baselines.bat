@echo off
REM Reset handler baselines
REM Deletes corrupted baselines and prompts to recapture in clean state
REM Usage: reset_baselines.bat
REM        Can be added as Stream Deck button

cd /d "C:\dev\Autopack"

REM Run the reset script
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\reset_baselines.ps1"

REM Keep window open so user can read instructions
pause

exit /b 0
