@echo off
REM Launch 9 Cursor windows for parallel development
REM Usage: launch_cursors.bat
REM StreamDeck: Execute this file with working directory set to C:\dev\Autopack

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -Command ^
  ".\scripts\wave_orchestrator.ps1 -Wave 1 -WorkflowFile 'C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_WORKFLOW.md' -StartCursor 9 -EndCursor 17"

REM Optional: Add pause for debugging (remove for StreamDeck production)
REM pause
