# Calculate proper grid with taskbar margin

Write-Host "=== TASKBAR CUTOFF ANALYSIS ===" -ForegroundColor Cyan
Write-Host ""

# Windows taskbar is typically 50px at bottom
$taskbarHeight = 50
$monitorHeight = 1440
$availableHeight = $monitorHeight - $taskbarHeight

Write-Host "Monitor height: $monitorHeight"
Write-Host "Taskbar height: $taskbarHeight"
Write-Host "Available height: $availableHeight (1390px)"
Write-Host ""

# Divide into 3 rows
$rowHeight = [math]::Floor($availableHeight / 3)
$remainder = $availableHeight % 3

Write-Host "Height per row: $rowHeight"
Write-Host "Remainder pixels: $remainder"
Write-Host ""

# Calculate row positions
$row1Start = 0
$row1End = $row1Start + $rowHeight
$row2Start = $row1End
$row2End = $row2Start + $rowHeight
$row3Start = $row2End
$row3End = $row3Start + $rowHeight + $remainder  # Add remainder to last row

Write-Host "Row 1: Y=$row1Start to $row1End (height: $($row1End - $row1Start))"
Write-Host "Row 2: Y=$row2Start to $row2End (height: $($row2End - $row2Start))"
Write-Host "Row 3: Y=$row3Start to $row3End (height: $($row3End - $row3Start))"
Write-Host ""

Write-Host "=== NEW CORRECTED GRID ===" -ForegroundColor Yellow
Write-Host ""

$newGrid = @{
    1 = @{X=2560; Y=$row1Start; W=853; H=$($row1End - $row1Start)}      # Top-Left
    2 = @{X=3413; Y=$row1Start; W=853; H=$($row1End - $row1Start)}      # Top-Center
    3 = @{X=4266; Y=$row1Start; W=854; H=$($row1End - $row1Start)}      # Top-Right
    4 = @{X=2560; Y=$row2Start; W=853; H=$($row2End - $row2Start)}      # Mid-Left
    5 = @{X=3413; Y=$row2Start; W=853; H=$($row2End - $row2Start)}      # Mid-Center
    6 = @{X=4266; Y=$row2Start; W=854; H=$($row2End - $row2Start)}      # Mid-Right
    7 = @{X=2560; Y=$row3Start; W=853; H=$($row3End - $row3Start)}      # Bot-Left
    8 = @{X=3413; Y=$row3Start; W=853; H=$($row3End - $row3Start)}      # Bot-Center
    9 = @{X=4266; Y=$row3Start; W=854; H=$($row3End - $row3Start)}      # Bot-Right
}

for ($i = 1; $i -le 9; $i++) {
    $slot = $newGrid[$i]
    Write-Host "Slot ${i}: X=$($slot.X), Y=$($slot.Y), W=$($slot.W), H=$($slot.H)"
}

Write-Host ""
Write-Host "Verification:"
Write-Host "Row 3 bottom: $row3End (should be <= 1440)"
Write-Host "Taskbar safe zone: $($monitorHeight - $taskbarHeight) to $monitorHeight"
