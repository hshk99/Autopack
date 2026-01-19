@echo off
REM Kill all running Cursor processes and cleanup
REM Usage: kill_auto_fill.bat

echo.
echo ========== KILL ALL CURSOR PROCESSES ==========
echo.
echo This will terminate all running Cursor instances and cleanup.
echo.

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1" -Kill

echo.
echo All processes terminated.
pause
