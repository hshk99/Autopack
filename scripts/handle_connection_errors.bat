@echo off
REM Quick error recovery - click Resume button in specified grid slot
REM Usage:
REM   handle_connection_errors.bat           (interactive mode)
REM   handle_connection_errors.bat 3         (click slot 3)
REM
REM Works with coordinates you provided for Resume button in all 9 slots
REM Manual control ensures accurate clicking without false positives

cd /d "C:\dev\Autopack"

REM Launch PowerShell script in new window
REM Pass any arguments (slot number) to the script
if "%1"=="" (
    start "Connection Error Handler" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1"
) else (
    start "Connection Error Handler" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1" -ArgumentList %1
)

exit /b 0
