@echo off
REM Auto-handle connection errors in Cursor windows
REM This uses visual detection + coordinate-based clicking
REM Detects error dialog by pixel sampling and clicks Resume button
REM Usage: handle_connection_errors.bat

cd /d "C:\dev\Autopack"

REM Launch PowerShell script in new window with visible output
start "Connection Error Handler (Visual Detection)" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_visual.ps1"

exit /b 0
