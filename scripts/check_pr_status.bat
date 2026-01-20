@echo off
REM Check PR status for all [PENDING] phases and send auto-messages to cursors
REM Usage: check_pr_status.bat
REM StreamDeck: Execute this file with working directory set to C:\dev\Autopack

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\check_pr_status.ps1"

REM Uncomment for debugging
REM pause
