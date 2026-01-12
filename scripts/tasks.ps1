<#
.SYNOPSIS
    Autopack Development Task Runner (Windows-first)

.DESCRIPTION
    Provides cross-platform development tasks that work natively on Windows
    without requiring Make, Bash, or WSL. Equivalent to the Makefile tasks.

.PARAMETER Task
    The task to run. Available tasks:
    - help       Show available tasks
    - install    Install dependencies
    - lint       Run linting checks (ruff, black)
    - format     Format code with black and ruff
    - test       Run unit tests
    - docker-up  Start Docker services
    - docker-down Stop Docker services
    - docker-logs View Docker logs
    - clean      Clean up generated files

.EXAMPLE
    .\scripts\tasks.ps1 help
    .\scripts\tasks.ps1 install
    .\scripts\tasks.ps1 test
    .\scripts\tasks.ps1 lint

.NOTES
    PR-06: Windows DX - First-class PowerShell task runner
    See docs/CONTRIBUTING.md for development workflow documentation.
#>

param(
    [Parameter(Position=0)]
    [ValidateSet("help", "install", "lint", "format", "test", "test-docs", "test-api", "test-llm", "test-fast", "docker-up", "docker-down", "docker-logs", "clean")]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host "Autopack Supervisor - Development Commands (PowerShell)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\scripts\tasks.ps1 <task>"
    Write-Host ""
    Write-Host "Available tasks:"
    Write-Host "  help        - Show this help message"
    Write-Host "  install     - Install dependencies"
    Write-Host "  lint        - Run linting checks (ruff check + black --check)"
    Write-Host "  format      - Format code (black + ruff fix)"
    Write-Host ""
    Write-Host "Fast local gates (5.3.5 - run before PR):" -ForegroundColor Cyan
    Write-Host "  test-docs   - Docs/SOT gate (fast, always run first)"
    Write-Host "  test-api    - API fast gate (no Postgres required)"
    Write-Host "  test-llm    - LLM wiring fast gate"
    Write-Host "  test-fast   - All fast gates combined (docs + api + llm)"
    Write-Host ""
    Write-Host "Full test runs:"
    Write-Host "  test        - Run all unit tests"
    Write-Host ""
    Write-Host "Docker:"
    Write-Host "  docker-up   - Start Docker services"
    Write-Host "  docker-down - Stop Docker services"
    Write-Host "  docker-logs - View Docker logs"
    Write-Host "  clean       - Clean up generated files"
    Write-Host ""
    Write-Host "Note: Equivalent Makefile targets are also available via make (requires Git Bash or WSL)."
}

function Invoke-Install {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Installation failed"
        exit 1
    }
    Write-Host "Installation complete!" -ForegroundColor Green
}

function Invoke-Lint {
    Write-Host "Running linting checks..." -ForegroundColor Yellow

    Write-Host "`n[1/2] Ruff check..." -ForegroundColor Cyan
    ruff check src/ tests/
    $ruffResult = $LASTEXITCODE

    Write-Host "`n[2/2] Black check..." -ForegroundColor Cyan
    black --check src/ tests/
    $blackResult = $LASTEXITCODE

    if ($ruffResult -ne 0 -or $blackResult -ne 0) {
        Write-Host "`nLint checks failed. Run '.\scripts\tasks.ps1 format' to fix." -ForegroundColor Red
        exit 1
    }

    Write-Host "`nAll lint checks passed!" -ForegroundColor Green
}

function Invoke-Format {
    Write-Host "Formatting code..." -ForegroundColor Yellow

    Write-Host "`n[1/2] Black format..." -ForegroundColor Cyan
    black src/ tests/

    Write-Host "`n[2/2] Ruff fix..." -ForegroundColor Cyan
    ruff check --fix src/ tests/

    Write-Host "`nFormatting complete!" -ForegroundColor Green
}

function Invoke-Test {
    Write-Host "Running tests..." -ForegroundColor Yellow
    pytest tests/ -v
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests failed"
        exit 1
    }
    Write-Host "All tests passed!" -ForegroundColor Green
}

# Fast local gates (5.3.5) - run before PR to get quick signal
function Invoke-TestDocs {
    Write-Host "Running docs/SOT gate (fast, always run first)..." -ForegroundColor Yellow
    # Disable coverage to avoid file locks on Windows
    python -m pytest -q -p no:pytest_cov tests/docs/
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docs/SOT tests failed"
        exit 1
    }
    Write-Host "Docs/SOT gate passed!" -ForegroundColor Green
}

function Invoke-TestApi {
    Write-Host "Running API fast gate (no Postgres)..." -ForegroundColor Yellow
    python -m pytest -q -p no:pytest_cov tests/api/
    if ($LASTEXITCODE -ne 0) {
        Write-Error "API tests failed"
        exit 1
    }
    Write-Host "API gate passed!" -ForegroundColor Green
}

function Invoke-TestLlm {
    Write-Host "Running LLM wiring fast gate..." -ForegroundColor Yellow
    python -m pytest -q -p no:pytest_cov tests/llm_service/
    if ($LASTEXITCODE -ne 0) {
        Write-Error "LLM tests failed"
        exit 1
    }
    Write-Host "LLM gate passed!" -ForegroundColor Green
}

function Invoke-TestFast {
    Write-Host "Running all fast gates (docs + api + llm)..." -ForegroundColor Yellow
    Write-Host ""

    Write-Host "[1/3] Docs/SOT gate..." -ForegroundColor Cyan
    python -m pytest -q -p no:pytest_cov tests/docs/
    $docsResult = $LASTEXITCODE

    Write-Host "`n[2/3] API fast gate..." -ForegroundColor Cyan
    python -m pytest -q -p no:pytest_cov tests/api/
    $apiResult = $LASTEXITCODE

    Write-Host "`n[3/3] LLM wiring gate..." -ForegroundColor Cyan
    python -m pytest -q -p no:pytest_cov tests/llm_service/
    $llmResult = $LASTEXITCODE

    Write-Host ""
    if ($docsResult -ne 0 -or $apiResult -ne 0 -or $llmResult -ne 0) {
        Write-Host "Some fast gates failed:" -ForegroundColor Red
        if ($docsResult -ne 0) { Write-Host "  - Docs/SOT: FAILED" -ForegroundColor Red }
        if ($apiResult -ne 0) { Write-Host "  - API: FAILED" -ForegroundColor Red }
        if ($llmResult -ne 0) { Write-Host "  - LLM: FAILED" -ForegroundColor Red }
        exit 1
    }

    Write-Host "All fast gates passed!" -ForegroundColor Green
}

function Invoke-DockerUp {
    Write-Host "Starting Docker services..." -ForegroundColor Yellow
    docker-compose up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to start Docker services"
        exit 1
    }
    Write-Host "Waiting for services to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    Write-Host "Docker services started!" -ForegroundColor Green
}

function Invoke-DockerDown {
    Write-Host "Stopping Docker services..." -ForegroundColor Yellow
    docker-compose down
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to stop Docker services"
        exit 1
    }
    Write-Host "Docker services stopped!" -ForegroundColor Green
}

function Invoke-DockerLogs {
    Write-Host "Showing Docker logs (Ctrl+C to exit)..." -ForegroundColor Yellow
    docker-compose logs -f
}

function Invoke-Clean {
    Write-Host "Cleaning up generated files..." -ForegroundColor Yellow

    $dirsToRemove = @(
        ".autonomous_runs",
        ".pytest_cache",
        "__pycache__"
    )

    foreach ($dir in $dirsToRemove) {
        if (Test-Path $dir) {
            Write-Host "  Removing $dir" -ForegroundColor Gray
            Remove-Item -Recurse -Force $dir
        }
    }

    # Remove all __pycache__ directories recursively
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
        Write-Host "  Removing $($_.FullName)" -ForegroundColor Gray
        Remove-Item -Recurse -Force $_.FullName
    }

    # Remove all .pyc files recursively
    Get-ChildItem -Recurse -File -Filter "*.pyc" | ForEach-Object {
        Write-Host "  Removing $($_.FullName)" -ForegroundColor Gray
        Remove-Item -Force $_.FullName
    }

    Write-Host "Cleanup complete!" -ForegroundColor Green
}

# Main dispatch
switch ($Task) {
    "help"        { Show-Help }
    "install"     { Invoke-Install }
    "lint"        { Invoke-Lint }
    "format"      { Invoke-Format }
    "test"        { Invoke-Test }
    "test-docs"   { Invoke-TestDocs }
    "test-api"    { Invoke-TestApi }
    "test-llm"    { Invoke-TestLlm }
    "test-fast"   { Invoke-TestFast }
    "docker-up"   { Invoke-DockerUp }
    "docker-down" { Invoke-DockerDown }
    "docker-logs" { Invoke-DockerLogs }
    "clean"       { Invoke-Clean }
    default       { Show-Help }
}
