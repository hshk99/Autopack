@echo off
REM Paste prompts from latest *Prompts.md file into each Cursor window
REM Usage: paste_prompts.bat
REM StreamDeck: Execute this file after generating prompts and positioning windows
REM Auto-detects the latest prompts file in C:\Users\hshk9\OneDrive\Backup\Desktop\

echo.
echo ========================================
echo   PASTE PROMPTS TO CURSOR WINDOWS
echo ========================================
echo.

cd /d "C:\dev\Autopack"

echo Starting PowerShell script...
echo.

REM Run the PowerShell script
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\paste_prompts_to_cursors.ps1"

REM Pause so you can see any errors
echo.
pause
