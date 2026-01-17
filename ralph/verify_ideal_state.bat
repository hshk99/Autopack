@echo off
REM =============================================================================
REM Autopack Ideal State Verification Script (Windows)
REM =============================================================================
REM Run this to check how close Autopack is to its ideal state.
REM =============================================================================

setlocal EnableDelayedExpansion

set PROJECT_DIR=%~dp0..
set IMP_TRACKING=C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_IMPS_MASTER.json

echo.
echo === Autopack Ideal State Verification ===
echo Project: %PROJECT_DIR%
echo IMP Tracking: %IMP_TRACKING%
echo.

set PASS=0
set FAIL=0

echo Self-Improvement Loop:
echo ----------------------

REM 1. Check TelemetryAnalyzer
if exist "%PROJECT_DIR%\src\autopack\telemetry\analyzer.py" (
    echo   [OK] TelemetryAnalyzer exists
    set /a PASS+=1
) else (
    echo   [FAIL] TelemetryAnalyzer exists
    set /a FAIL+=1
)

REM 2. Check telemetry_to_memory_bridge
if exist "%PROJECT_DIR%\src\autopack\memory\telemetry_to_memory_bridge.py" (
    echo   [OK] Telemetry-to-memory bridge exists
    set /a PASS+=1
) else (
    echo   [FAIL] Telemetry-to-memory bridge exists
    set /a FAIL+=1
)

REM 3. Check retrieve_insights
findstr /C:"def retrieve_insights" "%PROJECT_DIR%\src\autopack\memory\memory_service.py" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   [OK] MemoryService.retrieve_insights^(^)
    set /a PASS+=1
) else (
    echo   [FAIL] MemoryService.retrieve_insights^(^)
    set /a FAIL+=1
)

REM 4. Check task generation wired
findstr /C:"_generate_improvement_tasks" "%PROJECT_DIR%\src\autopack\executor\autonomous_loop.py" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    REM Check it's called, not just defined - simplified check
    findstr /C:"self._generate_improvement_tasks()" "%PROJECT_DIR%\src\autopack\executor\autonomous_loop.py" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        echo   [OK] Task generation wired to executor
        set /a PASS+=1
    ) else (
        echo   [FAIL] Task generation wired to executor ^(exists but not called^)
        set /a FAIL+=1
    )
) else (
    echo   [FAIL] Task generation wired to executor
    set /a FAIL+=1
)

REM 5. Check GeneratedTask persistence
findstr /C:"class GeneratedTaskModel" "%PROJECT_DIR%\src\autopack\models.py" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   [OK] GeneratedTask database model
    set /a PASS+=1
) else (
    echo   [FAIL] GeneratedTask database model
    set /a FAIL+=1
)

REM 6. Check get_pending_tasks
findstr /C:"def get_pending_tasks" "%PROJECT_DIR%\src\autopack\roadc\task_generator.py" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   [OK] TaskGenerator.get_pending_tasks^(^)
    set /a PASS+=1
) else (
    echo   [FAIL] TaskGenerator.get_pending_tasks^(^)
    set /a FAIL+=1
)

echo.
echo ROAD Framework:
echo ---------------

REM Check ROAD directories
if exist "%PROJECT_DIR%\src\autopack\roada\*" (echo   [OK] ROAD-A & set /a PASS+=1) else (echo   [FAIL] ROAD-A & set /a FAIL+=1)
if exist "%PROJECT_DIR%\src\autopack\roadb\*" (echo   [OK] ROAD-B & set /a PASS+=1) else (if exist "%PROJECT_DIR%\src\autopack\telemetry\analyzer.py" (echo   [OK] ROAD-B ^(in telemetry^) & set /a PASS+=1) else (echo   [FAIL] ROAD-B & set /a FAIL+=1))
if exist "%PROJECT_DIR%\src\autopack\roadc\*" (echo   [OK] ROAD-C & set /a PASS+=1) else (echo   [FAIL] ROAD-C & set /a FAIL+=1)
if exist "%PROJECT_DIR%\src\autopack\roadg\*" (echo   [OK] ROAD-G & set /a PASS+=1) else (echo   [FAIL] ROAD-G & set /a FAIL+=1)
if exist "%PROJECT_DIR%\src\autopack\roadh\*" (echo   [OK] ROAD-H & set /a PASS+=1) else (echo   [FAIL] ROAD-H & set /a FAIL+=1)
if exist "%PROJECT_DIR%\src\autopack\roadi\*" (echo   [OK] ROAD-I & set /a PASS+=1) else (echo   [FAIL] ROAD-I & set /a FAIL+=1)
if exist "%PROJECT_DIR%\src\autopack\roadj\*" (echo   [OK] ROAD-J & set /a PASS+=1) else (echo   [FAIL] ROAD-J & set /a FAIL+=1)
if exist "%PROJECT_DIR%\src\autopack\roadk\*" (echo   [OK] ROAD-K & set /a PASS+=1) else (echo   [FAIL] ROAD-K & set /a FAIL+=1)
if exist "%PROJECT_DIR%\src\autopack\roadl\*" (echo   [OK] ROAD-L & set /a PASS+=1) else (echo   [FAIL] ROAD-L & set /a FAIL+=1)

echo.
echo IMP Status:
echo -----------

if exist "%IMP_TRACKING%" (
    for /f %%i in ('python -c "import json; d=json.load(open(r'%IMP_TRACKING%', encoding='utf-8')); print(d.get('statistics',{}).get('total_imps',0))" 2^>nul') do echo   Total IMPs tracked: %%i
    for /f %%i in ('python -c "import json; d=json.load(open(r'%IMP_TRACKING%', encoding='utf-8')); print(d.get('statistics',{}).get('unimplemented',0))" 2^>nul') do echo   Unimplemented: %%i
    for /f %%i in ('python -c "import json; d=json.load(open(r'%IMP_TRACKING%', encoding='utf-8')); print(len([i for i in d.get('unimplemented_imps',[]) if i.get('priority')=='critical']))" 2^>nul') do set CRITICAL=%%i
    for /f %%i in ('python -c "import json; d=json.load(open(r'%IMP_TRACKING%', encoding='utf-8')); print(len([i for i in d.get('unimplemented_imps',[]) if i.get('priority')=='high']))" 2^>nul') do set HIGH=%%i

    echo   - CRITICAL: %CRITICAL%
    echo   - HIGH: %HIGH%

    if "%CRITICAL%"=="0" (
        echo   [OK] No CRITICAL IMPs remaining
        set /a PASS+=1
    ) else (
        echo   [FAIL] No CRITICAL IMPs remaining
        set /a FAIL+=1
    )
) else (
    echo   IMP tracking file not found
    set /a FAIL+=1
)

echo.
echo ==============================================
echo VERIFICATION SUMMARY
echo ==============================================
echo.
echo   Passed: %PASS%
echo   Failed: %FAIL%

set /a TOTAL=%PASS%+%FAIL%
set /a PERCENTAGE=%PASS%*100/%TOTAL%
echo   Progress: %PERCENTAGE%%%
echo.

if %FAIL% equ 0 (
    echo   IDEAL_STATE_REACHED: true
    echo.
    echo   Autopack has reached its README ideal state!
) else (
    echo   IDEAL_STATE_REACHED: false
    echo.
    echo   Run the evolution loop to close remaining gaps:
    echo     ralph\evolution_loop.bat
)

echo.
pause
