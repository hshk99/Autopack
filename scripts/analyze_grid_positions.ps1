# Analyze the window positions to understand the actual grid

$windows = @(
    @{ phaseId = 'feat005'; left = 2560; top = 463 },
    @{ phaseId = 'ops002'; left = 4266; top = 926 },
    @{ phaseId = 'ops001'; left = 3413; top = 926 },
    @{ phaseId = 'cost003'; left = 4266; top = 463 },
    @{ phaseId = 'safety010'; left = 3413; top = 0 },
    @{ phaseId = 'feat003'; left = 4266; top = 0 },
    @{ phaseId = 'cost007'; left = 2560; top = 926 },
    @{ phaseId = 'cost001'; left = 3413; top = 463 },
    @{ phaseId = 'safety006'; left = 2560; top = 0 }
)

# Group by position to understand grid
Write-Host "GRID ANALYSIS"
Write-Host "============="
Write-Host ""
Write-Host "Unique Y (row) positions:"
$uniqueY = $windows | Select-Object -ExpandProperty top -Unique | Sort-Object
$uniqueY | ForEach-Object { Write-Host "  Y = $_" }

Write-Host ""
Write-Host "Unique X (column) positions:"
$uniqueX = $windows | Select-Object -ExpandProperty left -Unique | Sort-Object
$uniqueX | ForEach-Object { Write-Host "  X = $_" }

Write-Host ""
Write-Host "GRID LAYOUT (Left=2560/3413/4266, Top=0/463/926):"
Write-Host ""
Write-Host "Top row (Y=0):"
$windows | Where-Object { $_.top -eq 0 } | Sort-Object left | ForEach-Object { Write-Host "  Slot X=$($_.left): $($_.phaseId)" }

Write-Host ""
Write-Host "Middle row (Y=463):"
$windows | Where-Object { $_.top -eq 463 } | Sort-Object left | ForEach-Object { Write-Host "  Slot X=$($_.left): $($_.phaseId)" }

Write-Host ""
Write-Host "Bottom row (Y=926):"
$windows | Where-Object { $_.top -eq 926 } | Sort-Object left | ForEach-Object { Write-Host "  Slot X=$($_.left): $($_.phaseId)" }

Write-Host ""
Write-Host "CONCLUSION: The grid uses window Left (not right) coordinates"
Write-Host "  Columns: 2560, 3413 (delta=853), 4266 (delta=853)"
Write-Host "  Rows: 0, 463 (delta=463), 926 (delta=463)"
