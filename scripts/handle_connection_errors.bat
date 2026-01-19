@echo off
REM Auto-handle connection errors in Cursor windows
REM This uses the keyboard-based approach (recommended)
REM Periodically sends keyboard shortcuts to recover from connection errors
REM Usage: handle_connection_errors.bat

cd /d "C:\dev\Autopack"

REM Launch PowerShell script in new window with visible output
start "Connection Error Handler (Keyboard-Based)" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_keyboard.ps1"

exit /b 0
