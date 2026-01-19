@echo off
REM Wrapper for capture_error_screenshot.ps1
REM Usage: capture_error_screenshot.bat [slot]
REM Example: capture_error_screenshot.bat 3
REM Or just run with no args for interactive mode

cd /d "C:\dev\Autopack"

if "%1"=="" (
    REM Interactive mode - user will be prompted
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\capture_error_screenshot.ps1"
) else (
    REM Direct mode - capture specific slot
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\capture_error_screenshot.ps1" -ArgumentList %1
)

exit /b 0
