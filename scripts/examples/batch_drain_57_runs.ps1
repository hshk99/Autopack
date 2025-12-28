# PowerShell script: Efficiently process the 57 runs with failed phases
#
# This script demonstrates how to use the batch drain controller
# to process failed phases across all runs in manageable batches.

$ErrorActionPreference = "Stop"

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "Batch Drain Controller - Process 57 Runs with Failed Phases" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$BATCH_SIZE = 20
$TOTAL_PHASES_TARGET = 100  # Process 100 failed phases total

Write-Host "Configuration:"
Write-Host "  Batch Size: $BATCH_SIZE phases per batch"
Write-Host "  Target: Process $TOTAL_PHASES_TARGET failed phases total"
Write-Host ""

# Step 1: Check current state
Write-Host "Step 1: Checking current state..." -ForegroundColor Yellow
python scripts/list_run_counts.py | Select-Object -First 20
Write-Host ""

# Step 2: Run first batch (dry run to preview)
Write-Host "Step 2: Preview first batch (dry run)..." -ForegroundColor Yellow
python scripts/batch_drain_controller.py `
    --batch-size $BATCH_SIZE `
    --dry-run
Write-Host ""

$response = Read-Host "Proceed with actual drain? (y/N)"
if ($response -ne 'y' -and $response -ne 'Y') {
    Write-Host "Aborted by user"
    exit 0
}

# Step 3: Process batches until target reached
$PROCESSED = 0
$BATCH_NUM = 1

while ($PROCESSED -lt $TOTAL_PHASES_TARGET) {
    $REMAINING = $TOTAL_PHASES_TARGET - $PROCESSED
    $CURRENT_BATCH_SIZE = $BATCH_SIZE

    if ($REMAINING -lt $BATCH_SIZE) {
        $CURRENT_BATCH_SIZE = $REMAINING
    }

    Write-Host ""
    Write-Host "===================================================================" -ForegroundColor Cyan
    Write-Host "Batch $BATCH_NUM : Processing $CURRENT_BATCH_SIZE phases" -ForegroundColor Cyan
    Write-Host "Progress: $PROCESSED / $TOTAL_PHASES_TARGET processed so far" -ForegroundColor Cyan
    Write-Host "===================================================================" -ForegroundColor Cyan
    Write-Host ""

    # Run batch drain
    try {
        python scripts/batch_drain_controller.py `
            --batch-size $CURRENT_BATCH_SIZE

        $EXIT_CODE = $LASTEXITCODE
    }
    catch {
        Write-Host "Error running batch drain: $_" -ForegroundColor Red
        $EXIT_CODE = 1
    }

    # Update progress
    $PROCESSED += $CURRENT_BATCH_SIZE
    $BATCH_NUM += 1

    # Check if we should continue
    if ($EXIT_CODE -ne 0) {
        Write-Host ""
        Write-Host "Warning: Batch completed with errors (exit code: $EXIT_CODE)" -ForegroundColor Yellow
        $response = Read-Host "Continue to next batch? (y/N)"
        if ($response -ne 'y' -and $response -ne 'Y') {
            Write-Host "Stopping after $PROCESSED phases processed"
            break
        }
    }

    Write-Host ""
    Write-Host "Batch $($BATCH_NUM - 1) complete. Pausing 5 seconds before next batch..." -ForegroundColor Green
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "Batch Drain Complete" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Final state:"
python scripts/list_run_counts.py | Select-Object -First 20
Write-Host ""
Write-Host "Review session files in: .autonomous_runs\batch_drain_sessions\" -ForegroundColor Green
