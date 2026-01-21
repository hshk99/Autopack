@echo off
REM Connection Error Handler Launcher
REM Choose between different detection methods

cd /d "C:\dev\Autopack"

echo.
echo ========================================
echo  Connection Error Handler
echo ========================================
echo.
echo Select detection method:
echo.
echo   1. OCR-based (Recommended - uses AI image recognition)
echo   2. Direct click (uses pre-mapped coordinates)
echo   3. Keyboard-based (sends keyboard shortcuts)
echo.
set /p choice="Enter choice (1-3) or press Enter for OCR: "

if "%choice%"=="" set choice=1
if "%choice%"=="1" goto ocr
if "%choice%"=="2" goto direct
if "%choice%"=="3" goto keyboard

echo Invalid choice. Using OCR method.
goto ocr

:ocr
echo.
echo Starting OCR-based handler (EasyOCR)...
echo.
call "%~dp0handle_connection_errors_ocr.bat"
goto end

:direct
echo.
echo Starting direct click handler...
echo.
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1"
goto end

:keyboard
echo.
echo Starting keyboard-based handler...
echo WARNING: This method sends keys blindly and may interfere with normal operation
echo.
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\handle_connection_errors_keyboard.ps1"
goto end

:end
pause
