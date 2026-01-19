# Analyze the grid gaps based on coordinate table provided

Write-Host "=== ANALYZING GRID GAPS ===" -ForegroundColor Cyan
Write-Host ""

# Current grid definition in scripts
$currentGrid = @{
    1 = @{X=2560; Y=0; W=853; H=420}      # Top-Left
    2 = @{X=3413; Y=0; W=853; H=420}      # Top-Center
    3 = @{X=4266; Y=0; W=854; H=420}      # Top-Right
    4 = @{X=2560; Y=440; W=853; H=420}    # Mid-Left
    5 = @{X=3413; Y=440; W=853; H=420}    # Mid-Center
    6 = @{X=4266; Y=440; W=854; H=420}    # Mid-Right
    7 = @{X=2560; Y=900; W=853; H=420}    # Bot-Left
    8 = @{X=3413; Y=900; W=853; H=420}    # Bot-Center
    9 = @{X=4266; Y=900; W=854; H=420}    # Bot-Right
}

Write-Host "Current Grid Analysis:"
Write-Host ""

# Check X gaps
Write-Host "Slot 1 Right Edge: 2560 + 853 = 3413"
Write-Host "Slot 2 Left Edge:  3413"
Write-Host "Gap between 1 and 2: 0 pixels" -ForegroundColor Green
Write-Host ""

Write-Host "Slot 2 Right Edge: 3413 + 853 = 4266"
Write-Host "Slot 3 Left Edge:  4266"
Write-Host "Gap between 2 and 3: 0 pixels" -ForegroundColor Green
Write-Host ""

# Check Y gaps
Write-Host "Slot 1 Bottom Edge: 0 + 420 = 420"
Write-Host "Slot 4 Top Edge:    440"
$gap1 = 440 - 420
Write-Host "Gap between rows 1 and 2: $gap1 pixels" -ForegroundColor Yellow
Write-Host ""

Write-Host "Slot 4 Bottom Edge: 440 + 420 = 860"
Write-Host "Slot 7 Top Edge:    900"
$gap2 = 900 - 860
Write-Host "Gap between rows 2 and 3: $gap2 pixels" -ForegroundColor Yellow
Write-Host ""

Write-Host "=== ISSUE IDENTIFIED ===" -ForegroundColor Red
Write-Host "There are gaps between rows:"
Write-Host "  - 20 pixels between rows 1 and 2"
Write-Host "  - 40 pixels between rows 2 and 3"
Write-Host ""
Write-Host "These gaps need to be closed to eliminate visible spaces."
Write-Host ""

Write-Host "=== PROPOSED CORRECTION ===" -ForegroundColor Cyan
Write-Host ""

# Calculate new heights to eliminate gaps
$totalHeight = 1440 - 100  # Leave 100px for taskbar margin
$heightPerRow = $totalHeight / 3
Write-Host "Total available height: $totalHeight"
Write-Host "Height per row: $heightPerRow"
Write-Host ""

# Recalculate without gaps
Write-Host "New proposed grid (no gaps):"
$newGrid = @{
    1 = @{X=2560; Y=0; W=853; H=473}      # Top-Left
    2 = @{X=3413; Y=0; W=853; H=473}      # Top-Center
    3 = @{X=4266; Y=0; W=854; H=473}      # Top-Right
    4 = @{X=2560; Y=473; W=853; H=473}    # Mid-Left
    5 = @{X=3413; Y=473; W=853; H=473}    # Mid-Center
    6 = @{X=4266; Y=473; W=854; H=473}    # Mid-Right
    7 = @{X=2560; Y=946; W=853; H=494}    # Bot-Left (extra pixels for rounding)
    8 = @{X=3413; Y=946; W=853; H=494}    # Bot-Center
    9 = @{X=4266; Y=946; W=854; H=494}    # Bot-Right
}

for ($i = 1; $i -le 9; $i++) {
    $slot = $newGrid[$i]
    Write-Host "Slot ${i}: X=$($slot.X), Y=$($slot.Y), W=$($slot.W), H=$($slot.H)"
}

Write-Host ""
Write-Host "Verification (no gaps):"
Write-Host "Slot 1 (0-473) + Slot 4 (473-946) + Slot 7 (946-1440) = 1440px total"
