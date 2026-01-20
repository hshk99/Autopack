# Test each executable for compatibility
$cursorDir = "C:\Users\hshk9\AppData\Local\Programs\cursor"

$exes = @(
    "$cursorDir\unins000.exe",
    "$cursorDir\resources\app\node_modules\@vscode\ripgrep\bin\rg.exe",
    "$cursorDir\resources\app\bin\cursor-tunnel.exe",
    "$cursorDir\resources\app\bin\helpers\browser_wer_helper.exe"
)

foreach ($exe in $exes) {
    if (Test-Path $exe) {
        Write-Host "`nTesting: $exe" -ForegroundColor Yellow
        try {
            $proc = Start-Process -FilePath $exe -ArgumentList "--version" -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
            Write-Host "  Exit code: $($proc.ExitCode)"
        } catch {
            Write-Host "  Error: $_" -ForegroundColor Red
        }
    }
}

# Check for any helper executables
Write-Host "`nAll helper executables:" -ForegroundColor Cyan
Get-ChildItem "$cursorDir\resources\app\bin\helpers" -Filter "*.exe" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  $($_.Name)"
}
