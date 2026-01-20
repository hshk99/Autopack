@echo off
REM Auto-fill empty cursor slots with next available [READY] prompts
REM Main orchestrator for Option B workflow
REM Respects wave boundaries - does NOT cross to next wave
REM Usage: auto_fill_empty_slots.bat
REM StreamDeck: Execute this file with working directory set to C:\dev\Autopack

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1"

REM Uncomment for debugging
REM pause
