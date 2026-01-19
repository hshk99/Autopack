@echo off
REM Auto-handle connection errors in Cursor windows
REM Monitors for connection error dialogs and automatically clicks Resume or Try again
REM Usage: handle_connection_errors.bat

cd /d "C:\dev\Autopack"

REM Launch PowerShell script in new window with visible output
start "Connection Error Handler" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors.ps1"

exit /b 0
