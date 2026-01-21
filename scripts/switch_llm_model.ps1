# Switch between LLM models (Claude / GLM-4.7)
# Usage:
#   .\switch_llm_model.ps1 -Model claude    # Switch to Claude
#   .\switch_llm_model.ps1 -Model glm       # Switch to GLM-4.7
#   .\switch_llm_model.ps1 -Status          # Show current model
#   .\switch_llm_model.ps1 -Toggle          # Toggle between models

param(
    [ValidateSet("claude", "glm")]
    [string]$Model = "",
    [switch]$Status,
    [switch]$Toggle
)

$configPath = Join-Path $PSScriptRoot "llm_config.json"

if (-not (Test-Path $configPath)) {
    Write-Host "[ERROR] Config file not found: $configPath" -ForegroundColor Red
    exit 1
}

$config = Get-Content $configPath -Raw | ConvertFrom-Json

function Show-Status {
    $activeModel = $config.active_model
    $modelInfo = $config.models.$activeModel

    Write-Host ""
    Write-Host "============ LLM MODEL STATUS ============" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Active Model: " -NoNewline
    Write-Host "$($modelInfo.name)" -ForegroundColor Green
    Write-Host "Shortcut:     $($modelInfo.shortcut)"
    Write-Host "Description:  $($modelInfo.description)"
    Write-Host ""
    Write-Host "Available Models:" -ForegroundColor Yellow
    foreach ($key in $config.models.PSObject.Properties.Name) {
        $m = $config.models.$key
        $marker = if ($key -eq $activeModel) { " [ACTIVE]" } else { "" }
        Write-Host "  - $($m.name) ($key): $($m.shortcut)$marker"
    }
    Write-Host ""
}

function Set-Model {
    param([string]$NewModel)

    if ($config.active_model -eq $NewModel) {
        Write-Host "[INFO] Already using $($config.models.$NewModel.name)" -ForegroundColor Yellow
        return
    }

    $oldModel = $config.active_model
    $config.active_model = $NewModel

    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8

    Write-Host ""
    Write-Host "============ MODEL SWITCHED ============" -ForegroundColor Green
    Write-Host ""
    Write-Host "Previous: $($config.models.$oldModel.name)"
    Write-Host "Current:  " -NoNewline
    Write-Host "$($config.models.$NewModel.name)" -ForegroundColor Green
    Write-Host "Shortcut: $($config.models.$NewModel.shortcut)"
    Write-Host ""
    Write-Host "[OK] All scripts will now use $($config.models.$NewModel.name)"
    Write-Host ""
}

# Main logic
if ($Status) {
    Show-Status
} elseif ($Toggle) {
    $newModel = if ($config.active_model -eq "claude") { "glm" } else { "claude" }
    Set-Model $newModel
} elseif ($Model) {
    Set-Model $Model
} else {
    Show-Status
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\switch_llm_model.ps1 -Model claude  # Switch to Claude"
    Write-Host "  .\switch_llm_model.ps1 -Model glm    # Switch to GLM-4.7"
    Write-Host "  .\switch_llm_model.ps1 -Toggle       # Toggle between models"
    Write-Host "  .\switch_llm_model.ps1 -Status       # Show current status"
    Write-Host ""
}
