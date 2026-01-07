@echo off
REM Navigate to repository root (parent of scripts/archive/root_scripts/)
cd /d "%~dp0..\..\..\"
set PYTHONPATH=src
python src/autopack/autonomous_executor.py --run-id phase3-delegated-20251202-194253 --run-type autopack_maintenance --stop-on-first-failure --verbose
pause
