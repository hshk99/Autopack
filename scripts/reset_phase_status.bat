@echo off
REM Wrapper for reset_phase_status.ps1 - reset phase status for testing
REM Usage: reset_phase_status.bat sec001 READY
REM Usage: reset_phase_status.bat (interactive mode)

setlocal enabledelayedexpansion

set PHASE_ID=%1
set NEW_STATUS=%2

if "!PHASE_ID!"=="" (
    REM Interactive mode - show available phases
    powershell -ExecutionPolicy Bypass -File "%~dp0reset_phase_status.ps1"
) else (
    if "!NEW_STATUS!"=="" (
        set NEW_STATUS=READY
    )
    powershell -ExecutionPolicy Bypass -File "%~dp0reset_phase_status.ps1" -PhaseId "!PHASE_ID!" -NewStatus "!NEW_STATUS!"
)

endlocal
