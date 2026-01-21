# Check Cursor Preferences for window state
$prefsFile = "C:\Users\hshk9\AppData\Roaming\Cursor\Preferences"

if (-not (Test-Path $prefsFile)) {
    Write-Host "Preferences file not found"
    exit 1
}

Write-Host "Reading Preferences file..."
Write-Host ""

$json = Get-Content $prefsFile | ConvertFrom-Json

# Look for window-related keys
$windowKeys = $json | Get-Member -MemberType NoteProperty | Where-Object { $_.Name -like '*window*' -or $_.Name -like '*restore*' -or $_.Name -like '*screen*' }

if ($windowKeys) {
    Write-Host "Found window-related settings:" -ForegroundColor Green
    foreach ($key in $windowKeys) {
        $name = $key.Name
        $value = $json.$name
        Write-Host "$name = $value"
    }
} else {
    Write-Host "No obvious window keys in Preferences"
}

Write-Host ""
Write-Host "Checking for workspace info..."
$allKeys = $json | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
Write-Host "Total settings: $($allKeys.Count)"
Write-Host ""

# Show all keys that might relate to windows/workspaces
$relevantKeys = $allKeys | Where-Object { $_ -match 'window|workspace|restore|session|screen' }
if ($relevantKeys) {
    Write-Host "Potentially relevant keys:"
    $relevantKeys | ForEach-Object { Write-Host "  - $_" }
} else {
    Write-Host "No window/workspace/restore/session keys found"
}
