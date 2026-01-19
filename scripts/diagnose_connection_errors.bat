@echo off
REM Handler Detection Diagnostic
REM Monitors handler and captures detailed detection information
REM Usage: diagnose_connection_errors.bat
REM        Trigger a connection error in Cursor, then run this to capture diagnostics

cd /d "C:\dev\Autopack"

REM Create output directory if needed
if not exist "C:\dev\Autopack\error_analysis" mkdir "C:\dev\Autopack\error_analysis"

REM Run diagnostic
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\diagnose_handler_detection.ps1"

exit /b 0
