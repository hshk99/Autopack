# Quick test of PR detection logic

$branchName = "wave1/sec-001-api-key-auth"
Write-Host "Testing PR detection for: $branchName"
Write-Host ""

$prJson = gh pr list --head $branchName --state all --json number,state,statusCheckRollup,title 2>/dev/null | ConvertFrom-Json

if ($null -eq $prJson -or $prJson.Count -eq 0) {
    Write-Host "PR NOT FOUND"
} else {
    $pr = $prJson
    if ($pr -is [array]) { $pr = $pr[0] }

    Write-Host "PR #$($pr.number)"
    Write-Host "State: $($pr.state)"
    Write-Host "Title: $($pr.title)"
    Write-Host ""

    if ($null -ne $pr.statusCheckRollup -and $pr.statusCheckRollup.Count -gt 0) {
        Write-Host "Status Checks:"
        $hasFailure = $false
        $hasRunning = $false

        foreach ($check in $pr.statusCheckRollup) {
            $conclusion = $check.conclusion
            $status = $check.status
            $name = $check.name

            if ($name -match "Core Tests|lint|Autopack CI" -or $conclusion -eq "FAILURE") {
                Write-Host "  [$conclusion] $name"
                if ($conclusion -eq "FAILURE") {
                    $hasFailure = $true
                }
                if ($status -eq "IN_PROGRESS") {
                    $hasRunning = $true
                }
            }
        }

        Write-Host ""
        if ($hasFailure) {
            Write-Host "OVERALL STATUS: ❌ FAILING"
        } elseif ($hasRunning) {
            Write-Host "OVERALL STATUS: ⏳ RUNNING"
        } else {
            Write-Host "OVERALL STATUS: ✅ PASSING"
        }
    }
}
