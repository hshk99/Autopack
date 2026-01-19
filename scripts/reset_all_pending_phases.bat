@echo off
REM Reset ALL [PENDING] phases back to [UNIMPLEMENTED] for re-running Button 2
REM Usage: reset_all_pending_phases.bat
REM This removes phases that haven't been started yet so you can re-run Button 2

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\reset_all_pending_phases.ps1"

REM Uncomment for debugging
REM pause
