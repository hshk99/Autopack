# Telemetry Seeding Quickstart Script (PowerShell)
#
# This script demonstrates the complete workflow for seeding telemetry data:
# 1. Create fresh telemetry seed DB
# 2. Seed known-success run
# 3. Start API server with correct DATABASE_URL
# 4. Drain phases to collect telemetry
# 5. Validate and analyze results
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\telemetry_seed_quickstart.ps1
#
# Requirements:
#   - Python 3.12+
#   - All dependencies installed (pip install -r requirements.txt)
#   - Run from repository root

$ErrorActionPreference = "Stop"

# Configuration
$DB_FILE = "autopack_telemetry_seed.db"
$RUN_ID = "telemetry-collection-v4"
$API_PORT = 8000
$API_URL = "http://127.0.0.1:$API_PORT"

Write-Host "========================================================================"
Write-Host "TELEMETRY SEEDING QUICKSTART"
Write-Host "========================================================================"
Write-Host ""

# Step 1: Create fresh telemetry seed DB
Write-Host "[Step 1/5] Creating fresh telemetry seed DB..." -ForegroundColor Yellow
if (Test-Path $DB_FILE) {
    Write-Host "  Removing old $DB_FILE..."
    Remove-Item $DB_FILE -Force
}

$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///$DB_FILE"

python -c "from autopack.database import init_db; init_db(); print('[OK] Schema initialized')"
Write-Host "Telemetry seed DB created" -ForegroundColor Green
Write-Host ""

# Step 2: Seed known-success run
Write-Host "[Step 2/5] Seeding known-success run..." -ForegroundColor Yellow
python scripts\create_telemetry_collection_run.py
Write-Host "Run '$RUN_ID' created with 10 phases" -ForegroundColor Green
Write-Host ""

# Step 3: Verify DB state
Write-Host "[Step 3/5] Verifying DB state..." -ForegroundColor Yellow
python scripts\db_identity_check.py | Select-Object -First 20
Write-Host "DB state verified" -ForegroundColor Green
Write-Host ""

# Step 4: Start API server in background
Write-Host "[Step 4/5] Starting API server ($API_URL)..." -ForegroundColor Yellow
Write-Host "  The server will run until you manually stop it"
Write-Host ""

# Start API server as background job
$apiJob = Start-Job -ScriptBlock {
    param($dbFile, $port)
    $env:PYTHONUTF8 = "1"
    $env:PYTHONPATH = "src"
    $env:DATABASE_URL = "sqlite:///$dbFile"
    python -m uvicorn autopack.main:app --host 127.0.0.1 --port $port
} -ArgumentList $DB_FILE, $API_PORT

Write-Host "  API server started (Job ID: $($apiJob.Id))"

# Wait for API server to start
Start-Sleep -Seconds 3

# Check if API server job is still running
$jobState = (Get-Job -Id $apiJob.Id).State
if ($jobState -ne "Running") {
    Write-Host "API server failed to start" -ForegroundColor Red
    Remove-Job -Id $apiJob.Id -Force
    exit 1
}

Write-Host "API server running at $API_URL" -ForegroundColor Green
Write-Host ""

# Step 5: Drain phases with batch drain controller
Write-Host "[Step 5/5] Draining phases to collect telemetry..." -ForegroundColor Yellow
Write-Host "  This will drain 10 phases from run '$RUN_ID'"
Write-Host "  TELEMETRY_DB_ENABLED=1 ensures telemetry collection"
Write-Host ""

try {
    # Drain phases with telemetry enabled
    $env:TELEMETRY_DB_ENABLED = "1"
    python scripts\batch_drain_controller.py `
        --run-id "$RUN_ID" `
        --batch-size 10 `
        --api-url "$API_URL" `
        --phase-timeout-seconds 900 `
        --max-total-minutes 60

    Write-Host ""
    Write-Host "Phases drained" -ForegroundColor Green
    Write-Host ""
}
finally {
    # Stop API server
    Write-Host "Stopping API server..."
    Stop-Job -Id $apiJob.Id -ErrorAction SilentlyContinue
    Remove-Job -Id $apiJob.Id -Force -ErrorAction SilentlyContinue
}

# Step 6: Validate telemetry collection
Write-Host ""
Write-Host "[Validation] Checking telemetry results..." -ForegroundColor Yellow
python scripts\db_identity_check.py | Select-String -Pattern "Telemetry Statistics" -Context 0,20

Write-Host ""
Write-Host "========================================================================"
Write-Host "TELEMETRY SEEDING COMPLETE" -ForegroundColor Green
Write-Host "========================================================================"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Analyze telemetry:"
Write-Host "     `$env:DATABASE_URL='sqlite:///$DB_FILE'; python scripts\analyze_token_telemetry_v3.py --success-only"
Write-Host ""
Write-Host "  2. Export telemetry to CSV:"
Write-Host "     `$env:DATABASE_URL='sqlite:///$DB_FILE'; python scripts\export_token_estimation_telemetry.py"
Write-Host ""
Write-Host "Database: $DB_FILE"
Write-Host "Run ID: $RUN_ID"
Write-Host "========================================================================"
