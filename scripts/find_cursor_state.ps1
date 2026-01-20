# Find all Cursor configuration and state files
Write-Host ""
Write-Host "============ SEARCHING CURSOR CONFIG ============" -ForegroundColor Cyan
Write-Host ""

# Check all possible Cursor data locations
$locations = @(
    @{Path = "$env:APPDATA\Cursor"; Name = 'Roaming Cursor' },
    @{Path = "$env:LOCALAPPDATA\Cursor"; Name = 'Local Cursor' },
    @{Path = "$env:LOCALAPPDATA\cursor-user-data"; Name = 'cursor-user-data' }
)

foreach ($loc in $locations) {
    $path = $loc.Path
    $name = $loc.Name

    if (Test-Path $path) {
        Write-Host "Found: $name" -ForegroundColor Green
        Write-Host "Path: $path"
        Write-Host ""

        # List all subdirectories
        Get-ChildItem -Path $path -Force -Directory | ForEach-Object {
            Write-Host "  Dir: $($_.Name)"
        }

        Write-Host ""
    }
}

# Look for files that might contain window state
Write-Host "Searching for state/workspace files..." -ForegroundColor Yellow
Write-Host ""

$stateFiles = Get-ChildItem -Path "$env:APPDATA\Cursor" -Force -File -Recurse -ErrorAction SilentlyContinue | `
    Where-Object { $_.Name -like '*state*' -or $_.Name -like '*workspace*' -or $_.Name -like '*window*' -or $_.Name -like '*session*' }

if ($stateFiles) {
    Write-Host "State/workspace files found:"
    $stateFiles | ForEach-Object {
        Write-Host "  $($_.FullName)"
        Write-Host "    Size: $($_.Length) bytes"
    }
} else {
    Write-Host "No obvious state files found"
}

Write-Host ""

# Check Preferences file
$prefsFile = "$env:APPDATA\Cursor\Preferences"
if (Test-Path $prefsFile) {
    Write-Host "Preferences file found:" -ForegroundColor Green
    Write-Host "  $prefsFile"
    Write-Host "  Size: $(Get-Item $prefsFile | Select-Object -ExpandProperty Length) bytes"
    Write-Host ""

    # Try to read first few lines
    Write-Host "First 500 characters of Preferences:"
    $content = Get-Content $prefsFile
    if ($content.Length -gt 500) {
        Write-Host "$($content.Substring(0, 500))..."
    } else {
        Write-Host $content
    }
}

Write-Host ""
