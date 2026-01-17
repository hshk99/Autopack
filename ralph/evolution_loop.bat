@echo off
REM =============================================================================
REM Autopack Continuous Evolution Loop (Windows)
REM =============================================================================
REM Runs discovery - implementation cycles until Autopack reaches its ideal state
REM or max cycles exceeded.
REM
REM Usage:
REM   ralph\evolution_loop.bat [max_cycles] [model]
REM
REM Examples:
REM   ralph\evolution_loop.bat          - Default: 50 cycles, opus model
REM   ralph\evolution_loop.bat 100      - 100 cycles max
REM   ralph\evolution_loop.bat 50 sonnet - Use sonnet model
REM =============================================================================

setlocal EnableDelayedExpansion

REM Configuration
set MAX_CYCLES=50
if not "%1"=="" set MAX_CYCLES=%1

set MODEL=opus
if not "%2"=="" set MODEL=%2

set DISCOVERY_MAX_ITER=10
set IMPLEMENTATION_MAX_ITER=20

REM Paths
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=C:\dev\Autopack
set PROMPT_FILE=%SCRIPT_DIR%PROMPT_evolution.md
set GUARDRAILS_FILE=%SCRIPT_DIR%guardrails.md
set IMP_TRACKING=C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_IMPS_MASTER.json
set LOG_DIR=%PROJECT_DIR%\.ralph\logs

REM Create log directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM State tracking
set CYCLE=0
set IDEAL_REACHED=false
set TOTAL_IMPS_CLOSED=0
set IMPLEMENTED_THIS_CYCLE=false

echo.
echo ==============================================
echo    AUTOPACK CONTINUOUS EVOLUTION LOOP
echo ==============================================
echo.
echo [INFO] Max cycles: %MAX_CYCLES%
echo [INFO] Model: %MODEL%
echo [INFO] Discovery iterations per cycle: %DISCOVERY_MAX_ITER%
echo [INFO] Implementation iterations per cycle: %IMPLEMENTATION_MAX_ITER%
echo [INFO] IMP tracking: %IMP_TRACKING%
echo [INFO] Log directory: %LOG_DIR%
echo.

REM Check prerequisites
where claude >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Claude CLI not found. Please install claude-code first.
    exit /b 1
)

if not exist "%PROMPT_FILE%" (
    echo [ERROR] Prompt file not found: %PROMPT_FILE%
    exit /b 1
)

REM NOTE: We do NOT check the IMP file to determine starting state.
REM Claude will perform fresh codebase discovery and find gaps through code analysis.
REM The IMP file is OUTPUT ONLY - for writing newly discovered gaps.
echo [INFO] Starting fresh codebase discovery (IMP file is OUTPUT only, not INPUT)
echo.

REM Main loop
:cycle_loop
if %CYCLE% GEQ %MAX_CYCLES% goto end_loop
if "%IDEAL_REACHED%"=="true" goto end_loop

set /a CYCLE=%CYCLE%+1
set IMPLEMENTED_THIS_CYCLE=false

echo.
echo ==============================================
echo EVOLUTION CYCLE %CYCLE% of %MAX_CYCLES%
echo ==============================================
echo Started: %DATE% %TIME%

set CYCLE_LOG=%LOG_DIR%\cycle_%CYCLE%_%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.log
set CYCLE_LOG=%CYCLE_LOG: =0%

REM =========================================================================
REM PHASE A: DISCOVERY
REM =========================================================================
echo.
echo [PHASE] Phase A: Discovery

set DISCOVERY_ITER=0
set DISCOVERY_COMPLETE=false

:discovery_loop
if %DISCOVERY_ITER% GEQ %DISCOVERY_MAX_ITER% goto discovery_done
if "%DISCOVERY_COMPLETE%"=="true" goto discovery_done

set /a DISCOVERY_ITER=%DISCOVERY_ITER%+1
echo [INFO] Discovery iteration %DISCOVERY_ITER%/%DISCOVERY_MAX_ITER%...

REM Create combined prompt file (avoids stdin size limits)
set COMBINED_PROMPT=%LOG_DIR%\combined_prompt.md
type "%PROMPT_FILE%" > "%COMBINED_PROMPT%" 2>nul
echo. >> "%COMBINED_PROMPT%"
echo --- >> "%COMBINED_PROMPT%"
echo. >> "%COMBINED_PROMPT%"
type "%GUARDRAILS_FILE%" >> "%COMBINED_PROMPT%" 2>nul

REM Run Claude for discovery
echo [INFO] Starting Claude... (this may take 2-5 minutes)
for /f %%s in ('powershell -Command "(Get-Item '%COMBINED_PROMPT%').Length / 1KB"') do echo [INFO] Prompt size: %%s KB
echo [INFO] Waiting for Claude response...
echo [INFO] (Check %CYCLE_LOG%.tmp for progress if needed)

REM Run Claude - capture to file, display after
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_claude.ps1" -PromptFile "%COMBINED_PROMPT%" -Model "%MODEL%" > "%CYCLE_LOG%.tmp" 2>&1
echo.
echo [INFO] Claude finished. Output:
echo ============================================================
type "%CYCLE_LOG%.tmp"
echo ============================================================
type "%CYCLE_LOG%.tmp" >> "%CYCLE_LOG%"
del "%CYCLE_LOG%.tmp" 2>nul

REM Check for exit signal (ideal state reached during discovery)
REM IMPORTANT: Comprehensive 10-area scan required - must scan ALL areas deeply
REM The IMP file is OUTPUT ONLY (for writing gaps), not for validation
findstr /C:"EXIT_SIGNAL: true" "%CYCLE_LOG%" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [INFO] Exit signal detected - checking comprehensive scan requirements...

    REM Must have completed ALL 10 scan areas
    findstr /C:"scan_areas_completed: 10/10" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] EXIT_SIGNAL without 10/10 scan areas - comprehensive scan required
        echo [INFO] Ralph must scan ALL 10 areas before claiming ideal state
        goto discovery_continue
    )

    REM Must have found zero gaps
    findstr /C:"total_gaps_found: 0" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] EXIT_SIGNAL with gaps found - must implement gaps first
        goto discovery_continue
    )

    REM Must have pytest verification
    findstr /C:"pytest_status: PASSED" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] EXIT_SIGNAL without pytest verification - runtime proof required
        goto discovery_continue
    )

    echo [SUCCESS] Claude completed comprehensive 10-area scan with pytest verification
    set IDEAL_REACHED=true
    goto end_loop

    :discovery_continue
    echo [INFO] Continuing discovery - comprehensive scan incomplete
)

REM Check for completion (simplified - full parsing would need more logic)
findstr /C:"DISCOVERY_COMPLETE: true" "%CYCLE_LOG%" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set DISCOVERY_COMPLETE=true
    echo [SUCCESS] Discovery phase complete
)

findstr /C:"IDEAL_STATE_REACHED: true" "%CYCLE_LOG%" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [INFO] Ideal state claim detected - checking comprehensive scan requirements...

    REM Must have ALL 10 scan areas completed
    findstr /C:"scan_areas_completed: 10/10" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] IDEAL_STATE_REACHED without 10/10 scan areas - continuing loop
        goto discovery_next
    )

    REM Must have zero gaps found
    findstr /C:"total_gaps_found: 0" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] IDEAL_STATE_REACHED with gaps found - continuing loop
        goto discovery_next
    )

    findstr /C:"pytest_status: PASSED" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] IDEAL_STATE_REACHED without pytest verification - continuing loop
        goto discovery_next
    )

    echo [SUCCESS] Comprehensive scan passed: 10/10 areas + 0 gaps + pytest
    set IDEAL_REACHED=true
    goto end_loop

    :discovery_next
)

timeout /t 2 /nobreak >nul
goto discovery_loop

:discovery_done

REM =========================================================================
REM PHASE B: IMPLEMENTATION
REM =========================================================================
echo.
echo [PHASE] Phase B: Implementation

for /f %%i in ('python -c "import json; d=json.load(open(r'%IMP_TRACKING%', encoding='utf-8')); print(d.get('statistics',{}).get('unimplemented',0))" 2^>nul') do set UNIMPLEMENTED=%%i
if not defined UNIMPLEMENTED set UNIMPLEMENTED=0

if %UNIMPLEMENTED% equ 0 (
    echo [INFO] No IMPs to implement, proceeding to ideal state check
    goto implementation_done
)

echo [INFO] %UNIMPLEMENTED% IMPs to implement

set IMPL_ITER=0
set IMPL_COMPLETE=false
set NO_PROGRESS=0

:implementation_loop
if %IMPL_ITER% GEQ %IMPLEMENTATION_MAX_ITER% goto implementation_done
if "%IMPL_COMPLETE%"=="true" goto implementation_done

set /a IMPL_ITER=%IMPL_ITER%+1
set PREV_UNIMPLEMENTED=%UNIMPLEMENTED%

echo [INFO] Implementation iteration %IMPL_ITER%/%IMPLEMENTATION_MAX_ITER%...

REM Reuse combined prompt file (already created in discovery phase)
if not exist "%COMBINED_PROMPT%" (
    set COMBINED_PROMPT=%LOG_DIR%\combined_prompt.md
    type "%PROMPT_FILE%" > "%COMBINED_PROMPT%" 2>nul
    echo. >> "%COMBINED_PROMPT%"
    echo --- >> "%COMBINED_PROMPT%"
    echo. >> "%COMBINED_PROMPT%"
    type "%GUARDRAILS_FILE%" >> "%COMBINED_PROMPT%" 2>nul
)

REM Run Claude for implementation - use PowerShell script for reliable large file piping
echo [INFO] Starting Claude... (this may take 2-5 minutes)
echo [INFO] Waiting for Claude response...
echo [INFO] (Check %CYCLE_LOG%.tmp for progress if needed)

REM Run Claude - capture to file, display after
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_claude.ps1" -PromptFile "%COMBINED_PROMPT%" -Model "%MODEL%" > "%CYCLE_LOG%.tmp" 2>&1
echo.
echo [INFO] Claude finished. Output:
echo ============================================================
type "%CYCLE_LOG%.tmp"
echo ============================================================
type "%CYCLE_LOG%.tmp" >> "%CYCLE_LOG%"
del "%CYCLE_LOG%.tmp" 2>nul

REM Check progress
for /f %%i in ('python -c "import json; d=json.load(open(r'%IMP_TRACKING%', encoding='utf-8')); print(d.get('statistics',{}).get('unimplemented',0))" 2^>nul') do set UNIMPLEMENTED=%%i

if %UNIMPLEMENTED% LSS %PREV_UNIMPLEMENTED% (
    set NO_PROGRESS=0
    set IMPLEMENTED_THIS_CYCLE=true
    set /a CLOSED=%PREV_UNIMPLEMENTED%-%UNIMPLEMENTED%
    set /a TOTAL_IMPS_CLOSED=%TOTAL_IMPS_CLOSED%+%CLOSED%
    echo [SUCCESS] Closed %CLOSED% IMP(s^). Remaining: %UNIMPLEMENTED%
    echo [INFO] Implementation happened this cycle - ideal state check will be deferred to next cycle
) else (
    set /a NO_PROGRESS=%NO_PROGRESS%+1
    echo [WARNING] No progress (%NO_PROGRESS%/3^)

    if %NO_PROGRESS% GEQ 3 (
        echo [ERROR] Circuit breaker: No progress for 3 iterations
        goto implementation_done
    )
)

if %UNIMPLEMENTED% equ 0 (
    set IMPL_COMPLETE=true
    echo [SUCCESS] All IMPs implemented!
)

timeout /t 2 /nobreak >nul
goto implementation_loop

:implementation_done

REM =========================================================================
REM PHASE C: IDEAL STATE CHECK
REM =========================================================================
echo.
echo [PHASE] Phase C: Ideal State Check

REM CRITICAL: Cannot claim ideal state if implementation happened this cycle
if "%IMPLEMENTED_THIS_CYCLE%"=="true" (
    echo.
    echo [GUARD] Implementation happened this cycle - CANNOT claim ideal state yet
    echo [INFO] Must run a fresh discovery cycle to verify implementations work
    echo [INFO] Forcing return to Phase A for next cycle
    echo.
    goto cycle_complete
)

REM IMPORTANT: Claude's code analysis is the ONLY source of truth.
REM We check for the verification table showing 7/7 data flow steps passing.
REM DO NOT check the IMP file - it's OUTPUT only (for writing gaps).

echo [INFO] No implementations this cycle - checking for ideal state...
echo [INFO] Checking Claude's verification output from this cycle...

REM Check if Claude output EXIT_SIGNAL with proper verification
findstr /C:"EXIT_SIGNAL: true" "%CYCLE_LOG%" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [INFO] Claude reported EXIT_SIGNAL - checking comprehensive scan requirements...

    REM Check 1: Must have completed ALL 10 scan areas
    findstr /C:"scan_areas_completed: 10/10" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] EXIT_SIGNAL without 10/10 scan areas
        echo [INFO] Claude must scan ALL 10 areas deeply before claiming ideal state
        echo [INFO] Continuing loop - incomplete scan
        goto cycle_complete
    )

    REM Check 2: Must have zero gaps found
    findstr /C:"total_gaps_found: 0" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] EXIT_SIGNAL with gaps found
        echo [INFO] Claude must implement all gaps before claiming ideal state
        echo [INFO] Continuing loop - gaps need implementation
        goto cycle_complete
    )

    REM Check 3: Must have pytest verification
    findstr /C:"pytest_status: PASSED" "%CYCLE_LOG%" >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] EXIT_SIGNAL without pytest verification
        echo [INFO] Claude must run pytest and show passing results
        echo [INFO] Continuing loop - no runtime verification
        goto cycle_complete
    )

    REM All checks passed
    echo [SUCCESS] Claude verified all requirements:
    echo   - 10/10 scan areas completed: PASS
    echo   - Zero gaps found: PASS
    echo   - Pytest verification: PASS
    set IDEAL_REACHED=true

    echo.
    echo ==============================================
    echo     IDEAL STATE REACHED!
    echo ==============================================
    echo.
    echo [SUCCESS] Autopack has evolved to its README ideal state
    echo [INFO] Verified through:
    echo   - Comprehensive 10-area deep scan
    echo   - Zero gaps found across all areas
    echo   - Runtime verification (pytest passed)
    echo [INFO] Total cycles: %CYCLE%
    echo [INFO] Total IMPs closed: %TOTAL_IMPS_CLOSED%
    echo.
) else (
    echo [INFO] Claude did not report EXIT_SIGNAL - continuing evolution
)

:cycle_complete

echo [INFO] Cycle %CYCLE% completed

REM Cooldown between cycles
if not "%IDEAL_REACHED%"=="true" (
    echo [INFO] Cooldown before next cycle...
    timeout /t 5 /nobreak >nul
)

goto cycle_loop

:end_loop

REM Final summary
echo.
echo ==============================================
echo    EVOLUTION LOOP COMPLETE
echo ==============================================
echo.

if "%IDEAL_REACHED%"=="true" (
    echo [SUCCESS] Status: IDEAL STATE REACHED
) else (
    echo [WARNING] Status: MAX CYCLES REACHED
    echo [INFO] Review logs in %LOG_DIR% for details
)

echo.
echo [INFO] Summary:
echo   - Cycles completed: %CYCLE%
echo   - IMPs closed: %TOTAL_IMPS_CLOSED%

if "%IDEAL_REACHED%"=="true" (
    echo   - Verification: All 10 scan areas PASS, 0 gaps, pytest PASS
) else (
    echo   - Verification: Incomplete - see logs for details
)

echo.
echo [INFO] Logs saved to: %LOG_DIR%
echo.

pause
