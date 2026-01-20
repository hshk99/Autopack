@echo off
REM OCR-based Connection Error Handler Launcher
REM Uses EasyOCR to detect error dialogs and click Resume/Approve buttons

echo.
echo ========================================
echo  OCR Connection Error Handler
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

REM Check if required packages are installed
python -c "import easyocr, mss, pyautogui" >nul 2>&1
if errorlevel 1 (
    echo Required packages not found. Installing...
    echo.
    pip install easyocr pillow pyautogui mss numpy
    echo.
    if errorlevel 1 (
        echo ERROR: Failed to install required packages
        echo Please run manually: pip install easyocr pillow pyautogui mss numpy
        pause
        exit /b 1
    )
)

echo Starting OCR-based handler...
echo.

REM Run the Python script
python "%~dp0handle_connection_errors_ocr.py" %*

pause
