@echo off
REM Detect empty cursor window slots in the 3x3 grid
REM Usage: detect_empty_slots.bat
REM StreamDeck: Execute this file

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\detect_empty_slots.ps1"

REM Uncomment for debugging
REM pause
