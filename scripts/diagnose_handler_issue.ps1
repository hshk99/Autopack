# Comprehensive diagnostic for handler issues

Write-Host ""
Write-Host "========== HANDLER DIAGNOSTIC TOOL ==========" -ForegroundColor Cyan
Write-Host ""

$issues = @()

# Check 1: PowerShell execution policy
Write-Host "[1/6] Checking PowerShell execution policy..." -ForegroundColor Yellow
try {
    $policy = Get-ExecutionPolicy -Scope CurrentUser
    if ($policy -eq "Bypass" -or $policy -eq "Unrestricted" -or $policy -eq "RemoteSigned") {
        Write-Host "  ✓ Execution policy OK: $policy" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Execution policy is $policy (should be Bypass/Unrestricted/RemoteSigned)" -ForegroundColor Red
        $issues += "ExecutionPolicy is restrictive - scripts may not run"
    }
} catch {
    Write-Host "  ✗ Error checking policy" -ForegroundColor Red
}

# Check 2: Handler file exists
Write-Host "[2/6] Checking handler files..." -ForegroundColor Yellow
$handlerFile = "C:\dev\Autopack\scripts\handle_connection_errors_automated.ps1"
$launcherFile = "C:\dev\Autopack\scripts\handle_connection_errors_automated.bat"

if (Test-Path $handlerFile) {
    $size = (Get-Item $handlerFile).Length
    Write-Host "  ✓ Handler exists: $($size) bytes" -ForegroundColor Green
} else {
    Write-Host "  ✗ Handler not found at: $handlerFile" -ForegroundColor Red
    $issues += "Handler PS1 file missing"
}

if (Test-Path $launcherFile) {
    Write-Host "  ✓ Launcher exists" -ForegroundColor Green
} else {
    Write-Host "  ✗ Launcher not found at: $launcherFile" -ForegroundColor Red
    $issues += "Launcher BAT file missing"
}

# Check 3: Baseline directory
Write-Host "[3/6] Checking baseline directory..." -ForegroundColor Yellow
$baselineDir = "C:\dev\Autopack\error_baselines"
if (Test-Path $baselineDir) {
    $files = Get-ChildItem "$baselineDir\baseline_*.png" -ErrorAction SilentlyContinue
    if ($files.Count -eq 9) {
        Write-Host "  ✓ All 9 baseline files exist" -ForegroundColor Green
    } elseif ($files.Count -gt 0) {
        Write-Host "  ⚠ Only $($files.Count) baseline files (expected 9)" -ForegroundColor Yellow
        $issues += "Missing baseline files - handler may not detect properly"
    } else {
        Write-Host "  ⚠ No baseline files yet (normal on first run)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ⚠ Baseline directory doesn't exist yet (will be created on first run)" -ForegroundColor Yellow
}

# Check 4: Cursor windows
Write-Host "[4/6] Checking for Cursor windows..." -ForegroundColor Yellow
try {
    $cursorProcess = Get-Process -Name "cursor" -ErrorAction SilentlyContinue
    if ($cursorProcess) {
        $count = @($cursorProcess).Count
        Write-Host "  ✓ Found $count Cursor process(es)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ No Cursor process found (grid may not be visible)" -ForegroundColor Red
        $issues += "Cursor not running - handler can't capture grid"
    }
} catch {
    Write-Host "  ✗ Error checking Cursor: $_" -ForegroundColor Red
}

# Check 5: Syntax of handler
Write-Host "[5/6] Checking handler syntax..." -ForegroundColor Yellow
try {
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $handlerFile,
        [ref]$null,
        [ref]$null
    )
    if ($ast.EndBlock.Statements.Count -gt 0) {
        Write-Host "  ✓ Handler syntax is valid" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Handler has no statements" -ForegroundColor Red
        $issues += "Handler file appears empty or malformed"
    }
} catch {
    Write-Host "  ✗ Syntax error in handler: $_" -ForegroundColor Red
    $issues += "Handler has syntax errors: $_"
}

# Check 6: Test mouse clicking capability
Write-Host "[6/6] Testing mouse click capability..." -ForegroundColor Yellow
try {
    Add-Type @"
using System;
using System.Runtime.InteropServices;

public class MouseTest {
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);

    public static void Test() {
        SetCursorPos(100, 100);
    }
}
"@ -ErrorAction Stop

    [MouseTest]::Test()
    Write-Host "  ✓ Mouse click capability available" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Mouse click disabled: $_" -ForegroundColor Red
    $issues += "Cannot click mouse - detected error won't recover"
}

# Summary
Write-Host ""
Write-Host "========== DIAGNOSTIC SUMMARY ==========" -ForegroundColor Cyan
Write-Host ""

if ($issues.Count -eq 0) {
    Write-Host "✓ All checks passed! Handler should work." -ForegroundColor Green
    Write-Host ""
    Write-Host "NEXT STEPS:" -ForegroundColor Yellow
    Write-Host "1. Start handler: C:\dev\Autopack\scripts\handle_connection_errors_automated.bat"
    Write-Host "2. Wait for baseline capture (~10 seconds)"
    Write-Host "3. Trigger a connection error in one Cursor window"
    Write-Host "4. Watch for: 'CONNECTION ERROR DETECTED IN GRID SLOT X'"
    Write-Host ""
    Write-Host "If error is NOT detected:" -ForegroundColor Yellow
    Write-Host "- Run: C:\dev\Autopack\scripts\analyze_error_detection.ps1"
    Write-Host "- Analyze slot to see actual pixel change percentages"
    Write-Host "- Thresholds may need tuning based on real error appearance"
} else {
    Write-Host "✗ Issues found that may prevent handler from working:" -ForegroundColor Red
    Write-Host ""
    foreach ($issue in $issues) {
        Write-Host "  • $issue" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "RECOMMENDATIONS:" -ForegroundColor Yellow
    if ($issues -contains "ExecutionPolicy is restrictive - scripts may not run") {
        Write-Host "  1. Run: powershell Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser"
    }
    if ($issues -contains "Cursor not running - handler can't capture grid") {
        Write-Host "  2. Start Cursor with 9 windows before running handler"
    }
    if ($issues -contains "Handler PS1 file missing") {
        Write-Host "  3. Verify: C:\dev\Autopack\scripts\handle_connection_errors_automated.ps1 exists"
    }
}

Write-Host ""
