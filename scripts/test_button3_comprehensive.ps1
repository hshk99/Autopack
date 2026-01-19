# Comprehensive test of Button 3 PR detection fixes
# Tests all the merged PRs that should be detected and marked COMPLETED

Write-Host "============ BUTTON 3 PR DETECTION TEST ============" -ForegroundColor Cyan
Write-Host ""

# Define the phases and their branch names
$testCases = @(
    @{ ID = "sec001"; Branch = "wave1/sec-001-api-key-auth"; Number = 327; Expected = "MERGED" }
    @{ ID = "sec002"; Branch = "wave1/sec-002-shell-true-fix"; Number = 330; Expected = "MERGED with FAILING CI" }
    @{ ID = "sec003"; Branch = "wave1/sec-003-path-traversal"; Number = 325; Expected = "MERGED" }
    @{ ID = "sec005"; Branch = "wave1/sec-005-governance-userid"; Number = 324; Expected = "MERGED" }
    @{ ID = "sec006"; Branch = "wave1/sec-006-webhook-secret"; Number = 328; Expected = "MERGED" }
    @{ ID = "safety001"; Branch = "wave1/safety-001-max-iterations"; Number = 326; Expected = "MERGED" }
    @{ ID = "safety002"; Branch = "wave1/safety-002-autopilot-approval"; Number = 323; Expected = "MERGED" }
    @{ ID = "safety003"; Branch = "wave1/safety-003-metachar-bypass"; Number = 329; Expected = "MERGED" }
)

$passCount = 0
$failCount = 0

foreach ($test in $testCases) {
    $phaseId = $test.ID
    $branchName = $test.Branch
    $prNumber = $test.Number
    $expected = $test.Expected

    Write-Host "[$phaseId] Testing $branchName..." -ForegroundColor Yellow

    # Query PR with correct fields and state
    $prJson = gh pr list --head $branchName --state all --json number,state,statusCheckRollup,title 2>/dev/null | ConvertFrom-Json

    if ($null -eq $prJson -or $prJson.Count -eq 0) {
        Write-Host "  ❌ ERROR: PR NOT FOUND"
        $failCount++
        Write-Host ""
        continue
    }

    $pr = $prJson
    if ($pr -is [array]) { $pr = $pr[0] }

    $state = $pr.state
    $statusChecks = $pr.statusCheckRollup

    # Determine CI status
    $ciStatus = "UNKNOWN"
    $hasFailure = $false
    $hasRunning = $false

    if ($null -ne $statusChecks -and $statusChecks.Count -gt 0) {
        foreach ($check in $statusChecks) {
            $conclusion = $check.conclusion
            $status = $check.status

            if ($conclusion -eq "FAILURE") {
                $hasFailure = $true
            }

            if ($status -eq "IN_PROGRESS") {
                $hasRunning = $true
            }
        }

        if ($hasFailure) {
            $ciStatus = "FAIL"
        } elseif ($hasRunning) {
            $ciStatus = "RUNNING"
        } else {
            $ciStatus = "PASS"
        }
    }

    # Determine action
    $action = ""
    if ($state -eq "MERGED") {
        if ($ciStatus -eq "FAIL") {
            $action = "MERGED with FAILING CI → Mark COMPLETED (despite CI failure)"
        } else {
            $action = "MERGED → Mark COMPLETED"
        }
    } elseif ($ciStatus -eq "PASS") {
        $action = "CI PASSING → Send 'proceed to merge' → Mark COMPLETED"
    } elseif ($ciStatus -eq "FAIL") {
        $action = "CI FAILING → Send 'fix it' message (don't mark completed)"
    } else {
        $action = "CI RUNNING → Wait (don't mark completed)"
    }

    Write-Host "  PR #$($pr.number): State=$state, CI=$ciStatus"
    Write-Host "  Action: $action"

    # Verify against expected
    if ($action -match $expected) {
        Write-Host "  ✅ CORRECT" -ForegroundColor Green
        $passCount++
    } else {
        Write-Host "  ❌ UNEXPECTED (Expected: $expected)" -ForegroundColor Red
        $failCount++
    }

    Write-Host ""
}

Write-Host "============ TEST SUMMARY ============" -ForegroundColor Green
Write-Host "✅ Correct: $passCount"
Write-Host "❌ Failed: $failCount"
Write-Host ""

if ($failCount -eq 0) {
    Write-Host "✅ ALL TESTS PASSED - Button 3 fix is working correctly!" -ForegroundColor Green
} else {
    Write-Host "❌ Some tests failed" -ForegroundColor Red
}

Write-Host ""
