@echo off
REM Kill all Cursor processes and PowerShell instances
REM Use this when auto_fill_empty_slots.bat launches wrong windows or gets stuck

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\kill_all_cursor.ps1"

REM Optional: Uncomment to see output before closing
REM pause
