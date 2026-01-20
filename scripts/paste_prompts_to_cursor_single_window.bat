@echo off
REM Paste a single prompt to a specific Cursor window slot
REM Includes Ctrl+M+O hotkey for opening project folder
REM Usage: paste_prompts_to_cursor_single_window.bat
REM StreamDeck: Not used directly (called by auto_fill_empty_slots.bat)

cd /d "C:\dev\Autopack"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\dev\Autopack\scripts\paste_prompts_to_cursor_single_window.ps1" %*

REM Uncomment for debugging
REM pause
