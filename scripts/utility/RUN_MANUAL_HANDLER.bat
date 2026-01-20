@echo off
REM Quick error recovery - click Resume button in specified grid slot
REM Double-click this file to use the manual handler

cd /d "C:\dev\Autopack"
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1"
pause
