@echo off
REM Connection Error Handler - Automated Detection (Phase 2)
REM Automatically detects connection errors and clicks Resume button
REM
REM Usage:
REM   handle_connection_errors_automated.bat
REM   (Runs automated handler in new window)

cd /d "C:\dev\Autopack"

REM Launch PowerShell script in new window
start "Connection Error Handler (AUTOMATED)" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_automated.ps1"

exit /b 0
