@echo off
REM Switch LLM Model (Claude / GLM-4.7)
REM Usage: switch_llm_model.bat [claude|glm|toggle|status]

cd /d "C:\dev\Autopack"

if "%1"=="" (
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\switch_llm_model.ps1" -Status
) else if /i "%1"=="claude" (
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\switch_llm_model.ps1" -Model claude
) else if /i "%1"=="glm" (
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\switch_llm_model.ps1" -Model glm
) else if /i "%1"=="toggle" (
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\switch_llm_model.ps1" -Toggle
) else if /i "%1"=="status" (
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\switch_llm_model.ps1" -Status
) else (
    echo Unknown option: %1
    echo Usage: switch_llm_model.bat [claude^|glm^|toggle^|status]
)
