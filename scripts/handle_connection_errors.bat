@echo off
REM Auto-handle connection errors in Cursor windows
REM Monitors for connection error dialogs and automatically clicks Resume or Try again
REM Usage: handle_connection_errors.bat

cd /d "C:\dev\Autopack"

echo.
echo Starting connection error monitor...
echo Press Ctrl+C to stop.
echo.

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors.ps1"

REM Uncomment for debugging
REM pause
