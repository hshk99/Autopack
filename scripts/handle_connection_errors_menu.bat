@echo off
REM Connection Error Handler - Mode Selection Menu
REM Choose between manual (Phase 1) or automated (Phase 2) recovery

setlocal enabledelayedexpansion

:menu
cls
echo.
echo ========== CONNECTION ERROR HANDLER - MODE SELECTION ==========
echo.
echo Phase 1: MANUAL RECOVERY (Proven Working)
echo   [1] Manual mode - You click slot number when error appears
echo.
echo Phase 2: AUTOMATED RECOVERY (New - Testing)
echo   [2] Automated mode - Detects errors automatically and clicks Resume
echo.
echo Other
echo   [Q] Quit
echo.
echo ============================================================
echo.
set /p choice="Select mode [1,2,Q]: "

if /i "%choice%"=="1" (
    echo.
    echo Launching Manual Error Handler (Phase 1)...
    echo You will type the slot number when an error appears.
    echo.
    timeout /t 2 /nobreak
    start "Connection Error Handler (MANUAL)" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1"
    exit /b 0
)

if /i "%choice%"=="2" (
    echo.
    echo Launching Automated Error Handler (Phase 2)...
    echo Handler will capture baselines and monitor for errors.
    echo Press Ctrl+C to stop.
    echo.
    timeout /t 2 /nobreak
    start "Connection Error Handler (AUTOMATED)" powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_automated.ps1"
    exit /b 0
)

if /i "%choice%"=="Q" (
    exit /b 0
)

echo Invalid choice. Please select 1, 2, or Q.
timeout /t 2 /nobreak
goto menu
