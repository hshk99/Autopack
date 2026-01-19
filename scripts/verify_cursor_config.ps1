# Verify Cursor is properly configured for Claude API
# This script checks and helps fix common configuration issues

Write-Host ""
Write-Host "============ CURSOR CONFIGURATION CHECKER ============" -ForegroundColor Cyan
Write-Host ""

Write-Host "STEP 1: Check if Cursor has Claude API configured..."
Write-Host ""

# Check for common Cursor config locations
$configLocations = @(
    "$env:APPDATA\Cursor\settings.json",
    "$env:USERPROFILE\.cursor\settings.json",
    "$env:USERPROFILE\AppData\Local\Cursor\User\settings.json",
    "$env:USERPROFILE\AppData\Roaming\Cursor\User\settings.json"
)

$foundConfig = $null
foreach ($loc in $configLocations) {
    if (Test-Path $loc) {
        Write-Host "[FOUND] Configuration at: $loc"
        $foundConfig = $loc
        break
    }
}

if (-not $foundConfig) {
    Write-Host "[INFO] No Cursor settings.json found in standard locations"
    Write-Host ""
    Write-Host "MANUAL SETUP REQUIRED:"
    Write-Host "====================="
    Write-Host ""
    Write-Host "1. Open each Cursor window (you'll have 9 of them)"
    Write-Host "2. In each window, go to: Settings → Extensions → Claude (or API settings)"
    Write-Host "3. Add your Claude API key:"
    Write-Host "   - Get it from: https://console.anthropic.com/account/keys"
    Write-Host "   - Paste the key into the API key field"
    Write-Host "4. Save settings"
    Write-Host ""
    Write-Host "Once configured in ONE Cursor instance, it may sync to others."
    Write-Host "If not, repeat for each instance."
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "STEP 2: Checking API key configuration..."
Write-Host ""

try {
    $configContent = Get-Content $foundConfig -Raw | ConvertFrom-Json

    # Look for Claude API key settings
    $claudeSettings = $configContent | Select-Object -ExpandProperty "*claude*" -ErrorAction SilentlyContinue

    if ($null -ne $claudeSettings) {
        Write-Host "[OK] Claude-related settings found"
        Write-Host "$claudeSettings"
    } else {
        Write-Host "[WARNING] No explicit Claude settings found in config"
        Write-Host ""
        Write-Host "This could mean:"
        Write-Host "  - Claude API key is not yet configured"
        Write-Host "  - Settings are stored elsewhere"
        Write-Host ""
    }
} catch {
    Write-Host "[ERROR] Could not parse config file: $_"
}

Write-Host ""
Write-Host "STEP 3: Quick Test"
Write-Host ""

Write-Host "To verify Cursor is working:"
Write-Host "1. Open any Cursor instance"
Write-Host "2. Try to use Claude Chat (Ctrl+K or Cmd+K)"
Write-Host "3. Ask a simple question like 'Hello'"
Write-Host "4. If it works, your configuration is correct"
Write-Host ""

Write-Host "If you see 'Unable to reach the model provider':"
Write-Host "  → Your API key is missing or invalid"
Write-Host "  → Get a new key from: https://console.anthropic.com/account/keys"
Write-Host "  → Set it in Cursor Settings"
Write-Host ""

Write-Host "============ END CHECK ============" -ForegroundColor Cyan
Write-Host ""
