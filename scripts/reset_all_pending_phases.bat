@echo off
REM Reset ALL [PENDING] phases back to [READY] for re-running Button 2
REM Usage: reset_all_pending_phases.bat
REM This marks phases as READY (not started) so you can re-run Button 2

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\reset_all_pending_phases.ps1"

REM Uncomment for debugging
REM pause
