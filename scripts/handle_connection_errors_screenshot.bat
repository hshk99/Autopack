@echo off
REM Auto-handle connection errors using screenshot detection
REM This is an alternative approach that detects errors visually in grid windows
REM Usage: handle_connection_errors_screenshot.bat

cd /d "C:\dev\Autopack"

REM Launch PowerShell script in new window with visible output
start "Connection Error Handler (Screenshot-Based)" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_screenshot.ps1"

exit /b 0
