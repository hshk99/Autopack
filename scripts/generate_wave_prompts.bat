@echo off
REM Generate all prompts for a wave from AUTOPACK_WORKFLOW.md
REM Creates Wave[N]_All_Phases.md and directories for each phase
REM Usage: generate_wave_prompts.bat
REM StreamDeck: Execute this file with working directory set to C:\dev\Autopack

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\generate_wave_prompts.ps1"

REM Uncomment for debugging
REM pause
