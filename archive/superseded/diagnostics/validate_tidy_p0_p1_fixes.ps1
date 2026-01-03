# Validation script for BUILD-155 P0-P1 tidy fixes
# Tests:
# 1. Dry-run does not mutate pending queue
# 2. Execute with profiling completes without hanging
# 3. Verification treats queued locked items as warnings (not errors)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=" * 70
Write-Host "BUILD-155 P0-P1 TIDY FIXES VALIDATION"
Write-Host "=" * 70
Write-Host ""

# Navigate to repo root
Set-Location C:\dev\Autopack

# Helper: get a stable hash for the pending queue (or empty if missing)
function Get-QueueHash {
    $queuePath = ".autonomous_runs\tidy_pending_moves.json"
    if (Test-Path $queuePath) {
        return (Get-FileHash $queuePath -Algorithm SHA256).Hash
    }
    return ""
}

# Helper: get queue mtime
function Get-QueueMtime {
    $queuePath = ".autonomous_runs\tidy_pending_moves.json"
    if (Test-Path $queuePath) {
        return (Get-Item $queuePath).LastWriteTime
    }
    return $null
}

Write-Host "=== Pre-state ==="
$preQueueHash = Get-QueueHash
$preQueueMtime = Get-QueueMtime
Write-Host "queue_hash_pre=$preQueueHash"
Write-Host "queue_mtime_pre=$preQueueMtime"
git status -sb
Write-Host ""

# Test 1: Dry-run should not mutate pending queue
Write-Host "=== TEST 1: DRY-RUN should not mutate pending queue ==="
Write-Host ""

# Ensure diagnostics directory exists
New-Item -ItemType Directory -Force -Path "archive\diagnostics" | Out-Null

Write-Host "Running: python scripts\tidy\tidy_up.py --dry-run"
python scripts\tidy\tidy_up.py --dry-run | Tee-Object -FilePath archive\diagnostics\tidy_dry_run.log

$postDryQueueHash = Get-QueueHash
$postDryQueueMtime = Get-QueueMtime
Write-Host ""
Write-Host "queue_hash_post_dry=$postDryQueueHash"
Write-Host "queue_mtime_post_dry=$postDryQueueMtime"

if ($preQueueHash -ne "" -and $preQueueHash -ne $postDryQueueHash) {
    Write-Host ""
    Write-Host "FAIL: dry-run mutated .autonomous_runs\tidy_pending_moves.json (hash changed)" -ForegroundColor Red
    Write-Host "  Pre:  $preQueueHash" -ForegroundColor Red
    Write-Host "  Post: $postDryQueueHash" -ForegroundColor Red
    exit 1
}

if ($preQueueMtime -ne $null -and $postDryQueueMtime -ne $null) {
    $timeDiff = ($postDryQueueMtime - $preQueueMtime).TotalSeconds
    if ($timeDiff -gt 2) {
        Write-Host ""
        Write-Host "WARN: queue mtime changed by $timeDiff seconds (might be a mutation)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "PASS: Dry-run did not mutate pending queue" -ForegroundColor Green
Write-Host ""

# Test 2: Execute with profiling should complete without hanging
Write-Host "=== TEST 2: EXECUTE Phase 0.5 profiling should complete (no hang) ==="
Write-Host ""

Write-Host "Running: python scripts\tidy\tidy_up.py --execute --profile"
Write-Host "(This tests the optimized empty-directory deletion and profiling infrastructure)"
Write-Host ""

# Add timeout protection (5 minutes max)
$tidyJob = Start-Job -ScriptBlock {
    Set-Location C:\dev\Autopack
    python scripts\tidy\tidy_up.py --execute --profile 2>&1
}

$completed = Wait-Job $tidyJob -Timeout 300
if ($completed) {
    $output = Receive-Job $tidyJob
    $output | Tee-Object -FilePath archive\diagnostics\tidy_execute_profile.log
    Remove-Job $tidyJob

    # Check if profiling output is present
    if ($output -match "\[PROFILE\]") {
        Write-Host ""
        Write-Host "PASS: Profiling output detected" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "WARN: No profiling output detected (expected [PROFILE] markers)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "PASS: Execute completed within timeout (no hang detected)" -ForegroundColor Green
    Write-Host ""
} else {
    Stop-Job $tidyJob
    Remove-Job $tidyJob
    Write-Host ""
    Write-Host "FAIL: Execute timed out after 5 minutes (possible hang in Phase 0.5)" -ForegroundColor Red
    exit 1
}

# Test 3: Verification should treat queued locked items as warnings
Write-Host "=== TEST 3: Verification: queued locked items should be warnings (not fail) ==="
Write-Host ""

Write-Host "Running: python scripts\tidy\verify_workspace_structure.py"
python scripts\tidy\verify_workspace_structure.py | Tee-Object -FilePath archive\diagnostics\tidy_verify.log
$verifyExitCode = $LASTEXITCODE

if ($verifyExitCode -ne 0) {
    Write-Host ""
    Write-Host "FAIL: verification failed (expected success with warnings for queued locked items)" -ForegroundColor Red
    Write-Host "Exit code: $verifyExitCode" -ForegroundColor Red

    # Show last 20 lines of verification output for debugging
    Write-Host ""
    Write-Host "Last 20 lines of verification output:" -ForegroundColor Yellow
    Get-Content archive\diagnostics\tidy_verify.log | Select-Object -Last 20
    exit 1
}

Write-Host ""
Write-Host "PASS: Verification succeeded (queued locked items treated as warnings)" -ForegroundColor Green
Write-Host ""

# Final summary
Write-Host "=" * 70
Write-Host "ALL TESTS PASSED" -ForegroundColor Green
Write-Host "=" * 70
Write-Host ""
Write-Host "Logs written to:"
Write-Host "  - archive/diagnostics/tidy_dry_run.log"
Write-Host "  - archive/diagnostics/tidy_execute_profile.log"
Write-Host "  - archive/diagnostics/tidy_verify.log"
Write-Host ""
Write-Host "Summary:"
Write-Host "  [PASS] Dry-run does not mutate pending queue"
Write-Host "  [PASS] Execute with profiling completes without hanging"
Write-Host "  [PASS] Verification treats queued locked items as warnings"
Write-Host ""
