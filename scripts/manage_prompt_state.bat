@echo off
REM Manage prompt state (load, save, update status)
REM Tracks prompt status: [READY], [PENDING], [COMPLETED]
REM Usage: manage_prompt_state.bat
REM StreamDeck: Not used directly (called by other scripts)

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\manage_prompt_state.ps1"

REM Uncomment for debugging
REM pause
