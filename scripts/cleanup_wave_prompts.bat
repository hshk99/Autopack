@echo off
REM Cleanup completed phases from Wave[N]_All_Phases.md and JSON files
REM Removes [COMPLETED] phases from:
REM   1. Wave[N]_All_Phases.md
REM   2. AUTOPACK_IMPS_MASTER.json
REM   3. AUTOPACK_WAVE_PLAN.json
REM Usage: cleanup_wave_prompts.bat
REM StreamDeck: Execute this file with working directory set to C:\dev\Autopack

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\cleanup_wave_prompts.ps1"

REM Uncomment for debugging
REM pause
