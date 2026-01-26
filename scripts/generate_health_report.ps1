# Generate Telemetry Health Report (PowerShell)
#
# Generates a markdown health report from telemetry data.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\generate_health_report.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\generate_health_report.ps1 -Hours 48
#   powershell -ExecutionPolicy Bypass -File scripts\generate_health_report.ps1 -OutputFile report.md
#
# Requirements:
#   - Python 3.12+
#   - All dependencies installed (pip install -r requirements.txt)
#   - Run from repository root

param(
    [int]$Hours = 24,
    [string]$BasePath = ".",
    [string]$OutputFile = ""
)

$ErrorActionPreference = "Stop"

# Configuration
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "src"

Write-Host "========================================================================"
Write-Host "TELEMETRY HEALTH REPORT GENERATOR"
Write-Host "========================================================================"
Write-Host ""
Write-Host "Configuration:"
Write-Host "  Base Path: $BasePath"
Write-Host "  Time Window: $Hours hours"
if ($OutputFile) {
    Write-Host "  Output File: $OutputFile"
}
Write-Host ""

# Resolve base path to absolute path
$AbsBasePath = (Resolve-Path $BasePath).Path

# Generate the report
$pythonScript = @"
import sys
sys.path.insert(0, 'src')
from telemetry_dashboard import TelemetryDashboard

dashboard = TelemetryDashboard('$AbsBasePath')
report = dashboard.render_markdown_report(hours=$Hours)
print(report)
"@

Write-Host "Generating report..." -ForegroundColor Yellow
Write-Host ""

$report = python -c $pythonScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to generate report" -ForegroundColor Red
    exit 1
}

if ($OutputFile) {
    # Write to file
    $report | Out-File -FilePath $OutputFile -Encoding utf8
    Write-Host "Report written to: $OutputFile" -ForegroundColor Green
} else {
    # Print to console
    Write-Host $report
}

Write-Host ""
Write-Host "========================================================================"
Write-Host "REPORT GENERATION COMPLETE" -ForegroundColor Green
Write-Host "========================================================================"
