# Check cleanup status and verify merged PRs
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "CLEANUP STATUS CHECK" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

$backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"

# 1. Check Unresolved Issues File
Write-Host "1. UNRESOLVED ISSUES FILE" -ForegroundColor Yellow
$unresolvedFile = Join-Path $backupDir "Wave1_Unresolved_Issues.json"

if (Test-Path $unresolvedFile) {
    Write-Host "  File EXISTS: $unresolvedFile" -ForegroundColor Green
    Write-Host "  Contents:"
    Get-Content $unresolvedFile | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "  File DOES NOT EXIST" -ForegroundColor Red
}
Write-Host ""

# 2. Check Wave1_All_Phases.md
Write-Host "2. WAVE1_ALL_PHASES.MD STATUS" -ForegroundColor Yellow
$waveFiles = Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
if ($waveFiles.Count -gt 0) {
    $waveFile = $waveFiles[0].FullName
    Write-Host "  File: $($waveFiles[0].Name)"

    # Count statuses
    $content = Get-Content $waveFile -Raw
    $readyCount = ([regex]::Matches($content, '\[READY\]')).Count
    $pendingCount = ([regex]::Matches($content, '\[PENDING\]')).Count
    $completedCount = ([regex]::Matches($content, '\[COMPLETED\]')).Count

    Write-Host "  READY: $readyCount | PENDING: $pendingCount | COMPLETED: $completedCount"

    # Check for Unresolved Issues section
    if ($content -match "## Unresolved Issues") {
        Write-Host "  Unresolved Issues section: PRESENT" -ForegroundColor Green
    } else {
        Write-Host "  Unresolved Issues section: NOT PRESENT" -ForegroundColor Yellow
    }

    # Show header
    Write-Host ""
    Write-Host "  Header (first 20 lines):"
    Get-Content $waveFile | Select-Object -First 20 | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "  No Wave file found" -ForegroundColor Red
}
Write-Host ""

# 3. Check AUTOPACK_IMPS_MASTER.json
Write-Host "3. AUTOPACK_IMPS_MASTER.JSON" -ForegroundColor Yellow
$masterFiles = Get-ChildItem -Path $backupDir -Filter "AUTOPACK_IMPS_MASTER.json" -ErrorAction SilentlyContinue
if ($masterFiles.Count -gt 0) {
    $masterFile = $masterFiles[0].FullName
    $masterJson = Get-Content $masterFile -Raw | ConvertFrom-Json
    $impCount = @($masterJson.improvements).Count
    Write-Host "  File: $($masterFiles[0].Name)"
    Write-Host "  Remaining improvements: $impCount"
    if ($impCount -gt 0) {
        Write-Host "  IDs: $(($masterJson.improvements | ForEach-Object { $_.id }) -join ', ')"
    }
} else {
    Write-Host "  File not found" -ForegroundColor Yellow
}
Write-Host ""

# 4. Check AUTOPACK_WAVE_PLAN.json
Write-Host "4. AUTOPACK_WAVE_PLAN.JSON" -ForegroundColor Yellow
$planFiles = Get-ChildItem -Path $backupDir -Filter "AUTOPACK_WAVE_PLAN.json" -ErrorAction SilentlyContinue
if ($planFiles.Count -gt 0) {
    $planFile = $planFiles[0].FullName
    $planJson = Get-Content $planFile -Raw | ConvertFrom-Json
    Write-Host "  File: $($planFiles[0].Name)"
    if ($planJson.PSObject.Properties["wave_1"]) {
        $wave1Phases = @($planJson.wave_1.phases)
        Write-Host "  Wave 1 phases remaining: $($wave1Phases.Count)"
        if ($wave1Phases.Count -gt 0) {
            Write-Host "  IDs: $(($wave1Phases | ForEach-Object { $_.id }) -join ', ')"
        }
    }
} else {
    Write-Host "  File not found" -ForegroundColor Yellow
}
Write-Host ""

# 5. Summary of merged PRs CI status
Write-Host "5. MERGED PRs CI STATUS SUMMARY" -ForegroundColor Yellow
Write-Host ""
$mergedPRs = @(345, 333, 332)
foreach ($prNum in $mergedPRs) {
    Write-Host "  PR #$prNum :"
    $prData = gh pr view $prNum --json title,state,statusCheckRollup 2>$null | ConvertFrom-Json

    if ($prData) {
        Write-Host "    Title: $($prData.title)"
        Write-Host "    State: $($prData.state)"

        # Analyze checks
        $failedChecks = @($prData.statusCheckRollup | Where-Object { $_.conclusion -eq "FAILURE" })
        $coreTests = $prData.statusCheckRollup | Where-Object { $_.name -eq "Core Tests (Must Pass)" }

        if ($coreTests) {
            Write-Host "    Core Tests: $($coreTests.conclusion)" -ForegroundColor $(if ($coreTests.conclusion -eq "SUCCESS") { "Green" } else { "Red" })
        }

        if ($failedChecks.Count -gt 0) {
            $failedNames = ($failedChecks | ForEach-Object { $_.name }) -join ", "
            Write-Host "    FAILED checks: $failedNames" -ForegroundColor Yellow
        } else {
            Write-Host "    All checks passed" -ForegroundColor Green
        }
    }
    Write-Host ""
}
